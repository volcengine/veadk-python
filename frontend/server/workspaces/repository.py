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

"""TOS persistence for Studio workspace definitions."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import WorkspaceRecord

_ID_RE = re.compile(r"[0-9a-f]{32}")
_MAX_JSON_BYTES = 256 * 1024


class WorkspaceNotFound(LookupError):
    pass


class WorkspaceConflict(RuntimeError):
    pass


class WorkspaceStorageUnavailable(RuntimeError):
    pass


class TosWorkspaceRepository:
    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS workspace storage requires a bucket.")
        self.bucket = bucket.strip()
        self._client_factory = client_factory
        self._prefix = f"{root_prefix.strip('/')}/workspaces"

    async def list(self, owner_id: str) -> list[WorkspaceRecord]:
        return await asyncio.to_thread(self._list, owner_id)

    async def get(self, owner_id: str, workspace_id: str) -> WorkspaceRecord:
        return await asyncio.to_thread(self._get, owner_id, workspace_id)

    async def create(self, record: WorkspaceRecord) -> WorkspaceRecord:
        return await asyncio.to_thread(self._create, record)

    async def update(self, record: WorkspaceRecord) -> WorkspaceRecord:
        return await asyncio.to_thread(self._update, record)

    async def delete(self, owner_id: str, workspace_id: str) -> None:
        await asyncio.to_thread(self._delete, owner_id, workspace_id)

    def _list(self, owner_id: str) -> list[WorkspaceRecord]:
        client = self._client_factory()
        prefix = f"{self._owner_prefix(owner_id)}/"
        records: list[WorkspaceRecord] = []
        for key in self._list_keys(client, prefix):
            if not key.endswith("/summary.json"):
                continue
            record = WorkspaceRecord.model_validate_json(
                self._read_object(client, key, _MAX_JSON_BYTES)
            )
            if record.owner_id == owner_id:
                records.append(record)
        return sorted(
            records, key=lambda item: (item.updated_at, item.id), reverse=True
        )

    def _get(self, owner_id: str, workspace_id: str) -> WorkspaceRecord:
        self._validate_id(workspace_id)
        try:
            content = self._read_object(
                self._client_factory(),
                self._summary_key(owner_id, workspace_id),
                _MAX_JSON_BYTES,
            )
        except Exception as error:
            if _status_code(error) == 404:
                raise WorkspaceNotFound("工作区不存在或已被删除。") from error
            raise
        record = WorkspaceRecord.model_validate_json(content)
        if record.id != workspace_id or record.owner_id != owner_id:
            raise WorkspaceNotFound("工作区不存在或已被删除。")
        return record

    def _create(self, record: WorkspaceRecord) -> WorkspaceRecord:
        self._validate_id(record.id)
        try:
            self._put_json(record, forbid_overwrite=True)
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise WorkspaceConflict("工作区 ID 已存在。") from error
            raise
        return record

    def _update(self, record: WorkspaceRecord) -> WorkspaceRecord:
        _ = self._get(record.owner_id, record.id)
        self._put_json(record)
        return record

    def _delete(self, owner_id: str, workspace_id: str) -> None:
        _ = self._get(owner_id, workspace_id)
        client = self._client_factory()
        prefix = f"{self._workspace_prefix(owner_id, workspace_id)}/"
        for key in self._list_keys(client, prefix):
            client.delete_object(bucket=self.bucket, key=key)

    def _owner_prefix(self, owner_id: str) -> str:
        owner = quote(owner_id.strip(), safe="")
        if not owner:
            raise ValueError("Workspace owner id cannot be empty.")
        return f"{self._prefix}/{owner}"

    def _workspace_prefix(self, owner_id: str, workspace_id: str) -> str:
        self._validate_id(workspace_id)
        return f"{self._owner_prefix(owner_id)}/{workspace_id}"

    def _summary_key(self, owner_id: str, workspace_id: str) -> str:
        return f"{self._workspace_prefix(owner_id, workspace_id)}/summary.json"

    @staticmethod
    def _validate_id(workspace_id: str) -> None:
        if not _ID_RE.fullmatch(workspace_id):
            raise WorkspaceNotFound("工作区不存在或已被删除。")

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
            raise ValueError("Stored workspace object is invalid or too large.")
        return content

    def _put_json(
        self, record: WorkspaceRecord, *, forbid_overwrite: bool = False
    ) -> None:
        content = record.model_dump_json(by_alias=True).encode("utf-8")
        if len(content) > _MAX_JSON_BYTES:
            raise ValueError("Workspace metadata is too large.")
        self._client_factory().put_object(
            bucket=self.bucket,
            key=self._summary_key(record.owner_id, record.id),
            content=content,
            content_length=len(content),
            content_type="application/json",
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
    "TosWorkspaceRepository",
    "WorkspaceConflict",
    "WorkspaceNotFound",
    "WorkspaceStorageUnavailable",
]
