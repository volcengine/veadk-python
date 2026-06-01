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

"""Claude Code SDK runtime for VeADK.

Drives an agent invocation through the Claude Code SDK (``claude-agent-sdk``)
instead of ADK's built-in LLM flow, while the surrounding ``Runner`` keeps owning
session, memory and tracing.

Key guarantees:

- The model is always the one configured on the agent (or via ``ANTHROPIC_MODEL``);
  if none resolves, the runtime fails fast.
- The SDK is fully isolated from the host's ``~/.claude`` settings via
  ``setting_sources=[]``; all credentials/endpoint are injected through
  ``ClaudeAgentOptions.env``. A wrong key therefore surfaces as an error rather
  than silently falling back to the host's working credentials.
- OpenAI-compatible endpoints are reached through an in-process Anthropic shim
  (see :mod:`veadk.runtime.cc.proxy`).
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, AsyncGenerator

from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query
from claude_agent_sdk.types import SystemPromptPreset

from veadk.runtime.base_runtime import BaseRuntime, build_system_append
from veadk.runtime.cc.proxy import detect_endpoint_kind
from veadk.runtime.cc.translate import build_prompt, sdk_message_to_events
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event

    from veadk.agent import Agent

logger = get_logger(__name__)


def _model_env(model: str) -> dict[str, str]:
    """Pin every Claude Code model tier to ``model``.

    Claude Code resolves several model "tiers" (opus/sonnet/haiku, the small fast
    model, etc.) from separate environment variables. Setting only
    ``ANTHROPIC_MODEL`` lets the host's inherited ``ANTHROPIC_DEFAULT_*_MODEL``
    leak into sub-tasks, so we override the whole family to guarantee the agent
    only ever calls the configured model.
    """
    return {
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_DEFAULT_OPUS_MODEL": model,
        "ANTHROPIC_DEFAULT_SONNET_MODEL": model,
        "ANTHROPIC_DEFAULT_HAIKU_MODEL": model,
        "ANTHROPIC_SMALL_FAST_MODEL": model,
    }


class ClaudeCodeRuntime(BaseRuntime):
    """Run an agent invocation via the Claude Code SDK."""

    name = "cc"

    async def run_async(
        self, agent: "Agent", ctx: "InvocationContext"
    ) -> AsyncGenerator["Event", None]:
        model = self._resolve_model(agent)
        api_base = agent.model_api_base or os.getenv("ANTHROPIC_BASE_URL")
        api_key = (
            agent.model_api_key
            or os.getenv("ANTHROPIC_AUTH_TOKEN")
            or os.getenv("ANTHROPIC_API_KEY")
        )

        kind = detect_endpoint_kind(api_base, agent.model_provider)
        env = await self._build_env(kind, model, api_base, api_key)

        # Append the agent identity/instruction to Claude Code's own system
        # prompt (preset), rather than replacing it.
        append_text = build_system_append(agent)
        system_prompt: SystemPromptPreset = {"type": "preset", "preset": "claude_code"}
        if append_text:
            system_prompt["append"] = append_text
        options = ClaudeAgentOptions(
            model=model,
            env=env,
            setting_sources=[],  # never inherit the host's ~/.claude settings
            system_prompt=system_prompt,
            allowed_tools=[],
            permission_mode="default",
        )

        prompt = build_prompt(ctx)
        logger.info(f"cc runtime: model={model}, endpoint_kind={kind}")

        # ResultMessage is the terminal message; capture any error and raise only
        # after the SDK stream completes (raising mid-iteration leaves the SDK's
        # async generator in a running state and breaks its cleanup).
        error: ResultMessage | None = None
        async for message in query(prompt=prompt, options=options):
            for event in sdk_message_to_events(message, agent.name, ctx.invocation_id):
                yield event
            if isinstance(message, ResultMessage) and message.is_error:
                error = message

        if error is not None:
            raise RuntimeError(
                f"Claude Code runtime error (subtype={error.subtype}): {error.result}"
            )

    def _resolve_model(self, agent: "Agent") -> str:
        name = agent.model_name
        if isinstance(name, list):
            name = name[0] if name else ""
        name = name or os.getenv("ANTHROPIC_MODEL", "")
        if not name:
            raise ValueError(
                "cc runtime requires a model: set Agent(model_name=...) "
                "or the ANTHROPIC_MODEL environment variable."
            )
        return name

    async def _build_env(
        self,
        kind: str,
        model: str,
        api_base: str | None,
        api_key: str | None,
    ) -> dict[str, str]:
        # Routing Claude Code to a non-Anthropic model (via the OpenAI<->Anthropic
        # shim) is disabled pending license/terms review. The cc runtime currently
        # supports only Anthropic-compatible endpoints. The shim itself still lives
        # in `proxy.py` so this can be re-enabled once cleared.
        if kind != "anthropic":
            raise ValueError(
                "The 'cc' runtime currently supports only Anthropic-compatible "
                "endpoints; routing Claude Code to a non-Anthropic model is "
                "disabled. Set an Anthropic endpoint (model_provider='anthropic') "
                "or use runtime='adk'."
            )

        # Native Anthropic endpoint.
        if not api_key:
            raise ValueError(
                "cc runtime with an Anthropic endpoint requires an API key."
            )
        # Set both header variants to the configured key so whichever the
        # endpoint reads, it is the configured one and never an inherited token.
        return {
            "ANTHROPIC_BASE_URL": api_base or "https://api.anthropic.com",
            "ANTHROPIC_API_KEY": api_key,
            "ANTHROPIC_AUTH_TOKEN": api_key,
            **_model_env(model),
        }
