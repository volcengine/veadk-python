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

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from threading import Lock
from types import SimpleNamespace

import pytest

from frontend.server.agent_usage.models import AgentUsageEvent
from frontend.server.agent_usage.repository import (
    AgentUsageEventConflict,
    TosAgentUsageRepository,
)


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS {status_code}")
        self.status_code = status_code


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._lock = Lock()

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        forbid_overwrite: bool,
        **_: object,
    ) -> None:
        with self._lock:
            object_key = (bucket, key)
            if forbid_overwrite and object_key in self.objects:
                raise _TosError(409)
            self.objects[object_key] = bytes(content)

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        with self._lock:
            try:
                return [self.objects[(bucket, key)]]
            except KeyError as error:
                raise _TosError(404) from error

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        with self._lock:
            keys = sorted(
                key
                for object_bucket, key in self.objects
                if object_bucket == bucket and key.startswith(prefix)
            )
        start = int(continuation_token or 0)
        selected = keys[start : start + max_keys]
        next_index = start + len(selected)
        truncated = next_index < len(keys)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in selected],
            is_truncated=truncated,
            next_continuation_token=str(next_index) if truncated else None,
        )


def _event(
    invocation_id: str,
    user_id: str,
    offset: int,
    display_name: str = "",
) -> AgentUsageEvent:
    return AgentUsageEvent(
        invocationId=invocation_id,
        runtimeId="runtime/id",
        appName="客服/助手",
        userId=user_id,
        displayName=display_name,
        usedAt=datetime(2026, 8, 11, tzinfo=timezone.utc) + timedelta(minutes=offset),
    )


@pytest.mark.asyncio
async def test_concurrent_events_are_not_lost_and_duplicate_is_idempotent() -> None:
    client = _FakeTosClient()
    repositories = [
        TosAgentUsageRepository(bucket="studio", client_factory=lambda: client)
        for _ in range(2)
    ]
    events = [
        _event("call-1", "user@example.com", 1, "User"),
        _event("call-2", "user@example.com", 2, "User"),
        _event("call-3", "another/user", 3, "Another"),
    ]

    await asyncio.gather(
        repositories[0].append(events[0]),
        repositories[1].append(events[1]),
        repositories[0].append(events[2]),
        repositories[1].append(events[0]),
    )

    summary = await repositories[0].get_summary(
        runtime_id="runtime/id",
        app_name="客服/助手",
        page=1,
        page_size=20,
    )
    assert summary.total_invocations == 3
    assert summary.total_users == 2
    assert [(item.user_id, item.invocation_count) for item in summary.users] == [
        ("user@example.com", 2),
        ("another/user", 1),
    ]
    assert all("user@example.com" not in key for _, key in client.objects)
    assert all("another/user" not in key for _, key in client.objects)


@pytest.mark.asyncio
async def test_duplicate_invocation_with_different_data_is_rejected() -> None:
    client = _FakeTosClient()
    repository = TosAgentUsageRepository(bucket="studio", client_factory=lambda: client)
    await repository.append(_event("call-1", "user-1", 1))

    with pytest.raises(AgentUsageEventConflict):
        await repository.append(_event("call-1", "user-2", 1))


@pytest.mark.asyncio
async def test_summary_paginates_users_and_uses_latest_display_name() -> None:
    client = _FakeTosClient()
    repository = TosAgentUsageRepository(bucket="studio", client_factory=lambda: client)
    for event in (
        _event("a-1", "a", 1, "Old A"),
        _event("a-2", "a", 4, "New A"),
        _event("b-1", "b", 3, "B"),
        _event("c-1", "c", 2, "C"),
    ):
        await repository.append(event)

    first = await repository.get_summary(
        runtime_id="runtime/id", app_name="客服/助手", page=1, page_size=2
    )
    second = await repository.get_summary(
        runtime_id="runtime/id", app_name="客服/助手", page=2, page_size=2
    )

    assert first.total_invocations == 4
    assert first.total_users == 3
    assert first.total_pages == 2
    assert [item.user_id for item in first.users] == ["a", "b"]
    assert first.users[0].display_name == "New A"
    assert [item.user_id for item in second.users] == ["c"]


@pytest.mark.asyncio
async def test_missing_agent_returns_an_empty_but_available_summary() -> None:
    repository = TosAgentUsageRepository(bucket="studio", client_factory=_FakeTosClient)

    summary = await repository.get_summary(
        runtime_id="missing", app_name="agent", page=1, page_size=20
    )

    assert summary.total_invocations == 0
    assert summary.total_users == 0
    assert summary.total_pages == 0
    assert summary.users == []
