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
_CURRENT_STORAGE_VERSION = "v3"
_PREVIOUS_STORAGE_VERSION = "v2"
_LEGACY_RECORD_FIELDS = (
    "name",
    "description",
    "operatingSystem",
    "language",
    "executionRuntime",
    "optionIds",
    "selectedSkills",
    "dockerfile",
    "id",
    "ownerId",
    "createdAt",
    "updatedAt",
    "latestVersionId",
)
_CURRENT_ONLY_RECORD_FIELDS = frozenset(
    {"baseEnvironment", "gitSource", "imageSource", "containerRepository"}
)
_CURRENT_ONLY_BUILD_FIELDS = frozenset({"toolId", "toolStatus", "sourceCommitSha"})


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
        legacy_root_prefix = root_prefix.strip("/")
        self._legacy_prefix = f"{legacy_root_prefix}/environments"
        self._previous_prefix = (
            f"{_replace_storage_version(legacy_root_prefix, _PREVIOUS_STORAGE_VERSION)}"
            "/environments"
        )
        self._prefix = (
            f"{_replace_storage_version(legacy_root_prefix, _CURRENT_STORAGE_VERSION)}"
            "/environments"
        )

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

    async def create_external_version(
        self,
        record: EnvironmentRecord,
        build: EnvironmentBuild,
        skill_manifest: EnvironmentSkillManifest | None = None,
        skill_files: list[tuple[str, bytes]] | None = None,
    ) -> EnvironmentRecord:
        return await asyncio.to_thread(
            self._create_external_version,
            record,
            build,
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
        records_by_id: dict[str, dict[str, tuple[EnvironmentRecord, bytes]]] = {}
        for prefix, storage_version in (
            (self._prefix, _CURRENT_STORAGE_VERSION),
            (self._previous_prefix, _PREVIOUS_STORAGE_VERSION),
            (self._legacy_prefix, "v1"),
        ):
            owner_prefix = f"{self._owner_prefix_for(prefix, owner_id)}/"
            for key in self._list_keys(client, owner_prefix):
                if not key.endswith("/summary.json"):
                    continue
                content = self._read_object(client, key, _MAX_JSON_BYTES)
                record = EnvironmentRecord.model_validate_json(content)
                if record.owner_id != owner_id:
                    continue
                records_by_id.setdefault(record.id, {})[storage_version] = (
                    record,
                    content,
                )
        records: list[EnvironmentRecord] = []
        for candidates in records_by_id.values():
            record, content, storage_version = self._select_record(candidates)
            self._reconcile_record_copies(
                client,
                record,
                content,
                storage_version=storage_version,
                candidates=candidates,
            )
            records.append(record)
        return sorted(
            records,
            key=lambda item: (item.updated_at, item.id),
            reverse=True,
        )

    def _get(self, owner_id: str, environment_id: str) -> EnvironmentRecord:
        self._validate_environment_id(environment_id)
        client = self._client_factory()
        candidates = self._read_versioned_candidates(
            client,
            self._summary_key(owner_id, environment_id),
            self._previous_summary_key(owner_id, environment_id),
            self._legacy_summary_key(owner_id, environment_id),
            _MAX_JSON_BYTES,
            not_found_message="环境不存在或已被删除。",
        )
        records = {
            storage_version: (EnvironmentRecord.model_validate_json(content), content)
            for content, storage_version in candidates
        }
        record, content, storage_version = self._select_record(records)
        if record.id != environment_id or record.owner_id != owner_id:
            raise EnvironmentNotFound("环境不存在或已被删除。")
        self._reconcile_record_copies(
            client,
            record,
            content,
            storage_version=storage_version,
            candidates=records,
        )
        return record

    def _create(self, record: EnvironmentRecord) -> EnvironmentRecord:
        self._validate_environment_id(record.id)
        try:
            self._get(record.owner_id, record.id)
        except EnvironmentNotFound:
            pass
        else:
            raise EnvironmentConflict("环境 ID 已存在。")
        try:
            client = self._client_factory()
            for key in self._summary_write_keys(record):
                self._put_json(client, key, record, forbid_overwrite=True)
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise EnvironmentConflict("环境 ID 已存在。") from error
            raise
        return record

    def _update(self, record: EnvironmentRecord) -> EnvironmentRecord:
        current = self._get(record.owner_id, record.id)
        if current.owner_id != record.owner_id:
            raise EnvironmentNotFound("环境不存在或已被删除。")
        client = self._client_factory()
        for key in self._summary_write_keys(record):
            self._put_json(client, key, record)
        return record

    def _delete(self, owner_id: str, environment_id: str) -> None:
        _ = self._get(owner_id, environment_id)
        client = self._client_factory()
        for prefix in (
            self._environment_prefix(owner_id, environment_id),
            self._previous_environment_prefix(owner_id, environment_id),
            self._legacy_environment_prefix(owner_id, environment_id),
        ):
            for key in self._list_keys(client, f"{prefix}/"):
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
        manifest = skill_manifest or EnvironmentSkillManifest()
        for version_prefix in self._version_write_prefixes(record, build.version_id):
            self._put_json(client, f"{version_prefix}/config.json", record)
            self._put_bytes(
                client,
                f"{version_prefix}/Dockerfile",
                dockerfile.encode(),
                "text/plain",
            )
            self._put_bytes(
                client, f"{version_prefix}/context.tar.gz", context, "application/gzip"
            )
            self._put_json(client, f"{version_prefix}/skills-manifest.json", manifest)
            for relative_path, content in skill_files:
                self._put_bytes(
                    client,
                    f"{version_prefix}/skills/{relative_path}",
                    content,
                    "text/plain",
                )
            self._put_json(client, f"{version_prefix}/build.json", build)
        for environment_prefix in self._environment_write_prefixes(record):
            self._put_json(client, f"{environment_prefix}/latest.json", build)
        updated = record.model_copy(update={"latest_version_id": build.version_id})
        for key in self._summary_write_keys(updated):
            self._put_json(client, key, updated)
        return updated

    def _create_external_version(
        self,
        record: EnvironmentRecord,
        build: EnvironmentBuild,
        skill_manifest: EnvironmentSkillManifest | None,
        skill_files: list[tuple[str, bytes]],
    ) -> EnvironmentRecord:
        self._validate_version_id(build.version_id)
        client = self._client_factory()
        manifest = skill_manifest or EnvironmentSkillManifest()
        for version_prefix in self._version_write_prefixes(record, build.version_id):
            self._put_json(client, f"{version_prefix}/config.json", record)
            self._put_json(client, f"{version_prefix}/skills-manifest.json", manifest)
            for relative_path, content in skill_files:
                self._put_bytes(
                    client,
                    f"{version_prefix}/skills/{relative_path}",
                    content,
                    "text/plain",
                )
            self._put_json(client, f"{version_prefix}/build.json", build)
            self._put_bytes(
                client,
                f"{version_prefix}/image.json",
                json.dumps({"image": build.image}, ensure_ascii=False).encode(),
                "application/json",
            )
        for environment_prefix in self._environment_write_prefixes(record):
            self._put_json(client, f"{environment_prefix}/latest.json", build)
        updated = record.model_copy(update={"latest_version_id": build.version_id})
        for key in self._summary_write_keys(updated):
            self._put_json(client, key, updated)
        return updated

    def _put_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str, content: bytes
    ) -> None:
        self._validate_environment_id(environment_id)
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
            raise ValueError("Invalid environment skill artifact id.")
        client = self._client_factory()
        for prefix in (
            self._environment_prefix(owner_id, environment_id),
            self._previous_environment_prefix(owner_id, environment_id),
        ):
            self._put_bytes(
                client,
                f"{prefix}/skills/{artifact_id}.json",
                content,
                "application/json",
            )

    def _get_skill_asset(
        self, owner_id: str, environment_id: str, artifact_id: str
    ) -> bytes:
        self._validate_environment_id(environment_id)
        if not re.fullmatch(r"[0-9a-f]{64}", artifact_id):
            raise ValueError("Invalid environment skill artifact id.")
        content, _ = self._read_versioned(
            self._client_factory(),
            f"{self._environment_prefix(owner_id, environment_id)}/skills/{artifact_id}.json",
            f"{self._previous_environment_prefix(owner_id, environment_id)}/skills/{artifact_id}.json",
            f"{self._legacy_environment_prefix(owner_id, environment_id)}/skills/{artifact_id}.json",
            2 * 1024 * 1024,
            not_found_message="环境技能不存在或已被删除。",
        )
        return content

    def _get_skill_manifest(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentSkillManifest:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        client = self._client_factory()
        try:
            content, _ = self._read_versioned(
                client,
                f"{self._version_prefix(owner_id, environment_id, version_id)}/skills-manifest.json",
                f"{self._previous_version_prefix(owner_id, environment_id, version_id)}/skills-manifest.json",
                f"{self._legacy_version_prefix(owner_id, environment_id, version_id)}/skills-manifest.json",
                _MAX_JSON_BYTES,
                not_found_message="环境技能清单不存在。",
            )
        except EnvironmentNotFound:
            return EnvironmentSkillManifest()
        return EnvironmentSkillManifest.model_validate_json(content)

    def _get_version_config(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> EnvironmentRecord:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        client = self._client_factory()
        content, storage_version = self._read_versioned(
            client,
            f"{self._version_prefix(owner_id, environment_id, version_id)}/config.json",
            f"{self._previous_version_prefix(owner_id, environment_id, version_id)}/config.json",
            f"{self._legacy_version_prefix(owner_id, environment_id, version_id)}/config.json",
            _MAX_JSON_BYTES,
            not_found_message="环境构建版本不存在。",
        )
        record = EnvironmentRecord.model_validate_json(content)
        if record.id != environment_id or record.owner_id != owner_id:
            raise EnvironmentNotFound("环境构建版本不存在。")
        if storage_version != _CURRENT_STORAGE_VERSION:
            self._repair_older_version_record(
                client,
                record,
                version_id,
                content,
                storage_version=storage_version,
            )
        return record

    def _get_version_skill_files(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> list[tuple[str, bytes]]:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        client = self._client_factory()
        prefix = ""
        keys: list[str] = []
        for candidate in (
            self._version_prefix(owner_id, environment_id, version_id),
            self._previous_version_prefix(owner_id, environment_id, version_id),
            self._legacy_version_prefix(owner_id, environment_id, version_id),
        ):
            prefix = f"{candidate}/skills/"
            keys = self._list_keys(client, prefix)
            if keys:
                break
        files: list[tuple[str, bytes]] = []
        total = 0
        for key in keys:
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
        client = self._client_factory()
        candidates = self._read_versioned_candidates(
            client,
            f"{self._version_prefix(owner_id, environment_id, version_id)}/build.json",
            f"{self._previous_version_prefix(owner_id, environment_id, version_id)}/build.json",
            f"{self._legacy_version_prefix(owner_id, environment_id, version_id)}/build.json",
            _MAX_JSON_BYTES,
            not_found_message="环境构建版本不存在。",
        )
        builds = {
            storage_version: (EnvironmentBuild.model_validate_json(content), content)
            for content, storage_version in candidates
        }
        modern_builds = {
            storage_version: value
            for storage_version, value in builds.items()
            if storage_version in {_CURRENT_STORAGE_VERSION, _PREVIOUS_STORAGE_VERSION}
        }
        if modern_builds:
            storage_version, (build, content) = max(
                modern_builds.items(),
                key=lambda item: (
                    item[1][0].updated_at,
                    item[0] == _CURRENT_STORAGE_VERSION,
                ),
            )
        else:
            storage_version = "v1"
            build, content = builds[storage_version]
        if build.environment_id != environment_id or build.version_id != version_id:
            raise EnvironmentNotFound("环境构建版本不存在。")
        if modern_builds:
            record = self._get_version_config(owner_id, environment_id, version_id)
            reconciled = False
            for prefix in self._version_write_prefixes(record, version_id):
                existing = builds.get(
                    _CURRENT_STORAGE_VERSION
                    if prefix.startswith(self._prefix + "/")
                    else _PREVIOUS_STORAGE_VERSION
                )
                if existing is None or existing[0] != build:
                    self._put_json(client, f"{prefix}/build.json", build)
                    reconciled = True
            if reconciled:
                for prefix in self._environment_write_prefixes(record):
                    self._put_json(client, f"{prefix}/latest.json", build)
        elif storage_version == "v1":
            self._repair_legacy_build(client, owner_id, build, content)
        return build

    def _update_build(
        self,
        owner_id: str,
        build: EnvironmentBuild,
        log: str | None,
    ) -> EnvironmentBuild:
        client = self._client_factory()
        record = self._get_version_config(
            owner_id,
            build.environment_id,
            build.version_id,
        )
        payload = log.encode("utf-8")[-_MAX_LOG_BYTES:] if log is not None else None
        for version_prefix in self._version_write_prefixes(record, build.version_id):
            self._put_json(client, f"{version_prefix}/build.json", build)
            if payload is not None:
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
        for environment_prefix in self._environment_write_prefixes(record):
            self._put_json(client, f"{environment_prefix}/latest.json", build)
        return build

    def _get_build_log(
        self,
        owner_id: str,
        environment_id: str,
        version_id: str,
    ) -> str:
        self._validate_environment_id(environment_id)
        self._validate_version_id(version_id)
        try:
            content, _ = self._read_versioned(
                self._client_factory(),
                f"{self._version_prefix(owner_id, environment_id, version_id)}/build.log",
                f"{self._previous_version_prefix(owner_id, environment_id, version_id)}/build.log",
                f"{self._legacy_version_prefix(owner_id, environment_id, version_id)}/build.log",
                _MAX_LOG_BYTES,
                not_found_message="环境构建日志不存在。",
            )
        except EnvironmentNotFound:
            return ""
        return content.decode("utf-8", errors="replace")

    def _owner_prefix(self, owner_id: str) -> str:
        return self._owner_prefix_for(self._prefix, owner_id)

    def _legacy_owner_prefix(self, owner_id: str) -> str:
        return self._owner_prefix_for(self._legacy_prefix, owner_id)

    def _previous_owner_prefix(self, owner_id: str) -> str:
        return self._owner_prefix_for(self._previous_prefix, owner_id)

    @staticmethod
    def _owner_prefix_for(prefix: str, owner_id: str) -> str:
        owner = quote(owner_id.strip(), safe="")
        if not owner:
            raise ValueError("Environment owner id cannot be empty.")
        return f"{prefix}/{owner}"

    def _environment_prefix(self, owner_id: str, environment_id: str) -> str:
        self._validate_environment_id(environment_id)
        return f"{self._owner_prefix(owner_id)}/{environment_id}"

    def _legacy_environment_prefix(self, owner_id: str, environment_id: str) -> str:
        self._validate_environment_id(environment_id)
        return f"{self._legacy_owner_prefix(owner_id)}/{environment_id}"

    def _previous_environment_prefix(self, owner_id: str, environment_id: str) -> str:
        self._validate_environment_id(environment_id)
        return f"{self._previous_owner_prefix(owner_id)}/{environment_id}"

    def _version_prefix(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> str:
        self._validate_version_id(version_id)
        return f"{self._environment_prefix(owner_id, environment_id)}/versions/{version_id}"

    def _legacy_version_prefix(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> str:
        self._validate_version_id(version_id)
        return (
            f"{self._legacy_environment_prefix(owner_id, environment_id)}"
            f"/versions/{version_id}"
        )

    def _previous_version_prefix(
        self, owner_id: str, environment_id: str, version_id: str
    ) -> str:
        self._validate_version_id(version_id)
        return (
            f"{self._previous_environment_prefix(owner_id, environment_id)}"
            f"/versions/{version_id}"
        )

    def _environment_write_prefixes(self, record: EnvironmentRecord) -> tuple[str, ...]:
        current = self._environment_prefix(record.owner_id, record.id)
        if record.base_environment == "codex-sandbox":
            return (current,)
        return (current, self._previous_environment_prefix(record.owner_id, record.id))

    def _version_write_prefixes(
        self, record: EnvironmentRecord, version_id: str
    ) -> tuple[str, ...]:
        current = self._version_prefix(record.owner_id, record.id, version_id)
        if record.base_environment == "codex-sandbox":
            return (current,)
        return (
            current,
            self._previous_version_prefix(record.owner_id, record.id, version_id),
        )

    def _summary_write_keys(self, record: EnvironmentRecord) -> tuple[str, ...]:
        return tuple(
            f"{prefix}/summary.json"
            for prefix in self._environment_write_prefixes(record)
        )

    def _summary_key(self, owner_id: str, environment_id: str) -> str:
        return f"{self._environment_prefix(owner_id, environment_id)}/summary.json"

    def _legacy_summary_key(self, owner_id: str, environment_id: str) -> str:
        return (
            f"{self._legacy_environment_prefix(owner_id, environment_id)}/summary.json"
        )

    def _previous_summary_key(self, owner_id: str, environment_id: str) -> str:
        return f"{self._previous_environment_prefix(owner_id, environment_id)}/summary.json"

    def _read_versioned(
        self,
        client: Any,
        current_key: str,
        previous_key: str,
        legacy_key: str,
        limit: int,
        *,
        not_found_message: str,
    ) -> tuple[bytes, str]:
        last_not_found: Exception | None = None
        for key, storage_version in (
            (current_key, _CURRENT_STORAGE_VERSION),
            (previous_key, _PREVIOUS_STORAGE_VERSION),
            (legacy_key, "v1"),
        ):
            try:
                return self._read_object(client, key, limit), storage_version
            except Exception as error:
                if _status_code(error) != 404:
                    raise
                last_not_found = error
        raise EnvironmentNotFound(not_found_message) from last_not_found

    def _read_versioned_candidates(
        self,
        client: Any,
        current_key: str,
        previous_key: str,
        legacy_key: str,
        limit: int,
        *,
        not_found_message: str,
    ) -> list[tuple[bytes, str]]:
        candidates: list[tuple[bytes, str]] = []
        last_not_found: Exception | None = None
        for key, storage_version in (
            (current_key, _CURRENT_STORAGE_VERSION),
            (previous_key, _PREVIOUS_STORAGE_VERSION),
        ):
            try:
                candidates.append(
                    (self._read_object(client, key, limit), storage_version)
                )
            except Exception as error:
                if _status_code(error) != 404:
                    raise
                last_not_found = error
        if candidates:
            return candidates
        try:
            return [(self._read_object(client, legacy_key, limit), "v1")]
        except Exception as error:
            if _status_code(error) != 404:
                raise
            last_not_found = error
        raise EnvironmentNotFound(not_found_message) from last_not_found

    @staticmethod
    def _select_record(
        candidates: dict[str, tuple[EnvironmentRecord, bytes]],
    ) -> tuple[EnvironmentRecord, bytes, str]:
        modern = {
            storage_version: value
            for storage_version, value in candidates.items()
            if storage_version in {_CURRENT_STORAGE_VERSION, _PREVIOUS_STORAGE_VERSION}
        }
        selected = modern or candidates
        storage_version, (record, content) = max(
            selected.items(),
            key=lambda item: (
                item[1][0].updated_at,
                item[0] == _CURRENT_STORAGE_VERSION,
                item[0] == _PREVIOUS_STORAGE_VERSION,
            ),
        )
        return record, content, storage_version

    def _reconcile_record_copies(
        self,
        client: Any,
        record: EnvironmentRecord,
        content: bytes,
        *,
        storage_version: str,
        candidates: dict[str, tuple[EnvironmentRecord, bytes]],
    ) -> None:
        if storage_version == "v1":
            self._repair_older_record(
                client,
                record,
                content,
                storage_version=storage_version,
            )
            return

        current = candidates.get(_CURRENT_STORAGE_VERSION)
        if current is None or current[0] != record:
            self._put_json(
                client,
                self._summary_key(record.owner_id, record.id),
                record,
            )

        previous_key = self._previous_summary_key(record.owner_id, record.id)
        previous = candidates.get(_PREVIOUS_STORAGE_VERSION)
        if record.base_environment == "codex-sandbox":
            if previous is not None:
                client.delete_object(bucket=self.bucket, key=previous_key)
            return
        if previous is None or previous[0] != record:
            self._put_json(client, previous_key, record)

    def _repair_older_record(
        self,
        client: Any,
        record: EnvironmentRecord,
        content: bytes,
        *,
        storage_version: str,
    ) -> None:
        payload = _json_object(content)
        if not _record_requires_newer_storage(payload, record, storage_version):
            return
        self._put_json_if_absent(
            client,
            self._summary_key(record.owner_id, record.id),
            record,
        )
        if storage_version == _PREVIOUS_STORAGE_VERSION:
            key = self._previous_summary_key(record.owner_id, record.id)
        else:
            key = self._legacy_summary_key(record.owner_id, record.id)
        if storage_version == "v1":
            if record.base_environment == "codex-sandbox":
                client.delete_object(bucket=self.bucket, key=key)
                return
            self._put_json(client, key, _legacy_record_payload(record))
            self._put_json(
                client,
                self._previous_summary_key(record.owner_id, record.id),
                record,
            )

    def _repair_older_version_record(
        self,
        client: Any,
        record: EnvironmentRecord,
        version_id: str,
        content: bytes,
        *,
        storage_version: str,
    ) -> None:
        payload = _json_object(content)
        if not _record_requires_newer_storage(payload, record, storage_version):
            return
        self._put_json_if_absent(
            client,
            f"{self._version_prefix(record.owner_id, record.id, version_id)}/config.json",
            record,
        )
        if storage_version == _PREVIOUS_STORAGE_VERSION:
            prefix = self._previous_version_prefix(
                record.owner_id, record.id, version_id
            )
        else:
            prefix = self._legacy_version_prefix(record.owner_id, record.id, version_id)
        key = f"{prefix}/config.json"
        if storage_version == "v1":
            if record.base_environment == "codex-sandbox":
                client.delete_object(bucket=self.bucket, key=key)
                return
            self._put_json(client, key, _legacy_record_payload(record))
            self._put_json(
                client,
                f"{self._previous_version_prefix(record.owner_id, record.id, version_id)}/config.json",
                record,
            )

    def _repair_legacy_build(
        self,
        client: Any,
        owner_id: str,
        build: EnvironmentBuild,
        content: bytes,
    ) -> None:
        payload = _json_object(content)
        if not (_CURRENT_ONLY_BUILD_FIELDS & payload.keys()):
            return
        self._put_json_if_absent(
            client,
            f"{self._version_prefix(owner_id, build.environment_id, build.version_id)}/build.json",
            build,
        )
        self._put_json(
            client,
            f"{self._legacy_version_prefix(owner_id, build.environment_id, build.version_id)}/build.json",
            {
                key: value
                for key, value in payload.items()
                if key not in _CURRENT_ONLY_BUILD_FIELDS
            },
        )

    def _put_json_if_absent(self, client: Any, key: str, value: Any) -> None:
        try:
            self._put_json(client, key, value, forbid_overwrite=True)
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise

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
        if hasattr(value, "model_dump_json"):
            content = value.model_dump_json(by_alias=True).encode("utf-8")
        else:
            content = json.dumps(
                value,
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
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


def _replace_storage_version(root_prefix: str, version: str) -> str:
    parent, separator, leaf = root_prefix.rpartition("/")
    if re.fullmatch(r"v[0-9]+", leaf):
        return f"{parent}{separator}{version}" if parent else version
    return f"{root_prefix}/{version}"


def _json_object(content: bytes) -> dict[str, Any]:
    value = json.loads(content)
    if not isinstance(value, dict):
        raise ValueError("Stored environment object must be a JSON object.")
    return value


def _legacy_record_payload(record: EnvironmentRecord) -> dict[str, Any]:
    payload = record.model_dump(mode="json", by_alias=True)
    return {key: payload[key] for key in _LEGACY_RECORD_FIELDS}


def _record_requires_newer_storage(
    payload: dict[str, Any],
    record: EnvironmentRecord,
    storage_version: str,
) -> bool:
    if storage_version == "v1":
        return record.base_environment == "codex-sandbox" or bool(
            _CURRENT_ONLY_RECORD_FIELDS & payload.keys()
        )
    return storage_version == _PREVIOUS_STORAGE_VERSION


__all__ = [
    "EnvironmentConflict",
    "EnvironmentNotFound",
    "EnvironmentStorageUnavailable",
    "TosEnvironmentRepository",
]
