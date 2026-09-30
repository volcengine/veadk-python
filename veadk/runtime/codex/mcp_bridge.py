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

"""Expose a turn's ADK tools to Codex through a local MCP server.

Instead of executing ADK tools invisibly inside the Responses shim, the agent's
tools are served to Codex as an MCP server that is injected per thread via
``thread_start(config={"mcp_servers": {"veadk": ...}})``. Codex then owns the
tool loop: it advertises the tools to the model (as the ``mcp__veadk``
namespace), calls them over streamable HTTP, and feeds the results back.

One process-wide server per event loop (:func:`get_bridge`) serves every turn.
Turns are isolated by a random bearer token minted by
:meth:`McpBridge.register_turn`: ``tools/list`` and ``tools/call`` only ever see
the calling token's tools, and an unknown token is refused with HTTP 401.

Codex-specific facts this module relies on (verified against codex 0.159.2):

- ``tools/call`` params carry ``_meta.callId`` -- the model's ``call_id`` --
  plus ``threadId``, ``sessionId``, ``itemId`` and ``x-codex-turn-metadata``
  (``turn_id``, ``model``, ``sandbox_mode``...). ``callId`` becomes the ADK
  function-call id so ADK events line up with Codex's items.
- When a result has ``structuredContent`` Codex sends *that* to the model
  instead of the text content, so interrupt results deliberately omit it.
- Under ``ApprovalMode.deny_all`` Codex refuses MCP calls unless the server's
  ``default_tools_approval_mode`` is ``"approve"``; parallel calls need
  ``supports_parallel_tool_calls``; the default per-call timeout is short, so
  ``tool_timeout_sec`` is always set (see :meth:`McpBridge.codex_server_config`).
"""

from __future__ import annotations

import asyncio
import atexit
import contextlib
import hashlib
import json
import secrets
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import uvicorn
from mcp import types
from mcp.server.lowlevel import Server
from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
from mcp.server.transport_security import TransportSecuritySettings

from veadk.utils.logger import get_logger

try:  # OpenTelemetry is optional; the bridge must import without it.
    from opentelemetry import context as otel_context_api
except Exception:  # pragma: no cover - depends on the install extras
    otel_context_api = None  # type: ignore[assignment]

logger = get_logger(__name__)

#: Same shape as ``tools_bridge.Executor``: ``(args, call_id) -> JSON string``.
Executor = Callable[[dict[str, Any], str], Awaitable[str]]

#: Executor payload statuses that mean the Codex turn has to stop.
INTERRUPT_STATUSES = frozenset(
    {"pending", "authentication_required", "confirmation_required", "transferred"}
)

_MCP_PATH = "/mcp"
_MAX_BODY_BYTES = 8 * 1024 * 1024
_START_TIMEOUT_SECONDS = 10.0
_STOP_TIMEOUT_SECONDS = 5.0
#: Codex's per-call MCP timeout when the ADK side has none. Codex's own default
#: is far too short for real tools, so something must always be configured.
_DEFAULT_TOOL_TIMEOUT_SECONDS = 3600.0
#: How long Codex may take to initialize/list tools before giving up.
_STARTUP_TIMEOUT_SECONDS = 30.0
_ERROR_TEXT_LIMIT = 2000

_SCOPE_TURN = "veadk.mcp_bridge.turn"
_SCOPE_SLOT = "veadk.mcp_bridge.slot"


@dataclass(frozen=True)
class BridgeInterrupt:
    """A tool call whose result means the Codex turn must stop."""

    call_id: str
    tool: str
    status: str  # "pending" | "authentication_required" | ... | "transferred"
    payload: dict[str, Any]


@dataclass
class BridgeTurnState:
    """What happened to one registered turn's tool calls."""

    interrupts: list[BridgeInterrupt] = field(default_factory=list)
    errors: list[BaseException] = field(default_factory=list)
    calls: int = 0


@dataclass
class _Turn:
    tools: list[types.Tool]
    executors: dict[str, Executor]
    invocation_id: str
    otel_context: Any
    state: BridgeTurnState = field(default_factory=BridgeTurnState)
    # JSON-RPC request id -> slot, so `notifications/cancelled` can find it.
    slots: dict[str, "_CallSlot"] = field(default_factory=dict)


@dataclass
class _CallSlot:
    """Links one HTTP ``tools/call`` request to the executor task it started."""

    task: asyncio.Task[str] | None = None
    cancelled: bool = False

    def cancel(self) -> None:
        if self.task is not None and self.task.done():
            return
        self.cancelled = True
        if self.task is not None:
            self.task.cancel()


def _token_key(token: str) -> str:
    # Turns are keyed by a digest so the lookup is not a timing oracle on the
    # raw token and raw tokens are not retained.
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


@contextlib.contextmanager
def _otel_scope(context: Any):
    """Attach ``context`` for the duration of the block, if OTel is available."""
    api = otel_context_api
    token = None
    if api is not None and context is not None:
        try:
            token = api.attach(context)
        except Exception:  # noqa: BLE001 - tracing must never break a tool
            token = None
    try:
        yield
    finally:
        if api is not None and token is not None:
            with contextlib.suppress(Exception):
                api.detach(token)


def _spec_to_tool(spec: dict[str, Any]) -> types.Tool:
    schema = spec.get("parameters")
    schema = dict(schema) if isinstance(schema, dict) else {}
    schema.setdefault("type", "object")
    if schema.get("type") == "object":
        schema.setdefault("properties", {})
    return types.Tool(
        name=str(spec["name"]),
        description=spec.get("description") or None,
        inputSchema=schema,
    )


def _text_result(text: str, *, is_error: bool = False) -> types.ServerResult:
    return types.ServerResult(
        types.CallToolResult(
            content=[types.TextContent(type="text", text=text)], isError=is_error
        )
    )


def _interrupt_text(tool: str, status: str, payload: dict[str, Any]) -> str:
    if status == "transferred":
        agent = payload.get("agent_name") or "another agent"
        return (
            f"Control has been transferred to agent `{agent}` by `{tool}`. "
            "Stop now: do not call any more tools and do not answer; "
            "that agent continues the conversation."
        )
    if status == "authentication_required":
        need = "user authentication"
    elif status == "confirmation_required":
        need = "user confirmation"
    else:
        need = "an external result"
    return (
        f"The tool call `{tool}` is waiting for {need}. Stop now: do not call "
        "any more tools and do not answer; the run resumes once it is provided."
    )


def _call_id_from_meta(meta: Any) -> str:
    if meta is None:
        return ""
    value = getattr(meta, "callId", None)
    if value is None:
        extra = getattr(meta, "model_extra", None) or {}
        value = extra.get("callId")
    return str(value) if value else ""


async def _send_simple(send: Any, status: int, body: bytes = b"") -> None:
    headers = [(b"content-type", b"application/json")] if body else []
    if status == 401:
        headers.append((b"www-authenticate", b"Bearer"))
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class McpBridge:
    """In-process streamable-HTTP MCP server serving registered turns' tools."""

    SERVER_NAME = "veadk"

    def __init__(self) -> None:
        self.url: str | None = None
        self._turns: dict[str, _Turn] = {}
        self._turns_lock = threading.Lock()
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[Any] | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._start_lock: asyncio.Lock | None = None
        self._start_lock_loop: asyncio.AbstractEventLoop | None = None
        self._manager: StreamableHTTPSessionManager | None = None
        self._manager_task: asyncio.Task[Any] | None = None
        self._manager_stop: asyncio.Event | None = None

    # -- turn registry -------------------------------------------------------

    def register_turn(
        self,
        specs: list[dict[str, Any]],
        executors: dict[str, Executor],
        *,
        invocation_id: str = "",
        otel_context: Any = None,
    ) -> str:
        """Register one turn's tools and return a fresh bearer token for it."""
        tools: list[types.Tool] = []
        for spec in specs:
            name = spec.get("name") if isinstance(spec, dict) else None
            if not name or name not in executors:
                logger.warning(
                    "codex_mcp_bridge_tool_skipped invocation_id=%s tool=%s "
                    "reason=no_executor",
                    invocation_id,
                    name,
                )
                continue
            tools.append(_spec_to_tool(spec))
        token = secrets.token_urlsafe(32)
        turn = _Turn(
            tools=tools,
            executors=dict(executors),
            invocation_id=invocation_id,
            otel_context=otel_context,
        )
        with self._turns_lock:
            self._turns[_token_key(token)] = turn
        logger.debug(
            "codex_mcp_bridge_turn_registered invocation_id=%s tools=%d",
            invocation_id,
            len(tools),
        )
        return token

    def unregister_turn(self, token: str) -> None:
        """Forget a turn; its token is rejected from now on."""
        with self._turns_lock:
            turn = self._turns.pop(_token_key(token), None)
        if turn is not None:
            for slot in list(turn.slots.values()):
                slot.cancel()

    def turn_state(self, token: str) -> BridgeTurnState | None:
        with self._turns_lock:
            turn = self._turns.get(_token_key(token))
        return turn.state if turn is not None else None

    def _lookup(self, token: str) -> _Turn | None:
        with self._turns_lock:
            return self._turns.get(_token_key(token))

    @property
    def busy(self) -> bool:
        with self._turns_lock:
            return bool(self._turns)

    # -- Codex config ----------------------------------------------------------

    def codex_server_config(
        self,
        *,
        bearer_token_env_var: str,
        tool_timeout_seconds: float | None,
    ) -> dict[str, Any]:
        """The value for ``config["mcp_servers"][McpBridge.SERVER_NAME]``."""
        if not self.url:
            raise RuntimeError("codex MCP bridge is not started")
        if tool_timeout_seconds and tool_timeout_seconds > 0:
            # Slightly above the ADK-side timeout, so the executor's own timeout
            # fires first and reports a proper tool error to the model.
            tool_timeout = float(tool_timeout_seconds) + max(
                5.0, 0.1 * float(tool_timeout_seconds)
            )
        else:
            tool_timeout = _DEFAULT_TOOL_TIMEOUT_SECONDS
        return {
            "url": self.url,
            "bearer_token_env_var": bearer_token_env_var,
            "default_tools_approval_mode": "approve",
            "supports_parallel_tool_calls": True,
            "tool_timeout_sec": tool_timeout,
            "startup_timeout_sec": _STARTUP_TIMEOUT_SECONDS,
            # Fail the thread loudly instead of running without the agent's tools.
            "required": True,
        }

    # -- MCP protocol ----------------------------------------------------------

    def _build_mcp_server(self) -> Server:
        server: Server = Server(self.SERVER_NAME)

        # Handlers are installed directly instead of through the decorators:
        # the decorators keep a single server-wide tool cache (and validate
        # calls against it), which is wrong when every turn has its own tools.
        async def list_tools(_req: Any) -> types.ServerResult:
            turn = server.request_context.request.scope.get(_SCOPE_TURN)
            tools = list(turn.tools) if turn is not None else []
            return types.ServerResult(types.ListToolsResult(tools=tools))

        async def call_tool(req: types.CallToolRequest) -> types.ServerResult:
            scope = server.request_context.request.scope
            return await self._call_tool(
                scope.get(_SCOPE_TURN), scope.get(_SCOPE_SLOT), req
            )

        server.request_handlers[types.ListToolsRequest] = list_tools
        server.request_handlers[types.CallToolRequest] = call_tool
        return server

    async def _call_tool(
        self,
        turn: _Turn | None,
        slot: _CallSlot | None,
        req: types.CallToolRequest,
    ) -> types.ServerResult:
        name = req.params.name
        if turn is None:
            return _text_result("Tool call rejected: unknown turn.", is_error=True)
        executor = turn.executors.get(name)
        if executor is None:
            return _text_result(f"Unknown tool: {name}", is_error=True)
        call_id = _call_id_from_meta(req.params.meta) or f"call_{uuid.uuid4().hex}"
        args = dict(req.params.arguments or {})
        slot = slot if slot is not None else _CallSlot()
        turn.state.calls += 1
        started = time.monotonic()

        async def _run() -> str:
            # Re-attach the invocation's OTel context: this runs under the
            # server task, whose contextvars were snapshotted at start-up.
            with _otel_scope(turn.otel_context):
                return await executor(args, call_id)

        def _log(status: str) -> None:
            logger.info(
                "codex_mcp_bridge_call invocation_id=%s call_id=%s tool=%s "
                "status=%s duration_ms=%d",
                turn.invocation_id,
                call_id,
                name,
                status,
                round((time.monotonic() - started) * 1000),
            )

        task = asyncio.ensure_future(_run())
        slot.task = task
        if slot.cancelled:
            task.cancel()
        try:
            raw = await task
        except asyncio.CancelledError:
            _log("cancelled")
            if slot.cancelled:
                # Codex dropped the request or sent `notifications/cancelled`;
                # nobody is waiting for this answer any more.
                return _text_result("Tool call was cancelled.", is_error=True)
            # This handler itself was cancelled (server shutdown): awaiting
            # the task already propagated the cancel into the executor.
            task.cancel()
            raise
        except Exception as e:  # noqa: BLE001 - never crash the server
            turn.state.errors.append(e)
            _log("error")
            # The message is what makes the failure diagnosable; it is
            # truncated and repr-escaped so one log line stays one line.
            # Tool arguments are never logged.
            logger.warning(
                "codex_mcp_bridge_executor_failed invocation_id=%s call_id=%s "
                "tool=%s error_type=%s error=%r",
                turn.invocation_id,
                call_id,
                name,
                type(e).__name__,
                str(e)[:_ERROR_TEXT_LIMIT],
            )
            message = f"Tool `{name}` failed: {type(e).__name__}: {e}"
            return _text_result(message[:_ERROR_TEXT_LIMIT], is_error=True)

        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        try:
            payload = json.loads(text)
        except (TypeError, ValueError):
            payload = None

        if isinstance(payload, dict):
            status = payload.get("status")
            if isinstance(status, str) and status in INTERRUPT_STATUSES:
                turn.state.interrupts.append(
                    BridgeInterrupt(
                        call_id=call_id, tool=name, status=status, payload=payload
                    )
                )
                _log(status)
                return _text_result(_interrupt_text(name, status, payload))
            _log(status[:40] if isinstance(status, str) else "completed")
            return types.ServerResult(
                types.CallToolResult(
                    content=[types.TextContent(type="text", text=text)],
                    structuredContent=payload,
                    isError=False,
                )
            )
        _log("completed")
        return _text_result(text)

    # -- HTTP ------------------------------------------------------------------

    async def _asgi(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return
        if scope.get("path", "").rstrip("/") != _MCP_PATH:
            await _send_simple(send, 404)
            return

        auth = ""
        for key, value in scope.get("headers") or ():
            if key.lower() == b"authorization":
                auth = value.decode("latin-1")
                break
        scheme, _, token = auth.partition(" ")
        turn = self._lookup(token.strip()) if scheme.lower() == "bearer" else None
        if turn is None:
            await _send_simple(send, 401, b'{"error":"unauthorized"}')
            return

        # Buffer the body so the JSON-RPC message can be inspected, then replay
        # it to the SDK transport.
        chunks: list[bytes] = []
        size = 0
        more = True
        while more:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            chunk = message.get("body", b"")
            size += len(chunk)
            if size > _MAX_BODY_BYTES:
                await _send_simple(send, 413)
                return
            chunks.append(chunk)
            more = message.get("more_body", False)
        body = b"".join(chunks)
        try:
            rpc = json.loads(body) if body else None
        except ValueError:
            rpc = None
        method = rpc.get("method") if isinstance(rpc, dict) else None

        if method == "notifications/cancelled":
            params = rpc.get("params") or {}
            request_id = params.get("requestId") if isinstance(params, dict) else None
            slot = turn.slots.get(str(request_id))
            if slot is not None:
                slot.cancel()
            await _send_simple(send, 202)
            return

        slot: _CallSlot | None = None
        rpc_id: str | None = None
        if method == "tools/call" and "id" in rpc:
            slot = _CallSlot()
            rpc_id = str(rpc["id"])
            turn.slots[rpc_id] = slot
        scope = dict(scope)
        scope[_SCOPE_TURN] = turn
        scope[_SCOPE_SLOT] = slot

        disconnected = asyncio.Event()

        async def _watch() -> None:
            # Codex aborting a call (e.g. an interrupted turn) drops the HTTP
            # request; that must reach the executor as a cancellation.
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    disconnected.set()
                    if slot is not None:
                        slot.cancel()
                    return

        replayed = False

        async def _replay() -> dict[str, Any]:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            await disconnected.wait()
            return {"type": "http.disconnect"}

        watcher = asyncio.ensure_future(_watch())
        try:
            manager = self._manager
            if manager is None:
                await _send_simple(send, 503)
                return
            await manager.handle_request(scope, _replay, send)
        finally:
            watcher.cancel()
            with contextlib.suppress(BaseException):
                await watcher
            if rpc_id is not None and turn.slots.get(rpc_id) is slot:
                del turn.slots[rpc_id]

    @staticmethod
    async def _run_manager(
        manager: StreamableHTTPSessionManager,
        ready: asyncio.Event,
        stop: asyncio.Event,
    ) -> None:
        # The SDK session manager needs a long-lived task group for the MCP
        # handlers. It lives in this bridge-owned task rather than in an ASGI
        # lifespan, so a loop torn down without `stop()` (a serverless
        # `asyncio.run` per invocation) cancels it quietly instead of making
        # uvicorn log a lifespan traceback.
        async with manager.run():
            ready.set()
            await stop.wait()

    # -- lifecycle -------------------------------------------------------------

    def usable_on(self, loop: asyncio.AbstractEventLoop) -> bool:
        """Whether this bridge is (or can be) serving on ``loop``."""
        if self._loop is None:
            return True  # never started
        if self._loop is not loop or loop.is_closed():
            return False
        return all(t is None or not t.done() for t in (self._task, self._manager_task))

    async def start(self) -> str:
        """Start the server on an ephemeral loopback port and return its URL."""
        if self.url:
            return self.url
        loop = asyncio.get_running_loop()
        if self._start_lock is None or self._start_lock_loop is not loop:
            self._start_lock = asyncio.Lock()
            self._start_lock_loop = loop
        async with self._start_lock:
            if self.url:
                return self.url
            manager = StreamableHTTPSessionManager(
                app=self._build_mcp_server(),
                stateless=True,
                # Plain JSON responses, not SSE: sse-starlette keeps a
                # process-global "should exit" flag that it latches when *any*
                # uvicorn server it can see shuts down, after which every SSE
                # response in the process ends immediately -- one bridge stop
                # with a call in flight would break every later bridge.
                json_response=True,
                security_settings=TransportSecuritySettings(
                    enable_dns_rebinding_protection=True,
                    allowed_hosts=["127.0.0.1:*", "localhost:*"],
                    allowed_origins=["http://127.0.0.1:*", "http://localhost:*"],
                ),
            )
            ready, stop = asyncio.Event(), asyncio.Event()
            manager_task = asyncio.ensure_future(
                self._run_manager(manager, ready, stop)
            )
            self._manager, self._manager_task, self._manager_stop = (
                manager,
                manager_task,
                stop,
            )
            self._loop = loop
            ready_wait = asyncio.ensure_future(ready.wait())
            await asyncio.wait(
                {ready_wait, manager_task},
                timeout=_START_TIMEOUT_SECONDS,
                return_when=asyncio.FIRST_COMPLETED,
            )
            ready_wait.cancel()
            if not ready.is_set():
                self.force_close()
                raise RuntimeError("codex MCP bridge session manager failed to start")

            config = uvicorn.Config(
                self._asgi,
                host="127.0.0.1",
                port=0,
                log_level="warning",
                lifespan="off",
                interface="asgi3",
                # In-flight tool calls hold responses open; do not let them
                # stall shutdown (stopping the manager cancels their handlers).
                timeout_graceful_shutdown=1,
            )
            server = uvicorn.Server(config)
            # Never take over the host process's SIGINT/SIGTERM: uvicorn >= 0.29
            # captures them in `capture_signals()` (the older
            # `install_signal_handlers` hook is kept for older versions).
            server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
            server.capture_signals = contextlib.nullcontext  # type: ignore[method-assign]
            task = asyncio.ensure_future(_serve(server))
            self._server, self._task, self._loop = server, task, loop

            deadline = time.monotonic() + _START_TIMEOUT_SECONDS
            while not server.started:
                if task.done():
                    exc = None if task.cancelled() else task.exception()
                    self.force_close()
                    raise RuntimeError(
                        "codex MCP bridge server exited before binding"
                    ) from exc
                if time.monotonic() >= deadline:
                    server.should_exit = True
                    task.cancel()
                    with contextlib.suppress(BaseException):
                        await task
                    self.force_close()
                    raise TimeoutError(
                        f"codex MCP bridge did not bind within {_START_TIMEOUT_SECONDS}s"
                    )
                await asyncio.sleep(0.02)
            try:
                port = server.servers[0].sockets[0].getsockname()[1]
            except (IndexError, AttributeError) as e:
                server.should_exit = True
                task.cancel()
                with contextlib.suppress(BaseException):
                    await task
                self.force_close()
                raise RuntimeError("codex MCP bridge reported no bound socket") from e
            self.url = f"http://127.0.0.1:{port}{_MCP_PATH}"
            logger.info("codex_mcp_bridge_started listen_url=%s", self.url)
            return self.url

    def _reset(self) -> None:
        self._server = None
        self._task = None
        self._loop = None
        self._manager = None
        self._manager_task = None
        self._manager_stop = None
        self.url = None

    def _drop_turns(self) -> None:
        with self._turns_lock:
            turns = list(self._turns.values())
            self._turns.clear()
        for turn in turns:
            for slot in list(turn.slots.values()):
                slot.cancel()

    async def stop(self, *, timeout: float = _STOP_TIMEOUT_SECONDS) -> None:
        """Drain the server, cancel in-flight calls and release the port."""
        running = None
        with contextlib.suppress(RuntimeError):
            running = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not running:
            self.force_close()
            return
        server, task = self._server, self._task
        manager_task, manager_stop = self._manager_task, self._manager_stop
        self._reset()
        # Cancelling the in-flight calls first lets their HTTP responses finish,
        # so the server drains promptly.
        self._drop_turns()
        if server is not None:
            server.should_exit = True
        try:
            if task is not None:
                await asyncio.wait_for(task, timeout)
            if manager_task is not None and manager_stop is not None:
                manager_stop.set()
                await asyncio.wait_for(manager_task, timeout)
        except asyncio.TimeoutError:
            logger.warning("codex_mcp_bridge_stop_timeout timeout_seconds=%s", timeout)
            for bound in getattr(server, "servers", None) or ():
                with contextlib.suppress(Exception):
                    bound.close()
            for pending in (task, manager_task):
                if pending is not None:
                    pending.cancel()
                    with contextlib.suppress(BaseException):
                        await pending
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 - shutdown must not raise
            logger.warning(
                "codex_mcp_bridge_stop_failed error_type=%s", type(e).__name__
            )
        else:
            logger.info("codex_mcp_bridge_stopped")

    def force_close(self) -> None:
        """Best-effort synchronous teardown (no running loop required)."""
        server = self._server
        tasks = (self._task, self._manager_task)
        self._reset()
        self._drop_turns()
        if server is not None:
            server.should_exit = True
            for bound in getattr(server, "servers", None) or ():
                with contextlib.suppress(Exception):
                    bound.close()
        for task in tasks:
            if task is None:
                continue
            with contextlib.suppress(Exception):
                if task.done():
                    if not task.cancelled():
                        task.exception()  # mark as retrieved
                else:
                    task.cancel()


async def _serve(server: uvicorn.Server) -> None:
    # uvicorn answers a failed bind with `sys.exit`, and a SystemExit escaping
    # a task tears down the whole event loop.
    try:
        await server.serve()
    except SystemExit as e:
        raise RuntimeError(f"codex MCP bridge server exited ({e.code})") from None


# One bridge per event loop: a bridge's server task lives on the loop that
# started it, so a worker running each invocation under its own `asyncio.run`
# (or on its own thread) needs its own. Guarded by a threading lock because the
# cache is shared across loops/threads; held only across dict operations.
_BRIDGES: dict[asyncio.AbstractEventLoop, McpBridge] = {}
_BRIDGES_LOCK = threading.Lock()


async def get_bridge() -> McpBridge:
    """Return this event loop's started bridge, creating it if needed."""
    loop = asyncio.get_running_loop()
    stale: list[McpBridge] = []
    with _BRIDGES_LOCK:
        for other_loop in [lp for lp in _BRIDGES if lp.is_closed()]:
            stale.append(_BRIDGES.pop(other_loop))
        bridge = _BRIDGES.get(loop)
        if bridge is not None and not bridge.usable_on(loop):
            stale.append(bridge)
            bridge = None
        if bridge is None:
            bridge = McpBridge()
            _BRIDGES[loop] = bridge
    for old in stale:
        logger.warning("codex_mcp_bridge_discarded reason=event_loop_closed_or_dead")
        old.force_close()
    try:
        await bridge.start()
    except BaseException:
        with _BRIDGES_LOCK:
            if _BRIDGES.get(loop) is bridge:
                del _BRIDGES[loop]
        bridge.force_close()
        raise
    return bridge


async def shutdown_bridge() -> None:
    """Stop the current event loop's bridge, if any (worker/app shutdown)."""
    loop = asyncio.get_running_loop()
    with _BRIDGES_LOCK:
        bridge = _BRIDGES.pop(loop, None)
    if bridge is not None:
        await bridge.stop()


# Registered with `atexit` by the decorator; the side effect is the point.
@atexit.register
def _close_bridges_at_exit() -> None:
    """Last-resort teardown: release listening sockets at interpreter exit."""
    acquired = _BRIDGES_LOCK.acquire(timeout=1.0)
    try:
        while _BRIDGES:
            with contextlib.suppress(Exception):
                _BRIDGES.popitem()[1].force_close()
    finally:
        if acquired:
            _BRIDGES_LOCK.release()
