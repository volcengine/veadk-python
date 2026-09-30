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

"""Self-tests for :class:`fake_codex_sdk.DirectDrivingCodex`.

The direct-mode fake is only worth building runtime tests on if it really does
what Codex does on the MCP side, so these drive it with no runtime at all
against a real FastMCP streamable-HTTP server on a loopback socket: real
``initialize`` / ``tools/list`` / ``tools/call`` JSON-RPC, a real bearer check,
real concurrency and real cancellation. The model is a :class:`ScriptedBackend`
plan that names MCP tools by their plain names.
"""

from __future__ import annotations

import asyncio
import json
import time
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, AsyncIterator

import pytest

import fake_codex_sdk
from fake_codex_sdk import DirectDrivingCodex, mcp_output_body
from scripted_backend import Round, ScriptedBackend

pytest.importorskip("mcp.server.fastmcp")
uvicorn = pytest.importorskip("uvicorn")

TOKEN = "bridge-secret"


class TextInput:
    """Name-compatible with ``openai_codex.TextInput`` (the fake reads names)."""

    def __init__(self, text: str) -> None:
        self.text = text


class _Bridge:
    """A two-tool FastMCP server standing in for VeADK's MCP bridge."""

    def __init__(self) -> None:
        self.url = ""
        self.rpc: list[dict[str, Any]] = []
        self.rejected: list[str] = []
        self.tool_log: list[tuple[str, str, float]] = []
        self.started = asyncio.Event()

    def calls(self) -> list[dict[str, Any]]:
        return [
            r["params"]
            for r in self.rpc
            if isinstance(r, dict) and r.get("method") == "tools/call"
        ]


@asynccontextmanager
async def _bridge() -> AsyncIterator[_Bridge]:
    from mcp.server.fastmcp import FastMCP

    state = _Bridge()
    mcp = FastMCP("veadk", stateless_http=True)

    @mcp.tool()
    async def echo(text: str, delay: float = 0.0) -> str:
        """Echo text back after an optional delay."""
        state.tool_log.append(("start", text, time.monotonic()))
        state.started.set()
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            state.tool_log.append(("cancelled", text, time.monotonic()))
            raise
        state.tool_log.append(("end", text, time.monotonic()))
        return text

    @mcp.tool()
    def boom() -> str:
        """Always fails."""
        raise RuntimeError("boom exploded on purpose")

    inner = mcp.streamable_http_app()

    async def app(scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http":
            return await inner(scope, receive, send)
        auth = dict(scope.get("headers") or []).get(b"authorization", b"").decode()
        if auth != f"Bearer {TOKEN}":
            state.rejected.append(auth)
            await send({"type": "http.response.start", "status": 401, "headers": []})
            await send({"type": "http.response.body", "body": b"unauthorized"})
            return
        chunks, more = [], True
        while more:
            message = await receive()
            chunks.append(message.get("body", b""))
            more = message.get("more_body", False)
        body = b"".join(chunks)
        if body:
            state.rpc.append(json.loads(body))
        replayed = False

        async def replay() -> Any:
            nonlocal replayed
            if not replayed:
                replayed = True
                return {"type": "http.request", "body": body, "more_body": False}
            return await receive()

        return await inner(scope, replay, send)

    # sse_starlette latches a process-wide `AppStatus.should_exit` once any
    # uvicorn server in the process shuts down, after which every SSE response
    # ends before its first event -- the next bridge's `initialize` would then
    # hang. Clear it on the way in and on the way out.
    from sse_starlette.sse import AppStatus

    AppStatus.should_exit = False
    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="warning", lifespan="on"
        )
    )
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
    task = asyncio.create_task(server.serve())
    try:
        while not server.started:
            if task.done():
                task.result()
            await asyncio.sleep(0.01)
        port = server.servers[0].sockets[0].getsockname()[1]
        state.url = f"http://127.0.0.1:{port}/mcp"
        yield state
    finally:
        server.should_exit = True
        await asyncio.wait_for(asyncio.gather(task, return_exceptions=True), 10)
        AppStatus.should_exit = False


def _thread_config(bridge: _Bridge, **server_overrides: Any) -> dict[str, Any]:
    server = {
        "url": bridge.url,
        "bearer_token_env_var": "VEADK_MCP_TOKEN",
        "default_tools_approval_mode": "approve",
        "supports_parallel_tool_calls": True,
    }
    server.update(server_overrides)
    return {
        "model_providers": {
            "veadk": {
                "name": "veadk",
                "base_url": "https://provider.invalid/v1",
                "env_key": "VEADK_PROVIDER_KEY",
                "wire_api": "responses",
            }
        },
        "mcp_servers": {"veadk": server},
    }


async def _start(
    bridge: _Bridge,
    backend: ScriptedBackend,
    *,
    approval_mode: str = "deny_all",
    **server_overrides: Any,
) -> tuple[DirectDrivingCodex, Any]:
    codex = DirectDrivingCodex(
        config=SimpleNamespace(
            cwd=None,
            env={"VEADK_PROVIDER_KEY": "provider-key", "VEADK_MCP_TOKEN": TOKEN},
        ),
        model_call=backend.as_aresponses(),
    )
    thread = await codex.thread_start(
        model="scripted-model",
        model_provider="veadk",
        developer_instructions="Be terse.",
        config=_thread_config(bridge, **server_overrides),
        approval_mode=approval_mode,
    )
    return codex, await thread.turn([TextInput("go")])


def _dump(payload: Any) -> dict[str, Any]:
    dump = payload.model_dump
    try:
        return dump(mode="json")
    except TypeError:  # the name-compatible shim takes no mode
        return dump()


async def _collect(turn: Any) -> list[tuple[str, dict[str, Any]]]:
    async def drain() -> list[tuple[str, dict[str, Any]]]:
        return [
            (type(n.payload).__name__, _dump(n.payload)) async for n in turn.stream()
        ]

    # A wedged fake must fail the test, not hang the worker.
    return await asyncio.wait_for(drain(), 30)


def _items(notes: list[tuple[str, dict[str, Any]]], kind: str) -> list[tuple]:
    return [
        (name, data["item"])
        for name, data in notes
        if name in ("ItemStartedNotification", "ItemCompletedNotification")
        and data["item"]["type"] == kind
    ]


def _outputs(request: dict[str, Any]) -> dict[str, Any]:
    return {
        item["call_id"]: item["output"]
        for item in request["input"]
        if item.get("type") == "function_call_output"
    }


# ----------------------------------------------------------------- scenarios


@pytest.mark.asyncio
async def test_tool_call_round_trip_through_real_mcp() -> None:
    backend = ScriptedBackend(
        [
            Round(tool_calls=(("echo", {"text": "hi"}),), usage=(5, 2)),
            Round(text="done", usage=(10, 4)),
        ],
        arm="codex",
    )
    async with _bridge() as bridge:
        codex, turn = await _start(bridge, backend)
        notes = await _collect(turn)

    assert bridge.rejected == []
    assert [r["method"] for r in bridge.rpc if "method" in r][:3] == [
        "initialize",
        "notifications/initialized",
        "tools/list",
    ]

    # Model request 1: MCP tools advertised as one namespace tool, titles
    # stripped, provider + credential taken from thread config and env.
    first = codex.requests[0]
    assert first["_provider"] == {
        "id": "veadk",
        "base_url": "https://provider.invalid/v1",
        "env_key": "VEADK_PROVIDER_KEY",
        "wire_api": "responses",
        "api_key": "provider-key",
    }
    (namespace,) = first["tools"]
    assert namespace["type"] == "namespace"
    assert namespace["name"] == "mcp__veadk"
    tools = {t["name"]: t for t in namespace["tools"]}
    assert set(tools) == {"echo", "boom"}
    assert "title" not in json.dumps(tools["echo"]["parameters"])
    assert tools["echo"]["parameters"]["required"] == ["text"]
    assert first["input"][0]["role"] == "developer"
    assert backend.calls[0].tool_names == ("echo", "boom")

    # MCP tools/call: plain tool name, parsed args, Codex's _meta.callId.
    (call,) = bridge.calls()
    assert call["name"] == "echo"
    assert call["arguments"] == {"text": "hi"}
    assert call["_meta"]["callId"] == "call-0-0"

    # Model request 2: the namespaced call and its structured output.
    second = codex.requests[1]
    fc = [i for i in second["input"] if i.get("type") == "function_call"]
    assert fc == [
        {
            "type": "function_call",
            "id": "fc-0-0",
            "name": "echo",
            "namespace": "mcp__veadk",
            "arguments": json.dumps({"text": "hi"}),
            "call_id": "call-0-0",
        }
    ]
    output = _outputs(second)["call-0-0"]
    assert output.startswith("Wall time: ")
    assert json.loads(mcp_output_body(output)) == {"result": "hi"}
    assert backend.calls[1].tool_records == (
        ("function_call", "echo"),
        ("function_response", "echo"),
    )

    names = [name for name, _ in notes]
    assert names[0] == "TurnStartedNotification"
    assert notes[-1][0] == "TurnCompletedNotification"
    assert notes[-1][1]["turn"]["status"] == "completed"
    texts = [
        item["text"]
        for name, item in _items(notes, "agentMessage")
        if name == "ItemCompletedNotification"
    ]
    assert texts == ["done"]


@pytest.mark.asyncio
async def test_mcp_tool_call_notifications_carry_codex_fields() -> None:
    backend = ScriptedBackend(
        [
            Round(tool_calls=(("echo", {"text": "hi"}),), usage=(5, 2)),
            Round(text="done", usage=(10, 4)),
        ],
        arm="codex",
    )
    async with _bridge() as bridge:
        codex, turn = await _start(bridge, backend)
        notes = await _collect(turn)

    (started, completed) = _items(notes, "mcpToolCall")
    assert started[0] == "ItemStartedNotification"
    assert completed[0] == "ItemCompletedNotification"
    for _, item in (started, completed):
        assert item["id"] == "call-0-0"
        assert item["server"] == "veadk"
        assert item["tool"] == "echo"
        assert item["arguments"] == {"text": "hi"}
    assert started[1]["status"] == "inProgress"
    assert completed[1]["status"] == "completed"
    assert completed[1]["result"]["content"][0]["text"] == "hi"
    assert completed[1]["result"]["structured_content"] == {"result": "hi"}
    assert completed[1]["duration_ms"] >= 0
    assert not completed[1].get("error")

    usage = [data for name, data in notes if name.startswith("ThreadTokenUsage")]
    assert len(usage) == len(codex.requests) == 2
    assert usage[0]["token_usage"]["last"]["input_tokens"] == 5
    assert usage[1]["token_usage"]["last"]["input_tokens"] == 10
    assert usage[1]["token_usage"]["total"]["input_tokens"] == 15
    assert usage[1]["token_usage"]["total"]["total_tokens"] == 21

    # When the SDK is installed, every payload must be a real SDK model: a
    # schema drift in the fake must not silently degrade to name-shims.
    if fake_codex_sdk.openai_codex_available():
        modules = {type(p).__module__ for p in codex.notifications}
        assert modules == {"openai_codex.generated.v2_all"}, modules


@pytest.mark.asyncio
@pytest.mark.parametrize("parallel", [True, False])
async def test_parallel_calls_overlap_only_when_server_allows(parallel: bool) -> None:
    backend = ScriptedBackend(
        [
            Round(
                tool_calls=(
                    ("echo", {"text": "a", "delay": 0.3}),
                    ("echo", {"text": "b", "delay": 0.3}),
                )
            ),
            Round(text="done"),
        ],
        arm="codex",
    )
    async with _bridge() as bridge:
        codex, turn = await _start(
            bridge, backend, supports_parallel_tool_calls=parallel
        )
        notes = await _collect(turn)

    at = {(phase, text): t for phase, text, t in bridge.tool_log}
    overlapped = at[("start", "b")] < at[("end", "a")]
    assert overlapped is parallel

    # Outputs go back in call order whatever order the calls finished in.
    second = codex.requests[1]
    outputs = [i for i in second["input"] if i.get("type") == "function_call_output"]
    assert [o["call_id"] for o in outputs] == ["call-0-0", "call-0-1"]
    assert [json.loads(mcp_output_body(o["output"])) for o in outputs] == [
        {"result": "a"},
        {"result": "b"},
    ]
    kinds = [(name, item["id"]) for name, item in _items(notes, "mcpToolCall")]
    if parallel:
        # Both started before either completed, as codex does.
        assert [k[0] for k in kinds[:2]] == ["ItemStartedNotification"] * 2


@pytest.mark.asyncio
async def test_tool_error_becomes_error_output() -> None:
    backend = ScriptedBackend(
        [Round(tool_calls=(("boom", {}),)), Round(text="recovered")], arm="codex"
    )
    async with _bridge() as bridge:
        codex, turn = await _start(bridge, backend)
        notes = await _collect(turn)

    (_, completed) = _items(notes, "mcpToolCall")
    assert completed[1]["status"] == "failed"
    assert "boom exploded on purpose" in completed[1]["result"]["content"][0]["text"]

    output = _outputs(codex.requests[1])["call-0-0"]
    assert isinstance(output, list)  # codex frames failures as input_text parts
    assert "boom exploded on purpose" in mcp_output_body(output)
    assert notes[-1][1]["turn"]["status"] == "completed"


@pytest.mark.asyncio
async def test_unapproved_mcp_tool_fails_without_calling_the_server() -> None:
    backend = ScriptedBackend(
        [Round(tool_calls=(("echo", {"text": "hi"}),)), Round(text="ok")],
        arm="codex",
    )
    async with _bridge() as bridge:
        codex, turn = await _start(bridge, backend, default_tools_approval_mode=None)
        notes = await _collect(turn)

    assert bridge.calls() == []
    (_, completed) = _items(notes, "mcpToolCall")
    assert completed[1]["status"] == "failed"
    assert completed[1]["error"] == {"message": fake_codex_sdk.MCP_APPROVAL_DENIED}
    output = _outputs(codex.requests[1])["call-0-0"]
    assert mcp_output_body(output) == fake_codex_sdk.MCP_APPROVAL_DENIED


@pytest.mark.asyncio
async def test_wrong_bearer_is_rejected_by_the_bridge() -> None:
    backend = ScriptedBackend([Round(text="unreachable")], arm="codex")
    async with _bridge() as bridge:
        codex = DirectDrivingCodex(
            config=SimpleNamespace(
                env={"VEADK_PROVIDER_KEY": "k", "VEADK_MCP_TOKEN": "wrong"}
            ),
            model_call=backend.as_aresponses(),
        )
        thread = await codex.thread_start(
            model="m", model_provider="veadk", config=_thread_config(bridge)
        )
        turn = await thread.turn([TextInput("go")])
        # The mcp client surfaces the 401 from inside its task group.
        with pytest.raises(Exception) as info:
            await asyncio.wait_for(_collect(turn), 10)
    assert "401 Unauthorized" in repr(info.value)
    assert bridge.rejected == ["Bearer wrong"]
    assert codex.requests == []


@pytest.mark.asyncio
async def test_interrupt_mid_tool_cancels_the_mcp_call() -> None:
    backend = ScriptedBackend(
        [
            Round(tool_calls=(("echo", {"text": "slow", "delay": 30}),)),
            Round(text="never"),
        ],
        arm="codex",
    )
    async with _bridge() as bridge:
        codex, turn = await _start(bridge, backend)
        consumer = asyncio.create_task(_collect(turn))
        await asyncio.wait_for(bridge.started.wait(), 10)
        began = time.monotonic()
        await turn.interrupt()
        notes = await asyncio.wait_for(consumer, 10)
        elapsed = time.monotonic() - began
        # Give the server a moment to observe the dropped request.
        for _ in range(100):
            if any(phase == "cancelled" for phase, _, _ in bridge.tool_log):
                break
            await asyncio.sleep(0.02)

    assert elapsed < 5
    assert notes[-1][0] == "TurnCompletedNotification"
    assert notes[-1][1]["turn"]["status"] == "interrupted"
    assert len(codex.requests) == 1  # no follow-up model call
    assert codex.mcp_calls[0]["status"] == "cancelled"
    phases = [phase for phase, _, _ in bridge.tool_log]
    assert "end" not in phases
    assert "cancelled" in phases


@pytest.mark.asyncio
async def test_default_model_call_is_the_patched_litellm(monkeypatch) -> None:
    fake_codex_sdk.install_openai_codex_stub()
    backend = ScriptedBackend([Round(text="patched")], arm="codex")
    monkeypatch.setattr(
        "veadk.runtime.codex.proxy.litellm.aresponses", backend.as_aresponses()
    )
    cls = DirectDrivingCodex.configured(max_agent_loops=2)
    async with _bridge() as bridge:
        async with cls(
            config=SimpleNamespace(
                env={"VEADK_PROVIDER_KEY": "k", "VEADK_MCP_TOKEN": TOKEN}
            )
        ) as codex:
            thread = await codex.thread_start(
                model="m", model_provider="veadk", config=_thread_config(bridge)
            )
            notes = await _collect(await thread.turn([TextInput("hi")]))
    assert cls.instances == [codex]
    assert backend.calls[0].current_text == "hi"
    assert notes[-1][1]["turn"]["status"] == "completed"
