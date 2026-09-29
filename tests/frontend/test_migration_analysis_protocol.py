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

"""End-to-end checks for the in-Sandbox analysis protocol.

These tests execute the real shell command Studio ships to the Dev Sandbox against a
stub ``codex`` binary, so the extraction, protocol retry, and status transitions are
verified as a whole rather than as isolated units.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import time

import pytest

from frontend.server.migration import service as migration_service


def _contract(status: str = "recommendation_ready") -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": status,
        "attempt": 1,
        "input_sha256": "a" * 64,
        "summary": "项目分析摘要",
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


def _message(text: str, phase: str | None = None) -> dict[str, object]:
    item: dict[str, object] = {"type": "agent_message", "text": text}
    if phase is not None:
        item["phase"] = phase
    return {"type": "item.completed", "item": item}


class AnalysisSandbox:
    """One temporary Sandbox-like root driving the real analysis command."""

    def __init__(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = tmp_path / "migration"
        self.bin = tmp_path / "bin"
        self.bin.mkdir(parents=True, exist_ok=True)
        self.plan_path = tmp_path / "plan.json"
        monkeypatch.setenv("FAKE_CODEX_PLAN", str(self.plan_path))
        for name, value in (
            ("MIGRATION_ROOT", str(self.root)),
            ("_PROJECT_PATH", f"{self.root}/workspace/source"),
            ("_ANALYSIS_RESULT_PATH", f"{self.root}/analysis/route.json"),
            ("_ANALYSIS_PROMPT_PATH", f"{self.root}/analysis/prompt.md"),
            ("_ANALYSIS_RETRY_PROMPT_PATH", f"{self.root}/analysis/retry-prompt.md"),
            ("_ANALYSIS_SCHEMA_PATH", f"{self.root}/analysis/route-schema.json"),
            ("_ANALYSIS_STATUS_PATH", f"{self.root}/control/task-status.json"),
            (
                "_ANALYSIS_PROCESS_EXIT_PATH",
                f"{self.root}/diagnostics/analysis/process-exit.json",
            ),
            (
                "_ANALYSIS_EXTRACTION_DIAGNOSTICS_PATH",
                f"{self.root}/diagnostics/analysis/result-extraction.json",
            ),
        ):
            monkeypatch.setattr(migration_service, name, value)
        for relative in (
            "workspace/source",
            "analysis",
            "control",
            "diagnostics/analysis",
        ):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        Path(migration_service._ANALYSIS_PROMPT_PATH).write_text(
            "分析提示词", encoding="utf-8"
        )
        Path(migration_service._ANALYSIS_RETRY_PROMPT_PATH).write_text(
            "## 协议重试\n只输出 JSON", encoding="utf-8"
        )
        Path(migration_service._ANALYSIS_SCHEMA_PATH).write_text("{}", encoding="utf-8")
        self._install_stub()

    def _install_stub(self) -> None:
        stub = self.bin / "codex"
        stub.write_text(
            "#!/usr/bin/env python3\n"
            "import json, os, sys\n"
            "plan = json.load(open(os.environ['FAKE_CODEX_PLAN'], encoding='utf-8'))\n"
            "prompt = sys.stdin.read()\n"
            "events = plan['retry'] if '协议重试' in prompt else plan['first']\n"
            "if events is None:\n"
            "    raise SystemExit(3)\n"
            "for event in events:\n"
            "    print(json.dumps(event, ensure_ascii=False))\n",
            encoding="utf-8",
        )
        stub.chmod(0o755)

    def plan(self, *, first: object, retry: object = None) -> None:
        self.plan_path.write_text(
            json.dumps({"first": first, "retry": retry}, ensure_ascii=False),
            encoding="utf-8",
        )

    def run(self, attempt: int = 1) -> None:
        command = migration_service._start_analysis_command(
            "migration-v1-" + "b" * 32,
            attempt,
        )
        environment = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
        }
        completed = subprocess.run(
            ["bash", "-c", command],
            capture_output=True,
            text=True,
            env=environment,
            check=False,
        )
        assert completed.returncode == 0, completed.stderr

    def wait_for_status(self, timeout: float = 20.0) -> dict[str, object]:
        status_path = self.root / "control/task-status.json"
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if status_path.is_file():
                value = json.loads(status_path.read_text(encoding="utf-8"))
                if value.get("state") != "analyzing":
                    return value
            time.sleep(0.05)
        raise AssertionError("analysis status was never written")

    def route(self) -> dict[str, object] | None:
        path = self.root / "analysis/route.json"
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def extraction_diagnostics(self) -> dict[str, object] | None:
        path = Path(migration_service._ANALYSIS_EXTRACTION_DIAGNOSTICS_PATH + ".1")
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_survives_a_trailing_progress_update(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: the reported failure had a progress update as the last message."""
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    sandbox.plan(
        first=[
            _message("正在扫描项目结构", phase="commentary"),
            _message(json.dumps(_contract(), ensure_ascii=False)),
            _message("已完成步骤 2：确认迁移边界", phase="commentary"),
        ]
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "ready"
    assert sandbox.route() is not None
    assert sandbox.route()["status"] == "recommendation_ready"  # type: ignore[index]
    assert sandbox.extraction_diagnostics() == {
        "reason": "extracted",
        "answer_messages": 1,
        "commentary_messages": 2,
    }


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_recovers_a_fenced_result_and_a_needs_input_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    contract = _contract("needs_input")
    contract["questions"] = [{"id": "q1", "prompt": "请选择入口", "required": True}]
    sandbox.plan(
        first=[
            _message(
                "结论：\n```json\n"
                + json.dumps(contract, ensure_ascii=False)
                + "\n```\n以上。"
            )
        ]
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "needs_input"
    assert sandbox.route() is not None


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_retries_in_turn_when_the_first_reply_has_no_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    sandbox.plan(
        first=[_message("我完成了分析，但没有输出 JSON。")],
        retry=[_message(json.dumps(_contract(), ensure_ascii=False))],
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "ready"
    assert sandbox.route() is not None


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_reports_a_retryable_protocol_failure_after_both_attempts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    sandbox.plan(
        first=[_message("没有 JSON。")],
        retry=[_message("仍然没有 JSON。")],
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "failed"
    assert status["error"]["code"] == "MIGRATION_ANALYSIS_RESULT_MISSING"
    assert status["error"]["retryable"] is True
    assert sandbox.route() is None
    assert sandbox.extraction_diagnostics() == {
        "reason": "no_contract_object",
        "answer_messages": 1,
        "commentary_messages": 0,
    }


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_rejects_an_event_stream_without_any_agent_message(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    sandbox.plan(
        first=[{"type": "item.completed", "item": {"type": "reasoning", "text": "x"}}],
        retry=[{"type": "item.completed", "item": {"type": "reasoning", "text": "y"}}],
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "failed"
    assert status["error"]["code"] == "MIGRATION_ANALYSIS_RESULT_MISSING"
    assert sandbox.extraction_diagnostics()["reason"] == "no_agent_message"  # type: ignore[index]


@pytest.mark.skipif(
    shutil.which("setsid") is None or shutil.which("bash") is None,
    reason="the analysis protocol needs bash and setsid",
)
def test_analysis_ignores_a_result_object_without_the_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unrelated JSON object must not be mistaken for the analysis result."""
    sandbox = AnalysisSandbox(tmp_path, monkeypatch)
    sandbox.plan(
        first=[_message(json.dumps({"attempt": 1}, ensure_ascii=False))],
        retry=[_message(json.dumps(_contract("unsupported"), ensure_ascii=False))],
    )

    sandbox.run()

    status = sandbox.wait_for_status()
    assert status["state"] == "failed"
    assert status["error"]["code"] == "MIGRATION_ANALYSIS_UNSUPPORTED"
