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

"""State orchestration for Studio migration-effect evaluation."""

from __future__ import annotations

import hashlib
import json
import re
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, NotRequired, Protocol, TypedDict, cast

from ..gateway import (
    MigrationGateway,
    MigrationGatewayError,
    MigrationRemoteFileNotFound,
    MigrationSandboxSession,
)
from ..service import (
    EVALUATION_SESSION_TTL_SECONDS,
    MIGRATION_ROOT,
    MigrationError,
    MigrationService,
)
from .contracts import (
    EvaluationContractError,
    normalize_dataset,
    validate_evaluation_asset,
    validate_evaluation_report,
    validate_evaluation_status,
)
from .dimensions import (
    EVALUATION_DIMENSION_IDS,
    EVALUATION_DIMENSIONS,
    STANDARD_DIMENSION_IDS,
)
from .models import (
    EVALUATION_CASES_MAX,
    EVALUATION_CRITERIA_MAX,
    EVALUATION_CRITERION_MAX_BYTES,
    EVALUATION_DATASET_MAX_BYTES,
    EVALUATION_MESSAGE_TEXT_MAX_BYTES,
    EVALUATION_MESSAGES_MAX,
    EVALUATION_OUTPUT_MAX_BYTES,
    EVALUATION_REFERENCE_MAX_BYTES,
    EvaluationDatasetBody,
    ResumeEvaluationBody,
)
from .repository import (
    EVALUATION_REPORT_MAX_BYTES,
    EvaluationAssetConflict,
    EvaluationAssetIntegrityError,
    EvaluationAssetMetadata,
    EvaluationAssetNotFound,
    EvaluationAssetStorageUnavailable,
)

EVALUATION_ROOT = f"{MIGRATION_ROOT}/evaluation/v1"
EVALUATION_DATASET_PATH = f"{EVALUATION_ROOT}/dataset/data.jsonl"
EVALUATION_DATASET_MANIFEST_PATH = f"{EVALUATION_ROOT}/dataset/manifest.json"
EVALUATION_STATUS_PATH = f"{EVALUATION_ROOT}/control/status.json"
EVALUATION_REPORT_PATH = f"{EVALUATION_ROOT}/report/report.json"
EVALUATION_REPORT_MARKDOWN_PATH = f"{EVALUATION_ROOT}/report/report.md"
EVALUATION_SECRET_PATH = f"{EVALUATION_ROOT}/secrets/environment.json"
EVALUATION_RUNNER_DIAGNOSTICS_ROOT = f"{EVALUATION_ROOT}/diagnostics"
MINIMUM_REMOTE_WRITE_REMAINING_SECONDS = 20 * 60
_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
_TERMINAL_MIGRATION_STATES = {
    "succeeded",
    "succeeded_with_warnings",
    "partial",
}
_STOPPED_MIGRATION_STATES = {"failed", "cancelled", "expired"}
_ACTIVE_EVALUATION_STATES = {
    "preparing",
    "deploying",
    "executing",
    "judging",
    "cleaning",
}
_CANCELLABLE_EVALUATION_STATES = _ACTIVE_EVALUATION_STATES | {
    "pending",
    "waiting_environment",
    "aggregating",
}


class _EvaluationConfig(TypedDict):
    preset: str
    dimensions: list[str]


class _EvaluationManifest(TypedDict):
    schema_version: int
    task_id: str
    preset: str
    dimensions: list[str]
    asset: dict[str, object]


class _EvaluationStatus(TypedDict):
    schema_version: int
    task_id: str
    attempt: int
    state: str
    message: str
    updated_at: str
    required_environment: NotRequired[list[str]]
    runtime_name: NotRequired[str]
    error: NotRequired[dict[str, object]]
    report_asset: NotRequired[dict[str, object]]


class EvaluationAssetRepository(Protocol):
    def commit_dataset(
        self,
        *,
        owner_id: str,
        task_id: str,
        version_id: str,
        sha256: str,
        content: bytes,
        case_count: int,
        created_at: str,
    ) -> EvaluationAssetMetadata: ...

    def commit_report(
        self,
        *,
        owner_id: str,
        task_id: str,
        version_id: str,
        sha256: str,
        content: bytes,
        attempt: int,
        created_at: str,
    ) -> EvaluationAssetMetadata: ...

    def load(
        self,
        *,
        owner_id: str,
        task_id: str,
        kind: Literal["dataset", "report"],
        version_id: str,
    ) -> tuple[EvaluationAssetMetadata, bytes]: ...


class EvaluationRunner(Protocol):
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
    ) -> None: ...

    def reconcile_cleanup(
        self,
        session: MigrationSandboxSession,
        *,
        runtime_name: str,
    ) -> bool: ...

    def cancel(
        self,
        session: MigrationSandboxSession,
        *,
        attempt: int,
        runtime_name: str | None,
    ) -> bool: ...


class MigrationEvaluationService:
    def __init__(
        self,
        migration: MigrationService,
        gateway: MigrationGateway,
        *,
        repository: EvaluationAssetRepository | None,
        runner: EvaluationRunner | None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._migration = migration
        self._gateway = gateway
        self._repository = repository
        self._runner = runner
        self._clock = clock

    @property
    def available(self) -> bool:
        return self._repository is not None and self._runner is not None

    def capabilities(self) -> dict[str, object]:
        return {
            "available": self.available,
            "reason": "" if self.available else "管理员未配置评测资产存储",
            "maxCases": EVALUATION_CASES_MAX,
            "maxDatasetBytes": EVALUATION_DATASET_MAX_BYTES,
            "maxMessagesPerCase": EVALUATION_MESSAGES_MAX,
            "maxMessagesBytes": EVALUATION_MESSAGE_TEXT_MAX_BYTES,
            "maxReferenceOutputBytes": EVALUATION_REFERENCE_MAX_BYTES,
            "maxCriteria": EVALUATION_CRITERIA_MAX,
            "maxCriterionBytes": EVALUATION_CRITERION_MAX_BYTES,
            "maxCapturedOutputBytes": EVALUATION_OUTPUT_MAX_BYTES,
            "inputMode": "page",
            "pageInputMethods": ["manual", "bulk_paste"],
            "defaultPreset": "standard",
            "maximumSessionTtlSeconds": EVALUATION_SESSION_TTL_SECONDS,
            "dimensions": [
                {
                    "id": item.id,
                    "label": item.label,
                    "description": item.description,
                }
                for item in EVALUATION_DIMENSIONS
            ],
        }

    def ensure_available(self, enabled: bool) -> None:
        if enabled and not self.available:
            raise MigrationError(
                "MIGRATION_EVALUATION_UNAVAILABLE",
                "管理员尚未配置迁移效果评测所需的持久化存储。",
                status_code=503,
                retryable=False,
            )

    def attach(
        self,
        task: dict[str, object],
        owner_id: str,
        *,
        advance: bool = False,
    ) -> dict[str, object]:
        task_id = str(task.get("id") or "")
        evaluation = task.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("enabled") is not True:
            return {
                **task,
                "evaluation": {
                    "enabled": False,
                    "state": "disabled",
                    "message": "未启用迁移效果评测",
                },
            }
        if advance:
            self.advance(task_id, owner_id, task=task)
        snapshot = self.snapshot(task_id, owner_id, task=task)
        can_stop = task.get("canStop") is True or (
            snapshot.get("state") in _CANCELLABLE_EVALUATION_STATES
        )
        return {**task, "canStop": can_stop, "evaluation": snapshot}

    def assert_dataset_locked(self, task_id: str, owner_id: str) -> None:
        task = self._migration.get_task(task_id, owner_id)
        evaluation = task.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("enabled") is not True:
            return
        config = self._require_enabled(task)
        if (
            self._manifest(
                self._session(task_id, owner_id),
                expected_config=config,
                optional=True,
            )
            is None
        ):
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_REQUIRED",
                "请先填写并锁定至少一个评测用例，再上传项目 ZIP。",
                status_code=409,
                retryable=False,
            )

    def put_dataset(
        self,
        task_id: str,
        owner_id: str,
        body: EvaluationDatasetBody,
    ) -> dict[str, object]:
        self.ensure_available(True)
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        if task.get("state") != "awaiting_upload" or task.get("canUpload") is not True:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_LOCKED",
                "项目上传后不能再修改评测数据集。",
                status_code=409,
                retryable=False,
            )
        session = self._session(task_id, owner_id)
        try:
            normalized = normalize_dataset(body)
        except EvaluationContractError as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_INVALID",
                str(error),
                status_code=400,
                retryable=False,
            ) from error
        existing = self._manifest(
            session,
            expected_config=config,
            optional=True,
        )
        if existing is not None:
            asset = existing["asset"]
            assert isinstance(asset, dict)
            if asset.get("sha256") == normalized.sha256:
                return self.get_dataset(task_id, owner_id)
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_LOCKED",
                "评测数据集已锁定，不能覆盖；请新建迁移任务。",
                status_code=409,
                retryable=False,
            )
        assert self._repository is not None
        created_at = self._now()
        try:
            metadata = self._repository.commit_dataset(
                owner_id=owner_id,
                task_id=task_id,
                version_id=normalized.version_id,
                sha256=normalized.sha256,
                content=normalized.content,
                case_count=normalized.case_count,
                created_at=created_at,
            )
        except EvaluationAssetConflict as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_CONFLICT",
                str(error),
                status_code=409,
                retryable=False,
            ) from error
        except EvaluationAssetIntegrityError as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_INVALID",
                "评测数据集完整性校验失败。",
                status_code=502,
                retryable=False,
            ) from error
        except EvaluationAssetStorageUnavailable as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE",
                str(error),
                status_code=503,
                retryable=True,
            ) from error
        manifest = {
            "schema_version": 1,
            "task_id": task_id,
            "preset": config["preset"],
            "dimensions": config["dimensions"],
            "asset": metadata.public(),
        }
        self._put(
            session,
            EVALUATION_DATASET_PATH,
            normalized.content,
            media_type="application/x-ndjson",
        )
        self._put(
            session,
            EVALUATION_DATASET_MANIFEST_PATH,
            self._json_bytes(manifest),
            media_type="application/json",
        )
        self._write_status(
            session,
            task_id=task_id,
            attempt=0,
            state="pending",
            message="评测数据集已锁定，等待迁移产物",
        )
        return self.get_dataset(task_id, owner_id)

    def get_dataset(self, task_id: str, owner_id: str) -> dict[str, object]:
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        manifest = self._manifest(
            session,
            expected_config=config,
            optional=True,
        )
        if manifest is None:
            return {"locked": False, "cases": []}
        assert self._repository is not None
        asset = manifest["asset"]
        assert isinstance(asset, dict)
        try:
            metadata, content = self._repository.load(
                owner_id=owner_id,
                task_id=task_id,
                kind="dataset",
                version_id=str(asset["versionId"]),
            )
            if metadata.public() != asset:
                raise EvaluationAssetIntegrityError(
                    "评测数据集清单与持久化资产不一致。"
                )
        except EvaluationAssetNotFound as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_MISSING",
                str(error),
                status_code=502,
                retryable=False,
            ) from error
        except EvaluationAssetIntegrityError as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_INVALID",
                "评测数据集完整性校验失败。",
                status_code=502,
                retryable=False,
            ) from error
        except EvaluationAssetStorageUnavailable as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE",
                str(error),
                status_code=503,
                retryable=True,
            ) from error
        return {
            "locked": True,
            "asset": asset,
            "cases": [self._public_case(line) for line in content.splitlines()],
        }

    def snapshot(
        self,
        task_id: str,
        owner_id: str,
        *,
        task: dict[str, object] | None = None,
    ) -> dict[str, object]:
        task = task or self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        manifest = self._manifest(
            session,
            expected_config=config,
            optional=True,
        )
        status = self._status(session, task_id, optional=True)
        if manifest is None:
            state = "waiting_dataset"
            message = "请添加并锁定评测用例"
        elif status is None:
            state = "pending"
            message = "评测数据集已锁定，等待迁移产物"
        else:
            state = str(status["state"])
            message = str(status["message"])
        error = status.get("error") if status is not None else None
        payload: dict[str, object] = {
            "enabled": True,
            "preset": config["preset"],
            "dimensions": config["dimensions"],
            "state": state,
            "message": message,
            "canResume": state == "waiting_environment",
            "canRetry": state in {"failed", "blocked"}
            and isinstance(error, dict)
            and error.get("retryable") is True,
        }
        if manifest is not None:
            payload["dataset"] = manifest["asset"]
        if status is not None:
            payload["attempt"] = status["attempt"]
            if "required_environment" in status:
                payload["requiredEnvironment"] = status["required_environment"]
            if "error" in status:
                payload["error"] = status["error"]
            if "report_asset" in status:
                payload["report"] = status["report_asset"]
        return payload

    def advance(
        self,
        task_id: str,
        owner_id: str,
        *,
        task: dict[str, object] | None = None,
    ) -> None:
        task = task or self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        manifest = self._manifest(
            session,
            expected_config=config,
            optional=True,
        )
        if manifest is None:
            return
        status = self._status(session, task_id, optional=True)
        state = str(status.get("state") or "pending") if status else "pending"
        if state == "aggregating":
            assert status is not None
            self._persist_report(
                session,
                owner_id,
                manifest,
                status,
                artifact_sha256=self._artifact_sha256(task_id, owner_id),
            )
            return
        if state in _ACTIVE_EVALUATION_STATES:
            self._reconcile_active_runner(session, task_id, status)
            return
        if state in {
            "waiting_environment",
            "completed",
            "failed",
            "blocked",
            "cancelled",
        }:
            return
        migration_state = str(task.get("state") or "")
        if migration_state in _STOPPED_MIGRATION_STATES:
            self._write_status(
                session,
                task_id=task_id,
                attempt=int(status.get("attempt") or 0) if status else 0,
                state="cancelled",
                message="迁移未生成可评测产物，评测已取消",
            )
            return
        if migration_state not in _TERMINAL_MIGRATION_STATES:
            return
        artifact_status = task.get("artifact")
        if (
            not isinstance(artifact_status, dict)
            or artifact_status.get("deployReady") is not True
        ):
            self._write_failure(
                session,
                task_id=task_id,
                attempt=int(status.get("attempt") or 0) if status else 0,
                state="blocked",
                code="MIGRATION_EVALUATION_ARTIFACT_NOT_DEPLOYABLE",
                message="迁移产物不可部署，无法执行效果评测。",
                retryable=False,
            )
            return
        artifact = self._migration.artifact(task_id, owner_id)
        artifact_sha256 = self._artifact_sha256(task_id, owner_id, artifact=artifact)
        environment = artifact.get("environment")
        required = (
            [str(item) for item in environment.get("required", [])]
            if isinstance(environment, dict)
            and isinstance(environment.get("required"), list)
            else []
        )
        attempt = int(status.get("attempt") or 0) + 1 if status else 1
        if required:
            self._write_status(
                session,
                task_id=task_id,
                attempt=attempt,
                state="waiting_environment",
                message="请补充临时部署所需的环境变量",
                required_environment=required,
            )
            return
        self._start(
            session,
            task_id=task_id,
            attempt=attempt,
            config=config,
            manifest=manifest,
            artifact_sha256=artifact_sha256,
            secret_path=None,
        )

    def resume(
        self,
        task_id: str,
        owner_id: str,
        body: ResumeEvaluationBody,
    ) -> dict[str, object]:
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        status = self._status(session, task_id)
        assert status is not None
        if status["state"] != "waiting_environment":
            raise MigrationError(
                "MIGRATION_EVALUATION_NOT_WAITING_ENVIRONMENT",
                "当前评测不处于等待环境变量状态。",
                status_code=409,
                retryable=False,
            )
        required_environment = status.get("required_environment")
        assert required_environment is not None
        required = set(required_environment)
        supplied = set(body.environment)
        if supplied != required:
            missing = sorted(required - supplied)
            extra = sorted(supplied - required)
            detail = "、".join(missing or extra)
            raise MigrationError(
                "MIGRATION_EVALUATION_ENVIRONMENT_MISMATCH",
                f"请只填写全部必需环境变量：{detail}",
                status_code=400,
                retryable=False,
            )
        manifest = self._manifest(session, expected_config=config)
        assert manifest is not None
        artifact_sha256 = self._artifact_sha256(task_id, owner_id)
        self._put(
            session,
            EVALUATION_SECRET_PATH,
            self._json_bytes(body.environment),
            media_type="application/json",
        )
        self._execute(
            session,
            f"chmod 600 {EVALUATION_SECRET_PATH}",
            operation="evaluation_protect_environment",
            timeout_seconds=30,
        )
        self._start(
            session,
            task_id=task_id,
            attempt=int(status["attempt"]),
            config=config,
            manifest=manifest,
            artifact_sha256=artifact_sha256,
            secret_path=EVALUATION_SECRET_PATH,
        )
        return self.snapshot(task_id, owner_id, task=task)

    def retry(self, task_id: str, owner_id: str) -> dict[str, object]:
        task = self._migration.get_task(task_id, owner_id)
        self._require_enabled(task)
        session = self._session(task_id, owner_id)
        status = self._status(session, task_id)
        assert status is not None
        error = status.get("error")
        if (
            status["state"] not in {"failed", "blocked"}
            or not isinstance(error, dict)
            or error.get("retryable") is not True
        ):
            raise MigrationError(
                "MIGRATION_EVALUATION_RETRY_NOT_ALLOWED",
                "当前评测不能重试。",
                status_code=409,
                retryable=False,
            )
        runtime_name = str(status.get("runtime_name") or "")
        if runtime_name:
            assert self._runner is not None
            if not self._runner.reconcile_cleanup(session, runtime_name=runtime_name):
                raise MigrationError(
                    "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED",
                    "临时 Runtime 清理尚未确认，请稍后重试。",
                    status_code=409,
                    retryable=True,
                )
        self._write_status(
            session,
            task_id=task_id,
            attempt=int(status["attempt"]),
            state="pending",
            message="正在准备重试评测",
        )
        self.advance(task_id, owner_id, task=task)
        return self.snapshot(task_id, owner_id, task=task)

    def cancel(self, task_id: str, owner_id: str) -> dict[str, object]:
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        manifest = self._manifest(
            session,
            expected_config=config,
            optional=True,
        )
        status = self._status(session, task_id, optional=True)
        state = str(status.get("state") or "pending") if status else "pending"
        if state == "cancelled":
            return self.snapshot(task_id, owner_id, task=task)
        if state == "completed":
            raise MigrationError(
                "MIGRATION_EVALUATION_CANCEL_NOT_ALLOWED",
                "评测已经完成，不能再终止。",
                status_code=409,
                retryable=False,
            )
        attempt = int(status.get("attempt") or 0) if status else 0
        runtime_name = str(status.get("runtime_name") or "") if status else ""
        if attempt > 0:
            assert self._runner is not None
            cleanup_confirmed = self._runner.cancel(
                session,
                attempt=attempt,
                runtime_name=runtime_name or None,
            )
            if not cleanup_confirmed:
                self._write_failure(
                    session,
                    task_id=task_id,
                    attempt=attempt,
                    state="blocked",
                    code="MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED",
                    message="评测进程已停止，但临时 Runtime 清理尚未确认。",
                    retryable=True,
                    runtime_name=runtime_name or None,
                )
                raise MigrationError(
                    "MIGRATION_EVALUATION_CLEANUP_UNCONFIRMED",
                    "评测进程已停止，但临时 Runtime 清理尚未确认。",
                    status_code=409,
                    retryable=True,
                )
        self._write_status(
            session,
            task_id=task_id,
            attempt=attempt,
            state="cancelled",
            message=(
                "迁移效果评测已终止"
                if manifest is not None
                else "评测用例尚未锁定，评测已终止"
            ),
        )
        return self.snapshot(task_id, owner_id, task=task)

    def get_report(self, task_id: str, owner_id: str) -> dict[str, object]:
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        status = self._status(session, task_id)
        assert status is not None
        asset = status.get("report_asset")
        if status["state"] != "completed" or not isinstance(asset, dict):
            raise MigrationError(
                "MIGRATION_EVALUATION_REPORT_NOT_READY",
                "评测报告尚未生成。",
                status_code=409,
                retryable=False,
            )
        assert self._repository is not None
        try:
            metadata, content = self._repository.load(
                owner_id=owner_id,
                task_id=task_id,
                kind="report",
                version_id=str(asset["versionId"]),
            )
            if metadata.public() != asset:
                raise EvaluationAssetIntegrityError("评测报告状态与持久化资产不一致。")
            value = json.loads(content)
            manifest = self._manifest(session, expected_config=config)
            assert manifest is not None
            report = validate_evaluation_report(
                value,
                expected_task_id=task_id,
                expected_attempt=int(status["attempt"]),
                expected_dataset_sha256=str(manifest["asset"]["sha256"]),
                expected_artifact_sha256=self._artifact_sha256(task_id, owner_id),
                expected_dimensions=config["dimensions"],
            )
        except (EvaluationAssetNotFound, EvaluationAssetIntegrityError) as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_REPORT_INVALID",
                "评测报告完整性校验失败。",
                status_code=502,
                retryable=False,
            ) from error
        except EvaluationAssetStorageUnavailable as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE",
                str(error),
                status_code=503,
                retryable=True,
            ) from error
        return {**report, "asset": asset}

    def download_report(
        self,
        task_id: str,
        owner_id: str,
    ) -> tuple[bytes, str]:
        report = self.get_report(task_id, owner_id)
        content = self._report_markdown(report).encode("utf-8")
        attempt = cast(int, report["attempt"])
        return content, f"migration-evaluation-{attempt}.md"

    def _start(
        self,
        session: MigrationSandboxSession,
        *,
        task_id: str,
        attempt: int,
        config: _EvaluationConfig,
        manifest: _EvaluationManifest,
        artifact_sha256: str,
        secret_path: str | None,
    ) -> None:
        remaining = self._remaining_seconds(session)
        if remaining < MINIMUM_REMOTE_WRITE_REMAINING_SECONDS:
            self._write_failure(
                session,
                task_id=task_id,
                attempt=attempt,
                state="blocked",
                code="MIGRATION_EVALUATION_TTL_INSUFFICIENT",
                message="迁移环境剩余时间不足 20 分钟，未启动新的远端写入。",
                retryable=False,
            )
            return
        runtime_name = self._runtime_name(task_id, attempt)
        self._write_status(
            session,
            task_id=task_id,
            attempt=attempt,
            state="preparing",
            message="正在准备临时评测环境",
            runtime_name=runtime_name,
        )
        assert self._runner is not None
        asset = manifest["asset"]
        assert isinstance(asset, dict)
        try:
            self._runner.start(
                session,
                task_id=task_id,
                attempt=attempt,
                runtime_name=runtime_name,
                dimensions=config["dimensions"],
                dataset_sha256=str(asset["sha256"]),
                artifact_sha256=artifact_sha256,
                secret_path=secret_path,
            )
        except Exception as error:
            self._write_failure(
                session,
                task_id=task_id,
                attempt=attempt,
                state="failed",
                code="MIGRATION_EVALUATION_START_FAILED",
                message="评测执行未能启动，请重试。",
                retryable=True,
                runtime_name=runtime_name,
            )
            raise MigrationError(
                "MIGRATION_EVALUATION_START_FAILED",
                "评测执行未能启动，请重试。",
                status_code=502,
                retryable=True,
            ) from error

    def _persist_report(
        self,
        session: MigrationSandboxSession,
        owner_id: str,
        manifest: _EvaluationManifest,
        status: _EvaluationStatus,
        *,
        artifact_sha256: str,
    ) -> None:
        task_id = session.task_id
        try:
            content = self._read(
                session,
                EVALUATION_REPORT_PATH,
                max_bytes=EVALUATION_REPORT_MAX_BYTES,
            )
        except MigrationError as error:
            if error.code != "MIGRATION_EVALUATION_REMOTE_FILE_MISSING":
                raise
            self._write_failure(
                session,
                task_id=task_id,
                attempt=int(status["attempt"]),
                state="failed",
                code="MIGRATION_EVALUATION_REPORT_MISSING",
                message="评测执行未生成报告，请重试。",
                retryable=True,
                runtime_name=str(status.get("runtime_name") or "") or None,
            )
            raise MigrationError(
                "MIGRATION_EVALUATION_REPORT_MISSING",
                "评测执行未生成报告，请重试。",
                status_code=502,
                retryable=True,
            ) from error
        assert content is not None
        asset = manifest["asset"]
        assert isinstance(asset, dict)
        config_dimensions = manifest["dimensions"]
        assert isinstance(config_dimensions, list)
        try:
            report_value = json.loads(content)
            validate_evaluation_report(
                report_value,
                expected_task_id=task_id,
                expected_attempt=int(status["attempt"]),
                expected_dataset_sha256=str(asset["sha256"]),
                expected_artifact_sha256=artifact_sha256,
                expected_dimensions=[str(item) for item in config_dimensions],
            )
        except (ValueError, EvaluationContractError) as error:
            self._write_failure(
                session,
                task_id=task_id,
                attempt=int(status["attempt"]),
                state="failed",
                code="MIGRATION_EVALUATION_REPORT_INVALID",
                message="评测执行返回了无效报告。",
                retryable=True,
                runtime_name=str(status.get("runtime_name") or "") or None,
            )
            raise MigrationError(
                "MIGRATION_EVALUATION_REPORT_INVALID",
                "评测执行返回了无效报告。",
                status_code=502,
                retryable=True,
            ) from error
        digest = hashlib.sha256(content).hexdigest()
        assert self._repository is not None
        try:
            metadata = self._repository.commit_report(
                owner_id=owner_id,
                task_id=task_id,
                version_id=digest[:32],
                sha256=digest,
                content=content,
                attempt=int(status["attempt"]),
                created_at=str(report_value["created_at"]),
            )
        except (
            EvaluationAssetConflict,
            EvaluationAssetIntegrityError,
            EvaluationAssetStorageUnavailable,
        ) as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE",
                str(error),
                status_code=503,
                retryable=True,
            ) from error
        self._write_status(
            session,
            task_id=task_id,
            attempt=int(status["attempt"]),
            state="completed",
            message="迁移效果评测已完成",
            report_asset=metadata.public(),
        )

    def _reconcile_active_runner(
        self,
        session: MigrationSandboxSession,
        task_id: str,
        status: _EvaluationStatus | None,
    ) -> None:
        if status is None:
            return
        attempt = int(status.get("attempt") or 0)
        if attempt < 1:
            return
        path = f"{EVALUATION_RUNNER_DIAGNOSTICS_ROOT}/runner-{attempt}-exit.json"
        content = self._read(session, path, max_bytes=4 * 1024, optional=True)
        if content is None:
            return
        exit_code: int | None = None
        try:
            value = json.loads(content)
            candidate = value.get("exit_code") if isinstance(value, dict) else None
            if isinstance(candidate, int) and not isinstance(candidate, bool):
                exit_code = candidate
        except (UnicodeDecodeError, ValueError):
            pass
        detail = f"（退出码 {exit_code}）" if exit_code is not None else ""
        self._write_failure(
            session,
            task_id=task_id,
            attempt=attempt,
            state="failed",
            code="MIGRATION_EVALUATION_RUNNER_EXITED",
            message=f"评测进程意外结束{detail}，请重试。",
            retryable=True,
            runtime_name=str(status.get("runtime_name") or "") or None,
        )

    def _manifest(
        self,
        session: MigrationSandboxSession,
        *,
        expected_config: _EvaluationConfig,
        optional: bool = False,
    ) -> _EvaluationManifest | None:
        value = self._read_json(
            session,
            EVALUATION_DATASET_MANIFEST_PATH,
            optional=optional,
        )
        if value is None:
            return None
        asset = value.get("asset")
        if (
            set(value)
            != {
                "schema_version",
                "task_id",
                "preset",
                "dimensions",
                "asset",
            }
            or value.get("schema_version") != 1
            or value.get("task_id") != session.task_id
            or value.get("preset") != expected_config["preset"]
            or value.get("dimensions") != expected_config["dimensions"]
        ):
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_INVALID",
                "评测数据集清单无效。",
                status_code=502,
                retryable=False,
            )
        try:
            validate_evaluation_asset(asset, kind="dataset")
        except EvaluationContractError as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_INVALID",
                "评测数据集清单无效。",
                status_code=502,
                retryable=False,
            ) from error
        return cast(_EvaluationManifest, value)

    def _status(
        self,
        session: MigrationSandboxSession,
        task_id: str,
        *,
        optional: bool = False,
    ) -> _EvaluationStatus | None:
        value = self._read_json(session, EVALUATION_STATUS_PATH, optional=optional)
        if value is None:
            return None
        try:
            validated = validate_evaluation_status(value, expected_task_id=task_id)
            return cast(_EvaluationStatus, validated)
        except EvaluationContractError as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STATE_INVALID",
                "评测状态文件格式无效。",
                status_code=502,
                retryable=False,
            ) from error

    def _write_status(
        self,
        session: MigrationSandboxSession,
        *,
        task_id: str,
        attempt: int,
        state: str,
        message: str,
        required_environment: list[str] | None = None,
        runtime_name: str | None = None,
        report_asset: dict[str, object] | None = None,
    ) -> None:
        value: dict[str, object] = {
            "schema_version": 1,
            "task_id": task_id,
            "attempt": attempt,
            "state": state,
            "message": message,
            "updated_at": self._now(),
        }
        if required_environment is not None:
            value["required_environment"] = required_environment
        if runtime_name:
            value["runtime_name"] = runtime_name
        if report_asset is not None:
            value["report_asset"] = report_asset
        validate_evaluation_status(value, expected_task_id=task_id)
        self._put(
            session,
            EVALUATION_STATUS_PATH,
            self._json_bytes(value),
            media_type="application/json",
        )

    def _write_failure(
        self,
        session: MigrationSandboxSession,
        *,
        task_id: str,
        attempt: int,
        state: str,
        code: str,
        message: str,
        retryable: bool,
        runtime_name: str | None = None,
    ) -> None:
        value: dict[str, object] = {
            "schema_version": 1,
            "task_id": task_id,
            "attempt": attempt,
            "state": state,
            "message": message,
            "updated_at": self._now(),
            "error": {
                "code": code,
                "message": message,
                "retryable": retryable,
            },
        }
        if runtime_name:
            value["runtime_name"] = runtime_name
        validate_evaluation_status(value, expected_task_id=task_id)
        self._put(
            session,
            EVALUATION_STATUS_PATH,
            self._json_bytes(value),
            media_type="application/json",
        )

    @staticmethod
    def _require_enabled(task: dict[str, object]) -> _EvaluationConfig:
        evaluation = task.get("evaluation")
        if not isinstance(evaluation, dict) or evaluation.get("enabled") is not True:
            raise MigrationError(
                "MIGRATION_EVALUATION_DISABLED",
                "该迁移任务未启用效果评测。",
                status_code=409,
                retryable=False,
            )
        dimensions = evaluation.get("dimensions")
        preset = evaluation.get("preset")
        if (
            preset not in {"standard", "custom"}
            or not isinstance(dimensions, list)
            or not dimensions
            or any(not isinstance(item, str) for item in dimensions)
            or any(item not in EVALUATION_DIMENSION_IDS for item in dimensions)
            or len(set(dimensions)) != len(dimensions)
            or [item for item in EVALUATION_DIMENSION_IDS if item in dimensions]
            != dimensions
            or (preset == "standard" and tuple(dimensions) != STANDARD_DIMENSION_IDS)
        ):
            raise MigrationError(
                "MIGRATION_EVALUATION_CONFIG_INVALID",
                "迁移评测配置无效。",
                status_code=502,
                retryable=False,
            )
        return {
            "preset": str(preset),
            "dimensions": [str(item) for item in dimensions],
        }

    def _artifact_sha256(
        self,
        task_id: str,
        owner_id: str,
        *,
        artifact: dict[str, object] | None = None,
    ) -> str:
        payload = artifact or self._migration.artifact(task_id, owner_id)
        descriptor = payload.get("artifact")
        sha256 = descriptor.get("sha256") if isinstance(descriptor, dict) else None
        if not isinstance(sha256, str) or re.fullmatch(r"[0-9a-f]{64}", sha256) is None:
            raise MigrationError(
                "MIGRATION_EVALUATION_ARTIFACT_INVALID",
                "迁移产物摘要无效，无法执行评测。",
                status_code=502,
                retryable=False,
            )
        return sha256

    def _session(self, task_id: str, owner_id: str) -> MigrationSandboxSession:
        if _TASK_ID_RE.fullmatch(task_id) is None:
            raise MigrationError(
                "MIGRATION_TASK_NOT_FOUND",
                "迁移会话不存在或已过期。",
                status_code=404,
            )
        try:
            return self._gateway.find_session(task_id, owner_id)
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _put(
        self,
        session: MigrationSandboxSession,
        path: str,
        content: bytes,
        *,
        media_type: str,
    ) -> None:
        try:
            self._gateway.put_file(session, path, content, media_type=media_type)
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _read(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        max_bytes: int,
        optional: bool = False,
    ) -> bytes | None:
        try:
            return self._gateway.get_file(session, path, max_bytes=max_bytes)
        except MigrationRemoteFileNotFound:
            if optional:
                return None
            raise MigrationError(
                "MIGRATION_EVALUATION_REMOTE_FILE_MISSING",
                "评测所需的远端文件不存在。",
                status_code=502,
                retryable=False,
            ) from None
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    def _read_json(
        self,
        session: MigrationSandboxSession,
        path: str,
        *,
        optional: bool = False,
    ) -> dict[str, object] | None:
        content = self._read(
            session,
            path,
            max_bytes=EVALUATION_REPORT_MAX_BYTES,
            optional=optional,
        )
        if content is None:
            return None
        try:
            value = json.loads(content)
        except (UnicodeDecodeError, ValueError) as error:
            raise MigrationError(
                "MIGRATION_EVALUATION_STATE_INVALID",
                "评测状态文件格式无效。",
                status_code=502,
            ) from error
        if not isinstance(value, dict):
            raise MigrationError(
                "MIGRATION_EVALUATION_STATE_INVALID",
                "评测状态文件格式无效。",
                status_code=502,
            )
        return {str(key): item for key, item in value.items()}

    def _execute(
        self,
        session: MigrationSandboxSession,
        command: str,
        *,
        operation: str,
        timeout_seconds: int,
    ) -> None:
        try:
            self._gateway.execute_bash(
                session,
                command,
                operation=operation,
                timeout_seconds=timeout_seconds,
            )
        except MigrationGatewayError as error:
            raise self._translate(error) from error

    @staticmethod
    def _translate(error: MigrationGatewayError) -> MigrationError:
        return MigrationError(
            error.code,
            str(error),
            status_code=error.status_code,
            retryable=error.retryable,
        )

    @staticmethod
    def _public_case(line: bytes) -> dict[str, object]:
        value = json.loads(line)
        messages = value["messages"]
        return {
            "caseId": value["case_id"],
            "userInput": messages[-1]["content"],
            "priorMessages": messages[:-1],
            "expectedOutcome": value.get("reference_output"),
            "criteria": value.get("criteria", []),
        }

    @staticmethod
    def _report_markdown(report: dict[str, object]) -> str:
        summary = report.get("summary")
        execution = report.get("execution")
        coverage = report.get("evidence_coverage")
        model = report.get("model")
        cleanup = report.get("runtime_cleanup")
        assert isinstance(summary, dict)
        assert isinstance(execution, dict)
        assert isinstance(coverage, dict)
        assert isinstance(model, dict)
        assert isinstance(cleanup, dict)
        score = summary.get("score")
        score_text = "N/A" if score is None else f"{score}/100"
        lines = [
            "# 迁移效果评测报告",
            "",
            f"- 任务：`{report['task_id']}`",
            f"- 评测集：`{report['dataset_version']}` / `{report['dataset_sha256']}`",
            f"- 迁移产物：`{report['artifact_sha256']}`",
            f"- 模型：`{model['id']}`",
            f"- Codex：`{model['codex_version']}`",
            f"- AgentKit CLI：`{model['agentkit_cli_version']}`",
            f"- Prompt 版本：`{report['prompt_version']}`",
            f"- 综合一致性：{score_text}",
            f"- 证据覆盖率：{coverage['rate']}%",
            f"- 执行成功率：{execution['success_rate']}%",
            f"- Runtime 清理：{cleanup['status']}",
            "",
            "## 维度结果",
            "",
        ]
        dimensions = summary.get("dimensions")
        assert isinstance(dimensions, list)
        for item in dimensions:
            assert isinstance(item, dict)
            item_score = item.get("score")
            item_score_text = "N/A" if item_score is None else f"{item_score}/100"
            lines.append(f"- `{item['id']}`：{item_score_text}；{item['reason']}")
        lines.extend(
            [
                "",
                "## 迁移差距与限制",
                "",
                str(report["migration_gap_description"]),
            ]
        )
        limitations = report.get("limitations")
        assert isinstance(limitations, list)
        lines.extend(f"- {item}" for item in limitations)
        lines.append("")
        return "\n".join(lines)

    @staticmethod
    def _runtime_name(task_id: str, attempt: int) -> str:
        suffix = task_id.removeprefix("migration-v1-")[:12]
        return f"migration-eval-{suffix}-a{attempt}"

    def _remaining_seconds(self, session: MigrationSandboxSession) -> float:
        try:
            expiry = datetime.fromisoformat(session.expire_at.replace("Z", "+00:00"))
        except ValueError:
            return 0
        return expiry.timestamp() - self._clock()

    def _now(self) -> str:
        return (
            datetime.fromtimestamp(self._clock(), timezone.utc)
            .isoformat()
            .replace("+00:00", "Z")
        )

    @staticmethod
    def _json_bytes(value: object) -> bytes:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")


__all__ = [
    "EVALUATION_DATASET_MANIFEST_PATH",
    "EVALUATION_DATASET_PATH",
    "EVALUATION_REPORT_MARKDOWN_PATH",
    "EVALUATION_REPORT_PATH",
    "EVALUATION_ROOT",
    "EVALUATION_RUNNER_DIAGNOSTICS_ROOT",
    "EVALUATION_SECRET_PATH",
    "EVALUATION_STATUS_PATH",
    "MINIMUM_REMOTE_WRITE_REMAINING_SECONDS",
    "EvaluationAssetRepository",
    "EvaluationRunner",
    "MigrationEvaluationService",
]
