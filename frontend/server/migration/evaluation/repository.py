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

"""Owner-scoped immutable TOS assets for migration evaluation."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import EVALUATION_DATASET_MAX_BYTES

_TASK_ID_RE = re.compile(r"^migration-v1-[0-9a-f]{32}$")
_VERSION_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_METADATA_BYTES = 64 * 1024
EVALUATION_REPORT_MAX_BYTES = 16 * 1024 * 1024
logger = logging.getLogger(__name__)


class EvaluationAssetNotFound(LookupError):
    pass


class EvaluationAssetConflict(RuntimeError):
    pass


class EvaluationAssetIntegrityError(RuntimeError):
    pass


class EvaluationAssetStorageUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class EvaluationAssetMetadata:
    schema_version: int
    kind: Literal["dataset", "report"]
    task_id: str
    owner_id: str
    version_id: str
    sha256: str
    size: int
    created_at: str
    acl: Literal["owner"] = "owner"
    case_count: int | None = None
    attempt: int | None = None

    def public(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schemaVersion": self.schema_version,
            "kind": self.kind,
            "assetId": f"{self.task_id}/{self.kind}/{self.version_id}",
            "version": self.version_id,
            "versionId": self.version_id,
            "sha256": self.sha256,
            "sizeBytes": self.size,
            "size": self.size,
            "createdAt": self.created_at,
            "acl": self.acl,
            "viewReady": True,
            "downloadReady": True,
        }
        if self.case_count is not None:
            payload["caseCount"] = self.case_count
        if self.attempt is not None:
            payload["attempt"] = self.attempt
        return payload


class TosMigrationEvaluationRepository:
    """Commit content first and its immutable visibility marker last."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("Migration evaluation storage requires a bucket.")
        self.bucket = bucket.strip()
        self._client_factory = client_factory
        self._prefix = f"{root_prefix.strip('/')}/users"

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
    ) -> EvaluationAssetMetadata:
        metadata = EvaluationAssetMetadata(
            schema_version=1,
            kind="dataset",
            task_id=task_id,
            owner_id=owner_id,
            version_id=version_id,
            sha256=sha256,
            size=len(content),
            case_count=case_count,
            created_at=created_at,
        )
        return self._commit(metadata, content, EVALUATION_DATASET_MAX_BYTES)

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
    ) -> EvaluationAssetMetadata:
        metadata = EvaluationAssetMetadata(
            schema_version=1,
            kind="report",
            task_id=task_id,
            owner_id=owner_id,
            version_id=version_id,
            sha256=sha256,
            size=len(content),
            attempt=attempt,
            created_at=created_at,
        )
        return self._commit(metadata, content, EVALUATION_REPORT_MAX_BYTES)

    def load(
        self,
        *,
        owner_id: str,
        task_id: str,
        kind: Literal["dataset", "report"],
        version_id: str,
    ) -> tuple[EvaluationAssetMetadata, bytes]:
        try:
            return self._load(owner_id, task_id, kind, version_id)
        except (
            EvaluationAssetNotFound,
            EvaluationAssetIntegrityError,
            ValueError,
        ):
            raise
        except Exception as error:
            raise EvaluationAssetStorageUnavailable(
                "评测资产存储暂时不可用，请稍后重试。"
            ) from error

    def _commit(
        self,
        metadata: EvaluationAssetMetadata,
        content: bytes,
        limit: int,
    ) -> EvaluationAssetMetadata:
        try:
            self._validate_metadata(metadata)
            if not content or len(content) > limit:
                raise EvaluationAssetIntegrityError("评测资产超过大小限制。")
            if hashlib.sha256(content).hexdigest() != metadata.sha256:
                raise EvaluationAssetIntegrityError("评测资产摘要校验失败。")
            client = self._client_factory()
            prefix = self._version_prefix(
                metadata.owner_id,
                metadata.task_id,
                metadata.kind,
                metadata.version_id,
            )
            content_key = f"{prefix}/{self._content_name(metadata.kind)}"
            marker_key = f"{prefix}/asset.json"
            marker = json.dumps(
                asdict(metadata),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
            content_created = self._put_immutable(
                client,
                content_key,
                content,
                "application/x-ndjson"
                if metadata.kind == "dataset"
                else "application/json",
                limit,
            )
            try:
                self._put_immutable(
                    client,
                    marker_key,
                    marker,
                    "application/json",
                    _MAX_METADATA_BYTES,
                )
            except Exception:
                if content_created:
                    try:
                        client.delete_object(bucket=self.bucket, key=content_key)
                    except Exception as cleanup_error:
                        logger.warning(
                            "Could not remove uncommitted migration evaluation asset "
                            "key=%s error_type=%s",
                            content_key,
                            type(cleanup_error).__name__,
                        )
                raise
            return metadata
        except (
            EvaluationAssetConflict,
            EvaluationAssetIntegrityError,
            ValueError,
        ):
            raise
        except Exception as error:
            raise EvaluationAssetStorageUnavailable(
                "评测资产存储暂时不可用，请稍后重试。"
            ) from error

    def _load(
        self,
        owner_id: str,
        task_id: str,
        kind: Literal["dataset", "report"],
        version_id: str,
    ) -> tuple[EvaluationAssetMetadata, bytes]:
        prefix = self._version_prefix(owner_id, task_id, kind, version_id)
        client = self._client_factory()
        try:
            marker = self._read(client, f"{prefix}/asset.json", _MAX_METADATA_BYTES)
            content = self._read(
                client,
                f"{prefix}/{self._content_name(kind)}",
                EVALUATION_DATASET_MAX_BYTES
                if kind == "dataset"
                else EVALUATION_REPORT_MAX_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise EvaluationAssetNotFound("评测资产不存在。") from error
            raise
        try:
            payload = json.loads(marker)
            metadata = EvaluationAssetMetadata(**payload)
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise EvaluationAssetIntegrityError("评测资产元数据无效。") from error
        self._validate_metadata(metadata)
        if (
            metadata.owner_id != owner_id
            or metadata.task_id != task_id
            or metadata.kind != kind
            or metadata.version_id != version_id
            or metadata.size != len(content)
            or metadata.sha256 != hashlib.sha256(content).hexdigest()
        ):
            raise EvaluationAssetIntegrityError("评测资产完整性校验失败。")
        return metadata, content

    def _owner_prefix(self, owner_id: str) -> str:
        owner = quote(owner_id.strip(), safe="")
        if not owner:
            raise ValueError("Evaluation owner id cannot be empty.")
        return f"{self._prefix}/{owner}/migration-evaluations"

    def _version_prefix(
        self,
        owner_id: str,
        task_id: str,
        kind: Literal["dataset", "report"],
        version_id: str,
    ) -> str:
        if _TASK_ID_RE.fullmatch(task_id) is None:
            raise ValueError("Invalid migration task id.")
        if _VERSION_ID_RE.fullmatch(version_id) is None:
            raise ValueError("Invalid evaluation asset version id.")
        plural = "datasets" if kind == "dataset" else "reports"
        return f"{self._owner_prefix(owner_id)}/tasks/{task_id}/{plural}/{version_id}"

    @staticmethod
    def _content_name(kind: Literal["dataset", "report"]) -> str:
        return "data.jsonl" if kind == "dataset" else "report.json"

    @staticmethod
    def _validate_metadata(metadata: EvaluationAssetMetadata) -> None:
        if (
            metadata.schema_version != 1
            or metadata.acl != "owner"
            or _TASK_ID_RE.fullmatch(metadata.task_id) is None
            or _VERSION_ID_RE.fullmatch(metadata.version_id) is None
            or _SHA256_RE.fullmatch(metadata.sha256) is None
            or not metadata.owner_id.strip()
            or not metadata.created_at.strip()
            or metadata.size <= 0
            or (
                metadata.kind == "dataset"
                and (metadata.case_count is None or not 1 <= metadata.case_count <= 100)
            )
            or (
                metadata.kind == "report"
                and (metadata.attempt is None or not 1 <= metadata.attempt <= 100)
            )
        ):
            raise EvaluationAssetIntegrityError("评测资产元数据无效。")

    def _put_immutable(
        self,
        client: Any,
        key: str,
        content: bytes,
        content_type: str,
        limit: int,
    ) -> bool:
        try:
            client.put_object(
                bucket=self.bucket,
                key=key,
                content=content,
                content_length=len(content),
                content_type=content_type,
                forbid_overwrite=True,
            )
            return True
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            if self._read(client, key, limit) == content:
                return False
            raise EvaluationAssetConflict("评测资产版本已存在。") from error

    def _read(self, client: Any, key: str, limit: int) -> bytes:
        response = client.get_object(bucket=self.bucket, key=key)
        content = (
            response.read(limit + 1)
            if hasattr(response, "read")
            else b"".join(response)
        )
        if not isinstance(content, bytes) or len(content) > limit:
            raise EvaluationAssetIntegrityError("评测资产无效或超过大小限制。")
        return content


def _status_code(error: BaseException) -> int | None:
    for current in (error, error.__cause__, error.__context__):
        if current is None:
            continue
        for name in ("status_code", "status", "http_status"):
            value = getattr(current, name, None)
            if value is None:
                continue
            try:
                return int(value)
            except (TypeError, ValueError):
                continue
    return None


__all__ = [
    "EVALUATION_REPORT_MAX_BYTES",
    "EvaluationAssetConflict",
    "EvaluationAssetIntegrityError",
    "EvaluationAssetMetadata",
    "EvaluationAssetNotFound",
    "EvaluationAssetStorageUnavailable",
    "TosMigrationEvaluationRepository",
]
