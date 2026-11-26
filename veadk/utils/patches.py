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

import asyncio
import contextvars
import functools
import sys

from packaging.version import Version

from veadk.tracing.telemetry.adk_compat import (
    patch_google_adk_telemetry as patch_google_adk_telemetry,
)
from veadk.utils.adk_compat import get_adk_version
from veadk.utils.logger import get_logger, safe_info
from veadk.version import VERSION

logger = get_logger(__name__)

_PARALLEL_RUN_CODE_CALL_COUNT = contextvars.ContextVar(
    "veadk_parallel_run_code_call_count", default=1
)


def patch_adk_workflow_agent_mode() -> None:
    """Backport ADK 2.2's safe peer-transfer check to ADK 2.0 and 2.1.

    These releases read ``peer_agent.mode`` unconditionally while collecting
    an LLM agent's peer transfer targets. Workflow agents do not define that
    field, so mixed LLM/workflow trees fail before the delegated LLM runs. ADK
    2.2 fixed the lookup with ``hasattr``; exposing ``None`` on ``BaseAgent``
    preserves its target-selection semantics for built-in workflows and
    custom agents without replacing ADK internals.
    """
    adk_version = get_adk_version()
    if not Version("2.0.0") <= adk_version < Version("2.2.0"):
        return

    try:
        from google.adk.agents import BaseAgent

        if not hasattr(BaseAgent, "mode"):
            BaseAgent.mode = None
    except (ImportError, AttributeError) as error:
        logger.debug(f"Skip ADK workflow-agent mode patch: {error}")


def _adk_tool_name(tool) -> str:
    return (
        getattr(tool, "name", None)
        or getattr(tool, "__name__", None)
        or tool.__class__.__name__
    )


def _resolve_tool_thread_pool_max_workers(tool, tool_context) -> int | None:
    invocation_context = getattr(tool_context, "_invocation_context", None)
    run_config = getattr(invocation_context, "run_config", None)
    thread_pool_config = getattr(run_config, "tool_thread_pool_config", None)
    if thread_pool_config is not None:
        return thread_pool_config.max_workers

    agent = getattr(invocation_context, "agent", None)
    thread_pool_config = getattr(agent, "tool_thread_pool_config", None)
    if thread_pool_config is not None:
        return thread_pool_config.max_workers

    return None


def _set_parallel_run_code_context(tool, tool_context, max_workers: int | None) -> None:
    parallel_run_code_call_count = _PARALLEL_RUN_CODE_CALL_COUNT.get()
    if (
        max_workers is not None
        and _adk_tool_name(tool) == "run_code"
        and parallel_run_code_call_count > 1
    ):
        setattr(
            tool_context,
            "_veadk_parallel_tool_call_count",
            parallel_run_code_call_count,
        )


def patch_adk_dynamic_agent_transfer() -> None:
    """Resolve scheduler transfers against the agent instance that just ran."""
    if get_adk_version() < Version("2.8.0"):
        return

    from google.adk.agents import BaseAgent
    from google.adk.workflow import _dynamic_node_scheduler
    from google.adk.workflow.utils import _transfer_utils

    original = _transfer_utils.resolve_and_derive_transfer_context
    if getattr(original, "_veadk_dynamic_transfer_patch", False):
        return

    @functools.wraps(original)
    def resolve_transfer(
        target_name, current_agent, root_agent, curr_ctx, curr_parent_ctx
    ):
        # The runner executes a clone but otherwise resolves against its template.
        active_agent = getattr(curr_ctx, "node", None)
        if isinstance(active_agent, BaseAgent):
            current_agent = active_agent
            root_agent = active_agent.root_agent
        return original(
            target_name, current_agent, root_agent, curr_ctx, curr_parent_ctx
        )

    resolve_transfer._veadk_dynamic_transfer_patch = True
    _transfer_utils.resolve_and_derive_transfer_context = resolve_transfer
    # ADK 2.8/2.9 import locally; 2.10/2.11 retain a module-level alias.
    if hasattr(_dynamic_node_scheduler, "resolve_and_derive_transfer_context"):
        _dynamic_node_scheduler.resolve_and_derive_transfer_context = resolve_transfer


def patch_asyncio():
    """Patch asyncio to ignore 'Event loop is closed' error.

    After invoking MCPToolset, we met the `RuntimeError: Event loop is closed` error. Related issue see:
    - https://github.com/google/adk-python/issues/1429
    - https://github.com/google/adk-python/pull/1420
    """
    patch_adk_workflow_agent_mode()
    patch_adk_dynamic_agent_transfer()

    original_del = asyncio.base_subprocess.BaseSubprocessTransport.__del__

    def patched_del(self):
        try:
            original_del(self)
        except RuntimeError as e:
            if "Event loop is closed" not in str(e):
                raise

    asyncio.base_subprocess.BaseSubprocessTransport.__del__ = patched_del

    from anyio._backends._asyncio import CancelScope

    original_cancel_scope_exit = CancelScope.__exit__

    def patched_cancel_scope_exit(self, exc_type, exc_val, exc_tb):
        try:
            return original_cancel_scope_exit(self, exc_type, exc_val, exc_tb)
        except RuntimeError as e:
            if (
                "Attempted to exit cancel scope in a different task than it was entered in"
                in str(e)
            ):
                return False
            raise

    CancelScope.__exit__ = patched_cancel_scope_exit


def _iter_loaded_attrs(mod):
    """Iterate ``(name, value)`` pairs for already-loaded module attrs.

    Walking ``dir(mod) + getattr(mod, name)`` would trip ``__getattr__`` hooks
    that ADK 2.0 uses for lazy loading (e.g. ``google.adk.tools``), which in
    turn drags in optional-dep submodules like ``discovery_engine_search_tool``
    that veadk does not need. Reading ``mod.__dict__`` avoids that side effect
    — we only see attrs that have actually been imported into the module
    namespace, which is exactly the set we want to patch.
    """
    namespace = getattr(mod, "__dict__", None)
    if not isinstance(namespace, dict):
        return
    # Snapshot to avoid "dict changed size during iteration" if a setattr
    # below mutates the namespace mid-loop.
    for name, value in tuple(namespace.items()):
        yield name, value


def patch_tracer() -> None:
    from opentelemetry import trace

    for mod_name, mod in tuple(sys.modules.items()):
        if mod_name.startswith("google.adk"):
            for var_name, var in _iter_loaded_attrs(mod):
                if var_name == "tracer" and isinstance(var, trace.Tracer):
                    setattr(
                        mod,
                        var_name,
                        trace.get_tracer(
                            instrumenting_module_name="veadk",
                            instrumenting_library_version=VERSION,
                            schema_url="https://opentelemetry.io/schemas/1.37.0",
                        ),
                    )
                    logger.debug(f"Patch {mod_name} {var_name} with VeADK tracer.")


def patch_adk_sync_tool_thread_pool() -> None:
    """Enable ADK's tool thread pool for non-live ``run_async`` tool calls.

    ADK before 2.11 needs the helper for both RunConfig and Agent defaults. ADK 2.11
    handles RunConfig natively, but still needs VeADK's Agent default and
    parallel run_code session isolation.
    """
    try:
        from google.adk.flows.llm_flows import functions as adk_functions
        from google.adk.tools.function_tool import FunctionTool

        if getattr(adk_functions, "_veadk_sync_tool_thread_pool_patched", False):
            return

        adk_version = get_adk_version()
        native_thread_pool = adk_version >= Version("2.11.0")
        if adk_version >= Version("2.10.0"):
            # The compatibility module only re-exports this function; patch its
            # defining module so real Runner calls use it too.
            from google.adk.flows.llm_flows.tools import _caller as call_module

            call_name = "_call_tool_async"
        elif adk_version >= Version("2.9.0"):
            from google.adk.flows.llm_flows import _tool_caller as call_module

            call_name = "_call_tool_async"
        else:
            call_module = adk_functions
            call_name = "__call_tool_async"
        original_call_tool_async = getattr(call_module, call_name)
        original_handle_function_call_list_async = getattr(
            adk_functions, "handle_function_call_list_async"
        )
        call_tool_in_thread_pool = getattr(
            adk_functions, "_call_tool_in_thread_pool", None
        )
        if not callable(call_tool_in_thread_pool):
            logger.debug("Skip ADK sync tool thread-pool patch: helper is unavailable.")
            return

        @functools.wraps(original_call_tool_async)
        async def veadk_call_tool_async(tool, args, tool_context):
            tool_name = getattr(tool, "name", type(tool).__name__)
            safe_info(logger, f"[tool-dispatch] call_tool enter tool={tool_name}")
            try:
                max_workers = _resolve_tool_thread_pool_max_workers(tool, tool_context)
                _set_parallel_run_code_context(tool, tool_context, max_workers)

                invocation_context = getattr(tool_context, "_invocation_context", None)
                run_config = getattr(invocation_context, "run_config", None)
                uses_native_pool = native_thread_pool and (
                    getattr(run_config, "tool_thread_pool_config", None) is not None
                )
                sync_function_tool = isinstance(tool, FunctionTool) and (
                    adk_functions._is_sync_tool(tool)
                )
                safe_info(
                    logger,
                    f"[tool-dispatch] call_tool config tool={tool_name} "
                    f"max_workers={max_workers} "
                    f"uses_native_pool={uses_native_pool} "
                    f"sync_function_tool={sync_function_tool}",
                )
                # Async tools such as AgentTool must keep their caller's event loop.
                if (
                    max_workers is not None
                    and not uses_native_pool
                    and sync_function_tool
                ):
                    return await call_tool_in_thread_pool(
                        tool,
                        args=args,
                        tool_context=tool_context,
                        max_workers=max_workers,
                    )

                return await original_call_tool_async(
                    tool=tool,
                    args=args,
                    tool_context=tool_context,
                )
            finally:
                safe_info(logger, f"[tool-dispatch] call_tool exit tool={tool_name}")

        @functools.wraps(original_handle_function_call_list_async)
        async def veadk_handle_function_call_list_async(
            invocation_context,
            function_calls,
            tools_dict,
            filters=None,
            tool_confirmation_dict=None,
        ):
            run_code_call_count = len(
                [
                    function_call
                    for function_call in function_calls
                    if function_call.name == "run_code"
                    and (not filters or function_call.id in filters)
                ]
            )
            tool_names = ",".join(
                getattr(function_call, "name", "") for function_call in function_calls
            )
            invocation_id = getattr(invocation_context, "invocation_id", "")
            session = getattr(invocation_context, "session", None)
            session_id = getattr(session, "id", "")
            safe_info(
                logger,
                f"[tool-dispatch] function_calls enter count={len(function_calls)} "
                f"tools={tool_names} invocation_id={invocation_id} "
                f"session_id={session_id}",
            )
            token = _PARALLEL_RUN_CODE_CALL_COUNT.set(run_code_call_count)
            try:
                return await original_handle_function_call_list_async(
                    invocation_context,
                    function_calls,
                    tools_dict,
                    filters=filters,
                    tool_confirmation_dict=tool_confirmation_dict,
                )
            finally:
                _PARALLEL_RUN_CODE_CALL_COUNT.reset(token)
                safe_info(
                    logger,
                    f"[tool-dispatch] function_calls exit count={len(function_calls)} "
                    f"tools={tool_names} invocation_id={invocation_id} "
                    f"session_id={session_id}",
                )

        setattr(call_module, call_name, veadk_call_tool_async)
        adk_functions.handle_function_call_list_async = (
            veadk_handle_function_call_list_async
        )
        adk_functions._veadk_sync_tool_thread_pool_patched = True
        logger.debug("Patch ADK non-live sync tool calls to honor thread pool config.")
    except Exception as e:  # pragma: no cover - defensive across adk versions
        logger.warning(f"Skip ADK sync tool thread-pool patch: {e}")


def _sanitize_adk_graph_value(value, field_name: str | None = None):
    if field_name == "model":
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            model_id = value.get("model")
            if model_id:
                return str(model_id)
        model_id = getattr(value, "model", None)
        if model_id:
            return str(model_id)

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {
            str(k): _sanitize_adk_graph_value(v, str(k))
            for k, v in value.items()
            if k != "llm_client"
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_adk_graph_value(item) for item in value]
    return str(value)


def patch_adk_build_graph_serialization() -> None:
    """Keep ADK dev build_graph JSON free of runtime-only client objects."""
    try:
        from google.adk.cli.utils import graph_serialization

        if getattr(
            graph_serialization,
            "_veadk_build_graph_serialization_patched",
            False,
        ):
            return

        original_serialize_agent = graph_serialization.serialize_agent

        @functools.wraps(original_serialize_agent)
        def veadk_serialize_agent(*args, **kwargs):
            agent = args[0] if args else kwargs.get("agent")
            serialized = _sanitize_adk_graph_value(
                original_serialize_agent(*args, **kwargs)
            )
            if isinstance(serialized, dict) and "sub_agents" not in serialized:
                sub_agents = getattr(agent, "sub_agents", None)
                if sub_agents:
                    serialized["sub_agents"] = [
                        veadk_serialize_agent(sub_agent) for sub_agent in sub_agents
                    ]
            return serialized

        graph_serialization.serialize_agent = veadk_serialize_agent
        graph_serialization._veadk_build_graph_serialization_patched = True
        logger.debug("Patch ADK build_graph serialization for VeADK agents.")
    except Exception as e:  # pragma: no cover - defensive across adk versions
        logger.warning(f"Skip ADK build_graph serialization patch: {e}")


# Substrings / exception type names that signal a dead MCP session (server
# restart, scale-down, idle expiry) or a broken transport — all recoverable by
# dropping the cached session and reconnecting.
_MCP_DEAD_MSGS = (
    "invalid session id",
    "session may have expired or does not exist",
    "session terminated",
    "connection lost",
)
_MCP_DEAD_TYPES = frozenset(
    {
        "BrokenResourceError",
        "ClosedResourceError",
        "EndOfStream",
        "RemoteProtocolError",
        "ReadError",
        "ConnectError",
    }
)


def _is_dead_mcp_session(error: BaseException) -> bool:
    message = str(error).lower()
    return (
        isinstance(error, ConnectionError)
        or type(error).__name__ in _MCP_DEAD_TYPES
        or any(s in message for s in _MCP_DEAD_MSGS)
    )


def _retry_once_on_dead_mcp_session(func):
    """Wrap an MCP coroutine so that, on a dead-session/broken-transport error,
    it closes the manager's cached sessions (recreated lazily) and retries once.

    Applies to any object exposing ``_mcp_session_manager`` (McpTool, McpToolset).
    """

    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except Exception as error:
            task = asyncio.current_task()
            cancelling = getattr(task, "cancelling", None)  # py>=3.11
            if (cancelling and cancelling() > 0) or not _is_dead_mcp_session(error):
                raise
            logger.info(f"Reconnecting MCP after dead session: {func.__qualname__}")
            await self._mcp_session_manager.close()  # drop all stale sessions
            return await func(self, *args, **kwargs)

    return wrapper


def patch_mcp_session_retry() -> None:
    """Reconnect to an MCP server after it drops the session.

    ADK caches MCP sessions but does not recreate them when the server restarts
    or scales down, so calls fail with "Session terminated" / broken transport.
    This wraps ``McpTool._run_async_impl`` and ``McpToolset.get_tools`` to drop
    the dead session and retry once. No-op if the google-adk internals are
    unavailable (e.g. after an incompatible upgrade).
    """
    try:
        from google.adk.tools.mcp_tool.mcp_tool import McpTool
        from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

        # McpTool is the base for MCPTool (which does not override the method).
        for cls, method in ((McpTool, "_run_async_impl"), (McpToolset, "get_tools")):
            if getattr(cls, "_veadk_mcp_retry_patched", False):
                continue
            original = getattr(
                getattr(cls, method), "__wrapped__", getattr(cls, method)
            )
            setattr(cls, method, _retry_once_on_dead_mcp_session(original))
            cls._veadk_mcp_retry_patched = True
    except Exception as e:  # pragma: no cover - defensive across adk versions
        logger.warning(f"Skip MCP session-retry patch: {e}")
