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


def test_the_delivery_turn_shows_the_studio_tool_it_called() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.01, include_dynamic_tools=True)

    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-1",
            item_type="dynamicToolCall",
            status="in_progress",
            name="publishArtifact",
            arguments={"path": "migration-result.zip"},
        )
    )
    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-1",
            item_type="dynamicToolCall",
            status="completed",
            name="publishArtifact",
            arguments={"path": "migration-result.zip"},
            response={
                "success": True,
                "contentItems": [
                    {
                        "type": "inputText",
                        "text": "产物已核对：path=migration-result.zip sha256=abc size=18。",
                    }
                ],
            },
        )
    )
    log.flush()

    items = recorder.items(phase="delivery")
    assert len(items) == 1
    assert items[0]["id"] == "delivery:1:tool-1"
    assert items[0]["kind"] == "command"
    assert items[0]["title"] == "已拉取迁移产物并核对字节"
    assert items[0]["status"] == "completed"
    assert items[0]["tool"]["input"] == {"path": "migration-result.zip"}
    assert items[0]["tool"]["output"].startswith("产物已核对：")
    assert "error" not in items[0]["tool"]


def test_a_rejected_delivery_verdict_is_rendered_as_the_failure_it_is() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.01, include_dynamic_tools=True)

    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-2",
            item_type="dynamicToolCall",
            status="completed",
            name="reportDelivery",
            arguments={"state": "succeeded_with_warnings"},
            response={
                "success": False,
                "contentItems": [
                    {
                        "type": "inputText",
                        "text": "这次交付的 state 已经确定为 succeeded，请按沙箱里的交付证据重新调用。",
                    }
                ],
            },
        )
    )
    log.flush()

    items = recorder.items(phase="delivery")
    assert items[0]["title"] == "提交交付结论未完成"
    assert items[0]["tool"]["error"].startswith("这次交付的 state 已经确定为 succeeded")
    assert "output" not in items[0]["tool"]


def test_an_unknown_studio_tool_still_gets_a_readable_row() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.01, include_dynamic_tools=True)

    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-3",
            item_type="dynamicToolCall",
            status="completed",
            name="studio_write_artifact",
        )
    )
    log.flush()

    items = recorder.items(phase="delivery")
    assert items[0]["title"] == "已调用工具 studio_write_artifact"
    assert items[0]["tool"]["name"] == "已调用工具 studio_write_artifact"


def test_a_turn_that_ends_on_its_verdict_closes_the_studio_tool_row() -> None:
    """结算式收尾：Studio 拿到结论就打断回合，工具行不能停在「进行中」。"""
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.01, include_dynamic_tools=True)

    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="tool-4",
            item_type="dynamicToolCall",
            status="in_progress",
            name="reportDelivery",
            arguments={"state": "succeeded"},
        )
    )
    log.flush()
    assert recorder.items(phase="delivery")[0]["status"] == "running"

    log.complete_dynamic_tools()
    log.flush()

    row = recorder.items(phase="delivery")[0]
    assert row["status"] == "completed"
    assert row["title"] == "已提交交付结论"
    assert row["tool"]["input"] == {"state": "succeeded"}


def test_closing_studio_tool_rows_needs_the_delivery_flag() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder, flush_seconds=0.01)

    log.complete_dynamic_tools()

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


def test_rows_keep_the_timing_and_shape_the_shared_renderer_reads() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder.__call__, include_dynamic_tools=True)
    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="call_1",
            item_type="commandExecution",
            phase="commentary",
            duration_ms=2_400,
            status="completed",
            name="运行命令",
            arguments={
                "command": "cat migration-result.json",
                "commandActions": [{"type": "read", "path": "migration-result.json"}],
            },
            response={"status": "completed", "exitCode": 0, "output": "{}"},
        )
    )
    log.flush()

    item = recorder.items(phase="delivery")[0]
    # 页面用智能构建同一套行渲染工具项：itemType 决定原生图标与不截断的输出，
    # durationMs 是折叠头里的耗时，commandActions 让标签能说清这条命令在做什么。
    assert item["itemType"] == "commandExecution"
    assert item["durationMs"] == 2_400
    assert item["phase"] == "commentary"
    assert item["tool"]["input"] == {
        "command": "cat migration-result.json",
        "commandActions": [{"type": "read", "path": "migration-result.json"}],
    }
    assert item["tool"]["exitCode"] == 0
    assert item["tool"]["output"] == "{}"
    # 行名用 app-server 自己的名字，和智能构建同一套标签规则；迁移自己的状态标题
    # 只是 codex exec 那一侧（日志里没有 name）的兜底。
    assert item["tool"]["name"] == "运行命令"
    assert item["title"] == "命令执行完成"


def test_an_output_only_line_still_carries_the_call_it_belongs_to() -> None:
    _, recorder = log_with(
        CodexAppServerEvent(
            kind="tool",
            item_id="cmd-live",
            item_type="commandExecution",
            status="running",
            name="运行命令",
            arguments={"command": "python -m compileall output"},
        ),
        CodexAppServerEvent(
            kind="tool_output", item_id="cmd-live", text="Listing files"
        ),
    )

    item = recorder.items(phase="migration")[0]
    # 输出增量是这条 id 的最后一行，页面仍要能认出这是哪条命令：否则命令跑着的时候
    # 行名退回迁移的措辞、标签也算不出来，跑完又变回 app-server 的名字。
    assert item["tool"]["name"] == "运行命令"
    assert item["tool"]["input"] == {"command": "python -m compileall output"}
    assert item["tool"]["output"] == "Listing files"


def test_a_studio_tool_row_keeps_its_native_type_and_timing() -> None:
    recorder = Recorder()
    log = AnalysisActivityLog(recorder.__call__, include_dynamic_tools=True)
    log.record(
        CodexAppServerEvent(
            kind="tool",
            item_id="call_2",
            item_type="dynamicToolCall",
            duration_ms=90,
            status="completed",
            name="publishArtifact",
            arguments={"path": "migration-result.zip"},
            response={"success": True, "contentItems": [{"text": "产物已核对。"}]},
        )
    )
    log.flush()

    item = recorder.items(phase="delivery")[0]
    assert item["kind"] == "command"
    assert item["status"] == "completed"
    assert item["title"] == "已拉取迁移产物并核对字节"
    assert item["itemType"] == "dynamicToolCall"
    assert item["durationMs"] == 90
    assert item["id"] == "delivery:1:call_2"
