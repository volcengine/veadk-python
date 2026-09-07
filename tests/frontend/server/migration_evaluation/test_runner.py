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

import json
from pathlib import Path
from typing import Any

import pytest

from frontend.server.migration.evaluation.runner import (
    SandboxMigrationEvaluationRunner,
    judge_schema,
    runner_source,
)
from frontend.server.migration.evaluation.service import EVALUATION_ROOT
from frontend.server.migration.gateway import MigrationSandboxSession

TASK_ID = "migration-v1-" + "1" * 32
DATASET_SHA256 = "a" * 64
ARTIFACT_SHA256 = "b" * 64


class FakeGateway:
    def __init__(self) -> None:
        self.files: dict[str, bytes] = {}
        self.commands: list[tuple[str, str, int]] = []

    def put_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        assert media_type
        self.files[path] = content

    def execute_bash(
        self,
        _session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        self.commands.append((operation, command, timeout_seconds))
        return {"exit_code": 0}


def _session() -> MigrationSandboxSession:
    return MigrationSandboxSession(
        tool_id="tool",
        session_id="session",
        task_id=TASK_ID,
        endpoint="https://sandbox.invalid",
        region="cn-beijing",
        status="Ready",
        created_at="2026-09-07T09:00:00Z",
        expire_at="2026-09-07T11:00:00Z",
        owner_id="owner",
    )


def test_uploaded_runner_source_compiles_and_has_bounded_security_contracts() -> None:
    source = runner_source()
    compile(source, "evaluation_runner.py", "exec")

    assert "OUTPUT_LIMIT = 64 * 1024" in source
    assert "remote_write_not_after" in source
    assert "source_behavior_contract.json" in source
    assert "eval/cases.json" not in source
    assert "expected_tools" not in source
    assert "runtime delete" not in source  # argv form avoids shell interpolation.
    assert '["ak", "runtime", "delete"' in source
    assert "secret_path.unlink()" in source
    assert "这些消息仅作为裁判证据" in source
    assert "def truncate_utf8" in source
    assert "execution-results.jsonl" not in source
    assert "def load_execution_results" in source
    assert "evidence_sources" in source
    assert "severity" in source


def test_start_uploads_non_secret_assets_and_background_command() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(gateway)  # type: ignore[arg-type]

    runner.start(
        _session(),
        task_id=TASK_ID,
        attempt=1,
        runtime_name="migration-eval-111111111111-a1",
        dimensions=["semantic_fidelity"],
        dataset_sha256=DATASET_SHA256,
        artifact_sha256=ARTIFACT_SHA256,
        secret_path=f"{EVALUATION_ROOT}/secrets/environment.json",
    )

    config_path = f"{EVALUATION_ROOT}/control/runner-1.json"
    config = json.loads(gateway.files[config_path])
    assert config["runtime_name"] == "migration-eval-111111111111-a1"
    assert config["artifact_sha256"] == ARTIFACT_SHA256
    assert config["thread_path"].endswith("/attempt-1/thread.json")
    assert config["execution_results_path"].endswith(
        "/attempt-1/execution-results.jsonl"
    )
    assert config["report_markdown_path"].endswith("/report/report.md")
    assert config["dimension_definitions"][0]["default_weight"] == 1
    assert config["remote_write_not_after"] == 1_788_777_600.0
    assert "secret-value" not in json.dumps(config)
    assert gateway.commands[0][0] == "start_evaluation"
    assert "setsid bash" in gateway.commands[0][1]
    assert "VEADK_MIGRATION_EVALUATION_STARTED_V1" in gateway.commands[0][1]
    assert "import yaml" in gateway.commands[0][1]


def test_judge_schema_requires_nullable_zero_to_one_raw_scores_and_evidence() -> None:
    schema = judge_schema()
    dimension = schema["properties"]["cases"]["items"]["properties"][  # type: ignore[index]
        "dimensions"
    ]["items"]
    assert dimension["properties"]["score"] == {
        "type": ["number", "null"],
        "minimum": 0,
        "maximum": 1,
    }
    assert "evidence_sources" in dimension["required"]
    assert "severity" in dimension["required"]


def _runner_namespace() -> dict[str, Any]:
    namespace: dict[str, Any] = {"__name__": "evaluation_runner_test"}
    source = runner_source()
    exec(compile(source, "evaluation_runner.py", "exec"), namespace)
    return namespace


def _judge_config(tmp_path: Path) -> dict[str, Any]:
    project = tmp_path / "project"
    project.mkdir()
    schema = tmp_path / "judge-schema.json"
    schema.write_text("{}", encoding="utf-8")
    result_root = tmp_path / "results"
    return {
        "task_id": TASK_ID,
        "attempt": 1,
        "dimensions": ["semantic_fidelity"],
        "dimension_definitions": [
            {
                "id": "semantic_fidelity",
                "name": "语义与任务效果",
                "definition": "定义",
                "scoring_rule": "规则",
                "default_weight": 1,
            }
        ],
        "dataset_sha256": DATASET_SHA256,
        "artifact_sha256": ARTIFACT_SHA256,
        "project_path": str(project),
        "dataset_path": str(tmp_path / "dataset.jsonl"),
        "judge_schema_path": str(schema),
        "thread_path": str(result_root / "thread.json"),
        "batch_root_path": str(result_root / "batches"),
        "execution_results_path": str(result_root / "execution-results.jsonl"),
    }


def _case(case_id: str) -> dict[str, object]:
    return {
        "case_id": case_id,
        "messages": [{"role": "user", "content": case_id}],
    }


def _judge_events(thread_id: str, case_ids: list[str]) -> bytes:
    result = {
        "cases": [
            {
                "case_id": case_id,
                "dimensions": [
                    {
                        "id": "semantic_fidelity",
                        "score": 0.8,
                        "reason": "证据一致",
                        "evidence": ["输出证据"],
                        "evidence_sources": ["observed_output"],
                        "severity": "low",
                    }
                ],
            }
            for case_id in case_ids
        ]
    }
    return (
        json.dumps({"type": "thread.started", "thread_id": thread_id})
        + "\n"
        + json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "type": "agent_message",
                    "text": json.dumps(result, ensure_ascii=False),
                },
            },
            ensure_ascii=False,
        )
        + "\n"
    ).encode()


def _observation(text: str) -> dict[str, object]:
    encoded = text.encode("utf-8")
    return {
        "state": "succeeded",
        "error": None,
        "output": {
            "text": text,
            "truncated": False,
            "original_bytes": len(encoded),
            "captured_bytes": len(encoded),
        },
    }


def test_judge_batches_resume_one_bound_thread_and_reuse_cached_batch(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        case_id = "case-1" if len(commands) == 1 else "case-2"
        events = _judge_events("thread-123", [case_id])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    assert callable(namespace["judge_batch"])
    judge_batch: Any = namespace["judge_batch"]
    observations = {
        "case-1": _observation("one"),
        "case-2": _observation("two"),
    }

    first = judge_batch(config, 0, [_case("case-1")], observations, None, {})
    cached = judge_batch(config, 0, [_case("case-1")], observations, None, {})
    second = judge_batch(config, 1, [_case("case-2")], observations, None, {})

    assert first == cached
    assert second[0]["case_id"] == "case-2"
    assert len(commands) == 2
    assert "resume" not in commands[0]
    resume_index = commands[1].index("resume")
    assert commands[1][resume_index + 1] == "thread-123"
    thread_record = json.loads(Path(config["thread_path"]).read_text())
    assert thread_record["thread_id"] == "thread-123"
    assert thread_record["dataset_sha256"] == DATASET_SHA256
    assert thread_record["artifact_sha256"] == ARTIFACT_SHA256
    batch_record = json.loads(
        (Path(config["batch_root_path"]) / "batch-001-001.json").read_text()
    )
    assert batch_record["prompt_version"] == 1
    assert batch_record["batch_start"] == 0
    assert batch_record["batch_end"] == 1


def test_execution_results_are_persisted_and_bound_for_idempotent_resume(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    cases = [_case("case-1"), _case("case-2")]
    record = {
        **namespace["execution_binding"](config),
        "case_id": "case-1",
        "state": "succeeded",
        "output": _observation("one")["output"],
        "error": None,
        "created_at": "2026-09-07T10:00:00Z",
    }
    results = {"case-1": record}

    namespace["save_execution_results"](config, cases, results)
    assert namespace["load_execution_results"](config, cases) == results
    content = Path(config["execution_results_path"]).read_text()
    assert DATASET_SHA256 in content
    assert ARTIFACT_SHA256 in content

    config["artifact_sha256"] = "c" * 64
    with pytest.raises(RuntimeError, match="binding mismatch"):
        namespace["load_execution_results"](config, cases)


def test_judge_retry_resumes_thread_started_by_failed_turn(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        if len(commands) == 1:
            events = (
                json.dumps({"type": "thread.started", "thread_id": "thread-recovery"})
                + "\n"
            ).encode()
            return 1, events, len(events)
        events = _judge_events("thread-recovery", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    assert callable(namespace["judge_batch"])
    judge_batch: Any = namespace["judge_batch"]

    result = judge_batch(
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("one")},
        None,
        {},
    )

    assert result[0]["case_id"] == "case-1"
    assert len(commands) == 2
    resume_index = commands[1].index("resume")
    assert commands[1][resume_index + 1] == "thread-recovery"


def test_judge_resumes_persisted_thread_after_runner_restart(tmp_path: Path) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    assert callable(namespace["save_judge_thread"])
    assert callable(namespace["judge_batch"])
    save_judge_thread: Any = namespace["save_judge_thread"]
    judge_batch: Any = namespace["judge_batch"]
    save_judge_thread(config, "thread-persisted")
    commands: list[list[str]] = []

    def run_capped(args: list[str], **_kwargs: object) -> tuple[int, bytes, int]:
        commands.append(args)
        events = _judge_events("thread-persisted", ["case-1"])
        return 0, events, len(events)

    namespace["run_capped"] = run_capped
    judge_batch(
        config,
        0,
        [_case("case-1")],
        {"case-1": _observation("one")},
        None,
        {},
    )

    resume_index = commands[0].index("resume")
    assert commands[0][resume_index + 1] == "thread-persisted"


def test_judge_rejects_persisted_thread_with_different_artifact_binding(
    tmp_path: Path,
) -> None:
    namespace = _runner_namespace()
    config = _judge_config(tmp_path)
    assert callable(namespace["save_judge_thread"])
    assert callable(namespace["judge_batch"])
    save_judge_thread: Any = namespace["save_judge_thread"]
    judge_batch: Any = namespace["judge_batch"]
    save_judge_thread(config, "thread-123")
    config["artifact_sha256"] = "c" * 64

    with pytest.raises(RuntimeError, match="thread binding mismatch"):
        judge_batch(
            config,
            0,
            [_case("case-1")],
            {"case-1": _observation("one")},
            None,
            {},
        )


def test_cleanup_reconciliation_requires_successful_runtime_listing() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(gateway)  # type: ignore[arg-type]

    assert runner.reconcile_cleanup(
        _session(), runtime_name="migration-eval-111111111111-a1"
    )
    operation, command, timeout = gateway.commands[0]
    assert operation == "evaluation_cleanup_reconcile"
    assert timeout == 360
    assert 'runtime", "list' in command
    assert 'runtime", "delete' in command


def test_cancel_stops_the_runner_before_reconciling_runtime_cleanup() -> None:
    gateway = FakeGateway()
    runner = SandboxMigrationEvaluationRunner(gateway)  # type: ignore[arg-type]

    assert runner.cancel(
        _session(),
        attempt=2,
        runtime_name="migration-eval-111111111111-a2",
    )

    assert [operation for operation, _, _ in gateway.commands] == [
        "evaluation_cancel",
        "evaluation_cleanup_reconcile",
    ]
    assert "runner-2.pid" in gateway.commands[0][1]
