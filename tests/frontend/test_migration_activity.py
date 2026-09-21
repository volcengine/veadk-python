# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import asyncio
import json

import pytest

from veadk.cli.codex_app_server import CodexAppServerEvent

from frontend.server.migration.activity import AnalysisActivityLog
from frontend.server.migration.service import _parse_activity_log

TASK_ID = "migration-v1-" + "1" * 32


class Recorder:
    """A flush target that keeps every payload it was asked to write."""

    def __init__(self, *, fail: bool = False) -> None:
        self.writes: list[bytes] = []
        self.fail = fail

    def __call__(self, content: bytes) -> None:
        if self.fail:
            raise RuntimeError("sandbox write failed")
        self.writes.append(content)

    def items(self, attempt: int = 1, *, phase: str = "analysis"):
        content = self.writes[-1] if self.writes else b""
        return _parse_activity_log(content, attempt, phase=phase)


def log_with(
    *events: CodexAppServerEvent, **kwargs
) -> tuple[AnalysisActivityLog, Recorder]:
    recorder = Recorder(**kwargs)
    log = AnalysisActivityLog(recorder, flush_seconds=0.01)
    for event in events:
        log.record(event)
    log.flush()
    return log, recorder


def test_app_server_events_become_the_items_the_page_renders() -> None:
    _, recorder = log_with(
        CodexAppServerEvent(
            kind="thinking",
            item_id="reason-1",
            item_type="reasoning",
            status="completed",
            text="先确认项目结构。",
        ),
        CodexAppServerEvent(
            kind="tool",
            item_id="cmd-1",
            item_type="commandExecution",
            status="completed",
            arguments={"command": "ls -la"},
            response={"output": "main.py\nrequirements.txt", "exitCode": 0},
        ),
        CodexAppServerEvent(
            kind="commentary",
            item_id="msg-1",
            item_type="agentMessage",
            phase="commentary",
            status="completed",
            text="正在读取入口文件。",
        ),
        CodexAppServerEvent(
            kind="plan",
            turn_id="turn-1",
            status="running",
            response=[
                {"step": "读取项目结构", "status": "completed"},
                {"step": "确认框架", "status": "inProgress"},
                {"step": "产出结论", "status": "pending"},
            ],
        ),
        CodexAppServerEvent(
            kind="tool",
            item_id="search-1",
            item_type="webSearch",
            status="completed",
            arguments={"query": "dify app entry"},
        ),
    )

    items = recorder.items()
    assert [(item["kind"], item["status"]) for item in items] == [
        ("reasoning", "completed"),
        ("command", "completed"),
        ("message", "completed"),
        ("plan", "running"),
        ("command", "completed"),
    ]
    assert items[0]["detail"] == "先确认项目结构。"
    assert items[1]["tool"]["input"] == {"command": "ls -la"}
    assert items[1]["tool"]["output"] == "main.py\nrequirements.txt"
    assert items[1]["tool"]["exitCode"] == 0
    assert items[2]["detail"] == "正在读取入口文件。"
    assert items[3]["plan"] == [
        {"text": "读取项目结构", "status": "completed"},
        {"text": "确认框架", "status": "in_progress"},
        {"text": "产出结论", "status": "pending"},
    ]
    assert items[4]["tool"]["input"] == {"query": "dify app entry"}


def test_live_deltas_grow_one_item_instead_of_piling_up_items() -> None:
    log, recorder = log_with(
        CodexAppServerEvent(
            kind="tool",
            item_id="cmd-1",
            item_type="commandExecution",
            status="running",
            arguments={"command": "python -m app"},
        ),
        CodexAppServerEvent(
            kind="tool_output",
            item_id="cmd-1",
            item_type="commandExecution",
            status="running",
            text="line one\n",
        ),
        CodexAppServerEvent(
            kind="tool_output",
            item_id="cmd-1",
            item_type="commandExecution",
            status="running",
            text="line two\n",
        ),
        CodexAppServerEvent(
            kind="text",
            item_id="msg-1",
            item_type="agentMessage",
            status="done",
            text="分析",
        ),
        CodexAppServerEvent(
            kind="text",
            item_id="msg-1",
            item_type="agentMessage",
            status="done",
            text="完成",
        ),
    )

    items = recorder.items()
    assert [item["id"] for item in items] == ["analysis:1:cmd-1", "analysis:1:msg-1"]
    assert items[0]["tool"]["output"] == "line one\nline two"
    assert items[0]["status"] == "running"
    assert items[1]["detail"] == "分析完成"

    # A snapshot replaces whatever the deltas assembled.
    log.record(
        CodexAppServerEvent(
            kind="text_snapshot",
            item_id="msg-1",
            item_type="agentMessage",
            status="done",
            text="分析完成，建议迁移。",
        )
    )
    log.flush()
    assert recorder.items()[1]["detail"] == "分析完成，建议迁移。"


def test_events_without_page_content_are_not_recorded() -> None:
    log, recorder = log_with(
        CodexAppServerEvent(kind="usage", status="running"),
        CodexAppServerEvent(kind="thread_status", status="running"),
        CodexAppServerEvent(kind="thinking", item_id="reason-1", text=""),
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-1",
            item_type="dynamicToolCall",
            status="completed",
            name="reportRoute",
        ),
        CodexAppServerEvent(kind="plan", turn_id="turn-1", response=[]),
    )

    assert log.lines == []
    assert recorder.writes == []


def test_the_log_is_written_once_per_change_and_bounded() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, max_bytes=400, flush_seconds=0.01)

    log.flush()
    assert recorder.writes == []
    for index in range(20):
        log.record(
            CodexAppServerEvent(
                kind="thinking",
                item_id=f"reason-{index}",
                status="completed",
                text="x" * 40,
            )
        )
    log.flush()
    log.flush()
    assert len(recorder.writes) == 1
    content = recorder.writes[0].decode()
    assert len(content.encode()) <= 400
    ids = [json.loads(line)["item"]["id"] for line in content.splitlines()]
    assert ids[-1] == "reason-19"
    assert "reason-0" not in ids


def test_a_failed_write_never_fails_the_analysis() -> None:
    log = AnalysisActivityLog(Recorder(fail=True), flush_seconds=0.01)
    log.record(CodexAppServerEvent(kind="thinking", item_id="r", text="thinking"))

    log.close()


@pytest.mark.asyncio
async def test_the_timer_writes_progress_while_the_turn_runs() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.1)
    log.record(CodexAppServerEvent(kind="thinking", item_id="r", text="thinking"))
    flusher = asyncio.create_task(log.run())
    try:
        for _ in range(50):
            if recorder.writes:
                break
            await asyncio.sleep(0.02)
        assert recorder.writes
    finally:
        flusher.cancel()
        with pytest.raises(asyncio.CancelledError):
            await flusher
