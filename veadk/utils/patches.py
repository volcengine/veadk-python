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
import sys
from typing import Callable

from veadk.tracing.telemetry.telemetry import (
    trace_call_llm,
    trace_send_data,
    trace_tool_call,
)
from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)


def patch_asyncio():
    """Patch asyncio to ignore 'Event loop is closed' error.

    After invoking MCPToolset, we met the `RuntimeError: Event loop is closed` error. Related issue see:
    - https://github.com/google/adk-python/issues/1429
    - https://github.com/google/adk-python/pull/1420
    """
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


def patch_google_adk_telemetry() -> None:
    trace_functions = {
        "trace_tool_call": trace_tool_call,
        "trace_call_llm": trace_call_llm,
        "trace_send_data": trace_send_data,
    }

    for mod_name, mod in tuple(sys.modules.items()):
        if mod_name.startswith("google.adk"):
            for var_name, var in _iter_loaded_attrs(mod):
                if var_name in trace_functions and isinstance(var, Callable):
                    setattr(mod, var_name, trace_functions[var_name])
                    logger.debug(
                        f"Patch {mod_name} {var_name} with {trace_functions[var_name]}"
                    )


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
    import functools

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
