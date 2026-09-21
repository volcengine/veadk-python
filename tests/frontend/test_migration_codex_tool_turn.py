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

"""Checks for the shared one-turn dynamic-tool helper."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from frontend.server.migration import codex_tool_turn
from frontend.server.migration.codex_tool_turn import (
    DynamicTool,
    ToolTurnDeadlineExceeded,
    ToolTurnUnavailable,
    run_tool_turn,
)
from veadk.cli.codex_app_server import CodexAppServerError


class _FakeSession:
    """A Codex app-server session that streams scripted events."""

    def __init__(
        self,
        events: list[str],
        *,
        connect_error: Exception | None = None,
        stream_error: Exception | None = None,
        forever: bool = False,
        thread_id: str = "thread-1",
    ) -> None:
        self.thread_id = thread_id
        self.cwd = ""
        self.model = ""
        self.interrupted = 0
        self.closed = 0
        self.attached: list[str] = []
        self.tools: list[str] = []
        self._events = events
        self._connect_error = connect_error
        self._stream_error = stream_error
        self._forever = forever

    def register_dynamic_tool(self, name, description, schema, handler) -> None:
        assert description
        assert schema == {}
        assert callable(handler)
        self.tools.append(name)

    async def connect(self) -> None:
        if self._connect_error is not None:
            raise self._connect_error

    async def attach_thread(self, thread_id: str) -> None:
        if self._connect_error is not None:
            raise self._connect_error
        self.attached.append(thread_id)
        self.thread_id = thread_id

    async def stream_turn(
        self,
        _prompt: str,
        *,
        timeout_seconds: float,
    ) -> AsyncIterator[str]:
        assert timeout_seconds > 0
        delivered = list(self._events)
        while True:
            for event in delivered:
                await asyncio.sleep(0.01)
                yield event
            if not self._forever:
                break
            delivered = ["keep-going"]
        if self._stream_error is not None:
            # 先交付事件，再让连接失败：结果已经到手时不能丢掉它。
            raise self._stream_error

    async def interrupt(self) -> None:
        self.interrupted += 1

    async def close(self) -> None:
        self.closed += 1


def _install(
    monkeypatch: pytest.MonkeyPatch,
    session: _FakeSession,
) -> _FakeSession:
    monkeypatch.setattr(
        codex_tool_turn,
        "CodexAppServerSession",
        lambda _endpoint: session,
    )
    return session


async def _run(session: _FakeSession, **overrides: Any) -> str:
    kwargs: dict[str, Any] = {
        "endpoint": "https://sandbox.invalid",
        "prompt": "judge this batch",
        "cwd": "/migration/output/veadk",
        "tool_name": "reportEvaluation",
        "tool_description": "提交判定结果。",
        "tool_schema": {},
        "handler": lambda _arguments: {"success": True},
        "has_result": lambda: False,
        "timeout_seconds": 5.0,
    }
    kwargs.update(overrides)
    return await run_tool_turn(**kwargs)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_run_tool_turn_stops_as_soon_as_the_result_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(
        monkeypatch,
        _FakeSession(["one", "two", "three"], thread_id="thread-live"),
    )
    seen: list[str] = []

    async def run() -> str:
        return await _run(
            session,
            event_sink=lambda event: seen.append(str(event)),
            has_result=lambda: len(seen) == 2,
        )

    assert await run() == "thread-live"
    # 结果到手就打断回合，后面的进展事件不再消费。
    assert seen == ["one", "two"]
    assert session.interrupted == 1
    assert session.closed == 1
    assert session.tools == ["reportEvaluation"]


@pytest.mark.asyncio
async def test_run_tool_turn_resumes_the_bound_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(monkeypatch, _FakeSession(["one"]))

    returned = await _run(session, thread_id="thread-bound", has_result=lambda: True)

    assert session.attached == ["thread-bound"]
    assert returned == "thread-bound"


@pytest.mark.asyncio
async def test_run_tool_turn_reports_a_transport_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(
        monkeypatch,
        _FakeSession([], connect_error=CodexAppServerError("app-server 未启动")),
    )

    with pytest.raises(ToolTurnUnavailable) as error:
        await _run(session)

    assert not isinstance(error.value, ToolTurnDeadlineExceeded)
    assert "app-server 未启动" in str(error.value)
    assert session.closed == 1


@pytest.mark.asyncio
async def test_run_tool_turn_reports_the_client_timeout_as_a_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(monkeypatch, _FakeSession([], stream_error=TimeoutError()))

    with pytest.raises(ToolTurnDeadlineExceeded):
        await _run(session)


@pytest.mark.asyncio
async def test_run_tool_turn_stops_at_the_wall_clock_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 事件一直在来（空闲超时永远不会触发），但已经超出调用方的窗口。
    session = _install(monkeypatch, _FakeSession(["progress"], forever=True))

    with pytest.raises(ToolTurnDeadlineExceeded):
        await _run(session, timeout_seconds=0.05)

    assert session.interrupted == 1
    assert session.closed == 1


@pytest.mark.asyncio
async def test_run_tool_turn_registers_every_tool_it_is_given(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(monkeypatch, _FakeSession(["one"], thread_id="thread-live"))

    await _run(
        session,
        extra_tools=(
            DynamicTool(
                name="askUser",
                description="提问。",
                schema={},
                handler=lambda _arguments: "answered",
            ),
        ),
        idle_timeout_seconds=30.0,
    )

    assert session.tools == ["reportEvaluation", "askUser"]


@pytest.mark.asyncio
async def test_run_tool_turn_does_not_charge_host_waiting_to_the_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """等用户回答的时间不算 Codex 的工作时间，不能因为等待就中断回合。"""
    session = _install(monkeypatch, _FakeSession(["progress"], forever=True))
    waited = [0.0]
    seen: list[str] = []

    def has_result() -> bool:
        seen.append("check")
        # 第一个事件之后才「回答」，这样等待发生在回合进行中。
        return len(seen) > 1

    waited[0] = 5.0
    thread = await _run(
        session,
        has_result=has_result,
        timeout_seconds=0.05,
        host_wait_seconds=lambda: waited[0],
    )
    assert thread == session.thread_id

    # 同一个回合如果不扣除等待时间，就会撞上墙钟预算。
    other = _install(monkeypatch, _FakeSession(["progress"], forever=True))
    with pytest.raises(ToolTurnDeadlineExceeded):
        await _run(other, timeout_seconds=0.05)


@pytest.mark.asyncio
async def test_run_tool_turn_keeps_a_result_delivered_before_the_stream_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(
        monkeypatch,
        _FakeSession(
            ["one"],
            stream_error=CodexAppServerError("连接中断"),
            thread_id="thread-delivered",
        ),
    )
    seen: list[str] = []

    async def run() -> str:
        return await _run(
            session,
            event_sink=lambda event: seen.append(str(event)),
            has_result=lambda: bool(seen),
        )

    assert await run() == "thread-delivered"
    assert session.interrupted == 1
