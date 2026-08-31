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

"""TOS persistence for Studio environment definitions and build versions."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import EnvironmentBuild, EnvironmentRecord, EnvironmentSkillManifest

_ID_RE = re.compile(r"[0-9a-f]{32}")
_VERSION_RE = re.compile(r"[0-9]{8}T[0-9]{6}Z-[0-9a-f]{8}")
_MAX_JSON_BYTES = 256 * 1024
_MAX_LOG_BYTES = 512 * 1024


class EnvironmentNotFound(LookupError):
    pass


class EnvironmentConflict(RuntimeError):
    pass


class EnvironmentStorageUnavailable(RuntimeError):
    pass


class TosEnvironmentRepository:
    """Persist environments under one owner-scoped, versioned object tree."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS environment storage requires a bucket.")
        self.bucket = bucket.strip()
        self._client_factory = client_factory
        self._prefix = f"{root_prefix.strip('/')}/environments"

    async def list(self, owner_id: str) -> list[EnvironmentRecord]:
        return await asyncio.to_thread(self._list, owner_id)

    async def get(self, owner_id: str, environment_id: str) -> EnvironmentRecord:
        return await asyncio.to_thread(self._get, owner_id, environment_id)

    async def create(self, record: EnvironmentRecord) -> EnvironmentRecord:
        return await asyncio.to_thread(self._create, record)

    async def update(self, record: EnvironmentRecord) -> EnvironmentRecord:
        return await asyncio.to_thread(self._update, record)

    async def delete(self, owner_id: str, environment_id: str) -> None:
        await asyncio.to_thread(self._delete, owner_id, environment_id)

    async def create_version(
        self,
        record: EnvironmentRecord,
        build: EnvironmentBuild,
        dockerfile: str,
        context: bytes,
        skill_manifest: EnvironmentSkillManifest | None = None,
        skill_files: list[tuple[str, bytes]] | None = None,
    ) -> EnvironmentRecord:
        return await asyncio.to_thread(
            self._create_version,
            record,
            build,
            dockerfile,
            context,
            skill_manifest,
            skill_files or [],
        )

    async def put_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str, content: bytes
    ) -> None:
        await asyncio.to_thread(
            self._put_skill_asset, owner_id, environment_id, artifact_id, content
        )

    async def get_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str
    ) -> bytes:
        return await asyncio.to_thread(
            self._get_skill_asset, owner_id, environment_id, artifact_id
        )

    async def get_skill_manifest(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentSkillManifest:
        return await asyncio.to_thread(
            self._get_skill_manifest, owner_id, environment_id, version_id
        )

    async def get_version_config(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentRecord:
        return await asyncio.to_thread(
            self._get_version_config, owner_id, environment_id, version_id
        )

    async def get_version_skill_files(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> list[tuple[str, bytes]]:
        return await asyncio.to_thread(
            self._get_version_skill_files, owner_id, environment_id, version_id
        )

    async def get_build(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> EnvironmentBuild:
        return await asyncio.to_thread(
            self._get_build, owner_id, environment_id, version_id
        )

    async def update_build(
        self,
        owner_id: str,
        build: EnvironmentBuild,
        *,
        log: str | None = None,
    ) -> EnvironmentBuild:
        return await asyncio.to_thread(self._update_build, owner_id, build, log)

    async def get_build_log(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> str:
        return await asyncio.to_thread(
            self._get_build_log,
            owner_id,
            environment_id,
            version_id,
        )

    def context_key(self, owner_id: str, environment_id: str, version_id: str) -> str:
        return f"{self._version_prefix(owner_id, environment_id, version_id)}/context.tar.gz"

    def _list(self, owner_id: str) -> list[EnvironmentRecord]:
        client = self._client_factory()
        owner_prefix = f"{self._owner_prefix(owner_id)}/"
        records: list[EnvironmentRecord] = []
        for key in self._list_keys(client, owner_prefix):
            if not key.endswith("/summary.json"):
                continue
            record = EnvironmentRecord.model_validate_json(
                self._read_object(client, key, _MAX_JSON_BYTES)
            )
            if record.owner_id == owner_id:
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.updated_at, item.id),
            reverse=True,
        )

    def _get(self, owner_id: str, environment_id: str) -> EnvironmentRecord:
        self._validate_environment_id(environment_id)
        client = self._client_factory()
        try:
            content = self._read_object(
                client,
                self._summary_key(owner_id, environment_id),
                _MAX_JSON_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise EnvironmentNotFound("环境不存在或已被删除。") from error
            raise
        record = EnvironmentRecord.model_validate_json(content)
        if record.id != environment_id or record.owner_id != owner_id:
            raise EnvironmentNotFound("环境不存在或已被删除。")
        return record

    def _create(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self._validate_environment_id(record.id)
        try:
            self._put_json(
                self._client_factory(),
                self._summary_key(record.owner_id, record.id),
                record,
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise EnvironmentConflict("环境 ID 已存在。") from error
            raise
        return record

    def _update(self, record: EnvironmentRecord) -> EnvironmentRecord:
        current = self._get(record.owner_id, record.id)
        if current.owner_id != record.owner_id:
            raise EnvironmentNotFound("环境不存在或已被删除。")
        self._put_json(
            self._client_factory(),
            self._summary_key(record.owner_id, record.id),
            record,
        )
        return record

    def _delete(self, owner_id: str, environment_id: str) -> None:
        _ = self._get(owner_id, environment_id)
        client = self._client_factory()
        prefix = f"{self._environment_prefix(owner_id, environment_id)}/"
        for key in self._list_keys(client, prefix):
            client.delete_object(bucket=self.bucket, key=key)

    def _create_version(
        self,
        record: EnvironmentRecord,
        build: EnvironmentBuild,
        dockerfile: str,
        context: bytes,
        skill_manifest: EnvironmentSkillManifest | None,
        skill_files: list[tuple[str, bytes]],
    ) -> EnvironmentRecord:
        self._validate_version_id(build.version_id)
        client = self._client_factory()
        version_prefix = self._version_prefix(
            record.owner_id, record.id, build.version_id
        )
        self._put_json(client, f"{version_prefix}/config.json", record)
        self._put_bytes(
            client, f"{version_prefix}/Dockerfile", dockerfile.encode(), "text/plain"
        )
        self._put_bytes(
            client, f"{version_prefix}/context.tar.gz", context, "application/gzip"
        )
        manifest = skill_manifest or EnvironmentSkillManifest()
        self._put_json(client, f"{version_prefix}/skills-manifest.json", manifest)
        for relative_path, content in skill_files:
            self._put_bytes(
                client,
                f"{version_prefix}/skills/{relative_path}",
                content,
                "text/plain",
            )
        self._put_json(client, f"{version_prefix}/build.json", build)
        self._put_json(
            client,
            f"{self._environment_prefix(record.owner_id, record.id)}/latest.json",
            build,
        )
        updated = record.model_copy(update={"latest_version_id": build.version_id})
        self._put_json(client, self._summary_key(record.owner_id, record.id), updated)
        return updated

    def _put_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str, content: bytes
    ) -> None:
        self._validate_environment_id(environment_id)
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
            raise ValueError("Invalid environment skill artifact id.")
        self._put_bytes(
            self._client_factory(),
            f"{self._environment_prefix(owner_id, environment_id)}/skills/{artifact_id}.json",
            content,
            "application/json",
        )

    def _get_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str
    ) -> bytes:
        self._validate_environment_id(environment_id)
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
            raise ValueError("Invalid environment skill artifact id.")
        return self._read_object(
            self._client_factory(),
            f"{self._environment_prefix(owner_id, environment_id)}/skills/{artifact_id}.json",
            2 * 1024 * 1024,
        )

    def _get_skill_manifest(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentSkillManifest:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        key = f"{self._version_prefix(owner_id, environment_id, version_id)}/skills-manifest.json"
        try:
            content = self._read_object(self._client_factory(), key, _MAX_JSON_BYTES)
        except Exception as error:
            if _status_code(error) == 404:
                return EnvironmentSkillManifest()
            raise
        return EnvironmentSkillManifest.model_validate_json(content)

    def _get_version_config(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentRecord:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        key = (
            f"{self._version_prefix(owner_id, environment_id, version_id)}/config.json"
        )
        try:
            content = self._read_object(self._client_factory(), key, _MAX_JSON_BYTES)
        except Exception as error:
            if _status_code(error) == 404:
                raise EnvironmentNotFound("环境构建版本不存在。") from error
            raise
        record = EnvironmentRecord.model_validate_json(content)
        if record.id != environment_id or record.owner_id != owner_id:
            raise EnvironmentNotFound("环境构建版本不存在。")
        return record

    def _get_version_skill_files(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> list[tuple[str, bytes]]:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        prefix = f"{self._version_prefix(owner_id, environment_id, version_id)}/skills/"
        client = self._client_factory()
        files: list[tuple[str, bytes]] = []
        total = 0
        for key in self._list_keys(client, prefix):
            content = self._read_object(client, key, 256 * 1024)
            total += len(content)
            if total > 2 * 1024 * 1024:
                raise ValueError("Stored environment skills are too large.")
            files.append((key.removeprefix(prefix), content))
        return files

    def _get_build(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> EnvironmentBuild:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        key = f"{self._version_prefix(owner_id, environment_id, version_id)}/build.json"
        try:
            content = self._read_object(self._client_factory(), key, _MAX_JSON_BYTES)
        except Exception as error:
            if _status_code(error) == 404:
                raise EnvironmentNotFound("环境构建版本不存在。") from error
            raise
        build = EnvironmentBuild.model_validate_json(content)
        if build.environment_id != environment_id or build.version_id != version_id:
            raise EnvironmentNotFound("环境构建版本不存在。")
        return build

    def _update_build(
        self,
        owner_id: str,
        build: EnvironmentBuild,
        log: str | None,
    ) -> EnvironmentBuild:
        version_prefix = self._version_prefix(
            owner_id, build.environment_id, build.version_id
        )
        client = self._client_factory()
        self._put_json(client, f"{version_prefix}/build.json", build)
        self._put_json(
            client,
            f"{self._environment_prefix(owner_id, build.environment_id)}/latest.json",
            build,
        )
        if log is not None:
            payload = log.encode("utf-8")[-_MAX_LOG_BYTES:]
            self._put_bytes(
                client, f"{version_prefix}/build.log", payload, "text/plain"
            )
        if build.image:
            self._put_bytes(
                client,
                f"{version_prefix}/image.json",
                json.dumps({"image": build.image}, ensure_ascii=False).encode(),
                "application/json",
            )
        return build

    def _get_build_log(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> str:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        key = f"{self._version_prefix(owner_id, environment_id, version_id)}/build.log"
        try:
            content = self._read_object(self._client_factory(), key, _MAX_LOG_BYTES)
        except Exception as error:
            if _status_code(error) == 404:
                return ""
            raise
        return content.decode("utf-8", errors="replace")

    def _owner_prefix(self, owner_id: str) -> str:
        owner = quote(owner_id.strip(), safe="")
        if not owner:
            raise ValueError("Environment owner id cannot be empty.")
        return f"{self._prefix}/{owner}"

    def _environment_prefix(self, owner_id: str, environment_id: str) -> str:
        self._validate_environment_id(environment_id)
        return f"{self._owner_prefix(owner_id)}/{environment_id}"

    def _version_prefix(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> str:
        self._validate_version_id(version_id)
        return f"{self._environment_prefix(owner_id, environment_id)}/versions/{version_id}"

    def _summary_key(self, owner_id: str, environment_id: str) -> str:
        return f"{self._environment_prefix(owner_id, environment_id)}/summary.json"

    @staticmethod
    def _validate_environment_id(environment_id: str) -> None:
        if not _ID_RE.fullmatch(environment_id):
            raise EnvironmentNotFound("环境不存在或已被删除。")

    @staticmethod
    def _validate_version_id(version_id: str) -> None:
        if not _VERSION_RE.fullmatch(version_id):
            raise EnvironmentNotFound("环境构建版本不存在。")

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
            raise ValueError("Stored environment object is invalid or too large.")
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
            raise ValueError("Environment metadata is too large.")
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
    "EnvironmentConflict",
    "EnvironmentNotFound",
    "EnvironmentStorageUnavailable",
    "TosEnvironmentRepository",
]
