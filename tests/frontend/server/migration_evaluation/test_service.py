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
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

import pytest

from frontend.server.migration.evaluation.models import (
    EvaluationDatasetBody,
    ResumeEvaluationBody,
)
from frontend.server.migration.evaluation.repository import EvaluationAssetMetadata
from frontend.server.migration.evaluation.service import (
    EVALUATION_DATASET_MANIFEST_PATH,
    EVALUATION_REPORT_PATH,
    EVALUATION_RUNNER_DIAGNOSTICS_ROOT,
    EVALUATION_SECRET_PATH,
    EVALUATION_STATUS_PATH,
    MigrationEvaluationService,
)
from frontend.server.migration.gateway import (
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)
from frontend.server.migration.service import MigrationError

TASK_ID = "migration-v1-" + "1" * 32
NOW = datetime(2026, 9, 7, 10, tzinfo=timezone.utc).timestamp()
DIMENSIONS = [
    "semantic_fidelity",
    "output_contract",
    "workflow_tool_fidelity",
]
ARTIFACT_SHA256 = "b" * 64


class FakeGateway:
    def __init__(self, *, remaining: int = 3600) -> None:
        self.session = MigrationSandboxSession(
            tool_id="tool",
            session_id="session",
            task_id=TASK_ID,
            endpoint="https://sandbox.invalid",
            region="cn-beijing",
            status="Ready",
            created_at="2026-09-07T09:00:00Z",
            expire_at=datetime.fromtimestamp(NOW + remaining, timezone.utc)
            .isoformat()
            .replace("+00:00", "Z"),
            owner_id="owner",
        )
        self.files: dict[str, bytes] = {}
        self.commands: list[tuple[str, str]] = []
        self.find_session_calls = 0

    def find_session(self, task_id: str, owner_id: str) -> MigrationSandboxSession:
        assert task_id == TASK_ID and owner_id == "owner"
        self.find_session_calls += 1
        return self.session

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

    def get_file(
        self,
        _session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes:
        if path not in self.files:
            raise MigrationRemoteFileNotFound(path)
        content = self.files[path]
        assert len(content) <= max_bytes
        return content

    def execute_bash(
        self,
        _session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> dict[str, object]:
        assert timeout_seconds > 0
        self.commands.append((operation, command))
        return {"exit_code": 0}


class FakeMigration:
    def __init__(self) -> None:
        self.task: dict[str, object] = {
            "id": TASK_ID,
            "state": "awaiting_upload",
            "canUpload": True,
            "artifact": {"deployReady": False},
            "evaluation": {
                "enabled": True,
                "preset": "standard",
                "dimensions": DIMENSIONS,
            },
        }
        self.required: list[str] = []

    def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
        assert task_id == TASK_ID and owner_id == "owner"
        return self.task

    def artifact(self, task_id: str, owner_id: str) -> dict[str, object]:
        assert task_id == TASK_ID and owner_id == "owner"
        return {
            "artifact": {"sha256": ARTIFACT_SHA256},
            "environment": {"required": self.required},
        }


class FakeRepository:
    def __init__(self) -> None:
        self.assets: dict[tuple[str, str], tuple[EvaluationAssetMetadata, bytes]] = {}
        self.load_calls = 0

    def commit_dataset(self, **kwargs: Any) -> EvaluationAssetMetadata:
        metadata = EvaluationAssetMetadata(
            schema_version=1,
            kind="dataset",
            task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"],
            version_id=kwargs["version_id"],
            sha256=kwargs["sha256"],
            size=len(kwargs["content"]),
            created_at=kwargs["created_at"],
            case_count=kwargs["case_count"],
        )
        self.assets[("dataset", metadata.version_id)] = (metadata, kwargs["content"])
        return metadata

    def commit_report(self, **kwargs: Any) -> EvaluationAssetMetadata:
        metadata = EvaluationAssetMetadata(
            schema_version=1,
            kind="report",
            task_id=kwargs["task_id"],
            owner_id=kwargs["owner_id"],
            version_id=kwargs["version_id"],
            sha256=kwargs["sha256"],
            size=len(kwargs["content"]),
            created_at=kwargs["created_at"],
            attempt=kwargs["attempt"],
        )
        self.assets[("report", metadata.version_id)] = (metadata, kwargs["content"])
        return metadata

    def load(self, *, kind: str, version_id: str, **_kwargs: Any):
        self.load_calls += 1
        return self.assets[(kind, version_id)]


class FakeRunner:
    def __init__(self) -> None:
        self.starts: list[dict[str, object]] = []
        self.cleanup = True
        self.cleanup_calls: list[str] = []
        self.cancellations: list[dict[str, object]] = []

    def start(
        self,
        session: MigrationSandboxSession,
        *,
        task_id: str,
        attempt: int,
        runtime_name: str,
        dimensions: list[str],
        dataset_sha256: str,
        artifact_sha256: str,
        secret_path: str | None,
    ) -> None:
        assert session.task_id == task_id
        self.starts.append(
            {
                "task_id": task_id,
                "attempt": attempt,
                "runtime_name": runtime_name,
                "dimensions": dimensions,
                "dataset_sha256": dataset_sha256,
                "artifact_sha256": artifact_sha256,
                "secret_path": secret_path,
            }
        )

    def reconcile_cleanup(
        self,
        session: MigrationSandboxSession,
        *,
        runtime_name: str,
    ) -> bool:
        assert session.task_id == TASK_ID
        assert runtime_name
        self.cleanup_calls.append(runtime_name)
        return self.cleanup

    def cancel(
        self,
        session: MigrationSandboxSession,
        *,
        attempt: int,
        runtime_name: str | None,
    ) -> bool:
        assert session.task_id == TASK_ID
        self.cancellations.append({"attempt": attempt, "runtime_name": runtime_name})
        return self.cleanup


def _service(*, remaining: int = 3600):
    migration = FakeMigration()
    gateway = FakeGateway(remaining=remaining)
    repository = FakeRepository()
    runner = FakeRunner()
    service = MigrationEvaluationService(
        migration,  # type: ignore[arg-type]
        gateway,  # type: ignore[arg-type]
        repository=repository,
        runner=runner,
        clock=lambda: NOW,
    )
    return service, migration, gateway, repository, runner


def _body() -> EvaluationDatasetBody:
    return EvaluationDatasetBody.model_validate(
        {"cases": [{"caseId": "case-1", "userInput": "你好"}]}
    )


def _ready(migration: FakeMigration) -> None:
    migration.task = {
        **migration.task,
        "state": "succeeded",
        "canUpload": False,
        "artifact": {"deployReady": True},
    }


def test_dataset_save_is_idempotent_without_repository_read_back() -> None:
    service, _migration, gateway, repository, _runner = _service()

    first = service.put_dataset(TASK_ID, "owner", _body())
    second = service.put_dataset(TASK_ID, "owner", _body())

    assert first == second
    assert first["locked"] is True
    assert first["cases"] == [
        {
            "caseId": "case-1",
            "userInput": "你好",
            "priorMessages": [],
            "expectedOutcome": None,
            "criteria": [],
        }
    ]
    assert repository.load_calls == 0
    assert EVALUATION_STATUS_PATH not in gateway.files


def test_dataset_can_be_saved_after_upload_starts_before_evaluation() -> None:
    service, migration, _gateway, repository, _runner = _service()
    migration.task = {
        **migration.task,
        "state": "analyzing",
        "canUpload": False,
    }

    dataset = service.put_dataset(TASK_ID, "owner", _body())

    assert dataset["locked"] is True
    assert repository.load_calls == 0


def test_non_terminal_attach_does_not_read_remote_evaluation_files() -> None:
    service, migration, gateway, _repository, _runner = _service()
    migration.task = {
        **migration.task,
        "state": "analyzing",
        "canUpload": False,
        "canStop": True,
    }

    attached = service.attach(migration.task, "owner", advance=True)

    assert attached["evaluation"]["state"] == "pending"  # type: ignore[index]
    assert attached["canStop"] is True
    assert gateway.find_session_calls == 0


def test_normalized_dataset_limit_is_returned_as_bounded_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service, _migration, _gateway, _repository, _runner = _service()
    monkeypatch.setattr(
        "frontend.server.migration.evaluation.contracts.EVALUATION_DATASET_MAX_BYTES",
        1,
    )

    with pytest.raises(MigrationError) as raised:
        service.put_dataset(TASK_ID, "owner", _body())

    assert raised.value.code == "MIGRATION_EVALUATION_DATASET_INVALID"
    assert raised.value.status_code == 400
    assert raised.value.retryable is False


def test_manifest_is_bound_to_task_config_and_persisted_asset() -> None:
    service, migration, gateway, repository, _runner = _service()
    dataset = service.put_dataset(TASK_ID, "owner", _body())
    manifest = json.loads(gateway.files[EVALUATION_DATASET_MANIFEST_PATH])
    manifest["preset"] = "custom"
    gateway.files[EVALUATION_DATASET_MANIFEST_PATH] = json.dumps(manifest).encode()

    with pytest.raises(MigrationError) as raised:
        service.snapshot(TASK_ID, "owner")
    assert raised.value.code == "MIGRATION_EVALUATION_DATASET_INVALID"
    assert raised.value.retryable is False

    manifest["preset"] = "standard"
    gateway.files[EVALUATION_DATASET_MANIFEST_PATH] = json.dumps(manifest).encode()
    version_id = str(dataset["asset"]["versionId"])  # type: ignore[index]
    metadata, content = repository.assets[("dataset", version_id)]
    repository.assets[("dataset", version_id)] = (
        replace(metadata, case_count=2),
        content,
    )

    with pytest.raises(MigrationError) as raised:
        service.get_dataset(TASK_ID, "owner")
    assert raised.value.code == "MIGRATION_EVALUATION_DATASET_INVALID"
    assert raised.value.retryable is False
    assert migration.task["evaluation"] == {
        "enabled": True,
        "preset": "standard",
        "dimensions": DIMENSIONS,
    }


def test_terminal_migration_waits_for_required_environment_without_starting() -> None:
    service, migration, _gateway, _repository, runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    migration.required = ["ARK_API_KEY"]

    service.advance(TASK_ID, "owner")
    snapshot = service.snapshot(TASK_ID, "owner")
    attached = service.attach(migration.task, "owner")

    assert snapshot["state"] == "waiting_environment"
    assert snapshot["requiredEnvironment"] == ["ARK_API_KEY"]
    assert snapshot["canResume"] is True
    assert attached["canStop"] is True
    assert runner.starts == []


def test_resume_uses_transient_secret_file_without_exposing_values() -> None:
    service, migration, gateway, _repository, runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    migration.required = ["ARK_API_KEY"]
    service.advance(TASK_ID, "owner")

    snapshot = service.resume(
        TASK_ID,
        "owner",
        ResumeEvaluationBody(environment={"ARK_API_KEY": "secret-value"}),
    )

    assert snapshot["state"] == "preparing"
    assert "secret-value" not in json.dumps(snapshot)
    assert json.loads(gateway.files[EVALUATION_SECRET_PATH]) == {
        "ARK_API_KEY": "secret-value"
    }
    assert all("secret-value" not in command for _, command in gateway.commands)
    assert runner.starts[0]["secret_path"] == EVALUATION_SECRET_PATH
    assert runner.starts[0]["artifact_sha256"] == ARTIFACT_SHA256


def test_new_remote_writes_are_blocked_below_twenty_minutes() -> None:
    service, migration, _gateway, _repository, runner = _service(remaining=1199)
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)

    service.advance(TASK_ID, "owner")
    snapshot = service.snapshot(TASK_ID, "owner")

    assert snapshot["state"] == "blocked"
    assert snapshot["error"]["code"] == "MIGRATION_EVALUATION_TTL_INSUFFICIENT"  # type: ignore[index]
    assert snapshot["canRetry"] is False
    assert runner.starts == []


def test_finished_runner_cannot_leave_an_active_evaluation_stuck() -> None:
    service, migration, gateway, _repository, runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")
    assert runner.starts
    gateway.files[f"{EVALUATION_RUNNER_DIAGNOSTICS_ROOT}/runner-1-exit.json"] = (
        json.dumps(
            {"schema_version": 1, "exit_code": 17, "finished_at": int(NOW)}
        ).encode()
    )

    service.advance(TASK_ID, "owner")
    snapshot = service.snapshot(TASK_ID, "owner")

    assert snapshot["state"] == "failed"
    assert snapshot["canRetry"] is True
    assert snapshot["error"]["code"] == "MIGRATION_EVALUATION_RUNNER_EXITED"  # type: ignore[index]
    assert "17" in snapshot["error"]["message"]  # type: ignore[index]


def _report(dataset_sha256: str) -> dict[str, object]:
    results = [
        {
            "id": dimension,
            "score": 80,
            "reason": "证据一致",
            "evidence": ["输出证据"],
            "evidence_sources": ["observed_output"],
            "severity": "low",
        }
        for dimension in DIMENSIONS
    ]
    return {
        "schema_version": 1,
        "task_id": TASK_ID,
        "attempt": 1,
        "dataset_sha256": dataset_sha256,
        "dataset_version": dataset_sha256[:32],
        "artifact_sha256": ARTIFACT_SHA256,
        "prompt_version": 1,
        "model": {
            "id": "model-1",
            "codex_version": "codex-cli 0.139.0",
            "agentkit_cli_version": "0.52.16",
        },
        "dimensions": DIMENSIONS,
        "dimension_weights": {dimension: 1 for dimension in DIMENSIONS},
        "cases": [
            {
                "case_id": "case-1",
                "execution": {"state": "succeeded", "error": None},
                "output": {
                    "text": "你好",
                    "truncated": False,
                    "original_bytes": 6,
                    "captured_bytes": 6,
                },
                "dimensions": results,
            }
        ],
        "summary": {
            "score": 80,
            "dimensions": [
                {
                    "id": dimension,
                    "score": 80,
                    "reason": "汇总",
                    "evidence": [],
                    "evidence_sources": ["observed_output"],
                    "severity": "low",
                }
                for dimension in DIMENSIONS
            ],
        },
        "execution": {
            "total": 1,
            "succeeded": 1,
            "failed": 0,
            "success_rate": 100,
        },
        "evidence_coverage": {"total": 3, "scored": 3, "na": 0, "rate": 100},
        "source_contract_only_case_count": 0,
        "lowest_scoring_cases": [{"case_id": "case-1", "score": 80}],
        "execution_failures": [],
        "critical_mismatches": [],
        "migration_gap_description": "差距详情见案例证据。",
        "runtime_cleanup": {"status": "confirmed"},
        "limitations": [],
        "created_at": "2026-09-07T10:00:00Z",
    }


def test_aggregating_report_is_validated_persisted_and_then_completed() -> None:
    service, migration, gateway, _repository, runner = _service()
    dataset = service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")
    assert runner.starts
    status = json.loads(gateway.files[EVALUATION_STATUS_PATH])
    status.update(state="aggregating", message="正在汇总")
    gateway.files[EVALUATION_STATUS_PATH] = json.dumps(status).encode()
    report = _report(dataset["asset"]["sha256"])  # type: ignore[index]
    gateway.files[EVALUATION_REPORT_PATH] = json.dumps(
        report,
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()

    service.advance(TASK_ID, "owner")
    snapshot = service.snapshot(TASK_ID, "owner")
    loaded = service.get_report(TASK_ID, "owner")
    markdown, filename = service.download_report(TASK_ID, "owner")

    assert snapshot["state"] == "completed"
    assert snapshot["report"]["kind"] == "report"  # type: ignore[index]
    assert loaded["summary"] == report["summary"]
    assert loaded["asset"] == snapshot["report"]
    assert filename == "migration-evaluation-1.md"
    assert "# 迁移效果评测报告" in markdown.decode()
    assert "AgentKit CLI：`0.52.16`" in markdown.decode()
    assert "通过" not in markdown.decode()


def test_cancel_stops_active_runner_and_requires_confirmed_cleanup() -> None:
    service, migration, _gateway, _repository, runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")

    cancelled = service.cancel(TASK_ID, "owner")

    assert cancelled["state"] == "cancelled"
    assert runner.cancellations == [
        {
            "attempt": 1,
            "runtime_name": "migration-eval-111111111111-a1",
        }
    ]


def test_cancel_exposes_cleanup_uncertainty_as_retryable_block() -> None:
    service, migration, _gateway, _repository, runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")
    runner.cleanup = False

    with pytest.raises(MigrationError) as raised:
        service.cancel(TASK_ID, "owner")

    assert raised.value.code == "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED"
    snapshot = service.snapshot(TASK_ID, "owner")
    assert snapshot["state"] == "blocked"
    assert snapshot["canRetry"] is True


def test_missing_report_becomes_a_retryable_terminal_state() -> None:
    service, migration, gateway, _repository, _runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")
    status = json.loads(gateway.files[EVALUATION_STATUS_PATH])
    status.update(state="aggregating", message="正在汇总")
    gateway.files[EVALUATION_STATUS_PATH] = json.dumps(status).encode()

    with pytest.raises(MigrationError) as raised:
        service.advance(TASK_ID, "owner")

    assert raised.value.code == "MIGRATION_EVALUATION_REPORT_MISSING"
    snapshot = service.snapshot(TASK_ID, "owner")
    assert snapshot["state"] == "failed"
    assert snapshot["canRetry"] is True


def _mark_retryable_runner_failure(
    service: MigrationEvaluationService,
    migration: FakeMigration,
    gateway: FakeGateway,
) -> None:
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    service.advance(TASK_ID, "owner")
    gateway.files[f"{EVALUATION_RUNNER_DIAGNOSTICS_ROOT}/runner-1-exit.json"] = (
        json.dumps(
            {"schema_version": 1, "exit_code": 17, "finished_at": int(NOW)}
        ).encode()
    )
    service.advance(TASK_ID, "owner")


def test_retry_queues_cleanup_without_waiting_for_runtime() -> None:
    service, migration, gateway, _repository, runner = _service()
    _mark_retryable_runner_failure(service, migration, gateway)

    queued = service.retry(TASK_ID, "owner")

    assert queued["state"] == "retrying"
    assert queued["canRetry"] is False
    assert runner.cleanup_calls == []
    assert len(runner.starts) == 1


def test_retrying_advance_cleans_up_then_starts_next_attempt() -> None:
    service, migration, gateway, _repository, runner = _service()
    _mark_retryable_runner_failure(service, migration, gateway)
    service.retry(TASK_ID, "owner")

    service.advance(TASK_ID, "owner")

    assert runner.cleanup_calls == ["migration-eval-111111111111-a1"]
    assert [start["attempt"] for start in runner.starts] == [1, 2]
    assert service.snapshot(TASK_ID, "owner")["state"] == "preparing"


def test_retrying_cleanup_failure_becomes_retryable_block() -> None:
    service, migration, gateway, _repository, runner = _service()
    _mark_retryable_runner_failure(service, migration, gateway)
    service.retry(TASK_ID, "owner")
    runner.cleanup = False

    service.advance(TASK_ID, "owner")

    snapshot = service.snapshot(TASK_ID, "owner")
    assert snapshot["state"] == "blocked"
    assert snapshot["canRetry"] is True
    assert snapshot["error"]["code"] == (  # type: ignore[index]
        "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED"
    )


def test_environment_payload_must_match_required_keys_exactly() -> None:
    service, migration, _gateway, _repository, _runner = _service()
    service.put_dataset(TASK_ID, "owner", _body())
    _ready(migration)
    migration.required = ["ARK_API_KEY"]
    service.advance(TASK_ID, "owner")

    with pytest.raises(MigrationError, match="全部必需"):
        service.resume(
            TASK_ID,
            "owner",
            ResumeEvaluationBody(environment={"OTHER": "value"}),
        )
