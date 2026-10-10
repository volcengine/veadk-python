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

"""Run the VeADK agent with remotely dispatched sandbox tools."""

import argparse
import asyncio
import inspect
import json
import logging
import os
import re
import signal
import socket
import tempfile
import uuid
from pathlib import Path
from typing import Any, NoReturn
from urllib.parse import urlsplit

from anthropic.lib.tools import ToolError
from anthropic.lib.tools.agent_toolset import (
    AgentToolContext,
    beta_agent_toolset_20260401,
)
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from veadk import Agent, Runner
from veadk.extensions import FeishuChannelExtension
from veadk.integrations.mpa.session_client import SelfHostSandboxClient
from veadk.integrations.mpa.session_resources import mcp_toolsets, skill_instructions
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runtime import (
    LocalRuntimeProvider,
    RuntimeProvider,
    ToolCall,
)
from veadk.runtime.managed_agents.events import iter_session_events, send_session_events
from veadk.runtime.managed_agents.loop import ManagedAgentEventState, ManagedAgentsLoop
from veadk.runtime.managed_agents.sandbox import (
    dispatch_runtime,
    enable_sandbox_turn_lifecycle,
    get_default_agent,
    sandbox_sessions,
)

logger = logging.getLogger(__name__)

APP_NAME = "self_host_sandbox_demo"
_POLL_TRACE_LOGGER = "anthropic.managed_agent_poll"
_MODEL_TRACE_LOGGER = "anthropic.managed_agent_model"
_POLL_PATH = "/v1/model-work/poll"


def configure_managed_agent_poll_trace(*, worker_id: str, base_url: str) -> None:
    """Enable the dedicated safe poll channel and announce its readiness."""
    if os.getenv("MANAGED_AGENT_POLL_TRACE", "").strip().lower() != "true":
        return
    logging.getLogger("anthropic._base_client").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logger = logging.getLogger(_POLL_TRACE_LOGGER)
    logger.setLevel(logging.INFO)
    logger.propagate = False
    if not any(
        getattr(existing, "_managed_agent_poll_trace", False)
        for existing in logger.handlers
    ):
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        handler.setFormatter(logging.Formatter("%(message)s"))
        handler._managed_agent_poll_trace = True
        logger.addHandler(handler)
    parsed = urlsplit(base_url)
    host = (
        f"[{parsed.hostname}]"
        if parsed.hostname and ":" in parsed.hostname
        else parsed.hostname
    )
    port = f":{parsed.port}" if parsed.port is not None else ""
    origin = f"{parsed.scheme}://{host}{port}" if parsed.scheme and host else ""
    safe_worker_id = (
        worker_id
        if len(worker_id) <= 128 and re.fullmatch(r"[A-Za-z0-9_.:-]+", worker_id)
        else ""
    )
    logger.info(
        json.dumps(
            {
                "account_scope": True,
                "event": "poll_trace_ready",
                "origin": origin,
                "path": _POLL_PATH,
                "worker_id": safe_worker_id,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )


def configure_managed_agent_model_trace() -> None:
    """Configure the logger at its owner so every Ark hook shares it."""
    from veadk.models.ark_llm import configure_managed_agent_model_trace as configure

    configure()


def _managed_tool_placeholder() -> NoReturn:
    raise RuntimeError(
        "Managed Agent tools must be intercepted by managed_work_tool_runtime"
    )


def managed_bash(
    command: str | None = None,
    restart: bool | None = None,
    timeout_ms: int | None = None,
) -> dict[str, Any]:
    """Run a command in the Managed Agent worker."""
    _managed_tool_placeholder()


def managed_read(file_path: str, view_range: list[int] | None = None) -> dict[str, Any]:
    """Read a file from the Managed Agent worker."""
    _managed_tool_placeholder()


def managed_write(file_path: str, content: str) -> dict[str, Any]:
    """Write a file in the Managed Agent worker."""
    _managed_tool_placeholder()


def managed_edit(
    file_path: str,
    old_string: str,
    new_string: str,
    replace_all: bool = False,
) -> dict[str, Any]:
    """Replace text in a Managed Agent worker file."""
    _managed_tool_placeholder()


def managed_glob(pattern: str, path: str | None = None) -> dict[str, Any]:
    """List paths matching a glob in the Managed Agent worker."""
    _managed_tool_placeholder()


def managed_grep(pattern: str, path: str | None = None) -> dict[str, Any]:
    """Search files in the Managed Agent worker."""
    _managed_tool_placeholder()


for _tool, _name in (
    (managed_bash, "bash"),
    (managed_read, "read"),
    (managed_write, "write"),
    (managed_edit, "edit"),
    (managed_glob, "glob"),
    (managed_grep, "grep"),
):
    _tool.__name__ = _name

_MANAGED_TOOLS = {
    "bash": managed_bash,
    "read": managed_read,
    "write": managed_write,
    "edit": managed_edit,
    "glob": managed_glob,
    "grep": managed_grep,
}
_LOCAL_BUILTIN_TOOLS = {"web_fetch", "web_search"}
_CANONICAL_MANAGED_TOOLS = (
    "bash",
    "read",
    "write",
    "edit",
    "glob",
    "grep",
    "web_fetch",
    "web_search",
)
# Backward-compatible export used by the example's existing integrations/tests.


def managed_short_term_memory() -> ShortTermMemory:
    """Keep per-Work ADK bookkeeping local to the Worker process."""
    return ShortTermMemory(backend="local")


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _enabled(config: Any, default: bool) -> bool:
    value = _field(config, "enabled")
    return default if value is None else bool(value)


def _contains_http_status(error: BaseException, statuses: set[int]) -> bool:
    """Inspect nested SDK/TaskGroup failures without exposing their bodies."""
    status = getattr(error, "status_code", None) or getattr(error, "status", None)
    try:
        if status is not None and int(status) in statuses:
            return True
    except (TypeError, ValueError):
        pass
    return any(
        _contains_http_status(child, statuses)
        for child in getattr(error, "exceptions", ())
        if isinstance(child, BaseException)
    )


async def _run_with_identity_retry(
    operation: Any,
    credential_provider: Any | None,
    *,
    should_stop: Any = lambda: False,
) -> Any:
    """Retry only startup auth propagation failures with a refreshed key."""
    auth_attempt = 0
    while True:
        if should_stop():
            return 0
        try:
            return await operation()
        except BaseException as error:
            if (
                credential_provider is None
                or not _contains_http_status(error, {401, 403})
                or auth_attempt >= 5
            ):
                raise
            auth_attempt += 1
            credential_provider.invalidate()
            delay = min(8.0, float(2 ** (auth_attempt - 1)))
            print(
                "MANAGED_AGENT_IDENTITY_RETRY "
                f"attempt={auth_attempt} delay_seconds={delay:g}",
                flush=True,
            )
            await asyncio.sleep(delay)
            if should_stop():
                return 0


async def _run_dispatcher_with_identity_retry(
    dispatcher_factory: Any,
    credential_provider: Any | None,
    *,
    max_items: int | None,
    max_concurrency: int,
    should_stop: Any = lambda: False,
) -> int:
    async def run_dispatcher() -> int:
        if should_stop():
            return 0
        dispatcher = dispatcher_factory()
        if should_stop():
            dispatcher.drain()
            return 0
        return await dispatcher.run(
            max_items=max_items, max_concurrency=max_concurrency
        )

    return await _run_with_identity_retry(
        run_dispatcher, credential_provider, should_stop=should_stop
    )


class ManagedCustomTool(BaseTool):
    """Expose an app-owned custom tool and wait for its Session result event."""

    def __init__(self, definition: Any, sdk: Any, session_id: str) -> None:
        self.input_schema = dict(_field(definition, "input_schema", {}) or {})
        self.sdk = sdk
        self.session_id = session_id
        super().__init__(
            name=str(_field(definition, "name", "")),
            description=str(_field(definition, "description", "") or ""),
        )

    def _get_declaration(self) -> types.FunctionDeclaration:
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters_json_schema=self.input_schema,
        )

    async def run_async(self, *, args: dict[str, Any], tool_context: Any) -> Any:
        tool_use_id = str(
            getattr(tool_context, "function_call_id", "") or f"toolu_{uuid.uuid4().hex}"
        )
        await send_session_events(
            self.sdk,
            self.session_id,
            events=[
                {
                    "type": "agent.custom_tool_use",
                    "id": tool_use_id,
                    "name": self.name,
                    "input": args,
                },
                {
                    "type": "session.status_idle",
                    "stop_reason": {
                        "type": "requires_action",
                        "action_type": "custom_tool_result",
                        "event_ids": [tool_use_id],
                    },
                },
            ],
        )
        result = await _wait_for_session_event(
            self.sdk,
            self.session_id,
            event_type="user.custom_tool_result",
            link_field="custom_tool_use_id",
            link_id=tool_use_id,
        )
        await send_session_events(
            self.sdk, self.session_id, events=[{"type": "session.status_running"}]
        )
        content = _event_content_text(_field(result, "content"))
        return {
            "error" if bool(_field(result, "is_error", False)) else "result": content
        }


async def _wait_for_session_event(
    sdk: Any,
    session_id: str,
    *,
    event_type: str | tuple[str, ...],
    link_field: str,
    link_id: str,
) -> Any:
    timeout = _managed_action_timeout_seconds()
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while loop.time() < deadline:
        async for event in iter_session_events(
            sdk, session_id, limit=1000, order="desc"
        ):
            if (
                _field(event, "type")
                in ((event_type,) if isinstance(event_type, str) else event_type)
                and _field(event, link_field) == link_id
            ):
                return event
        await asyncio.sleep(0.5)
    raise TimeoutError(f"timed out waiting for {event_type} for {link_id}")


def _event_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    values = []
    for block in content or []:
        text = _field(block, "text")
        if text:
            values.append(str(text))
    return "\n".join(values) or "(no output)"


def _agent_tool_config_name(config: Any) -> str:
    """Official SDK configs use the type discriminator; accept legacy names."""
    return str(_field(config, "type") or _field(config, "name") or "")


def _tool_permission_map(snapshot: Any) -> dict[str, str]:
    policies: dict[str, str] = {}
    for toolset in _field(snapshot, "tools", []) or []:
        toolset_type = str(_field(toolset, "type", ""))
        if toolset_type not in {"agent_toolset_20260401", "mcp_toolset"}:
            continue
        default = _field(toolset, "default_config", {}) or {}
        default_policy = str(
            _field(
                _field(default, "permission_policy", {}) or {}, "type", "always_allow"
            )
        )
        prefix = (
            f"mcp__{_field(toolset, 'mcp_server_name', '')}__"
            if toolset_type == "mcp_toolset"
            else ""
        )
        for config in _field(toolset, "configs", []) or []:
            name = (
                _agent_tool_config_name(config)
                if toolset_type == "agent_toolset_20260401"
                else str(_field(config, "name", ""))
            )
            policy = str(
                _field(
                    _field(config, "permission_policy", {}) or {},
                    "type",
                    default_policy,
                )
            )
            policies[prefix + name] = policy
        policies[prefix + "*"] = default_policy
    return policies


def managed_agent_config(
    snapshot: Any,
    *,
    sdk: Any | None = None,
    session_id: str | None = None,
    skill_dirs: list[Path] | None = None,
    credential_keys: Any = None,
) -> dict[str, Any]:
    """Translate a frozen Managed Agent snapshot to a VeADK Agent config."""
    model = _field(snapshot, "model", "")
    model_name = _field(model, "id", model)
    if not isinstance(model_name, str) or not model_name:
        model_name = os.getenv("MODEL_AGENT_NAME", "")
    if not model_name:
        raise ValueError("Managed Session agent snapshot has no model id")

    enabled_names: list[str] = []
    unsupported: list[str] = []
    for toolset in _field(snapshot, "tools", []) or []:
        toolset_type = str(_field(toolset, "type", "") or "")
        if toolset_type == "mcp_toolset":
            continue
        if toolset_type == "custom":
            if sdk is None or not session_id:
                unsupported.append(
                    f"custom tool {_field(toolset, 'name', '')} (missing Session client)"
                )
            continue
        if toolset_type != "agent_toolset_20260401":
            unsupported.append(toolset_type or "unknown tool definition")
            continue
        default_config = _field(toolset, "default_config", {}) or {}
        default_enabled = _enabled(default_config, True)
        default_policy = _field(
            _field(default_config, "permission_policy", {}) or {}, "type"
        )
        configs = _field(toolset, "configs", []) or []
        configured: dict[str, Any] = {
            _agent_tool_config_name(config): config for config in configs
        }
        names = set(configured) | (
            set(_CANONICAL_MANAGED_TOOLS) if default_enabled else set()
        )
        for config in configs:
            name = _agent_tool_config_name(config)
            if not _enabled(config, default_enabled):
                names.discard(name)
        for name in sorted(names):
            config = configured.get(name, {})
            enabled = _enabled(config, default_enabled)
            if not enabled:
                continue
            policy = (
                _field(_field(config, "permission_policy", {}) or {}, "type")
                or default_policy
            )
            if policy not in {None, "always_allow", "always_ask"}:
                unsupported.append(f"{name} (permission_policy={policy})")
            enabled_names.append(name)

    unsupported.extend(
        name
        for name in enabled_names
        if name not in _MANAGED_TOOLS and name not in _LOCAL_BUILTIN_TOOLS
    )
    if unsupported:
        raise ValueError(
            f"Unsupported Managed Agent tools for VeADK: {', '.join(sorted(set(unsupported)))}"
        )
    tools = list(
        dict.fromkeys(
            _MANAGED_TOOLS[name] for name in enabled_names if name in _MANAGED_TOOLS
        )
    )
    if "web_fetch" in enabled_names:
        from veadk.tools.builtin_tools.web_fetch import web_fetch

        tools.append(web_fetch)
    if "web_search" in enabled_names:
        from veadk.tools.builtin_tools.web_search import web_search

        tools.append(web_search)
    resolved_instruction = str(_field(snapshot, "system", "") or "")
    if skill_dirs:
        resolved_instruction += skill_instructions(skill_dirs)
    tools.extend(mcp_toolsets(snapshot, credential_keys=credential_keys))
    if sdk is not None and session_id:
        tools.extend(
            ManagedCustomTool(tool, sdk, session_id)
            for tool in _field(snapshot, "tools", []) or []
            if _field(tool, "type") == "custom"
        )
    raw_name = str(_field(snapshot, "name", "managed_agent"))
    name = re.sub(r"[^A-Za-z0-9_]", "_", raw_name).strip("_") or "managed_agent"
    if name[0].isdigit():
        name = f"agent_{name}"
    model_base_url = _field(model, "base_url", None)
    return {
        **({"model_api_base": model_base_url} if model_base_url else {}),
        "name": name,
        "description": str(_field(snapshot, "description", "") or ""),
        "instruction": resolved_instruction,
        "model_name": model_name,
        "enable_responses": True,
        "enable_responses_cache": True,
        "model_extra_config": {
            "store": True,
            "retry_expired_response": False,
            # Conversation storage is independent of the paid cache service.
            "extra_body": {"caching": {"type": "disabled"}},
        },
        "tools": tools,
        "before_tool_callback": dispatch_runtime.before_tool_callback
        if tools
        else None,
    }


async def resolve_session_model_key(session: Any, runtime_type: str) -> str:
    """Require Session Identity unless a local worker explicitly opts in."""
    from veadk.runtime.managed_agents.identity import (
        RuntimeIdentityError,
        session_model_credentials,
    )

    source = os.getenv("MANAGED_AGENT_MODEL_CREDENTIAL_SOURCE", "session")
    if source not in {"session", "environment"}:
        raise ValueError("Unknown Managed Agent model credential source")
    if (
        source == "environment"
        and runtime_type != "agentkit_runtime"
        and _field(session, "ark_api_key_provider") is None
    ):
        key = os.getenv("MODEL_AGENT_API_KEY", "")
        if not key:
            raise RuntimeIdentityError("missing_model_key", False)
        return key
    return await session_model_credentials.get(session)


def managed_runner(
    short_term_memory: ShortTermMemory,
    snapshot: Any | None = None,
    *,
    before_tool_callback: Any | None = None,
    sdk: Any | None = None,
    session_id: str | None = None,
    skill_dirs: list[Path] | None = None,
    credential_keys: Any = None,
    model_api_key: str | None = None,
) -> Runner:
    if snapshot is None:
        managed_agent = get_default_agent()
    else:
        config = managed_agent_config(
            snapshot,
            sdk=sdk,
            session_id=session_id,
            skill_dirs=skill_dirs,
            credential_keys=credential_keys,
        )
        if before_tool_callback is not None and config["tools"]:
            config["before_tool_callback"] = before_tool_callback
        if model_api_key is not None:
            config["model_api_key"] = model_api_key
        managed_agent = Agent(**config)
    return Runner(
        agent=managed_agent,
        app_name=APP_NAME,
        short_term_memory=short_term_memory,
    )


def _managed_tool_environment() -> dict[str, str]:
    """Return a subprocess environment without control-plane credentials."""
    allowed = {"LANG", "LC_ALL", "PATH", "TERM", "TZ"}
    return {key: value for key, value in os.environ.items() if key in allowed}


# Real execution budget for one tool invocation when the model does not ask for a
# specific timeout. 300s is the deployed contract; the outer wait
# (MANAGED_AGENT_ACTION_TIMEOUT_SECONDS) must exceed it so a long tool is never
# cut off before it can finish and be cleaned up.
MANAGED_TOOL_TIMEOUT_ENV = "MANAGED_AGENT_TOOL_TIMEOUT_SECONDS"
MANAGED_TOOL_TIMEOUT_DEFAULT_SECONDS = 300.0


def _managed_tool_timeout_seconds() -> float:
    """Tool execution budget: env override, otherwise the 300s default."""
    raw = os.getenv(MANAGED_TOOL_TIMEOUT_ENV, "").strip()
    try:
        value = float(raw)
    except ValueError:
        value = 0.0
    return value if value > 0 else MANAGED_TOOL_TIMEOUT_DEFAULT_SECONDS


# Cancellation and process-group cleanup need to fit between the tool budget and
# the outer wait that would give up on the tool result.
MANAGED_TOOL_CLEANUP_MARGIN_SECONDS = 60.0


def _managed_action_timeout_seconds() -> float:
    """Outer wait for a tool result, never below budget + cleanup margin."""
    raw = os.getenv("MANAGED_AGENT_ACTION_TIMEOUT_SECONDS", "3600").strip()
    try:
        configured = float(raw)
    except ValueError:
        configured = 3600.0
    return max(
        configured,
        _managed_tool_timeout_seconds() + MANAGED_TOOL_CLEANUP_MARGIN_SECONDS,
    )


def _with_default_tool_timeout(event: dict[str, Any]) -> dict[str, Any]:
    """Annotate a published tool_use event with the deployment execution budget.

    The remote executor (sandbox ``ant`` worker) has no timeout option of its own;
    it uses the ``timeout_ms`` carried by the event. Without this the remote path
    silently falls back to the executor default and a long tool is cut short.
    """
    if event.get("name") != "bash":
        return event
    payload = event.get("input")
    if not isinstance(payload, dict):
        return event
    if payload.get("timeout") is not None or payload.get("timeout_ms") is not None:
        return event
    annotated = dict(event)
    annotated["input"] = {
        **payload,
        "timeout_ms": int(_managed_tool_timeout_seconds() * 1000),
    }
    return annotated


async def aclose_runnable_tool(tool: object) -> None:
    """Preserve SDK cleanup protocols without logging secret-bearing errors."""
    closer = getattr(tool, "aclose", None) or getattr(tool, "close", None)
    if closer is not None:
        try:
            result = closer()
            if inspect.isawaitable(result):
                await result
        except Exception as error:
            logger.warning("Native tool cleanup failed: %s", type(error).__name__)

    # Official beta_tool/beta_async_tool retain their entered context here.
    # Context-manager cleanup is additive to close/aclose, not an alternative.
    context = getattr(tool, "_context_manager", None)
    if context is not None:
        try:
            aexit = getattr(context, "__aexit__", None)
            if aexit is not None:
                await aexit(None, None, None)
            else:
                context.__exit__(None, None, None)
        except Exception as error:
            logger.warning("Native tool context exit failed: %s", type(error).__name__)


class NativeAgentTools:
    """Own one SDK toolset and its persistent shell for a runner's lifetime."""

    def __init__(self, workdir: Path) -> None:
        self.context = AgentToolContext(
            workdir=workdir, env=_managed_tool_environment()
        )
        self.tools = {
            tool.name: tool for tool in beta_agent_toolset_20260401(self.context)
        }

    async def close(self) -> None:
        failures: list[BaseException] = []
        for tool in self.tools.values():
            try:
                await aclose_runnable_tool(tool)
            except (Exception, asyncio.CancelledError) as error:
                failures.append(error)
        try:
            await self.context.close()
        except (Exception, asyncio.CancelledError) as error:
            failures.append(error)
        if failures:
            raise failures[0]

    async def run(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self.tools.get(name)
        if tool is None:
            raise ValueError(f"No native tool registered for {name!r}")
        payload = _with_default_tool_timeout({"name": name, "input": arguments})[
            "input"
        ]
        try:
            content = await tool.call(payload)
            is_error = False
        except ToolError as error:
            content, is_error = error.content, True
        text = _event_content_text(content)
        return {
            "status": "failed" if is_error else "completed",
            "exit_code": 1 if is_error else 0,
            "stdout": "" if is_error else text,
            "stderr": text if is_error else "",
            "content": content,
            "is_error": is_error,
        }


async def _run_managed_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    workdir: Path,
    native_tools: NativeAgentTools | None = None,
) -> dict[str, Any]:
    tools = native_tools or NativeAgentTools(workdir)
    try:
        return await tools.run(tool_name, arguments)
    finally:
        if native_tools is None:
            await tools.close()


def mcp_result_content(result: Any) -> tuple[list[dict[str, Any]], bool]:
    """Convert MCP CallToolResult to Managed Agents content blocks."""
    if hasattr(result, "model_dump"):
        result = result.model_dump(mode="json", exclude_none=True)
    is_error = isinstance(result, dict) and bool(
        result.get("isError") or result.get("error")
    )
    blocks = result.get("content") if isinstance(result, dict) else None
    content: list[dict[str, Any]] = []
    if isinstance(blocks, list):
        for block in blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                content.append({"type": "text", "text": block.get("text", "")})
            elif isinstance(block, dict) and block.get("type") == "image":
                content.append(
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "data": block["data"],
                            "media_type": block["mimeType"],
                        },
                    }
                )
            else:
                # MCP resource/audio/link blocks have no identical Session
                # variant; retain their payload as text instead of dropping it.
                content.append(
                    {"type": "text", "text": json.dumps(block, ensure_ascii=False)}
                )
    if not content:
        payload = (
            result.get("structuredContent", result)
            if isinstance(result, dict)
            else result
        )
        content = [
            {
                "type": "text",
                "text": payload
                if isinstance(payload, str)
                else json.dumps(payload, ensure_ascii=False, default=str),
            }
        ]
    return content, is_error


def managed_work_tool_runtime(
    sdk: Any, session_id: str, *, workdir: Path, snapshot: Any | None = None
) -> RuntimeProvider:
    """Execute tools locally or await the configured remote sandbox worker."""

    policies = _tool_permission_map(snapshot) if snapshot is not None else {}
    local_runtime = LocalRuntimeProvider()
    native_tools = NativeAgentTools(workdir)

    async def confirm(tool_call: ToolCall, event: dict[str, Any]) -> bool:
        wildcard = (
            tool_call.name.rsplit("__", 1)[0] + "__*" if "__" in tool_call.name else "*"
        )
        policy = policies.get(tool_call.name, policies.get(wildcard, "always_allow"))
        if policy != "always_ask":
            return True
        if event["type"] in {"agent.tool_use", "agent.mcp_tool_use"}:
            event["evaluated_permission"] = "ask"
        await send_session_events(
            sdk,
            session_id,
            events=[
                event,
                {
                    "type": "session.status_idle",
                    "stop_reason": {
                        "type": "requires_action",
                        "action_type": "tool_confirmation",
                        "event_ids": [event["id"]],
                    },
                },
            ],
        )
        verdict = await _wait_for_session_event(
            sdk,
            session_id,
            event_type="user.tool_confirmation",
            link_field="tool_use_id",
            link_id=str(event["id"]),
        )
        await send_session_events(
            sdk, session_id, events=[{"type": "session.status_running"}]
        )
        return _field(verdict, "result") == "allow"

    async def publish_result(
        kind: str, tool_use_id: str, result: Any, is_error: bool
    ) -> None:
        content = (
            result
            if isinstance(result, (str, list))
            else json.dumps(result, ensure_ascii=False, default=str)
        )
        await send_session_events(
            sdk,
            session_id,
            events=[
                {
                    "type": f"agent.{kind}_result",
                    f"{kind}_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        )

    async def execute(tool_call: ToolCall) -> Any:
        tool_use_id = tool_call.id or f"toolu_{uuid.uuid4().hex}"
        if isinstance(tool_call.tool, ManagedCustomTool):
            return await local_runtime.execute(tool_call)
        is_mcp = hasattr(tool_call.tool, "_mcp_tool") or hasattr(
            tool_call.tool, "_mcp_session_manager"
        )
        if is_mcp:
            server_name = str(
                getattr(tool_call.tool, "managed_agents_mcp_server_name", "mcp")
            )
            prefix = f"mcp__{server_name}__"
            original_name = (
                tool_call.name.removeprefix(prefix)
                if tool_call.name.startswith(prefix)
                else tool_call.name
            )
            event = {
                "type": "agent.mcp_tool_use",
                "id": tool_use_id,
                "mcp_server_name": server_name,
                "name": original_name or tool_call.name,
                "input": tool_call.arguments,
                "evaluated_permission": "allow",
            }
            if not await confirm(tool_call, event):
                await publish_result(
                    "mcp_tool",
                    tool_use_id,
                    [{"type": "text", "text": "MCP tool call denied by user"}],
                    True,
                )
                return {"error": "tool call denied by user"}
            if (
                policies.get(
                    tool_call.name, policies.get("mcp__" + server_name + "__*")
                )
                != "always_ask"
            ):
                await send_session_events(sdk, session_id, events=[event])
            try:
                result = await local_runtime.execute(tool_call)
            except Exception:
                # A tool failure is a model-visible result, not a failed turn.
                result = {"error": "MCP tool execution failed"}
            content, is_error = mcp_result_content(result)
            await publish_result("mcp_tool", tool_use_id, content, is_error)
            return result

        if (
            tool_call.name not in _MANAGED_TOOLS
            and tool_call.name not in _LOCAL_BUILTIN_TOOLS
        ):
            return await local_runtime.execute(tool_call)

        event = {
            "type": "agent.tool_use",
            "id": tool_use_id,
            "name": tool_call.name,
            "input": tool_call.arguments,
            "evaluated_permission": "allow",
        }
        if os.getenv("MANAGED_AGENT_TOOL_EXECUTION", "local") == "remote":
            event = _with_default_tool_timeout(event)
        if not await confirm(tool_call, event):
            return {"error": "tool call denied by user"}
        if event["evaluated_permission"] != "ask":
            await send_session_events(sdk, session_id, events=[event])
        if os.getenv("MANAGED_AGENT_TOOL_EXECUTION", "local") == "remote":
            result_event = await _wait_for_session_event(
                sdk,
                session_id,
                event_type=("user.tool_result", "agent.tool_result"),
                link_field="tool_use_id",
                link_id=tool_use_id,
            )
            content = _field(result_event, "content")
            is_error = bool(_field(result_event, "is_error", False))
            if _field(result_event, "type") == "user.tool_result":
                await publish_result("tool", tool_use_id, content, is_error)
            return {"error" if is_error else "result": content}
        try:
            if tool_call.name in _MANAGED_TOOLS:
                result = await _run_managed_tool(
                    tool_call.name,
                    tool_call.arguments,
                    workdir=workdir,
                    native_tools=native_tools,
                )
            else:
                result = await local_runtime.execute(tool_call)
        except Exception as error:  # noqa: BLE001 -- tool failures become result events
            result = {
                "status": "failed",
                "exit_code": -1,
                "stdout": "",
                "stderr": str(error)
                if isinstance(error, ToolError)
                else "Tool execution failed",
            }
        if isinstance(result, dict) and "content" in result and "is_error" in result:
            content, is_error = result["content"], result["is_error"]
        elif (
            isinstance(result, dict)
            and {"exit_code", "stdout", "stderr"} <= result.keys()
        ):
            content = "\n".join(
                part
                for part in (
                    f"exit={result['exit_code']}",
                    str(result["stdout"]),
                    str(result["stderr"]),
                )
                if part
            )
            is_error = result.get("status") == "failed"
        else:
            content = (
                result
                if isinstance(result, str)
                else json.dumps(result, ensure_ascii=False, default=str)
            )
            is_error = False
        await send_session_events(
            sdk,
            session_id,
            events=[
                {
                    "type": "agent.tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }
            ],
        )
        return result

    class ManagedWorkRuntime(RuntimeProvider):
        def __init__(self) -> None:
            super().__init__(name="managed_agents_work_runtime")

        async def execute(self, tool_call: ToolCall) -> Any:
            return await execute(tool_call)

        async def close(self) -> None:
            await native_tools.close()

    return ManagedWorkRuntime()


async def close_managed_runner(runner: Runner) -> None:
    failures: list[BaseException] = []
    for tool in getattr(runner.agent, "tools", []) or []:
        close = getattr(tool, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except (Exception, asyncio.CancelledError) as error:
            failures.append(error)
    if failures:
        raise failures[0]


async def serve_managed_agent_worker(
    *,
    worker_id: str | None = None,
    max_work_items: int | None = None,
    readiness_probe: bool = False,
) -> int:
    """Poll Task Server work and execute claimed sessions with VeADK."""
    session_client = SelfHostSandboxClient()
    short_term_memory = managed_short_term_memory()
    resolved_worker_id = worker_id or f"{socket.gethostname()}-{uuid.uuid4().hex[:12]}"
    if session_client.runtime_type == "agentkit_runtime":
        session_client._default_headers["Anthropic-Worker-ID"] = resolved_worker_id
    default_workdir = Path(tempfile.gettempdir()) / "veadk-managed-agents" / "workspace"
    workdir = Path(os.getenv("MANAGED_AGENT_WORKDIR", default_workdir)).resolve()
    workdir.mkdir(parents=True, exist_ok=True)
    ready_file = Path(
        os.getenv("MANAGED_AGENT_READY_FILE", "/tmp/managed-agent-worker-ready")
    )
    ready_file.unlink(missing_ok=True)
    event_states: dict[str, ManagedAgentEventState] = {}
    max_event_states = int(os.getenv("MANAGED_AGENT_EVENT_STATE_CACHE_SIZE", "4096"))
    if max_event_states < 1:
        raise ValueError("MANAGED_AGENT_EVENT_STATE_CACHE_SIZE must be positive")

    def event_state_for(session_id: str) -> ManagedAgentEventState:
        state = event_states.get(session_id)
        if state is not None:
            # Dict insertion order provides a small LRU without another cache
            # dependency. Moving the key never changes the shared state object.
            event_states.pop(session_id)
            event_states[session_id] = state
            return state

        if len(event_states) >= max_event_states:
            for cached_session_id, cached_state in tuple(event_states.items()):
                if not cached_state.lock.locked():
                    event_states.pop(cached_session_id)
                    break
        state = ManagedAgentEventState()
        event_states[session_id] = state
        return state

    try:
        async with session_client.create_async_client() as sdk:
            configure_managed_agent_poll_trace(
                worker_id=resolved_worker_id, base_url=str(sdk.base_url)
            )
            configure_managed_agent_model_trace()
            if readiness_probe:

                async def poll_readiness() -> Any:
                    return await sdk.beta.environments.work.poll(
                        session_client.environment_id,
                        block_ms=1,
                        anthropic_worker_id=resolved_worker_id,
                        extra_headers=session_client._default_headers,
                    )

                pending = await _run_with_identity_retry(
                    poll_readiness, session_client._identity_credentials
                )
                if pending is not None:
                    raise RuntimeError(
                        "readiness probe requires an empty isolated work queue"
                    )

            async def handle(work_item: Any, scoped_sdk: Any) -> None:
                if getattr(getattr(work_item, "data", None), "type", None) != "session":
                    return
                session_id = str(work_item.data.id)
                print(
                    f"MANAGED_AGENT_WORK_CLAIM worker_id={resolved_worker_id} "
                    f"work_id={work_item.id} session_id={session_id}",
                    flush=True,
                )
                phase = "work_metadata"
                try:
                    await scoped_sdk.beta.environments.work.update(
                        work_item.id,
                        environment_id=work_item.environment_id,
                        metadata={"managed_agent_worker_id": resolved_worker_id},
                    )
                    phase = "session_retrieve"
                    session = await scoped_sdk.beta.sessions.retrieve(session_id)
                    from veadk.integrations.mpa.session_resources import (
                        cleanup_session_skills,
                        materialize_session_skills,
                        session_workdir,
                    )

                    phase = "session_resources"
                    item_workdir = session_workdir(workdir, session_id)
                    downloaded_skills: list[Path] = []
                    try:
                        downloaded_skills = await materialize_session_skills(
                            session, item_workdir, client=scoped_sdk
                        )
                        phase = "model_identity"
                        model_api_key = await resolve_session_model_key(
                            session, session_client.runtime_type
                        )
                        phase = "runner_create"
                        tool_runtime = managed_work_tool_runtime(
                            scoped_sdk,
                            session_id,
                            workdir=item_workdir,
                            snapshot=session.agent,
                        )
                        runner = None
                        try:
                            runner = managed_runner(
                                short_term_memory,
                                session.agent,
                                before_tool_callback=tool_runtime.before_tool_callback,
                                sdk=scoped_sdk,
                                session_id=session_id,
                                skill_dirs=downloaded_skills,
                                model_api_key=model_api_key,
                                credential_keys=_field(session, "credential_keys", []),
                            )
                            phase = "events_run"
                            await ManagedAgentsLoop(
                                runner=runner,
                                session_id=session_id,
                                event_state=event_state_for(session_id),
                            ).run_pending(scoped_sdk, max_turns=1)
                        finally:
                            try:
                                if runner is not None:
                                    await close_managed_runner(runner)
                            finally:
                                await tool_runtime.close()
                    finally:
                        await cleanup_session_skills(downloaded_skills)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    if session_client.runtime_type == "agentkit_runtime":
                        from veadk.runtime.managed_agents.identity import (
                            RuntimeIdentityError,
                        )

                        safe_error = (
                            error
                            if isinstance(error, RuntimeIdentityError)
                            else RuntimeIdentityError(
                                "work_execution_failed",
                                bool(getattr(error, "retryable", False)),
                            )
                        )
                        print(
                            f"MANAGED_AGENT_WORK_FAILURE phase={phase} "
                            f"error_type={type(error).__name__} "
                            f"http_status={getattr(error, 'status_code', None)}",
                            flush=True,
                        )
                        await send_session_events(
                            scoped_sdk,
                            session_id,
                            events=[
                                {"type": "session.error", "error": str(safe_error)}
                            ],
                        )
                        raise safe_error from None
                    await send_session_events(
                        scoped_sdk,
                        session_id,
                        events=[
                            {
                                "type": "session.error",
                                "error": "Managed Work execution failed",
                            }
                        ],
                    )
                    raise

            from veadk.runtime.managed_agents.dispatcher import (
                EnvironmentWorkDispatcher,
            )

            concurrency = int(os.getenv("MANAGED_AGENT_WORK_CONCURRENCY", "1"))
            if concurrency < 1:
                raise ValueError("MANAGED_AGENT_WORK_CONCURRENCY must be positive")
            loop = asyncio.get_running_loop()

            dispatcher: Any | None = None
            readiness_tasks: list[asyncio.Task] = []

            async def announce_ready(instance: Any) -> None:
                await instance.ready.wait()
                if shutdown_requested:
                    return
                ready_file.parent.mkdir(parents=True, exist_ok=True)
                ready_file.write_text(resolved_worker_id + "\n")
                print(
                    f"MANAGED_AGENT_WORKER_READY worker_id={resolved_worker_id} "
                    f"environment_id={session_client.environment_id} "
                    f"runtime_type={session_client.runtime_type or 'default'}",
                    flush=True,
                )

            shutdown_requested = False

            def drain_worker() -> None:
                nonlocal shutdown_requested
                shutdown_requested = True
                ready_file.unlink(missing_ok=True)
                if dispatcher is not None:
                    dispatcher.drain()
                print(
                    f"MANAGED_AGENT_WORKER_DRAIN worker_id={resolved_worker_id}",
                    flush=True,
                )

            for signum in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(signum, drain_worker)
            try:

                def dispatcher_factory() -> Any:
                    nonlocal dispatcher
                    dispatcher = EnvironmentWorkDispatcher(
                        sdk,
                        handler=handle,
                        account_work=os.getenv(
                            "MANAGED_AGENT_WORK_SCOPE", "environment"
                        )
                        == "account",
                        environment_id=session_client.environment_id,
                        environment_key=session_client.bearer_token,
                        worker_id=resolved_worker_id,
                        extra_headers=session_client._default_headers,
                    )
                    readiness_tasks.append(
                        asyncio.create_task(announce_ready(dispatcher))
                    )
                    return dispatcher

                return await _run_dispatcher_with_identity_retry(
                    dispatcher_factory,
                    getattr(session_client, "_identity_credentials", None),
                    max_items=max_work_items,
                    max_concurrency=concurrency,
                    should_stop=lambda: shutdown_requested,
                )
            finally:
                for task in readiness_tasks:
                    task.cancel()
                await asyncio.gather(*readiness_tasks, return_exceptions=True)
                for signum in (signal.SIGINT, signal.SIGTERM):
                    loop.remove_signal_handler(signum)
    finally:
        ready_file.unlink(missing_ok=True)


async def serve_claimed_managed_agent_work() -> int:
    """Serve a claimed session until the external dispatcher reclaims the sandbox."""
    session_client = SelfHostSandboxClient()
    work_id = os.getenv("MA_WORK_ID") or os.getenv("ANTHROPIC_WORK_ID")
    session_id = os.getenv("MA_SESSION_ID") or os.getenv("ANTHROPIC_SESSION_ID")
    if not work_id or not session_id:
        raise ValueError(
            "MA_WORK_ID/ANTHROPIC_WORK_ID and MA_SESSION_ID/ANTHROPIC_SESSION_ID "
            "are required for claimed Work mode"
        )

    root = Path(os.getenv("MANAGED_AGENT_WORKDIR", "/workspace")).resolve()
    root.mkdir(parents=True, exist_ok=True)
    short_term_memory = managed_short_term_memory()
    async with session_client.create_async_client() as sdk:
        session = await sdk.beta.sessions.retrieve(session_id)
        from veadk.integrations.mpa.session_resources import (
            cleanup_session_skills,
            materialize_session_skills,
            session_workdir,
        )

        item_workdir = session_workdir(root, session_id)
        downloaded_skills: list[Path] = []
        try:
            downloaded_skills = await materialize_session_skills(
                session, item_workdir, client=sdk
            )
            model_api_key = await resolve_session_model_key(
                session, session_client.runtime_type
            )
            tool_runtime = managed_work_tool_runtime(
                sdk, session_id, workdir=item_workdir, snapshot=session.agent
            )
            runner = None
            try:
                runner = managed_runner(
                    short_term_memory,
                    session.agent,
                    before_tool_callback=tool_runtime.before_tool_callback,
                    sdk=sdk,
                    session_id=session_id,
                    skill_dirs=downloaded_skills,
                    model_api_key=model_api_key,
                    credential_keys=_field(session, "credential_keys", []),
                )
                turns = await ManagedAgentsLoop(
                    runner=runner, session_id=session_id
                ).run_claimed(
                    sdk,
                    environment_id=session_client.environment_id,
                    work_id=work_id,
                    last_heartbeat=os.getenv("MA_LATEST_HEARTBEAT_AT")
                    or "NO_HEARTBEAT",
                )
            finally:
                try:
                    if runner is not None:
                        await close_managed_runner(runner)
                finally:
                    await tool_runtime.close()
        finally:
            await cleanup_session_skills(downloaded_skills)

        print(
            f"MANAGED_AGENT_CLAIMED_WORK_COMPLETE work_id={work_id} "
            f"session_id={session_id} turns={turns}",
            flush=True,
        )
        return turns


async def serve_feishu_channel(stop_event: asyncio.Event | None = None) -> None:
    """Serve Feishu conversations until the process receives a stop signal."""
    runner = enable_sandbox_turn_lifecycle(
        Runner(agent=get_default_agent(), app_name=APP_NAME)
    )
    channel = FeishuChannelExtension(
        runner=runner,
        streaming=True,
        show_thinking=True,
        show_tool_calls=True,
        show_tool_results=True,
        separate_tool_call_cards=True,
        separate_thinking_card=True,
        create_topic=True,
    )
    loop = asyncio.get_running_loop()
    shutdown_event = stop_event or asyncio.Event()

    if stop_event is None:
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(signal_number, shutdown_event.set)
            except NotImplementedError:  # pragma: no cover - Windows fallback
                signal.signal(signal_number, lambda *_: shutdown_event.set())

    channel.start(loop)
    print("Feishu Channel is running. Press Ctrl+C to stop.")
    try:
        await shutdown_event.wait()
    finally:
        await channel.shutdown()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prompt",
        default=(
            "Use the bash tool to run: printf 'veadk-self-host-ok'. "
            "Then reply with the exact output."
        ),
    )
    parser.add_argument("--session-id", default=None)
    parser.add_argument(
        "--managed-agent-loop",
        action="store_true",
        help=(
            "Consume one pending user.message from the existing Managed Session with "
            "local bookkeeping, then exit."
        ),
    )
    parser.add_argument(
        "--managed-agent-worker",
        action="store_true",
        help="Continuously poll and execute Managed Agent session work.",
    )
    parser.add_argument(
        "--managed-agent-work-item",
        action="store_true",
        help="Execute one WorkItem already claimed by an external dispatcher.",
    )
    parser.add_argument("--worker-id", default=None)
    parser.add_argument("--max-work-items", type=int, default=None)
    parser.add_argument(
        "--managed-agent-readiness-probe",
        action="store_true",
        help="Require one successful empty work poll before logging worker readiness.",
    )
    parser.add_argument(
        "--managed-agent-model-trace-probe",
        action="store_true",
        help="Run one controlled Ark Responses request through the real worker import path.",
    )
    parser.add_argument("--model-trace-probe-url", default=None)
    parser.add_argument(
        "--feishu",
        action="store_true",
        help="Keep running and serve conversations through the Feishu bot channel.",
    )
    args = parser.parse_args()

    if args.managed_agent_model_trace_probe:
        if not args.model_trace_probe_url:
            parser.error(
                "--managed-agent-model-trace-probe requires --model-trace-probe-url"
            )
        from veadk.models.ark_llm import ArkLlm

        configure_managed_agent_model_trace()
        model = ArkLlm(
            model="openai/managed-agent-trace-probe",
            api_base=args.model_trace_probe_url,
            api_key="managed-agent-trace-probe",  # gitleaks:allow controlled test credential
            enable_responses_cache=False,
        )
        responses = [
            response
            async for response in model.generate_content_via_responses(
                {
                    "model": "openai/managed-agent-trace-probe",
                    "api_base": args.model_trace_probe_url,
                    "api_key": "managed-agent-trace-probe",  # gitleaks:allow controlled test credential
                    "input": [],
                    "tools": [{"name": "bash", "type": "function"}],
                    "tool_choice": {"type": "function", "name": "bash"},
                }
            )
        ]
        calls = [
            call
            for response in responses
            for call in response.content.parts
            if getattr(call, "function_call", None) is not None
        ]
        if len(calls) != 1 or calls[0].function_call.name != "bash":
            raise RuntimeError("controlled model trace probe did not return bash")
        print("MANAGED_AGENT_MODEL_TRACE_PROBE_OK tool=bash", flush=True)
        return

    if args.managed_agent_loop:
        session_client = SelfHostSandboxClient(session_id=args.session_id)
        if not session_client.session_id:
            parser.error(
                "--managed-agent-loop requires --session-id, ANTHROPIC_SESSION_ID, or SANDBOX_SESSION_ID"
            )
        sandbox_sessions.bind(session_client.session_id, session_client)
        runner = managed_runner(managed_short_term_memory())
        turns = await ManagedAgentsLoop(
            runner=runner,
            session_client=session_client,
        ).run(max_turns=1)
        print(f"Managed Agents loop completed {turns} turn(s).")
        return

    if args.managed_agent_worker:
        count = await serve_managed_agent_worker(
            worker_id=args.worker_id,
            max_work_items=args.max_work_items,
            readiness_probe=args.managed_agent_readiness_probe,
        )
        print(f"Managed Agents worker completed {count} work item(s).")
        return

    if args.managed_agent_work_item:
        turns = await serve_claimed_managed_agent_work()
        print(f"Managed Agents claimed Work completed {turns} turn(s).")
        return

    if args.feishu:
        await serve_feishu_channel()
        return

    session_id = args.session_id or f"veadk-{uuid.uuid4()}"
    runner = enable_sandbox_turn_lifecycle(
        Runner(agent=get_default_agent(), app_name=APP_NAME)
    )
    output = await runner.run(messages=args.prompt, session_id=session_id)
    print(output)


if __name__ == "__main__":
    asyncio.run(main())
