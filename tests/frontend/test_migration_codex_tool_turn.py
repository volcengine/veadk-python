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
from veadk.cli.codex_app_server import CodexAppServerError, CodexAppServerSession


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
        turn_id: str = "",
        settled_turn: dict[str, object] | None = None,
        settled_turns: list[dict[str, object]] | None = None,
        read_error: Exception | None = None,
    ) -> None:
        self.thread_id = thread_id
        self.active_turn_id = turn_id
        self.settled_turn = settled_turn
        self.settled_turns = list(settled_turns or [])
        self.read_error = read_error
        self.reads: list[str] = []
        self.cwd = ""
        self.model = ""
        self.interrupted = 0
        self.closed = 0
        self.lifecycle_requested = False
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
        emit_turn_lifecycle: bool = False,
    ) -> AsyncIterator[str]:
        assert timeout_seconds > 0
        self.lifecycle_requested = emit_turn_lifecycle
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

    async def read_turn(self, turn_id: str) -> dict[str, object] | None:
        self.reads.append(turn_id)
        if self.read_error is not None:
            raise self.read_error
        if self.settled_turns:
            return (
                self.settled_turns.pop(0)
                if len(self.settled_turns) > 1
                else self.settled_turns[0]
            )
        return self.settled_turn

    def turn_lifecycle_event(self, kind: str, turn: dict[str, object]) -> object:
        # 用真实会话的投影，测的就是页面最终要读的那份读数。
        return CodexAppServerSession.turn_lifecycle_event(self, kind, turn)  # type: ignore[arg-type]

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
async def test_run_tool_turn_asks_for_the_turn_lifecycle_so_the_page_can_report_cost(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(monkeypatch, _FakeSession(["one"]))

    await _run(session, has_result=lambda: True)

    # 场景：迁移的 app-server 回合不是 Studio 任务回合，默认拿不到回合生命周期事件，
    # 页面就没有本轮耗时/模型可报。既然迁移页要和智能构建报同样的读数，这个 helper
    # 必须显式索取它们。
    assert session.lifecycle_requested is True


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


@pytest.mark.asyncio
async def test_run_tool_turn_settles_a_turn_that_ended_on_its_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_tool_turn, "_TURN_SETTLE_SECONDS", 0)
    session = _install(
        monkeypatch,
        _FakeSession(
            ["one", "two"],
            turn_id="turn-9",
            # 我们收下结果后要求打断，codex 记的就是 interrupted，耗时是它自己的。
            settled_turn={
                "id": "turn-9",
                "status": "interrupted",
                "startedAt": 1_000,
                "completedAt": 9_000,
                "model": "codex-mini",
            },
        ),
    )
    session.model = "codex-mini"
    settled: list[object] = []

    await _run(
        session,
        event_sink=settled.append,
        has_result=lambda: True,
    )

    # 结果一到手就打断的回合没有 turn_completed：回读这一轮补一条结算，页面才有
    # 本轮耗时/模型可报（智能构建正是靠这条事件显示读数的）。
    lifecycle = [
        event for event in settled if getattr(event, "kind", "") == "turn_completed"
    ]
    assert session.reads == ["turn-9"]
    assert len(lifecycle) == 1
    assert lifecycle[0].status == "completed"  # type: ignore[attr-defined]
    assert lifecycle[0].response["durationMs"] == 8_000  # type: ignore[attr-defined]
    assert lifecycle[0].response["model"] == "codex-mini"  # type: ignore[attr-defined]
    assert session.closed == 1


@pytest.mark.asyncio
async def test_run_tool_turn_reports_the_status_of_a_turn_it_had_to_stop(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_tool_turn, "_TURN_SETTLE_SECONDS", 0)
    session = _install(
        monkeypatch,
        _FakeSession(
            ["one"],
            turn_id="turn-9",
            settled_turn={"id": "turn-9", "status": "interrupted"},
        ),
    )
    settled: list[object] = []

    # 没拿到结果、又是被窗口掐停的：读数照报，但状态是 codex 记的那个。
    await _run(session, event_sink=settled.append, has_result=lambda: False)

    lifecycle = [
        event for event in settled if getattr(event, "kind", "") == "turn_completed"
    ]
    assert lifecycle[0].status == "interrupted"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_tool_turn_waits_for_a_still_running_turn_to_settle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(codex_tool_turn, "_TURN_SETTLE_SECONDS", 0)
    session = _install(
        monkeypatch,
        _FakeSession(
            ["one"],
            turn_id="turn-9",
            settled_turns=[
                {"id": "turn-9", "status": "inProgress"},
                {
                    "id": "turn-9",
                    "status": "completed",
                    "startedAt": 100,
                    "completedAt": 1_100,
                },
            ],
        ),
    )
    settled: list[object] = []

    await _run(session, event_sink=settled.append, has_result=lambda: True)

    # 打断和状态落定之间有竞态：还在跑就再读一次，而不是报一个没有终态的读数。
    lifecycle = [
        event for event in settled if getattr(event, "kind", "") == "turn_completed"
    ]
    assert session.reads == ["turn-9", "turn-9"]
    assert lifecycle[0].response["durationMs"] == 1_000  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_tool_turn_never_fails_on_settlement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _install(
        monkeypatch,
        _FakeSession(
            ["one"],
            turn_id="turn-9",
            read_error=CodexAppServerError("连接已断开"),
        ),
    )
    settled: list[object] = []

    returned = await _run(session, event_sink=settled.append, has_result=lambda: True)

    # 读数是装饰：回读失败不能把已经拿到结果的回合变成失败。
    assert returned == "thread-1"
    assert [
        event for event in settled if getattr(event, "kind", "") == "turn_completed"
    ] == []
    assert session.closed == 1
