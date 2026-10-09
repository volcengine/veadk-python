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

"""The Codex MCP bridge, exercised over real loopback HTTP.

Every offline test talks to the real bridge server through the ``mcp`` client
library (or raw ``httpx`` where the test needs control over the HTTP request
itself, e.g. to drop the connection mid-call). The last test, opt-in with
``CODEX_RUN_SMOKE=1``, drives the real Codex binary against the bridge with a
stub Responses model.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import time
import uuid
from typing import Any, AsyncIterator

import httpx
import pytest
import pytest_asyncio
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client

from veadk.runtime.codex import mcp_bridge
from veadk.runtime.codex.mcp_bridge import McpBridge, get_bridge, shutdown_bridge

_ECHO_SPEC = {
    "type": "function",
    "name": "echo",
    "description": "Echo the text back.",
    "parameters": {
        "type": "object",
        "properties": {"text": {"type": "string"}},
        "required": ["text"],
    },
}


def _spec(name: str) -> dict[str, Any]:
    return {**_ECHO_SPEC, "name": name}


async def _echo(args: dict[str, Any], call_id: str) -> str:
    return json.dumps({"status": "completed", "echo": args.get("text"), "id": call_id})


@pytest_asyncio.fixture
async def bridge() -> AsyncIterator[McpBridge]:
    b = await get_bridge()
    try:
        yield b
    finally:
        await shutdown_bridge()


@contextlib.asynccontextmanager
async def _session(url: str, token: str) -> AsyncIterator[ClientSession]:
    async with httpx.AsyncClient(
        headers={"Authorization": f"Bearer {token}"}, timeout=30
    ) as http:
        async with streamable_http_client(url, http_client=http) as (r, w, _):
            async with ClientSession(r, w) as session:
                await session.initialize()
                yield session


def _rpc_headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }


def _tools_call(rpc_id: int, name: str, args: dict[str, Any], call_id: str) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": rpc_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": args, "_meta": {"callId": call_id}},
    }


async def _wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError("condition not reached in time")
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_tools_are_isolated_per_token(bridge: McpBridge) -> None:
    seen: list[str] = []

    def make(tag: str):
        async def run(args: dict[str, Any], call_id: str) -> str:
            seen.append(tag)
            return json.dumps({"status": "completed", "tag": tag})

        return run

    token_a = bridge.register_turn([_spec("alpha")], {"alpha": make("a")})
    token_b = bridge.register_turn([_spec("beta")], {"beta": make("b")})
    assert token_a != token_b

    async with _session(bridge.url, token_a) as session:
        names = [t.name for t in (await session.list_tools()).tools]
        assert names == ["alpha"]
        # Turn A cannot reach turn B's tool even by name.
        result = await session.call_tool("beta", {"text": "x"})
        assert result.isError
    async with _session(bridge.url, token_b) as session:
        tools = (await session.list_tools()).tools
        assert [t.name for t in tools] == ["beta"]
        assert tools[0].inputSchema == _ECHO_SPEC["parameters"]
        assert tools[0].description == "Echo the text back."
    assert seen == []
    assert bridge.turn_state(token_a).calls == 0


@pytest.mark.asyncio
async def test_unknown_or_missing_token_is_rejected(bridge: McpBridge) -> None:
    bridge.register_turn([_spec("alpha")], {"alpha": _echo})
    body = {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}}
    async with httpx.AsyncClient() as http:
        for headers in (
            _rpc_headers("not-a-real-token"),
            {k: v for k, v in _rpc_headers("x").items() if k != "Authorization"},
        ):
            resp = await http.post(bridge.url, json=body, headers=headers)
            assert resp.status_code == 401
            assert "alpha" not in resp.text


@pytest.mark.asyncio
async def test_success_returns_structured_content(bridge: McpBridge) -> None:
    token = bridge.register_turn(
        [_spec("echo")], {"echo": _echo}, invocation_id="inv-1"
    )
    async with _session(bridge.url, token) as session:
        result = await session.call_tool(
            "echo", {"text": "hi"}, meta={"callId": "call_model_1"}
        )
    assert not result.isError
    assert result.structuredContent == {
        "status": "completed",
        "echo": "hi",
        "id": "call_model_1",  # `_meta.callId` became the executor's call_id
    }
    assert json.loads(result.content[0].text) == result.structuredContent
    state = bridge.turn_state(token)
    assert state.calls == 1
    assert state.interrupts == [] and state.errors == []


@pytest.mark.asyncio
async def test_missing_call_id_gets_a_generated_one(bridge: McpBridge) -> None:
    token = bridge.register_turn([_spec("echo")], {"echo": _echo})
    async with _session(bridge.url, token) as session:
        result = await session.call_tool("echo", {"text": "hi"})
    assert result.structuredContent["id"].startswith("call_")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status",
    ["pending", "authentication_required", "confirmation_required", "transferred"],
)
async def test_interrupt_statuses_are_recorded(bridge: McpBridge, status: str) -> None:
    async def run(args: dict[str, Any], call_id: str) -> str:
        payload = {"status": status, "call_id": call_id}
        if status == "transferred":
            payload["agent_name"] = "billing_agent"
        return json.dumps(payload)

    token = bridge.register_turn([_spec("stop")], {"stop": run})
    async with _session(bridge.url, token) as session:
        result = await session.call_tool("stop", {}, meta={"callId": "call_x"})
    assert not result.isError
    # No structuredContent: Codex would send it instead of the stop text.
    assert result.structuredContent is None
    text = result.content[0].text
    assert "Stop now" in text
    if status == "transferred":
        assert "billing_agent" in text
    [interrupt] = bridge.turn_state(token).interrupts
    assert interrupt.call_id == "call_x"
    assert interrupt.tool == "stop"
    assert interrupt.status == status
    assert interrupt.payload["status"] == status


@pytest.mark.asyncio
async def test_executor_exception_is_error_and_recorded(bridge: McpBridge) -> None:
    async def boom(args: dict[str, Any], call_id: str) -> str:
        raise RuntimeError("kaboom")

    token = bridge.register_turn(
        [_spec("boom"), _spec("echo")], {"boom": boom, "echo": _echo}
    )
    async with _session(bridge.url, token) as session:
        result = await session.call_tool("boom", {})
        assert result.isError
        assert "kaboom" in result.content[0].text
        # The server survives and keeps serving.
        again = await session.call_tool("echo", {"text": "still here"})
        assert again.structuredContent["echo"] == "still here"
    [error] = bridge.turn_state(token).errors
    assert isinstance(error, RuntimeError)


@pytest.mark.asyncio
async def test_parallel_calls_overlap_within_and_across_turns(
    bridge: McpBridge,
) -> None:
    active = 0
    peak = 0
    all_in = asyncio.Event()

    async def slow(args: dict[str, Any], call_id: str) -> str:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        if active == 4:
            all_in.set()
        try:
            # Only returns if all four calls are running at the same time.
            await asyncio.wait_for(all_in.wait(), 5)
        finally:
            active -= 1
        return json.dumps({"status": "completed", "text": args["text"]})

    tokens = [bridge.register_turn([_spec("slow")], {"slow": slow}) for _ in range(2)]

    async def two_calls(token: str) -> list[Any]:
        async with _session(bridge.url, token) as session:
            return await asyncio.gather(
                session.call_tool("slow", {"text": f"{token[:4]}-1"}),
                session.call_tool("slow", {"text": f"{token[:4]}-2"}),
            )

    results = await asyncio.gather(*(two_calls(t) for t in tokens))
    assert peak == 4
    for result in (r for pair in results for r in pair):
        assert not result.isError
    assert [bridge.turn_state(t).calls for t in tokens] == [2, 2]


async def _start_blocking_call(
    bridge: McpBridge,
) -> tuple[str, asyncio.Event, asyncio.Event]:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def block(args: dict[str, Any], call_id: str) -> str:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return json.dumps({"status": "completed"})

    token = bridge.register_turn([_spec("block")], {"block": block})
    return token, started, cancelled


@pytest.mark.asyncio
async def test_client_disconnect_cancels_the_executor(bridge: McpBridge) -> None:
    token, started, cancelled = await _start_blocking_call(bridge)
    async with httpx.AsyncClient(timeout=30) as http:
        call = asyncio.ensure_future(
            http.post(
                bridge.url,
                json=_tools_call(7, "block", {}, "call_dc"),
                headers=_rpc_headers(token),
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        # Drop the connection mid-call, the way Codex does on an interrupt.
        call.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await call
    await asyncio.wait_for(cancelled.wait(), 5)


@pytest.mark.asyncio
async def test_cancelled_notification_cancels_the_executor(bridge: McpBridge) -> None:
    token, started, cancelled = await _start_blocking_call(bridge)
    async with httpx.AsyncClient(timeout=30) as http:
        call = asyncio.ensure_future(
            http.post(
                bridge.url,
                json=_tools_call(9, "block", {}, "call_nc"),
                headers=_rpc_headers(token),
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        # Another turn's token cannot cancel this call.
        other = bridge.register_turn([], {})
        note = {
            "jsonrpc": "2.0",
            "method": "notifications/cancelled",
            "params": {"requestId": 9, "reason": "user interrupt"},
        }
        resp = await http.post(bridge.url, json=note, headers=_rpc_headers(other))
        assert resp.status_code == 202
        await asyncio.sleep(0.2)
        assert not cancelled.is_set()
        resp = await http.post(bridge.url, json=note, headers=_rpc_headers(token))
        assert resp.status_code == 202
        await asyncio.wait_for(cancelled.wait(), 5)
        answer = await asyncio.wait_for(call, 5)
    assert "cancelled" in answer.text


@pytest.mark.asyncio
async def test_unregister_invalidates_the_token(bridge: McpBridge) -> None:
    token = bridge.register_turn([_spec("echo")], {"echo": _echo})
    async with _session(bridge.url, token) as session:
        assert (await session.call_tool("echo", {"text": "x"})).structuredContent
    bridge.unregister_turn(token)
    assert bridge.turn_state(token) is None
    async with httpx.AsyncClient() as http:
        resp = await http.post(
            bridge.url,
            json=_tools_call(1, "echo", {"text": "x"}, "c"),
            headers=_rpc_headers(token),
        )
    assert resp.status_code == 401


def _recording_echo(seen: list[dict[str, Any]]):
    async def run(args: dict[str, Any], call_id: str) -> str:
        seen.append(args)
        return await _echo(args, call_id)

    return run


@pytest.mark.asyncio
async def test_oversized_body_is_rejected_before_any_tool_runs(
    bridge: McpBridge, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A body over the cap gets 413 and never reaches an executor.

    The bridge buffers each request to inspect it, so without the cap one
    authenticated caller could make the host process hold an arbitrarily large
    body in memory. The cap is lowered here only so the test does not push
    8 MiB through loopback; the check is the same code path.
    """
    limit = 4096
    monkeypatch.setattr(mcp_bridge, "_MAX_BODY_BYTES", limit)
    seen: list[dict[str, Any]] = []
    token = bridge.register_turn([_spec("echo")], {"echo": _recording_echo(seen)})
    async with httpx.AsyncClient(timeout=30) as http:
        small = await http.post(
            bridge.url,
            json=_tools_call(1, "echo", {"text": "ok"}, "call_small"),
            headers=_rpc_headers(token),
        )
        assert small.status_code == 200, small.text
        assert seen == [{"text": "ok"}]

        big = _tools_call(2, "echo", {"text": "x" * (4 * limit)}, "call_big")
        resp = await http.post(bridge.url, json=big, headers=_rpc_headers(token))
    assert resp.status_code == 413
    assert seen == [{"text": "ok"}], "the oversized call reached the executor"
    assert bridge.turn_state(token).calls == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("path", ["/", "/mcpx", "/mcp/tools", "/other"])
async def test_paths_other_than_mcp_are_not_found(bridge: McpBridge, path: str) -> None:
    """Only ``/mcp`` is served; any other path is 404 even with a valid token.

    The bridge is a bare ASGI callable, not a router: without the path check
    every URL on the loopback port would be a second, unadvertised MCP
    endpoint.
    """
    seen: list[dict[str, Any]] = []
    token = bridge.register_turn([_spec("echo")], {"echo": _recording_echo(seen)})
    url = str(httpx.URL(bridge.url).copy_with(path=path))
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(
            url,
            json=_tools_call(1, "echo", {"text": "x"}, "call_path"),
            headers=_rpc_headers(token),
        )
    assert resp.status_code == 404
    assert seen == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("header", "value", "status"),
    [
        ("Host", "evil.example.com", 421),
        ("Host", "attacker.test:{port}", 421),
        ("Origin", "http://evil.example.com", 403),
        ("Origin", "http://attacker.test:{port}", 403),
    ],
)
async def test_non_loopback_host_or_origin_is_rejected(
    bridge: McpBridge, header: str, value: str, status: int
) -> None:
    """DNS-rebinding protection: only loopback Host/Origin are served.

    A web page on an attacker's domain that re-resolves to 127.0.0.1 can make
    the user's browser send requests to the bridge's port. The bearer token
    stops those in practice, but the bridge must not rely on it alone: a
    request whose Host or Origin is not loopback is refused before any tool
    runs. The loopback request first shows the headers themselves are fine.
    """
    seen: list[dict[str, Any]] = []
    token = bridge.register_turn([_spec("echo")], {"echo": _recording_echo(seen)})
    port = httpx.URL(bridge.url).port
    loopback = f"http://localhost:{port}" if header == "Origin" else f"localhost:{port}"
    async with httpx.AsyncClient(timeout=30) as http:
        ok = await http.post(
            bridge.url,
            json=_tools_call(1, "echo", {"text": "loopback"}, "call_ok"),
            headers={**_rpc_headers(token), header: loopback},
        )
        assert ok.status_code == 200, ok.text
        resp = await http.post(
            bridge.url,
            json=_tools_call(2, "echo", {"text": "rebound"}, "call_evil"),
            headers={**_rpc_headers(token), header: value.format(port=port)},
        )
    assert resp.status_code == status, resp.text
    assert seen == [{"text": "loopback"}], "a non-loopback request ran a tool"


@pytest.mark.asyncio
async def test_stop_with_a_call_in_flight_cancels_it_and_a_new_bridge_works() -> None:
    bridge = await get_bridge()
    token, started, cancelled = await _start_blocking_call(bridge)
    async with httpx.AsyncClient(timeout=30) as http:
        call = asyncio.ensure_future(
            http.post(
                bridge.url,
                json=_tools_call(3, "block", {}, "call_stop"),
                headers=_rpc_headers(token),
            )
        )
        await asyncio.wait_for(started.wait(), 5)
        await asyncio.wait_for(shutdown_bridge(), 10)
        await asyncio.wait_for(cancelled.wait(), 5)
        with contextlib.suppress(Exception):
            await call
    assert bridge.url is None and bridge.turn_state(token) is None

    # Nothing process-global was latched by that shutdown: a fresh bridge on
    # the same loop still answers calls.
    fresh = await get_bridge()
    try:
        assert fresh is not bridge
        token = fresh.register_turn([_spec("echo")], {"echo": _echo})
        async with _session(fresh.url, token) as session:
            result = await session.call_tool("echo", {"text": "after"})
        assert result.structuredContent["echo"] == "after"
    finally:
        await shutdown_bridge()


def test_bridge_restarts_cleanly_on_a_new_loop() -> None:
    async def use_bridge() -> tuple[McpBridge, str]:
        b = await get_bridge()
        assert await get_bridge() is b  # cached for this loop
        token = b.register_turn([_spec("echo")], {"echo": _echo})
        async with _session(b.url, token) as session:
            result = await session.call_tool("echo", {"text": "loop"})
        assert result.structuredContent["echo"] == "loop"
        return b, b.url

    first, first_url = asyncio.run(use_bridge())
    second, second_url = asyncio.run(use_bridge())
    try:
        assert second is not first
        # The dead loop's bridge was torn down and forgot its turns.
        assert first.url is None and not first.busy
        assert second.url == second_url
    finally:
        second.force_close()
        mcp_bridge._BRIDGES.clear()


def test_codex_server_config_shape() -> None:
    b = McpBridge()
    with pytest.raises(RuntimeError):
        b.codex_server_config(bearer_token_env_var="X", tool_timeout_seconds=None)
    b.url = "http://127.0.0.1:1/mcp"
    cfg = b.codex_server_config(bearer_token_env_var="VEADK_T", tool_timeout_seconds=60)
    assert cfg["url"] == b.url
    assert cfg["bearer_token_env_var"] == "VEADK_T"
    assert cfg["default_tools_approval_mode"] == "approve"
    assert cfg["supports_parallel_tool_calls"] is True
    assert cfg["tool_timeout_sec"] > 60
    unbounded = b.codex_server_config(
        bearer_token_env_var="VEADK_T", tool_timeout_seconds=None
    )
    assert unbounded["tool_timeout_sec"] >= 600


# ---------------------------------------------------------------- real binary


class _StubModel:
    """A scripted streaming Responses API standing in for the model."""

    def __init__(self, tool_name: str, args: dict[str, Any]) -> None:
        self.requests: list[dict[str, Any]] = []
        self.call_id = f"call_{uuid.uuid4().hex[:12]}"
        self._tool_name = tool_name
        self._args = args
        self._server: Any = None
        self._task: asyncio.Task[Any] | None = None
        app = FastAPI()

        @app.post("/v1/responses")
        async def responses(request: Request) -> Any:
            body = await request.json()
            self.requests.append(body)
            return StreamingResponse(
                self._sse(body, self._script(body)), media_type="text/event-stream"
            )

        @app.api_route("/v1/{path:path}", methods=["GET", "POST"])
        async def other(path: str) -> Any:
            return {"object": "list", "data": [], "models": []}

        self._app = app

    def _script(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        if len(self.requests) == 1:
            namespace = f"mcp__{McpBridge.SERVER_NAME}"
            return [
                {
                    "type": "function_call",
                    "id": f"fc_{uuid.uuid4().hex[:12]}",
                    "call_id": self.call_id,
                    "name": self._tool_name,
                    "namespace": namespace,
                    "arguments": json.dumps(self._args),
                    "status": "completed",
                }
            ]
        return [
            {
                "type": "message",
                "id": f"msg_{uuid.uuid4().hex[:12]}",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "done", "annotations": []}],
            }
        ]

    @staticmethod
    def _sse(body: dict[str, Any], output: list[dict[str, Any]]):
        base = {
            "id": f"resp_{uuid.uuid4().hex[:12]}",
            "object": "response",
            "created_at": int(time.time()),
            "model": body.get("model", "stub"),
            "status": "in_progress",
            "output": [],
        }
        seq = 0

        def ev(kind: str, **data: Any) -> str:
            nonlocal seq
            seq += 1
            payload = {"type": kind, "sequence_number": seq, **data}
            return f"event: {kind}\ndata: {json.dumps(payload)}\n\n"

        yield ev("response.created", response=base)
        for i, item in enumerate(output):
            yield ev("response.output_item.added", output_index=i, item=item)
            yield ev("response.output_item.done", output_index=i, item=item)
        usage = {
            "input_tokens": 11,
            "output_tokens": 7,
            "total_tokens": 18,
            "input_tokens_details": {"cached_tokens": 0},
            "output_tokens_details": {"reasoning_tokens": 0},
        }
        done = dict(base, status="completed", output=output, usage=usage)
        yield ev("response.completed", response=done)

    async def start(self) -> str:
        config = uvicorn.Config(
            self._app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
        )
        self._server = uvicorn.Server(config)
        self._server.install_signal_handlers = lambda: None
        self._task = asyncio.ensure_future(self._server.serve())
        while not self._server.started:
            if self._task.done():
                self._task.result()
            await asyncio.sleep(0.02)
        port = self._server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}/v1"

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, 10)


def _smoke_skip_reason() -> str | None:
    from tests.runtime.codex.test_codex_runtime_smoke import _skip_reason

    return _skip_reason()


def _describe(note: Any) -> str:
    try:
        payload = note.payload.model_dump(mode="json", exclude_none=True)
    except Exception:  # noqa: BLE001 - diagnostics only
        payload = repr(getattr(note, "payload", note))
    return f"{getattr(note, 'method', '?')}: {json.dumps(payload, default=str)[:400]}"


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_codex_calls_adk_executor_through_bridge() -> None:
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip("set CODEX_RUN_SMOKE=1 to spawn the real Codex binary")
    reason = _smoke_skip_reason()
    if reason:
        pytest.skip(reason)

    from openai_codex import ApprovalMode, AsyncCodex, CodexConfig, Sandbox

    executed: list[tuple[dict[str, Any], str]] = []
    notes: list[str] = []

    async def lookup_order(args: dict[str, Any], call_id: str) -> str:
        executed.append((args, call_id))
        return json.dumps(
            {"status": "completed", "order": args["order_id"], "state": "shipped"}
        )

    spec = {
        "type": "function",
        "name": "lookup_order",
        "description": "Look up an order.",
        "parameters": {
            "type": "object",
            "properties": {"order_id": {"type": "string"}},
            "required": ["order_id"],
        },
    }
    bridge = await get_bridge()
    token = bridge.register_turn(
        [spec], {"lookup_order": lookup_order}, invocation_id="smoke"
    )
    model = _StubModel("lookup_order", {"order_id": "A-42"})
    model_url = await model.start()
    home = tempfile.mkdtemp(prefix="veadk_mcp_bridge_home_")
    work = tempfile.mkdtemp(prefix="veadk_mcp_bridge_work_")
    env = {
        "CODEX_HOME": home,
        "STUB_KEY": "stub-key",
        "VEADK_MCP_BRIDGE_TOKEN": token,
        "OPENAI_API_KEY": "",
    }
    config = {
        "model_providers": {
            "stub": {
                "name": "stub",
                "base_url": model_url,
                "env_key": "STUB_KEY",
                "wire_api": "responses",
            }
        },
        "mcp_servers": {
            McpBridge.SERVER_NAME: bridge.codex_server_config(
                bearer_token_env_var="VEADK_MCP_BRIDGE_TOKEN",
                tool_timeout_seconds=30,
            )
        },
    }
    try:
        async with AsyncCodex(config=CodexConfig(cwd=work, env=env)) as codex:
            thread = await codex.thread_start(
                model="gpt-5.4",
                model_provider="stub",
                config=config,
                approval_mode=ApprovalMode.deny_all,
                sandbox=Sandbox.read_only,
                ephemeral=True,
                cwd=work,
            )
            turn = await thread.turn("Where is order A-42?")

            async def consume() -> None:
                async for note in turn.stream():
                    notes.append(_describe(note))

            await asyncio.wait_for(consume(), 60)
    finally:
        await model.stop()
        bridge.unregister_turn(token)
        await shutdown_bridge()

    debug = {"notifications": notes, "model_requests": len(model.requests)}
    assert executed == [({"order_id": "A-42"}, model.call_id)], debug
    first_tools = model.requests[0].get("tools") or []
    namespace = next(
        t for t in first_tools if t.get("name") == f"mcp__{McpBridge.SERVER_NAME}"
    )
    assert [t["name"] for t in namespace["tools"]] == ["lookup_order"]
    assert len(model.requests) >= 2
    outputs = [
        item
        for item in model.requests[1].get("input") or []
        if item.get("type") == "function_call_output"
        and item.get("call_id") == model.call_id
    ]
    assert outputs, "the tool result never reached the next model request"
    text = json.dumps(outputs[0].get("output"))
    assert "shipped" in text and "A-42" in text
    assert "approval" not in text.lower()
