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
import html
import json
import logging
import re
import shlex
import time
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Literal, Protocol, TypedDict, cast

from typing_extensions import NotRequired

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
EVALUATION_SECRET_PATH = f"{EVALUATION_ROOT}/secrets/environment.json"
EVALUATION_RUNNER_DIAGNOSTICS_ROOT = f"{EVALUATION_ROOT}/diagnostics"
MINIMUM_REMOTE_WRITE_REMAINING_SECONDS = 20 * 60
logger = logging.getLogger(__name__)
_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
_ASSET_VERSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
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
}
_CANCELLABLE_EVALUATION_STATES = _ACTIVE_EVALUATION_STATES | {
    "pending",
    "waiting_environment",
    "aggregating",
}


class _EvaluationConfig(TypedDict):
    preset: str
    dimensions: list[str]
    locale: str


class _EvaluationManifest(TypedDict):
    schema_version: int
    task_id: str
    preset: str
    dimensions: list[str]
    locale: str
    asset: dict[str, object]


class _EvaluationEnvironment(TypedDict):
    required: list[str]
    optional: list[str]
    defaults: dict[str, str]


class _EvaluationStatus(TypedDict):
    schema_version: int
    task_id: str
    attempt: int
    state: str
    message: str
    updated_at: str
    environment: NotRequired[_EvaluationEnvironment]
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
        locale: str = "zh-CN",
        dataset_sha256: str,
        artifact_sha256: str,
        secret_path: str | None,
    ) -> None: ...

    def stop(
        self,
        session: MigrationSandboxSession,
        *,
        attempt: int,
    ) -> None: ...


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
        if str(task.get("state") or "") not in (
            _TERMINAL_MIGRATION_STATES | _STOPPED_MIGRATION_STATES
        ):
            state = (
                "waiting_dataset"
                if task.get("state") == "awaiting_upload"
                else "pending"
            )
            message = (
                "请添加并保存评测用例"
                if state == "waiting_dataset"
                else "迁移完成后自动开始评测"
            )
            snapshot: dict[str, object] = {
                "enabled": True,
                "preset": evaluation.get("preset", "standard"),
                "dimensions": evaluation.get("dimensions", []),
                "locale": evaluation.get("locale", "zh-CN"),
                "state": state,
                "message": message,
                "canResume": False,
                "canRetry": False,
            }
            return {**task, "evaluation": snapshot}
        if advance:
            self.advance(task_id, owner_id, task=task)
        snapshot = self.snapshot(task_id, owner_id, task=task)
        can_stop = task.get("canStop") is True or (
            snapshot.get("state") in _CANCELLABLE_EVALUATION_STATES
        )
        return {**task, "canStop": can_stop, "evaluation": snapshot}

    def put_dataset(
        self,
        task_id: str,
        owner_id: str,
        body: EvaluationDatasetBody,
    ) -> dict[str, object]:
        self.ensure_available(True)
        task = self._migration.get_task(task_id, owner_id)
        config = self._require_enabled(task)
        if str(task.get("state") or "") in _STOPPED_MIGRATION_STATES:
            raise MigrationError(
                "MIGRATION_EVALUATION_DATASET_LOCKED",
                "迁移已结束，不能再保存评测用例。",
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
                return self._dataset_payload(asset, normalized.content)
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
            "locale": config["locale"],
            "asset": metadata.public(),
        }
        self._put(
            session,
            EVALUATION_DATASET_PATH,
            normalized.content,
            media_type="application/x-ndjson",
        )
        # Publish the manifest last. The watcher cannot start an evaluation until
        # the dataset is durable in the Session; a missing status means pending.
        self._put(
            session,
            EVALUATION_DATASET_MANIFEST_PATH,
            self._json_bytes(manifest),
            media_type="application/json",
        )
        return self._dataset_payload(metadata.public(), normalized.content)

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

    def _dataset_payload(
        self,
        asset: dict[str, object],
        content: bytes,
    ) -> dict[str, object]:
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
            "locale": config["locale"],
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
            if "environment" in status:
                payload["environment"] = status["environment"]
            if "runtime_name" in status:
                payload["runtimeName"] = status["runtime_name"]
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
        environment = self._evaluation_environment(artifact)
        attempt = int(status.get("attempt") or 0) + 1 if status else 1
        if environment["required"] or environment["optional"]:
            self._write_status(
                session,
                task_id=task_id,
                attempt=attempt,
                state="waiting_environment",
                message="请补充临时部署所需的环境变量",
                environment=environment,
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
            return self.snapshot(task_id, owner_id, task=task)
        environment = status.get("environment")
        assert environment is not None
        required = set(environment["required"])
        allowed = required | set(environment["optional"])
        supplied = set(body.environment)
        if not required.issubset(supplied) or not supplied.issubset(allowed):
            missing = sorted(required - supplied)
            extra = sorted(supplied - allowed)
            detail = "、".join(missing or extra)
            raise MigrationError(
                "MIGRATION_EVALUATION_ENVIRONMENT_MISMATCH",
                f"请填写全部必需环境变量，且不要提交未声明的变量：{detail}",
                status_code=400,
                retryable=False,
            )
        manifest = self._manifest(session, expected_config=config)
        assert manifest is not None
        artifact_sha256 = self._artifact_sha256(task_id, owner_id)
        try:
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
        except Exception:
            self._delete_environment_file(session, EVALUATION_SECRET_PATH)
            raise
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
        config = self._require_enabled(task)
        session = self._session(task_id, owner_id)
        status = self._status(session, task_id)
        assert status is not None
        error = status.get("error")
        if (
            status["state"] not in {"failed", "blocked"}
            or not isinstance(error, dict)
            or error.get("retryable") is not True
        ):
            return self.snapshot(task_id, owner_id, task=task)
        attempt = int(status["attempt"])
        manifest = self._manifest(session, expected_config=config)
        assert manifest is not None
        artifact = self._migration.artifact(task_id, owner_id)
        artifact_sha256 = self._artifact_sha256(
            task_id,
            owner_id,
            artifact=artifact,
        )
        environment = self._evaluation_environment(artifact)
        next_attempt = attempt + 1
        if environment["required"] or environment["optional"]:
            self._write_status(
                session,
                task_id=task_id,
                attempt=next_attempt,
                state="waiting_environment",
                message="请补充临时部署所需的环境变量",
                environment=environment,
            )
        else:
            self._start(
                session,
                task_id=task_id,
                attempt=next_attempt,
                config=config,
                manifest=manifest,
                artifact_sha256=artifact_sha256,
                secret_path=None,
            )
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
        if attempt > 0:
            assert self._runner is not None
            try:
                self._runner.stop(session, attempt=attempt)
            except Exception:
                raise MigrationError(
                    "MIGRATION_EVALUATION_STOP_FAILED",
                    "评测进程未能停止，请重试。",
                    status_code=502,
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

    def _load_report_html(
        self,
        task_id: str,
        owner_id: str,
        version_id: str,
    ) -> tuple[EvaluationAssetMetadata, bytes]:
        if _ASSET_VERSION_ID_RE.fullmatch(version_id) is None:
            raise MigrationError(
                "MIGRATION_EVALUATION_REPORT_REFERENCE_INVALID",
                "评测报告引用无效。",
                status_code=400,
                retryable=False,
            )
        assert self._repository is not None
        try:
            metadata, content = self._repository.load(
                owner_id=owner_id,
                task_id=task_id,
                kind="report",
                version_id=version_id,
            )
            if metadata.attempt is None:
                raise EvaluationAssetIntegrityError("评测报告格式无效。")
            decoded = content.decode("utf-8")
            if not decoded.startswith("<!doctype html>"):
                raise EvaluationAssetIntegrityError("评测报告格式无效。")
        except (
            EvaluationAssetNotFound,
            EvaluationAssetIntegrityError,
            UnicodeDecodeError,
        ) as error:
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
        return metadata, content

    def download_report(
        self,
        task_id: str,
        owner_id: str,
        version_id: str,
    ) -> tuple[bytes, str]:
        metadata, content = self._load_report_html(task_id, owner_id, version_id)
        assert metadata.attempt is not None
        return content, f"migration-evaluation-{metadata.attempt}.html"

    def preview_report(
        self,
        task_id: str,
        owner_id: str,
        version_id: str,
    ) -> bytes:
        _metadata, content = self._load_report_html(task_id, owner_id, version_id)
        return content

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
            if secret_path is not None:
                self._delete_environment_file(session, secret_path)
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
            message="正在校验迁移产物和评测用例",
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
                locale=config["locale"],
                dataset_sha256=str(asset["sha256"]),
                artifact_sha256=artifact_sha256,
                secret_path=secret_path,
            )
        except MigrationError as error:
            if secret_path is not None:
                self._delete_environment_file(session, secret_path)
            self._write_failure(
                session,
                task_id=task_id,
                attempt=attempt,
                state="failed",
                code=error.code,
                message=str(error),
                retryable=error.retryable,
                runtime_name=runtime_name,
            )
            raise
        except Exception as error:
            if secret_path is not None:
                self._delete_environment_file(session, secret_path)
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

    def _delete_environment_file(
        self,
        session: MigrationSandboxSession,
        path: str,
    ) -> None:
        script = (
            "import os\n"
            f"path={path!r}\n"
            "try:\n"
            "    os.unlink(path)\n"
            "except FileNotFoundError:\n"
            "    pass\n"
        )
        try:
            self._execute(
                session,
                f"python3 -c {shlex.quote(script)}",
                operation="evaluation_delete_environment",
                timeout_seconds=30,
            )
        except Exception as error:
            logger.warning(
                "Could not delete evaluation environment file task_id=%s error_type=%s",
                session.task_id,
                type(error).__name__,
            )

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
            validated_report = validate_evaluation_report(
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
        report_content = self._report_html(
            validated_report,
            locale=str(manifest["locale"]),
        ).encode("utf-8")
        digest = hashlib.sha256(report_content).hexdigest()
        assert self._repository is not None
        try:
            metadata = self._repository.commit_report(
                owner_id=owner_id,
                task_id=task_id,
                version_id=digest[:32],
                sha256=digest,
                content=report_content,
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
                "locale",
                "asset",
            }
            or value.get("schema_version") != 1
            or value.get("task_id") != session.task_id
            or value.get("preset") != expected_config["preset"]
            or value.get("dimensions") != expected_config["dimensions"]
            or value.get("locale") != expected_config["locale"]
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
        environment: _EvaluationEnvironment | None = None,
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
        if environment is not None:
            value["environment"] = environment
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
        locale = evaluation.get("locale")
        if (
            preset not in {"standard", "custom"}
            or locale not in {"zh-CN", "en-US"}
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
            "locale": str(locale),
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
    def _report_html(report: dict[str, object], *, locale: str) -> str:
        summary = report.get("summary")
        execution = report.get("execution")
        coverage = report.get("evidence_coverage")
        model = report.get("model")
        assert isinstance(summary, dict)
        assert isinstance(execution, dict)
        assert isinstance(coverage, dict)
        assert isinstance(model, dict)
        score = summary.get("score")

        def escape(value: object) -> str:
            return html.escape(str(value), quote=True)

        copy = (
            {
                "title": "Migration Effect Evaluation Report",
                "attempt": "Evaluation attempt {attempt} · {created_at}",
                "dataset": "Dataset {version}",
                "overall": "Overall consistency",
                "coverage": "Evidence coverage",
                "coverage_count": "{scored} / {total} dimensions",
                "execution": "Execution success rate",
                "execution_count": "{succeeded} / {total} cases",
                "selected_dimensions": "Evaluation dimensions",
                "gap": "Migration differences",
                "limitations": "Evaluation limitations",
                "case": "Case {index} · {case_id}",
                "agent_output": "Agent output",
                "runtime_data": "Runtime raw observable data",
                "runtime_size": "{captured} / {original} bytes",
                "truncated": "truncated",
                "no_runtime_data": "No data captured",
                "case_results": "Case results and evidence",
                "model": "Model",
                "artifact": "Migration artifact",
                "separator": ": ",
            }
            if locale == "en-US"
            else {
                "title": "迁移效果评测报告",
                "attempt": "第 {attempt} 次评测 · {created_at}",
                "dataset": "评测集 {version}",
                "overall": "综合一致性",
                "coverage": "证据覆盖率",
                "coverage_count": "{scored} / {total} 个维度",
                "execution": "执行成功率",
                "execution_count": "{succeeded} / {total} 个用例",
                "selected_dimensions": "本次评测维度",
                "gap": "迁移差距说明",
                "limitations": "评测限制",
                "case": "用例 {index} · {case_id}",
                "agent_output": "Agent 输出",
                "runtime_data": "Runtime 原始可观察数据",
                "runtime_size": "{captured} / {original} 字节",
                "truncated": "已截断",
                "no_runtime_data": "未采集到数据",
                "case_results": "用例结果与证据",
                "model": "模型",
                "artifact": "迁移产物",
                "separator": "：",
            }
        )
        score_text = "N/A" if score is None else f"{score}/100"
        labels = {item.id: item.localized(locale)[0] for item in EVALUATION_DIMENSIONS}
        report_dimensions = report.get("dimensions")
        assert isinstance(report_dimensions, list)
        selected_dimension_text = (", " if locale == "en-US" else "、").join(
            labels.get(str(item), str(item)) for item in report_dimensions
        )
        dimension_cards: list[str] = []
        dimensions = summary.get("dimensions")
        assert isinstance(dimensions, list)
        for item in dimensions:
            assert isinstance(item, dict)
            item_score = item.get("score")
            item_score_text = "N/A" if item_score is None else f"{item_score}/100"
            dimension_cards.append(
                '<article class="dimension"><span>'
                f"{escape(labels.get(str(item['id']), str(item['id'])))}</span>"
                f"<strong>{escape(item_score_text)}</strong>"
                f"<p>{escape(item['reason'])}</p></article>"
            )
        limitations = report.get("limitations")
        assert isinstance(limitations, list)
        limitation_html = "".join(f"<li>{escape(item)}</li>" for item in limitations)
        cases = report.get("cases")
        assert isinstance(cases, list)
        case_html: list[str] = []
        for index, case in enumerate(cases, start=1):
            assert isinstance(case, dict)
            output = cast(dict[str, object], case["output"])
            runtime_observation = cast(dict[str, object], case["runtime_observation"])
            execution_result = cast(dict[str, object], case["execution"])
            results = cast(list[dict[str, object]], case["dimensions"])
            result_html = []
            for result in results:
                result_score = result.get("score")
                result_score_text = (
                    "N/A" if result_score is None else f"{result_score}/100"
                )
                evidence = cast(list[object], result.get("evidence", []))
                evidence_html = "".join(f"<li>{escape(item)}</li>" for item in evidence)
                result_html.append(
                    '<section class="case-dimension"><header><strong>'
                    f"{escape(labels.get(str(result['id']), str(result['id'])))}</strong>"
                    f"<b>{escape(result_score_text)}</b></header><p>{escape(result['reason'])}</p>"
                    f"{'<ul>' + evidence_html + '</ul>' if evidence_html else ''}</section>"
                )
            error = execution_result.get("error")
            error_html = ""
            if isinstance(error, dict):
                error_html = f'<p class="error">{escape(error.get("message", ""))}</p>'
            runtime_text = str(runtime_observation["text"])
            runtime_size = copy["runtime_size"].format(
                captured=escape(runtime_observation["captured_bytes"]),
                original=escape(runtime_observation["original_bytes"]),
            )
            if runtime_observation["truncated"] is True:
                runtime_size += f" · {copy['truncated']}"
            runtime_html = (
                '<details class="runtime-observation"><summary>'
                f"<span>{copy['runtime_data']}</span>"
                f"<small>{runtime_size}</small></summary>"
                f"<pre>{escape(runtime_text)}</pre></details>"
                if runtime_text
                else (
                    '<details class="runtime-observation"><summary>'
                    f"<span>{copy['runtime_data']}</span>"
                    f"<small>{copy['no_runtime_data']}</small></summary></details>"
                )
            )
            case_html.append(
                '<details class="case"><summary><span>'
                f"{escape(copy['case'].format(index=index, case_id=case['case_id']))}</span>"
                f"<b>{escape(execution_result['state'])}</b></summary>{error_html}"
                f"<h3>{copy['agent_output']}</h3><pre>{escape(output['text'])}</pre>"
                f"{runtime_html}"
                f'<div class="case-dimensions">{"".join(result_html)}</div></details>'
            )
        attempt_text = copy["attempt"].format(
            attempt=report["attempt"],
            created_at=report["created_at"],
        )
        dataset_text = copy["dataset"].format(version=report["dataset_version"])
        coverage_count = copy["coverage_count"].format(
            scored=coverage["scored"],
            total=coverage["total"],
        )
        execution_count = copy["execution_count"].format(
            succeeded=execution["succeeded"],
            total=execution["total"],
        )
        return f"""<!doctype html>
<html lang="{locale}"><head><meta charset="utf-8"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{copy["title"]}</title><style>
:root{{color-scheme:light;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;color:#18212f;background:#f6f8fb}}*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1080px;margin:auto;padding:32px}}header.hero{{display:flex;justify-content:space-between;gap:24px;align-items:start;margin-bottom:20px}}h1{{font-size:26px;margin:0 0 8px}}.muted,small{{color:#647084}}code{{overflow-wrap:anywhere}}.meta{{display:grid;gap:5px;font-size:12px;color:#647084}}.metrics,.dimensions{{display:grid;gap:12px;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));margin:16px 0}}.metric,.dimension,.panel,.case{{border:1px solid #dfe4ec;border-radius:12px;background:#fff}}.metric{{padding:16px}}.metric span,.dimension span{{display:block;color:#647084;font-size:12px}}.metric strong{{display:block;font-size:28px;margin-top:6px}}.dimension{{padding:14px}}.dimension strong{{display:block;font-size:20px;margin:5px 0}}p{{line-height:1.6}}.panel{{padding:16px;margin:16px 0}}.panel h2{{font-size:16px;margin:0 0 8px}}.case{{margin:10px 0;padding:0 14px}}.case summary{{display:flex;justify-content:space-between;gap:12px;padding:14px 0;cursor:pointer}}.case h3{{font-size:13px}}pre{{max-height:320px;overflow:auto;padding:12px;border-radius:8px;background:#f2f4f7;white-space:pre-wrap;word-break:break-word}}.runtime-observation{{margin:12px 0;border:1px solid #e6eaf0;border-radius:8px}}.runtime-observation summary{{padding:10px 12px;font-size:12px}}.runtime-observation pre{{max-height:240px;margin:0 10px 10px}}.case-dimensions{{display:grid;gap:8px;margin:12px 0 16px}}.case-dimension{{padding:10px;border:1px solid #e6eaf0;border-radius:8px}}.case-dimension header{{display:flex;justify-content:space-between}}.case-dimension p,.case-dimension li{{font-size:12px;color:#526075}}.error{{color:#b42318}}@media(max-width:600px){{main{{padding:18px}}header.hero{{display:block}}}}
</style></head><body><main><header class="hero"><div><h1>{copy["title"]}</h1><p class="muted">{escape(attempt_text)}</p></div><div class="meta"><code>{escape(report["task_id"])}</code><span>{escape(dataset_text)}</span><span>Prompt v{escape(report["prompt_version"])}</span></div></header>
<section class="metrics"><article class="metric"><span>{copy["overall"]}</span><strong>{escape(score_text)}</strong></article><article class="metric"><span>{copy["coverage"]}</span><strong>{escape(coverage["rate"])}%</strong><small>{escape(coverage_count)}</small></article><article class="metric"><span>{copy["execution"]}</span><strong>{escape(execution["success_rate"])}%</strong><small>{escape(execution_count)}</small></article></section>
<section class="panel"><h2>{copy["selected_dimensions"]}</h2><p>{escape(selected_dimension_text)}</p></section>
<section class="dimensions">{"".join(dimension_cards)}</section><section class="panel"><h2>{copy["gap"]}</h2><p>{escape(report["migration_gap_description"])}</p></section>
{f'<section class="panel"><h2>{copy["limitations"]}</h2><ul>{limitation_html}</ul></section>' if limitation_html else ""}
<section><h2>{copy["case_results"]}</h2>{"".join(case_html)}</section><section class="panel meta"><span>{copy["model"]}{copy["separator"]}{escape(model["id"])}</span><span>Codex{copy["separator"]}{escape(model["codex_version"])}</span><span>AgentKit CLI{copy["separator"]}{escape(model["agentkit_cli_version"])}</span><span>{copy["artifact"]}{copy["separator"]}<code>{escape(report["artifact_sha256"])}</code></span></section>
</main></body></html>"""

    @staticmethod
    def _evaluation_environment(
        artifact: dict[str, object],
    ) -> _EvaluationEnvironment:
        value = artifact.get("environment")
        if not isinstance(value, dict):
            return {"required": [], "optional": [], "defaults": {}}
        names = {
            field: [str(item) for item in value.get(field, [])]
            if isinstance(value.get(field), list)
            else []
            for field in ("required", "optional")
        }
        declared = set(names["required"] + names["optional"])
        source_defaults = value.get("defaults")
        defaults = (
            {
                str(key): item
                for key, item in source_defaults.items()
                if isinstance(key, str)
                and key in declared
                and isinstance(item, str)
                and item
            }
            if isinstance(source_defaults, dict)
            else {}
        )
        return {
            "required": names["required"],
            "optional": names["optional"],
            "defaults": defaults,
        }

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
