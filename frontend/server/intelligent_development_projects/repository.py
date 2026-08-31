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

"""Owner-scoped TOS persistence for intelligent-development source versions."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from collections.abc import Callable
from typing import Any, TypeVar
from urllib.parse import quote

from pydantic import ValidationError

from frontend.server.source_project_limits import (
    SOURCE_PROJECT_MAX_BYTES,
    SOURCE_PROJECT_MAX_REPORT_BYTES,
)
from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import (
    IntelligentDevelopmentProject,
    IntelligentDevelopmentSessionBinding,
    IntelligentDevelopmentVersion,
    SourceProjectOrigin,
    StoredDevelopmentVersion,
)

_ID_RE = re.compile(r"[0-9a-f]{32}")
_VERSION_MARKER_RE = re.compile(
    r"/projects/(?P<project>[0-9a-f]{32})/versions/[0-9a-f]{32}/version\.json$"
)
_MAX_JSON_BYTES = 256 * 1024
_MAX_ARTIFACT_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_REPORT_BYTES = SOURCE_PROJECT_MAX_REPORT_BYTES
T = TypeVar("T")
logger = logging.getLogger(__name__)


class IntelligentDevelopmentProjectNotFound(LookupError):
    pass


class IntelligentDevelopmentVersionNotFound(LookupError):
    pass


class IntelligentDevelopmentProjectConflict(RuntimeError):
    pass


class IntelligentDevelopmentVersionIntegrityError(RuntimeError):
    pass


class IntelligentDevelopmentProjectStorageUnavailable(RuntimeError):
    pass


class TosIntelligentDevelopmentProjectRepository:
    """Store project summaries and immutable full-source versions in TOS."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS intelligent-development storage requires a bucket.")
        self.bucket = bucket.strip()
        self._client_factory = client_factory
        self._prefix = f"{root_prefix.strip('/')}/users"

    async def list_projects(self, owner_id: str) -> list[IntelligentDevelopmentProject]:
        return await self._run(self._list_projects, owner_id)

    async def get_project(
        self, owner_id: str, project_id: str
    ) -> IntelligentDevelopmentProject:
        return await self._run(self._get_project, owner_id, project_id)

    async def list_versions(
        self, owner_id: str, project_id: str
    ) -> list[IntelligentDevelopmentVersion]:
        return await self._run(self._list_versions, owner_id, project_id)

    async def get_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentVersion:
        return await self._run(self._get_version, owner_id, project_id, version_id)

    async def load_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> StoredDevelopmentVersion:
        return await self._run(self._load_version, owner_id, project_id, version_id)

    async def commit_version(
        self,
        owner_id: str,
        project_name: str,
        metadata: IntelligentDevelopmentVersion,
        artifact: bytes,
        validation_report: bytes,
        *,
        project_origin: SourceProjectOrigin = "intelligent-development",
    ) -> IntelligentDevelopmentProject:
        return await self._run(
            self._commit_version,
            owner_id,
            project_name,
            metadata,
            artifact,
            validation_report,
            project_origin,
        )

    async def delete_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentProject | None:
        return await self._run(self._delete_version, owner_id, project_id, version_id)

    async def put_binding(self, binding: IntelligentDevelopmentSessionBinding) -> None:
        await self._run(self._put_binding, binding)

    async def get_binding(
        self, owner_id: str, session_id: str
    ) -> IntelligentDevelopmentSessionBinding:
        return await self._run(self._get_binding, owner_id, session_id)

    async def delete_binding(self, owner_id: str, session_id: str) -> None:
        await self._run(self._delete_binding, owner_id, session_id)

    async def _run(self, function: Callable[..., T], *args: object) -> T:
        try:
            return await asyncio.to_thread(function, *args)
        except (
            IntelligentDevelopmentProjectNotFound,
            IntelligentDevelopmentVersionNotFound,
            IntelligentDevelopmentProjectConflict,
            IntelligentDevelopmentVersionIntegrityError,
            ValueError,
        ):
            raise
        except Exception as error:
            raise IntelligentDevelopmentProjectStorageUnavailable(
                "项目存储暂时不可用，请稍后重试。"
            ) from error

    def _list_projects(self, owner_id: str) -> list[IntelligentDevelopmentProject]:
        client = self._client_factory()
        prefix = f"{self._projects_prefix(owner_id)}/"
        keys = self._list_keys(client, prefix)
        committed_counts: dict[str, int] = {}
        for key in keys:
            match = _VERSION_MARKER_RE.search(key)
            if match is not None:
                project_id = match.group("project")
                committed_counts[project_id] = committed_counts.get(project_id, 0) + 1
        projects: list[IntelligentDevelopmentProject] = []
        for key in keys:
            if not key.endswith("/summary.json"):
                continue
            try:
                project = IntelligentDevelopmentProject.model_validate_json(
                    self._read_object(client, key, _MAX_JSON_BYTES)
                )
            except (ValidationError, ValueError) as error:
                raise IntelligentDevelopmentVersionIntegrityError(
                    "项目记录格式无效。"
                ) from error
            if project.owner_id != owner_id:
                continue
            committed_count = committed_counts.get(project.project_id, 0)
            if committed_count == 0:
                continue
            if committed_count != project.version_count:
                versions = self._list_committed_versions(
                    client, owner_id, project.project_id
                )
                latest = max(
                    versions,
                    key=lambda item: (item.created_at, item.version_id),
                )
                project = project.model_copy(
                    update={
                        "updated_at": latest.created_at,
                        "latest_version_id": latest.version_id,
                        "latest_version_created_at": latest.created_at,
                        "latest_version_verified": latest.verified,
                        "latest_agent_name": latest.agent_name,
                        "version_count": len(versions),
                    }
                )
            projects.append(project)
        return sorted(
            projects,
            key=lambda item: (item.updated_at, item.project_id),
            reverse=True,
        )

    def _get_project(
        self, owner_id: str, project_id: str
    ) -> IntelligentDevelopmentProject:
        self._validate_id(project_id, project=True)
        try:
            content = self._read_object(
                self._client_factory(),
                self._summary_key(owner_id, project_id),
                _MAX_JSON_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise IntelligentDevelopmentProjectNotFound(
                    "项目不存在或已被删除。"
                ) from error
            raise
        try:
            project = IntelligentDevelopmentProject.model_validate_json(content)
        except ValidationError as error:
            raise IntelligentDevelopmentVersionIntegrityError(
                "项目记录格式无效。"
            ) from error
        if project.owner_id != owner_id or project.project_id != project_id:
            raise IntelligentDevelopmentProjectNotFound("项目不存在或已被删除。")
        return project

    def _list_versions(
        self, owner_id: str, project_id: str
    ) -> list[IntelligentDevelopmentVersion]:
        _ = self._get_project(owner_id, project_id)
        client = self._client_factory()
        prefix = f"{self._project_prefix(owner_id, project_id)}/versions/"
        versions: list[IntelligentDevelopmentVersion] = []
        for key in self._list_keys(client, prefix):
            if not key.endswith("/version.json"):
                continue
            try:
                version = IntelligentDevelopmentVersion.model_validate_json(
                    self._read_object(client, key, _MAX_JSON_BYTES)
                )
            except (ValidationError, ValueError) as error:
                raise IntelligentDevelopmentVersionIntegrityError(
                    "项目版本记录格式无效。"
                ) from error
            if version.project_id != project_id:
                raise IntelligentDevelopmentVersionIntegrityError(
                    "项目版本归属校验失败。"
                )
            versions.append(version)
        return sorted(
            versions,
            key=lambda item: (item.created_at, item.version_id),
            reverse=True,
        )

    def _get_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentVersion:
        self._validate_id(project_id, project=True)
        self._validate_id(version_id, project=False)
        try:
            content = self._read_object(
                self._client_factory(),
                self._version_marker_key(owner_id, project_id, version_id),
                _MAX_JSON_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise IntelligentDevelopmentVersionNotFound(
                    "项目版本不存在或已被删除。"
                ) from error
            raise
        try:
            version = IntelligentDevelopmentVersion.model_validate_json(content)
        except ValidationError as error:
            raise IntelligentDevelopmentVersionIntegrityError(
                "项目版本记录格式无效。"
            ) from error
        if version.project_id != project_id or version.version_id != version_id:
            raise IntelligentDevelopmentVersionNotFound("项目版本不存在或已被删除。")
        return version

    def _load_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> StoredDevelopmentVersion:
        metadata = self._get_version(owner_id, project_id, version_id)
        client = self._client_factory()
        prefix = self._version_prefix(owner_id, project_id, version_id)
        try:
            artifact = self._read_object(
                client, f"{prefix}/source.zip", _MAX_ARTIFACT_BYTES
            )
            report = self._read_object(
                client, f"{prefix}/validation.json", _MAX_REPORT_BYTES
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise IntelligentDevelopmentVersionIntegrityError(
                    "项目版本源码不完整。"
                ) from error
            raise
        if (
            hashlib.sha256(artifact).hexdigest() != metadata.artifact_sha256
            or hashlib.sha256(report).hexdigest() != metadata.validation_report_sha256
            or len(artifact) != metadata.artifact_size
        ):
            raise IntelligentDevelopmentVersionIntegrityError(
                "项目版本源码完整性校验失败。"
            )
        return StoredDevelopmentVersion(metadata, artifact, report)

    def _commit_version(
        self,
        owner_id: str,
        project_name: str,
        metadata: IntelligentDevelopmentVersion,
        artifact: bytes,
        validation_report: bytes,
        project_origin: SourceProjectOrigin,
    ) -> IntelligentDevelopmentProject:
        self._validate_id(metadata.project_id, project=True)
        self._validate_id(metadata.version_id, project=False)
        if hashlib.sha256(artifact).hexdigest() != metadata.artifact_sha256:
            raise IntelligentDevelopmentVersionIntegrityError(
                "待保存源码的摘要校验失败。"
            )
        if (
            hashlib.sha256(validation_report).hexdigest()
            != metadata.validation_report_sha256
        ):
            raise IntelligentDevelopmentVersionIntegrityError(
                "待保存验证报告的摘要校验失败。"
            )
        if len(artifact) != metadata.artifact_size:
            raise IntelligentDevelopmentVersionIntegrityError(
                "待保存源码的大小校验失败。"
            )
        if not artifact or len(artifact) > _MAX_ARTIFACT_BYTES:
            raise IntelligentDevelopmentVersionIntegrityError(
                "待保存源码超过大小限制。"
            )
        if not validation_report or len(validation_report) > _MAX_REPORT_BYTES:
            raise IntelligentDevelopmentVersionIntegrityError(
                "待保存验证报告超过大小限制。"
            )
        client = self._client_factory()
        prefix = self._version_prefix(
            owner_id, metadata.project_id, metadata.version_id
        )
        artifact_key = f"{prefix}/source.zip"
        report_key = f"{prefix}/validation.json"
        marker_key = f"{prefix}/version.json"
        marker = metadata.model_dump_json(by_alias=True).encode("utf-8")
        created_keys: list[str] = []
        try:
            if self._put_immutable_bytes(
                client,
                artifact_key,
                artifact,
                "application/zip",
                _MAX_ARTIFACT_BYTES,
            ):
                created_keys.append(artifact_key)
            if self._put_immutable_bytes(
                client,
                report_key,
                validation_report,
                "application/json",
                _MAX_REPORT_BYTES,
            ):
                created_keys.append(report_key)
            marker_created = self._put_immutable_bytes(
                client,
                marker_key,
                marker,
                "application/json",
                _MAX_JSON_BYTES,
            )
            if marker_created:
                created_keys.append(marker_key)
        except Exception:
            self._delete_uncommitted_objects(client, created_keys)
            raise

        versions = self._list_committed_versions(client, owner_id, metadata.project_id)
        previous = self._project_if_present(client, owner_id, metadata.project_id)
        latest = max(versions, key=lambda item: (item.created_at, item.version_id))
        created_at = (
            previous.created_at
            if previous is not None
            else min(item.created_at for item in versions)
        )
        project = IntelligentDevelopmentProject(
            projectId=metadata.project_id,
            ownerId=owner_id,
            origin=previous.origin if previous is not None else project_origin,
            name=(
                previous.name
                if previous is not None
                else (project_name.strip() or latest.agent_name)[:128]
            ),
            createdAt=created_at,
            updatedAt=latest.created_at,
            latestVersionId=latest.version_id,
            latestVersionCreatedAt=latest.created_at,
            latestVersionVerified=latest.verified,
            latestAgentName=latest.agent_name,
            versionCount=len(versions),
        )
        try:
            self._put_json(
                client,
                self._summary_key(owner_id, metadata.project_id),
                project,
            )
        except Exception:
            if marker_created:
                try:
                    client.delete_object(bucket=self.bucket, key=marker_key)
                except Exception:
                    logger.exception(
                        "Could not roll back intelligent-development version marker %s",
                        metadata.version_id,
                    )
                else:
                    self._delete_uncommitted_objects(
                        client,
                        [key for key in created_keys if key != marker_key],
                    )
            raise
        return project

    def _delete_version(
        self, owner_id: str, project_id: str, version_id: str
    ) -> IntelligentDevelopmentProject | None:
        project = self._get_project(owner_id, project_id)
        metadata = self._get_version(owner_id, project_id, version_id)
        client = self._client_factory()
        prefix = self._version_prefix(owner_id, project_id, version_id)
        marker_key = f"{prefix}/version.json"
        client.delete_object(bucket=self.bucket, key=marker_key)
        try:
            remaining = self._list_committed_versions(client, owner_id, project_id)
            if not remaining:
                client.delete_object(
                    bucket=self.bucket,
                    key=self._summary_key(owner_id, project_id),
                )
                updated = None
            else:
                latest = max(
                    remaining,
                    key=lambda item: (item.created_at, item.version_id),
                )
                updated = project.model_copy(
                    update={
                        "updated_at": latest.created_at,
                        "latest_version_id": latest.version_id,
                        "latest_version_created_at": latest.created_at,
                        "latest_version_verified": latest.verified,
                        "latest_agent_name": latest.agent_name,
                        "version_count": len(remaining),
                    }
                )
                self._put_json(
                    client,
                    self._summary_key(owner_id, project_id),
                    updated,
                )
        except Exception:
            try:
                self._put_immutable_bytes(
                    client,
                    marker_key,
                    metadata.model_dump_json(by_alias=True).encode("utf-8"),
                    "application/json",
                    _MAX_JSON_BYTES,
                )
            except Exception:
                logger.exception(
                    "Could not restore intelligent-development version marker %s",
                    version_id,
                )
            raise

        for key in (f"{prefix}/source.zip", f"{prefix}/validation.json"):
            try:
                client.delete_object(bucket=self.bucket, key=key)
            except Exception:
                logger.warning(
                    "Committed deletion but could not clean intelligent-development object %s",
                    key,
                    exc_info=True,
                )
        return updated

    def _put_binding(self, binding: IntelligentDevelopmentSessionBinding) -> None:
        self._put_json(
            self._client_factory(),
            self._binding_key(binding.owner_id, binding.session_id),
            binding,
        )

    def _get_binding(
        self, owner_id: str, session_id: str
    ) -> IntelligentDevelopmentSessionBinding:
        try:
            content = self._read_object(
                self._client_factory(),
                self._binding_key(owner_id, session_id),
                _MAX_JSON_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise IntelligentDevelopmentProjectNotFound(
                    "开发会话未绑定项目。"
                ) from error
            raise
        try:
            binding = IntelligentDevelopmentSessionBinding.model_validate_json(content)
        except ValidationError as error:
            raise IntelligentDevelopmentVersionIntegrityError(
                "开发会话的项目绑定格式无效。"
            ) from error
        if binding.owner_id != owner_id or binding.session_id != session_id:
            raise IntelligentDevelopmentProjectNotFound("开发会话未绑定项目。")
        return binding

    def _delete_binding(self, owner_id: str, session_id: str) -> None:
        self._client_factory().delete_object(
            bucket=self.bucket,
            key=self._binding_key(owner_id, session_id),
        )

    def _list_committed_versions(
        self, client: Any, owner_id: str, project_id: str
    ) -> list[IntelligentDevelopmentVersion]:
        prefix = f"{self._project_prefix(owner_id, project_id)}/versions/"
        versions: list[IntelligentDevelopmentVersion] = []
        for key in self._list_keys(client, prefix):
            if key.endswith("/version.json"):
                try:
                    version = IntelligentDevelopmentVersion.model_validate_json(
                        self._read_object(client, key, _MAX_JSON_BYTES)
                    )
                except (ValidationError, ValueError) as error:
                    raise IntelligentDevelopmentVersionIntegrityError(
                        "项目版本记录格式无效。"
                    ) from error
                if version.project_id != project_id:
                    raise IntelligentDevelopmentVersionIntegrityError(
                        "项目版本归属校验失败。"
                    )
                versions.append(version)
        return versions

    def _project_if_present(
        self, client: Any, owner_id: str, project_id: str
    ) -> IntelligentDevelopmentProject | None:
        try:
            content = self._read_object(
                client, self._summary_key(owner_id, project_id), _MAX_JSON_BYTES
            )
        except Exception as error:
            if _status_code(error) == 404:
                return None
            raise
        try:
            return IntelligentDevelopmentProject.model_validate_json(content)
        except ValidationError as error:
            raise IntelligentDevelopmentVersionIntegrityError(
                "项目记录格式无效。"
            ) from error

    def _owner_prefix(self, owner_id: str) -> str:
        owner = quote(owner_id.strip(), safe="")
        if not owner:
            raise ValueError("Intelligent-development owner id cannot be empty.")
        return f"{self._prefix}/{owner}/intelligent-development"

    def _projects_prefix(self, owner_id: str) -> str:
        return f"{self._owner_prefix(owner_id)}/projects"

    def _project_prefix(self, owner_id: str, project_id: str) -> str:
        self._validate_id(project_id, project=True)
        return f"{self._projects_prefix(owner_id)}/{project_id}"

    def _version_prefix(self, owner_id: str, project_id: str, version_id: str) -> str:
        self._validate_id(version_id, project=False)
        return f"{self._project_prefix(owner_id, project_id)}/versions/{version_id}"

    def _summary_key(self, owner_id: str, project_id: str) -> str:
        return f"{self._project_prefix(owner_id, project_id)}/summary.json"

    def _version_marker_key(
        self, owner_id: str, project_id: str, version_id: str
    ) -> str:
        return f"{self._version_prefix(owner_id, project_id, version_id)}/version.json"

    def _binding_key(self, owner_id: str, session_id: str) -> str:
        session = quote(session_id.strip(), safe="")
        if not session:
            raise ValueError("Intelligent-development session id cannot be empty.")
        return f"{self._owner_prefix(owner_id)}/sessions/{session}/binding.json"

    @staticmethod
    def _validate_id(value: str, *, project: bool) -> None:
        if _ID_RE.fullmatch(value) is None:
            if project:
                raise IntelligentDevelopmentProjectNotFound("项目不存在或已被删除。")
            raise IntelligentDevelopmentVersionNotFound("项目版本不存在或已被删除。")

    def _list_keys(self, client: Any, prefix: str) -> list[str]:
        token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self.bucket,
                prefix=prefix,
                continuation_token=token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if getattr(item, "key", None)
            )
            if not getattr(output, "is_truncated", False):
                return keys
            token = str(getattr(output, "next_continuation_token", "") or "")
            if not token:
                raise RuntimeError("TOS returned a truncated listing without a token.")

    def _read_object(self, client: Any, key: str, limit: int) -> bytes:
        response = client.get_object(bucket=self.bucket, key=key)
        content = (
            response.read(limit + 1)
            if hasattr(response, "read")
            else b"".join(response)
        )
        if not isinstance(content, bytes) or len(content) > limit:
            raise IntelligentDevelopmentVersionIntegrityError(
                "项目存储对象无效或超过大小限制。"
            )
        return content

    def _put_json(
        self,
        client: Any,
        key: str,
        value: Any,
        *,
        forbid_overwrite: bool = False,
    ) -> None:
        content = value.model_dump_json(by_alias=True).encode("utf-8")
        if len(content) > _MAX_JSON_BYTES:
            raise ValueError("Intelligent-development metadata is too large.")
        self._put_bytes(
            client,
            key,
            content,
            "application/json",
            forbid_overwrite=forbid_overwrite,
        )

    def _put_bytes(
        self,
        client: Any,
        key: str,
        content: bytes,
        content_type: str,
        *,
        forbid_overwrite: bool = False,
    ) -> None:
        client.put_object(
            bucket=self.bucket,
            key=key,
            content=content,
            content_length=len(content),
            content_type=content_type,
            forbid_overwrite=forbid_overwrite,
        )

    def _put_immutable_bytes(
        self,
        client: Any,
        key: str,
        content: bytes,
        content_type: str,
        limit: int,
    ) -> bool:
        """Create immutable content, accepting an exact idempotent retry."""
        try:
            self._put_bytes(
                client,
                key,
                content,
                content_type,
                forbid_overwrite=True,
            )
            return True
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            existing = self._read_object(client, key, limit)
            if existing == content:
                return False
            raise IntelligentDevelopmentProjectConflict("项目版本已存在。") from error

    def _delete_uncommitted_objects(self, client: Any, keys: list[str]) -> None:
        for key in reversed(keys):
            try:
                client.delete_object(bucket=self.bucket, key=key)
            except Exception:
                logger.warning(
                    "Could not clean uncommitted intelligent-development object %s",
                    key,
                    exc_info=True,
                )


def _status_code(error: BaseException) -> int | None:
    for current in (error, error.__cause__, error.__context__):
        if current is None:
            continue
        for name in ("status_code", "status", "http_status"):
            value = getattr(current, name, None)
            try:
                return int(value) if value is not None else None
            except (TypeError, ValueError):
                continue
    return None


__all__ = [
    "IntelligentDevelopmentProjectConflict",
    "IntelligentDevelopmentProjectNotFound",
    "IntelligentDevelopmentProjectStorageUnavailable",
    "IntelligentDevelopmentVersionIntegrityError",
    "IntelligentDevelopmentVersionNotFound",
    "TosIntelligentDevelopmentProjectRepository",
]
