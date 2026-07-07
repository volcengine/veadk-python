# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OpenAI Codex runtime for VeADK.

Drives an agent invocation through the Codex SDK (``codex_app_server``) instead
of ADK's built-in LLM flow, while the surrounding ``Runner`` keeps owning
session, memory and tracing.

Key guarantees (mirroring the ``cc`` runtime):

- The model is always the one configured on the agent (or via ``ANTHROPIC_MODEL`` /
  settings); if none resolves, the runtime fails fast.
- Codex is isolated from the host's ``~/.codex`` via a dedicated ``CODEX_HOME`` with
  a generated ``config.toml``; the backend credential is injected through the
  provider's ``env_key`` env var. A wrong key fails loudly.
- Codex only speaks the Responses API, so requests are routed through an
  in-process Responses→chat shim (see :mod:`veadk.runtime.codex.proxy`).

Note: this requires the ``openai-codex`` SDK (``pip install openai-codex``),
which bundles the Codex CLI binary via its ``openai-codex-cli-bin`` dependency.
"""

from __future__ import annotations

import os
import tempfile
from typing import TYPE_CHECKING, AsyncGenerator

from openai_codex import AsyncCodex  # type: ignore[import-not-found]
from openai_codex.generated.v2_all import (  # type: ignore[import-not-found]
    ItemCompletedNotification,
    TurnCompletedNotification,
)

from veadk.runtime.base_runtime import BaseRuntime, build_system_append
from veadk.runtime.codex.proxy import get_shim
from veadk.runtime.codex.skills import sync_skills_to_codex_home
from veadk.runtime.codex.tools_bridge import build_executable_tools, close_toolsets
from veadk.runtime.codex.translate import build_prompt, item_to_events
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event

    from veadk.agent import Agent

logger = get_logger(__name__)

_PROVIDER_ID = "veadk"
_KEY_ENV = "VEADK_CODEX_API_KEY"
_LOCAL_SHIM_TOKEN = "veadk-local"

# Cache one isolated CODEX_HOME per (shim_url, model).
_CODEX_HOMES: dict[tuple[str, str], str] = {}


class CodexRuntime(BaseRuntime):
    """Run an agent invocation via the Codex SDK."""

    name = "codex"

    async def run_async(
        self, agent: "Agent", ctx: "InvocationContext"
    ) -> AsyncGenerator["Event", None]:
        model = self._resolve_model(agent)
        api_base = agent.model_api_base or os.getenv("OPENAI_BASE_URL")
        api_key = agent.model_api_key or os.getenv("OPENAI_API_KEY")
        if not api_base or not api_key:
            raise ValueError(
                "codex runtime requires model_api_base and model_api_key "
                "(the chat endpoint Codex is bridged onto)."
            )

        shim = await get_shim(api_base, api_key)
        shim_url = shim.url or ""
        codex_home = _prepare_codex_home(shim_url, model)
        # Expose the agent's skills to Codex by materializing them under
        # `$CODEX_HOME/skills/`, where Codex's native skill system discovers
        # them. Best-effort: a skill failure must not abort the turn.
        try:
            sync_skills_to_codex_home(agent, codex_home)
        except Exception as e:  # noqa: BLE001
            logger.warning(f"codex: skill sync skipped: {e}")

        # Bridge the agent's ADK tools (function/MCP) to the shim: it advertises
        # them to the backend as plain `function` tools and executes them itself,
        # so they never reach Codex (whose `namespace` MCP form Ark rejects). See
        # veadk.runtime.codex.tools_bridge / proxy.
        tool_specs, tool_executors, opened_toolsets = await build_executable_tools(
            agent, ctx
        )
        shim.set_agent_tools(tool_specs, tool_executors)

        # Codex has no clean SDK channel to append to its base system prompt, so
        # the agent identity/instruction is folded into a leading block of the
        # input (a labelled preamble), not the transcript itself.
        prompt = build_prompt(ctx)
        append_text = build_system_append(agent)
        if append_text:
            prompt = (
                f"# System instructions\n\n{append_text}\n\n# Conversation\n\n{prompt}"
            )
        logger.info(f"codex runtime: model={model}, shim={shim_url}")

        # Isolate from the host's ~/.codex and pin the backend credential. The
        # Codex app-server subprocess reads these from the environment at spawn.
        previous = {k: os.environ.get(k) for k in ("CODEX_HOME", _KEY_ENV)}
        os.environ["CODEX_HOME"] = codex_home
        os.environ[_KEY_ENV] = _LOCAL_SHIM_TOKEN
        try:
            # Stream the turn: emit ADK events as each Codex item completes
            # (reasoning, tool calls, messages) instead of collecting the whole
            # turn first. This keeps the BaseRuntime async-generator contract
            # truly incremental, so thinking/tool steps show up live (a blocking
            # thread.run() would leave the client silent for the whole turn).
            async with AsyncCodex() as codex:
                thread = await codex.thread_start(model=model)
                turn = await thread.turn(prompt)
                stream = turn.stream()
                try:
                    async for note in stream:
                        payload = note.payload
                        if (
                            isinstance(payload, ItemCompletedNotification)
                            and payload.turn_id == turn.id
                        ):
                            for event in item_to_events(
                                payload.item, agent.name, ctx.invocation_id
                            ):
                                yield event
                        elif (
                            isinstance(payload, TurnCompletedNotification)
                            and payload.turn.id == turn.id
                            and payload.turn.error
                        ):
                            raise RuntimeError(payload.turn.error.message)
                finally:
                    # stream() is an async generator at runtime; close it to
                    # unregister the turn's notification listener.
                    aclose = getattr(stream, "aclose", None)
                    if aclose is not None:
                        await aclose()
        finally:
            # Drop this turn's tools from the (shared) shim and release any MCP
            # sessions opened for them.
            shim.set_agent_tools([], {})
            await close_toolsets(opened_toolsets)
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def _resolve_model(self, agent: "Agent") -> str:
        name = agent.model_name
        if isinstance(name, list):
            name = name[0] if name else ""
        name = name or os.getenv("OPENAI_MODEL", "")
        if not name:
            raise ValueError(
                "codex runtime requires a model: set Agent(model_name=...) "
                "or the OPENAI_MODEL environment variable."
            )
        return name


def _prepare_codex_home(shim_url: str, model: str) -> str:
    """Create (and cache) an isolated CODEX_HOME with a config.toml.

    The config points Codex at the local Responses shim using a dedicated
    ``veadk`` provider, so the run never touches the host's ``~/.codex``.
    """
    cache_key = (shim_url, model)
    cached = _CODEX_HOMES.get(cache_key)
    if cached is not None:
        return cached

    home = tempfile.mkdtemp(prefix="veadk-codex-")
    # Defaults tuned for a server-side agent on a single chat backend:
    # - review_model points the auto-review reviewer at the configured model;
    #   Codex's default reviewer ("codex-auto-review") is not a real model on
    #   the backend and would 404 through the shim.
    # - approval_policy=never + sandbox_mode=danger-full-access let the agent
    #   read, write, run commands and reach the network (e.g. fetch from
    #   arXiv) without an approval round-trip.
    # - disable_response_storage: the chat-backed Responses shim has no
    #   server-side response store.
    config = (
        f'model = "{model}"\n'
        f'model_provider = "{_PROVIDER_ID}"\n'
        f'review_model = "{model}"\n'
        f'approval_policy = "never"\n'
        f'sandbox_mode = "danger-full-access"\n'
        f"disable_response_storage = true\n"
        f'model_reasoning_effort = "medium"\n'
        f'personality = "pragmatic"\n\n'
        f"[model_providers.{_PROVIDER_ID}]\n"
        f'name = "{_PROVIDER_ID}"\n'
        f'base_url = "{shim_url}/v1"\n'
        f'env_key = "{_KEY_ENV}"\n'
        f'wire_api = "responses"\n\n'
        # Only consulted under sandbox_mode="workspace-write"; harmless under
        # full-access, but lets a narrower mode still reach the network.
        f"[sandbox_workspace_write]\n"
        f"network_access = true\n"
    )
    with open(os.path.join(home, "config.toml"), "w", encoding="utf-8") as f:
        f.write(config)

    _CODEX_HOMES[cache_key] = home
    return home
