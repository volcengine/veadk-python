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

"""TOS persistence for immutable agent usage events."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

from .models import AgentUsageEvent, AgentUsageSummary, AgentUsageUser

_KEY_PREFIX = f"{STUDIO_STORAGE_ROOT_PREFIX}/agent-usage"
_MAX_EVENT_BYTES = 32 * 1024


class AgentUsageEventConflict(RuntimeError):
    """Raised when an invocation ID is reused with different event data."""


class TosAgentUsageRepository:
    """Append usage events without mutable counters or cross-instance locks."""

    def __init__(self, *, bucket: str, client_factory: Callable[[], Any]) -> None:
        if not bucket.strip():
            raise ValueError("TOS agent usage storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory

    async def append(self, event: AgentUsageEvent) -> None:
        await asyncio.to_thread(self._append, event)

    def _append(self, event: AgentUsageEvent) -> None:
        client = self._client_factory()
        content = event.model_dump_json(by_alias=True).encode("utf-8")
        event_key = self._event_key(event)
        try:
            client.put_object(
                bucket=self._bucket,
                key=event_key,
                content=content,
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise
            existing = self._get_bytes(client, event_key)
            if existing != content:
                raise AgentUsageEventConflict(
                    f"Invocation {event.invocation_id!r} already has different data."
                ) from error

        marker = json.dumps(
            {"userId": event.user_id}, ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        try:
            client.put_object(
                bucket=self._bucket,
                key=self._user_marker_key(event),
                content=marker,
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) not in {409, 412}:
                raise

    async def get_summary(
        self,
        *,
        runtime_id: str,
        app_name: str,
        page: int,
        page_size: int,
    ) -> AgentUsageSummary:
        return await asyncio.to_thread(
            self._get_summary,
            runtime_id,
            app_name,
            page,
            page_size,
        )

    def _get_summary(
        self,
        runtime_id: str,
        app_name: str,
        page: int,
        page_size: int,
    ) -> AgentUsageSummary:
        client = self._client_factory()
        events = [
            AgentUsageEvent.model_validate_json(self._get_bytes(client, key))
            for key in self._list_event_keys(client, runtime_id, app_name)
        ]
        per_user: dict[str, AgentUsageUser] = {}
        for event in events:
            current = per_user.get(event.user_id)
            if current is None:
                per_user[event.user_id] = AgentUsageUser(
                    userId=event.user_id,
                    displayName=event.display_name,
                    invocationCount=1,
                    lastUsedAt=event.used_at,
                )
                continue
            current.invocation_count += 1
            if event.used_at >= current.last_used_at:
                current.last_used_at = event.used_at
                current.display_name = event.display_name

        users = sorted(
            per_user.values(),
            key=lambda item: (
                -item.invocation_count,
                -item.last_used_at.timestamp(),
                item.user_id,
            ),
        )
        total_users = len(users)
        start = (page - 1) * page_size
        return AgentUsageSummary(
            runtimeId=runtime_id,
            appName=app_name,
            totalInvocations=len(events),
            totalUsers=total_users,
            page=page,
            pageSize=page_size,
            totalPages=math.ceil(total_users / page_size) if total_users else 0,
            users=users[start : start + page_size],
        )

    def _list_event_keys(
        self,
        client: Any,
        runtime_id: str,
        app_name: str,
    ) -> list[str]:
        prefix = f"{self._agent_prefix(runtime_id, app_name)}/events/"
        continuation_token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if str(getattr(item, "key", "")).endswith(".json")
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated an agent usage listing without a continuation token."
                )

    def _get_bytes(self, client: Any, key: str) -> bytes:
        response = client.get_object(bucket=self._bucket, key=key)
        if hasattr(response, "read"):
            content = response.read()
        else:
            content = b"".join(response)
        if len(content) > _MAX_EVENT_BYTES:
            raise ValueError("Studio agent usage event is too large.")
        return content

    @classmethod
    def _event_key(cls, event: AgentUsageEvent) -> str:
        invocation_hash = _digest(event.invocation_id)
        return (
            f"{cls._agent_prefix(event.runtime_id, event.app_name)}/events/"
            f"{invocation_hash}.json"
        )

    @classmethod
    def _user_marker_key(cls, event: AgentUsageEvent) -> str:
        return (
            f"{cls._agent_prefix(event.runtime_id, event.app_name)}/users/"
            f"{_digest(event.user_id)}.json"
        )

    @staticmethod
    def _agent_prefix(runtime_id: str, app_name: str) -> str:
        return f"{_KEY_PREFIX}/{quote(runtime_id, safe='')}/{quote(app_name, safe='')}"


def _digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
