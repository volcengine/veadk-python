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

"""TOS is the source of truth for Runtime evaluation data"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any
from urllib.parse import quote
from uuid import uuid4

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX, StudioStorageConfig
from frontend.server.storage.tos import create_cached_tos_client_factory

from .models import EvaluationSet, Record, Sample, now

MAX_OBJECT_BYTES = 1024 * 1024


class EvaluationError(RuntimeError):
    def __init__(self, message: str, status: int = 502) -> None:
        super().__init__(message)
        self.status = status


def sample_id(
    source: str, user_id: str, session_id: str, message_id: str, version: str = ""
) -> str:
    return hashlib.sha256(
        json.dumps([source, user_id, session_id, message_id, version]).encode()
    ).hexdigest()


class EvaluationStorage:
    def __init__(self, provider: Any, resolve_credentials: Callable) -> None:
        self.config = StudioStorageConfig.from_env(provider)
        self.factory = (
            create_cached_tos_client_factory(self.config, resolve_credentials)
            if self.config.configured
            else None
        )

    def for_runtime(self, runtime_id: str) -> TosEvaluationRepository:
        if self.factory is None:
            raise EvaluationError(self.config.unavailable_reason, 503)
        return TosEvaluationRepository(self.config.bucket, self.factory, runtime_id)


class TosEvaluationRepository:
    def __init__(
        self, bucket: str, client_factory: Callable[[], Any], runtime_id: str
    ) -> None:
        if not runtime_id or runtime_id in {".", ".."}:
            raise ValueError("Runtime ID is required")
        self.bucket = bucket
        self.factory = client_factory
        self.runtime_id = runtime_id
        self.prefix = (
            f"{STUDIO_STORAGE_ROOT_PREFIX}/evaluation/{quote(runtime_id, safe='')}/"
        )

    def _key(self, folder: str, identifier: str) -> str:
        if not re.fullmatch(r"[a-zA-Z0-9_-]{1,128}", identifier):
            raise EvaluationError("记录 ID 无效", 400)
        return f"{self.prefix}{folder}/{identifier}.json"

    def _read(self, folder: str, identifier: str) -> tuple[dict, str] | None:
        try:
            response = self.factory().get_object(
                bucket=self.bucket, key=self._key(folder, identifier)
            )
            data = response.read(MAX_OBJECT_BYTES + 1)
        except Exception as error:
            if getattr(error, "status_code", None) == 404:
                return None
            if isinstance(error, EvaluationError):
                raise
            raise EvaluationError(
                "读取评测存储失败，请检查 TOS 配置和访问权限"
            ) from error
        if len(data) > MAX_OBJECT_BYTES:
            raise EvaluationError("评测记录超过大小限制")
        try:
            content = json.loads(data)
        except (ValueError, UnicodeDecodeError) as error:
            raise EvaluationError("评测记录不是有效的 JSON 数据") from error
        if not isinstance(content, dict) or content.get("id") != identifier:
            raise EvaluationError("评测记录格式无效")
        etag = str(response.etag)
        if not etag:
            raise EvaluationError("评测记录缺少版本信息")
        return content, etag

    def _write(
        self, folder: str, identifier: str, content: dict, revision: str = ""
    ) -> str:
        data = json.dumps(content, ensure_ascii=False).encode()
        if len(data) > MAX_OBJECT_BYTES:
            raise EvaluationError("单条评测数据不能超过 1 MB", 400)
        options = {"if_match": revision} if revision else {"forbid_overwrite": True}
        try:
            response = self.factory().put_object(
                bucket=self.bucket,
                key=self._key(folder, identifier),
                content=data,
                content_type="application/json",
                **options,
            )
            return str(response.etag)
        except Exception as error:
            if getattr(error, "status_code", None) in {409, 412}:
                raise EvaluationError("数据已被修改，请刷新后重试", 409) from error
            if isinstance(error, EvaluationError):
                raise
            raise EvaluationError(
                "保存评测存储失败，请检查 TOS 配置和访问权限"
            ) from error

    def _save(self, folder: str, record: Record, revision: str = "") -> Any:
        updated = record.model_copy(update={"updated_at": now()})
        etag = self._write(
            folder, updated.id, updated.model_dump(mode="json", by_alias=True), revision
        )
        return updated.model_copy(update={"revision": etag})

    def _get_set(self, identifier: str, include_deleted: bool = False) -> EvaluationSet:
        result = self._read("sets", identifier)
        if result is None or (result[0].get("deletedAt") and not include_deleted):
            raise EvaluationError("评测集不存在或已删除", 404)
        return EvaluationSet.model_validate({**result[0], "revision": result[1]})

    def _scan(self, folder: str) -> list[tuple[dict, str]]:
        keys: list[str] = []
        token = ""
        seen: set[str] = set()
        while True:
            try:
                response = self.factory().list_objects_type2(
                    bucket=self.bucket,
                    prefix=f"{self.prefix}{folder}/",
                    continuation_token=token,
                    max_keys=1000,
                )
            except Exception as error:
                raise EvaluationError(
                    "读取评测列表失败，请检查 TOS 配置和访问权限"
                ) from error
            keys.extend(
                item.key.rsplit("/", 1)[-1][:-5]
                for item in response.contents
                if item.key.endswith(".json")
            )
            if not response.is_truncated:
                break
            token = response.next_continuation_token
            if not token or token in seen:
                raise EvaluationError("TOS 列表分页响应无效")
            seen.add(token)
        with ThreadPoolExecutor(max_workers=8) as pool:
            return [
                item
                for item in pool.map(lambda key: self._read(folder, key), keys)
                if item is not None
            ]

    async def ensure_defaults(self) -> list[EvaluationSet]:
        return await asyncio.to_thread(self._ensure_defaults)

    def _ensure_defaults(self) -> list[EvaluationSet]:
        return [self._ensure_default(kind) for kind in ("good", "bad")]

    def _ensure_default(self, kind: str) -> EvaluationSet:
        record = EvaluationSet(
            id=kind,
            name="Good Case" if kind == "good" else "Bad Case",
            defaultKind="good" if kind == "good" else "bad",
        )
        try:
            return self._save("sets", record)
        except EvaluationError as error:
            if error.status != 409:
                raise
            # A deletion marker deliberately prevents background re-creation
            return self._get_set(kind)

    async def create_set(
        self, name: str, description: str, actor: str
    ) -> EvaluationSet:
        record = EvaluationSet(
            id=uuid4().hex, name=name, description=description, createdBy=actor
        )
        return await asyncio.to_thread(self._save, "sets", record)

    async def get_set(self, identifier: str) -> EvaluationSet:
        return await asyncio.to_thread(self._get_set, identifier)

    async def update_set(
        self, identifier: str, name: str, description: str, revision: str
    ) -> EvaluationSet:
        record = await self.get_set(identifier)
        return await asyncio.to_thread(
            self._save,
            "sets",
            record.model_copy(update={"name": name, "description": description}),
            revision,
        )

    async def list_sets(self) -> list[EvaluationSet]:
        rows = await asyncio.to_thread(self._scan, "sets")
        return [
            EvaluationSet.model_validate({**row, "revision": etag})
            for row, etag in rows
            if not row.get("deletedAt")
        ]

    async def list_samples(self) -> list[Sample]:
        sets, rows = await asyncio.gather(
            self.list_sets(), asyncio.to_thread(self._scan, "samples")
        )
        active = {item.id for item in sets}
        return sorted(
            [
                Sample.model_validate({**row, "revision": etag})
                for row, etag in rows
                if not row.get("deletedAt") and row.get("evaluationSetId") in active
            ],
            key=lambda row: (row.created_at, row.id),
            reverse=True,
        )

    async def get_sample(self, identifier: str) -> Sample:
        result = await asyncio.to_thread(self._read, "samples", identifier)
        if result is None or result[0].get("deletedAt"):
            raise EvaluationError("样本不存在或已删除", 404)
        record = Sample.model_validate({**result[0], "revision": result[1]})
        await self.get_set(record.evaluation_set_id)
        return record

    async def save_sample(self, record: Sample, revision: str = "") -> Sample:
        collection = await self.get_set(record.evaluation_set_id)
        if collection.default_kind:
            record = record.model_copy(update={"kind": collection.default_kind})
        result = await asyncio.to_thread(self._save, "samples", record, revision)
        try:
            await self.get_set(record.evaluation_set_id)
        except EvaluationError as error:
            if error.status == 404:
                await self.delete_sample(result.id, result.revision)
            raise
        return result

    async def save_feedback(self, record: Sample) -> Sample:
        await asyncio.to_thread(self._ensure_default, record.evaluation_set_id)
        previous = await asyncio.to_thread(self._read, "samples", record.id)
        if previous and not previous[0].get("deletedAt"):
            record = record.model_copy(update={"created_at": previous[0]["createdAt"]})
        return await self.save_sample(record, previous[1] if previous else "")

    async def save_automatic(self, record: Sample) -> Sample | None:
        previous = await asyncio.to_thread(self._read, "samples", record.id)
        if previous:
            if previous[0].get("deletedAt"):
                return None
            return await self.get_sample(record.id)
        await asyncio.to_thread(self._ensure_default, record.evaluation_set_id)
        try:
            return await self.save_sample(record)
        except EvaluationError as error:
            if error.status != 409:
                raise
            return await self.get_sample(record.id)

    async def delete_sample(self, identifier: str, revision: str = "") -> bool:
        previous = await asyncio.to_thread(self._read, "samples", identifier)
        if previous is None or previous[0].get("deletedAt"):
            return False
        marker = {
            "schemaVersion": 1,
            "id": identifier,
            "evaluationSetId": previous[0]["evaluationSetId"],
            "source": previous[0]["source"],
            "userId": previous[0].get("userId", ""),
            "sessionId": previous[0].get("sessionId", ""),
            "messageId": previous[0].get("messageId", ""),
            "deletedAt": now(),
        }
        await asyncio.to_thread(
            self._write, "samples", identifier, marker, revision or previous[1]
        )
        return True

    async def delete_set(self, identifier: str, revision: str) -> None:
        record = await asyncio.to_thread(self._get_set, identifier, True)
        if not record.deleted_at:
            await asyncio.to_thread(
                self._save,
                "sets",
                record.model_copy(update={"deleted_at": now(), "description": ""}),
                revision,
            )
        rows = await asyncio.to_thread(self._scan, "samples")
        for row, etag in rows:
            if row.get("evaluationSetId") == identifier and not row.get("deletedAt"):
                await self.delete_sample(str(row["id"]), etag)

    async def feedback_states(
        self, user_id: str, session_id: str, event_ids: list[str]
    ) -> dict:
        async def read(event_id: str):
            identifier = sample_id("user", user_id, session_id, event_id)
            result = await asyncio.to_thread(self._read, "samples", identifier)
            if result is None or result[0].get("deletedAt"):
                return event_id, {"rating": None, "syncStatus": "synced"}
            row, _ = result
            try:
                collection = await self.get_set(row["evaluationSetId"])
            except EvaluationError as error:
                if error.status != 404:
                    raise
                return event_id, {"rating": None, "syncStatus": "synced"}
            return event_id, {
                "rating": row.get("kind"),
                "comment": row.get("comment", ""),
                "evaluationSetId": collection.id,
                "evaluationSetName": collection.name,
                "evaluationItemId": identifier,
                "workspaceId": None,
                "syncStatus": "synced",
                "statePersistence": "runtime",
            }

        result = {}
        for start in range(0, len(event_ids), 8):
            for event_id, state in await asyncio.gather(
                *(read(value) for value in event_ids[start : start + 8])
            ):
                result[f"veadk_feedback:{event_id}"] = state
        return result
