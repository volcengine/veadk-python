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

"""Checks for the optional Codex app-server route-analysis path."""

from __future__ import annotations

import asyncio
import json
import threading
import time

import pytest

from frontend.server.migration import service as migration_service
from frontend.server.migration.analysis_input import AnalysisInputRegistry
from frontend.server.migration.analysis_contract import (
    RECOMMENDATION_KIND,
    UNSUPPORTED_KIND,
)
from frontend.server.migration.app_server import (
    MigrationAnalysisUnavailable,
    AnalysisRecorder,
    app_server_analysis_enabled,
)
from frontend.server.migration.gateway import MigrationSandboxSession
from frontend.server.migration.service import MigrationService


def _session() -> MigrationSandboxSession:
    return MigrationSandboxSession(
        tool_id="tool-dev",
        session_id="session-1",
        task_id="migration-v1-" + "c" * 32,
        endpoint="https://sandbox.invalid",
        region="cn-beijing",
        status="Ready",
        created_at="2099-01-01T00:00:00Z",
        expire_at="2099-01-01T01:00:00Z",
        owner_id="owner",
    )


def _contract(status: str = "recommendation_ready") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "attempt": 1,
        "input_sha256": "a" * 64,
        "summary": "摘要",
        "frameworks": [],
        "recommended": (
            None
            if status == "unsupported"
            else {"framework": "dify", "entry": None, "reason": "理由"}
        ),
        "entries": [],
        "boundary": {"include": [], "exclude": []},
        "assumptions": [],
        "questions": [],
        "warnings": [],
    }


class _Recorder:
    """Minimal service-side recorder for the app-server path."""

    def __init__(self) -> None:
        self.written: dict[str, object] = {}
        self.commands: list[str] = []

    def put_file(self, session, path, content, *, media_type):
        self.written[path] = json.loads(content)


class _Service(MigrationService):
    def __init__(self, recorder: _Recorder, *, marker: dict[str, object] | None = None):
        self._recorder = recorder
        self._analysis_drivers = {}
        self._analysis_input = AnalysisInputRegistry()
        self._marker = marker
        self._session_marker = marker

    def _put(self, session, path, content, *, media_type):
        self._recorder.put_file(session, path, content, media_type=media_type)

    def _execute(self, session, command, *, operation, timeout_seconds=120):
        self._recorder.commands.append(command)
        return {}

    def _session(self, task_id, owner_id):
        return _session()

    def _read_json(self, session, path, *, optional=False):
        return self._session_marker


def _wait_for_driver(service: MigrationService, *, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while service._analysis_drivers and time.monotonic() < deadline:
        time.sleep(0.01)
    assert not service._analysis_drivers, "分析后台驱动没有结束"


def test_app_server_analysis_is_enabled_by_default_and_can_be_pinned_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)
    assert app_server_analysis_enabled() is True

    monkeypatch.setenv("AGENTKIT_MIGRATION_APP_SERVER", "0")
    assert app_server_analysis_enabled() is False

    recorder = _Recorder()
    service = _Service(recorder)
    assert (
        service._start_app_server_analysis(
            _session(),
            prompt="分析",
            attempt=1,
            input_sha256="a" * 64,
        )
        is False
    )
    assert recorder.written == {}
    assert service._analysis_drivers == {}


def test_app_server_analysis_runs_on_a_background_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)
    recorded: dict[str, object] = {}
    release = threading.Event()

    async def _run(**kwargs: object) -> dict[str, object]:
        recorded.update(kwargs)
        await asyncio.to_thread(release.wait, 5)
        return _contract()

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)
    session = _session()

    assert (
        service._start_app_server_analysis(
            session,
            prompt="分析",
            attempt=1,
            input_sha256="a" * 64,
            model_id="doubao-test",
        )
        is True
    )

    # 上传请求立刻返回：此刻只有「正在分析」和租约，结果还没写。
    assert recorder.written[migration_service._ANALYSIS_STATUS_PATH] == {
        "schema_version": 1,
        "attempt": 1,
        "state": "analyzing",
        "message": "正在分析项目框架、入口与迁移边界",
    }
    lease = recorder.written[migration_service._ANALYSIS_DRIVER_PATH]
    assert lease["driver"] == "app-server"
    assert lease["state"] == "running"
    assert lease["attempt"] == 1
    assert migration_service._ANALYSIS_RESULT_PATH not in recorder.written

    release.set()
    _wait_for_driver(service)

    assert recorded["attempt"] == 1
    assert recorded["model"] == "doubao-test"
    assert recorded["cwd"] == migration_service._PROJECT_PATH
    # Studio owns the document shape now, so the turn is handed verified facts and a
    # place to report what happened instead of a strict schema to fill in.
    assert "schema" not in recorded
    assert recorded["detection"] == {
        "schema_version": 1,
        "files": {"count": 0, "listed": []},
        "documents": [],
        "candidates": [],
        "unreadable": [],
        "degraded": True,
        "degraded_reason": "detection_missing",
    }
    assert isinstance(recorded["diagnostics"], dict)
    assert recorder.written[migration_service._ANALYSIS_RESULT_PATH]["status"] == (
        "recommendation_ready"
    )
    assert recorder.written[migration_service._ANALYSIS_STATUS_PATH] == {
        "schema_version": 1,
        "attempt": 1,
        "state": "ready",
        "message": "项目分析完成，请确认迁移方式",
    }
    assert recorder.written[migration_service._ANALYSIS_DRIVER_PATH]["state"] == "done"


def test_app_server_analysis_persists_an_unsupported_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)

    async def _run(**_kwargs: object) -> dict[str, object]:
        return _contract("unsupported")

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)

    assert service._start_app_server_analysis(
        _session(), prompt="分析", attempt=1, input_sha256="a" * 64
    )
    _wait_for_driver(service)

    assert recorder.written[migration_service._ANALYSIS_STATUS_PATH] == {
        "schema_version": 1,
        "attempt": 1,
        "state": "failed",
        "message": "当前项目不适用于已支持的迁移方式",
        "error": {
            "code": "MIGRATION_ANALYSIS_UNSUPPORTED",
            "message": "项目分析未找到可执行的迁移方式。",
            "retryable": False,
        },
    }


def test_app_server_analysis_falls_back_to_the_scripted_driver(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)

    async def _run(**_kwargs: object) -> dict[str, object]:
        raise MigrationAnalysisUnavailable(
            "无法连接 AgentKit Session 中的 Codex 服务。"
        )

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)
    session = _session()

    assert service._start_app_server_analysis(
        session, prompt="分析", attempt=1, input_sha256="a" * 64
    )
    _wait_for_driver(service)

    assert recorder.commands[0] == migration_service._clear_analysis_status_command()
    assert "ANALYSIS_STARTED_V1" in recorder.commands[1]
    assert recorder.written[migration_service._ANALYSIS_DRIVER_PATH]["driver"] == (
        "codex-exec"
    )


@pytest.mark.parametrize(
    "marker",
    [
        {"driver": "codex-exec", "state": "running", "attempt": 1, "heartbeat_at": 0.0},
        {"driver": "app-server", "state": "done", "attempt": 1, "heartbeat_at": 0.0},
    ],
)
def test_analysis_recovery_ignores_turns_that_are_not_a_stalled_app_server(
    marker: dict[str, object],
) -> None:
    recorder = _Recorder()
    service = _Service(recorder, marker=marker)

    assert (
        service.recover_stalled_analysis("migration-v1-" + "c" * 32, "owner") is False
    )
    assert recorder.commands == []


def test_analysis_recovery_waits_for_a_fresh_lease() -> None:
    recorder = _Recorder()
    service = _Service(
        recorder,
        marker={
            "driver": "app-server",
            "state": "running",
            "attempt": 1,
            "heartbeat_at": time.time(),
        },
    )

    assert (
        service.recover_stalled_analysis("migration-v1-" + "c" * 32, "owner") is False
    )
    assert recorder.commands == []


def test_a_stalled_app_server_analysis_is_handed_back_to_the_script() -> None:
    recorder = _Recorder()
    service = _Service(
        recorder,
        marker={
            "driver": "app-server",
            "state": "running",
            "attempt": 1,
            "heartbeat_at": time.time() - 10_000,
        },
    )

    assert service.recover_stalled_analysis("migration-v1-" + "c" * 32, "owner") is True
    assert recorder.commands[0] == migration_service._clear_analysis_status_command()
    assert "ANALYSIS_STARTED_V1" in recorder.commands[1]


def test_a_live_in_process_worker_blocks_analysis_recovery() -> None:
    class _Alive:
        @staticmethod
        def is_alive() -> bool:
            return True

    recorder = _Recorder()
    service = _Service(
        recorder,
        marker={
            "driver": "app-server",
            "state": "running",
            "attempt": 1,
            "heartbeat_at": time.time() - 10_000,
        },
    )
    session = _session()
    service._analysis_drivers[(session.session_id, 1)] = _Alive()

    assert (
        service.recover_stalled_analysis("migration-v1-" + "c" * 32, "owner") is False
    )
    assert recorder.commands == []


def test_recorder_fills_in_what_the_model_did_not_shape() -> None:
    """A judgement with only a summary still lands a usable recommendation."""
    recorder = AnalysisRecorder(
        attempt=3,
        input_sha256="b" * 64,
        detection={
            "schema_version": 1,
            "files": {"count": 2, "listed": ["md5.txt", "template.yml"]},
            "documents": [],
            "candidates": [
                {
                    "id": "dify",
                    "confidence": "high",
                    "evidence": [
                        {"path": "template.yml", "line": 5, "reason": "kind: app"},
                        {"path": "template.yml", "line": 8, "reason": "workflow.graph"},
                    ],
                }
            ],
            "unreadable": [],
            "degraded": False,
            "degraded_reason": "",
        },
    )

    accepted = recorder.handler(RECOMMENDATION_KIND)(
        {"summary": "这是一个 Dify 风格的工作流导出。", "frameworks": "dify"}
    )

    assert accepted.success is True
    assert recorder.kind == RECOMMENDATION_KIND
    assert recorder.result is not None
    assert recorder.result["status"] == "recommendation_ready"
    # Studio's own bookkeeping, not the model's.
    assert recorder.result["attempt"] == 3
    assert recorder.result["input_sha256"] == "b" * 64
    assert recorder.result["schema_version"] == 1
    # The verified candidate survives, and the unusable field was noted, not fatal.
    assert recorder.result["frameworks"][0]["id"] == "dify"
    assert recorder.result["recommended"]["framework"] == "dify"
    assert any("frameworks" in note for note in recorder.notes)
    assert recorder.refusals == []


def test_recorder_refuses_a_verdict_without_evidence_and_keeps_the_turn_alive() -> None:
    recorder = AnalysisRecorder(
        attempt=1,
        input_sha256="a" * 64,
        detection={
            "schema_version": 1,
            "files": {"count": 2, "listed": ["md5.txt", "template.yml"]},
            "documents": [],
            "candidates": [],
            "unreadable": [],
            "degraded": False,
            "degraded_reason": "",
        },
    )

    rejected = recorder.handler(UNSUPPORTED_KIND)(
        {"summary": "结构测试。", "evidence": []}
    )

    assert rejected.success is False
    assert "reportUnsupported" in rejected.text
    assert recorder.result is None
    assert recorder.refusals

    # A verdict citing a file the archive never had is refused too.
    unknown = recorder.handler(UNSUPPORTED_KIND)(
        {
            "summary": "这个项目里有完整的勒索行为链，无法安全迁移，建议用户先移除相关代码再新建迁移。",
            "evidence": [
                {"path": "missing.py", "line": 1, "reason": "加密并删除用户数据"},
                {"path": "template.yml", "line": 5, "reason": "同上"},
            ],
        }
    )
    assert unknown.success is False
    assert "missing.py" in unknown.text

    accepted = recorder.handler(UNSUPPORTED_KIND)(
        {
            "summary": "该项目只有两个文件且缺少任何可执行的 Agent 源码，无法恢复 Agent 行为，建议补充源码后新建迁移。",
            "evidence": [
                {"path": "template.yml", "line": 5, "reason": "只有导出的 DSL"},
                {"path": "md5.txt", "line": 1, "reason": "只有校验值"},
            ],
        }
    )
    assert accepted.success is True
    assert recorder.result is not None
    assert recorder.result["status"] == "unsupported"
    assert recorder.result["recommended"] is None
    # The evidence that justified the verdict stays visible on the page.
    assert any("template.yml:5" in warning for warning in recorder.result["warnings"])


def test_a_turn_that_delivers_nothing_still_produces_a_usable_conclusion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """模型没交付结论时不再把任务判死，也不再花一轮脚本驱动。"""
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)

    async def _run(**kwargs: object) -> dict[str, object] | None:
        diagnostics = kwargs["diagnostics"]
        assert isinstance(diagnostics, dict)
        diagnostics.update(
            {
                "accepted": False,
                "kind": "",
                "notes": [],
                "refusals": ["evidence:2 条可用"],
                "events": 42,
            }
        )
        return None

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)

    assert service._start_app_server_analysis(
        _session(), prompt="分析", attempt=1, input_sha256="a" * 64
    )
    _wait_for_driver(service)

    stored = recorder.written[migration_service._ANALYSIS_RESULT_PATH]
    assert stored["status"] == "recommendation_ready"
    assert "没有取得可用的模型分析结论" in stored["summary"]
    assert any("保守结论" in warning for warning in stored["warnings"])
    assert any("evidence" in warning for warning in stored["warnings"])
    assert recorder.written[migration_service._ANALYSIS_STATUS_PATH]["state"] == "ready"
    # The expensive scripted driver is not started for a model-layer miss.
    assert recorder.commands == []
    outcome = recorder.written[migration_service._ANALYSIS_OUTCOME_PATH]
    assert outcome["accepted"] is False
    assert outcome["events"] == 42


def test_app_server_analysis_asks_the_user_inside_the_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """一轮分析里先提问、再交付结果：用户回答不重跑分析。"""
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)
    recorded: dict[str, object] = {}
    delivered: dict[str, object] = {}
    questions = (
        {
            "id": "framework",
            "header": "目标框架",
            "question": "迁移到 langchain 还是 dify？",
            "options": [],
        },
    )

    async def _run(**kwargs: object) -> dict[str, object]:
        recorded.update(kwargs)
        ask = kwargs["questioner"]
        delivered["answers"] = await ask(questions)  # type: ignore[operator]
        wait = kwargs["host_wait_seconds"]
        delivered["waited"] = wait()  # type: ignore[operator]
        return _contract()

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)
    session = _session()
    assert (
        service._start_app_server_analysis(
            session,
            prompt="分析",
            attempt=1,
            input_sha256="a" * 64,
            timeout_seconds=12.0,
        )
        is True
    )

    pending = None
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        pending = service._analysis_input.pending(session.session_id)
        if pending is not None:
            break
        time.sleep(0.01)
    assert pending is not None, "分析回合没有把问题交给页面"
    assert (
        service._analysis_input.resolve(
            session.session_id,
            request_id=pending.request_id,
            answers={"framework": ("dify",)},
        )
        is True
    )
    _wait_for_driver(service)

    assert delivered["answers"] == {"framework": ("dify",)}
    # 等用户的时间既不计入模型预算，也不能让客户端的空闲计时器提前取消回合。
    assert float(delivered["waited"]) > 0.0  # type: ignore[arg-type]
    assert recorded["idle_timeout_seconds"] == (
        12.0
        + migration_service._ANALYSIS_INPUT_WINDOW_SECONDS
        + migration_service._ANALYSIS_INPUT_IDLE_MARGIN_SECONDS
    )
    assert service._analysis_input.pending(session.session_id) is None
    assert recorder.written[migration_service._ANALYSIS_STATUS_PATH]["state"] == "ready"


def test_app_server_analysis_keeps_going_when_nobody_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """没人回答时回合继续，让 Codex 用 needs_input 交付问题，而不是挂住。"""
    monkeypatch.delenv("AGENTKIT_MIGRATION_APP_SERVER", raising=False)
    monkeypatch.setattr(migration_service, "_ANALYSIS_INPUT_WINDOW_SECONDS", 0.05)
    delivered: dict[str, object] = {}
    questions = (
        {
            "id": "framework",
            "header": "目标框架",
            "question": "迁移到 langchain 还是 dify？",
            "options": [],
        },
    )

    async def _run(**kwargs: object) -> dict[str, object]:
        ask = kwargs["questioner"]
        delivered["answers"] = await ask(questions)  # type: ignore[operator]
        return _contract("needs_input")

    monkeypatch.setattr(migration_service, "run_route_analysis", _run)

    recorder = _Recorder()
    service = _Service(recorder)
    session = _session()
    assert (
        service._start_app_server_analysis(
            session,
            prompt="分析",
            attempt=1,
            input_sha256="a" * 64,
        )
        is True
    )
    _wait_for_driver(service)

    assert delivered["answers"] is None
    assert service._analysis_input.pending(session.session_id) is None
    assert (
        recorder.written[migration_service._ANALYSIS_STATUS_PATH]["state"]
        == "needs_input"
    )
