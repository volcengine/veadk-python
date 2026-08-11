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
import sys
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.agent_usage import create_service, mount_routes
from frontend.server.agent_usage.models import AgentUsageEvent, AgentUsageSummary
from frontend.server.agent_usage.service import (
    AgentUsageService,
    AgentUsageStorageUnavailable,
)
from frontend.server.storage import StudioStorageConfig
from frontend.server.storage.tos import create_tos_client_factory


class _Repository:
    def __init__(self) -> None:
        self.events: list[AgentUsageEvent] = []
        self.release = asyncio.Event()

    async def append(self, event: AgentUsageEvent) -> None:
        await self.release.wait()
        self.events.append(event)

    async def get_summary(self, **kwargs: Any) -> AgentUsageSummary:
        return AgentUsageSummary(
            runtimeId=kwargs["runtime_id"],
            appName=kwargs["app_name"],
            totalInvocations=0,
            totalUsers=0,
            page=kwargs["page"],
            pageSize=kwargs["page_size"],
            totalPages=0,
            users=[],
        )


class _FailingRepository(_Repository):
    async def append(self, event: AgentUsageEvent) -> None:
        raise RuntimeError("write failed")

    async def get_summary(self, **kwargs: Any) -> AgentUsageSummary:
        raise RuntimeError("read failed")


@pytest.mark.asyncio
async def test_record_is_non_blocking_and_close_waits_for_pending_writes() -> None:
    repository = _Repository()
    service = AgentUsageService(repository)
    service.record_success(
        invocation_id="call-1",
        runtime_id="runtime",
        app_name="agent",
        user_id="user",
        display_name="User",
        used_at=datetime(2026, 8, 11, tzinfo=timezone.utc),
    )
    await asyncio.sleep(0)
    assert repository.events == []

    closing = asyncio.create_task(service.close())
    await asyncio.sleep(0)
    assert not closing.done()
    repository.release.set()
    await closing
    assert [event.invocation_id for event in repository.events] == ["call-1"]


@pytest.mark.asyncio
async def test_unavailable_service_does_not_fake_empty_usage() -> None:
    service = AgentUsageService(None, unavailable_reason="storage missing")

    with pytest.raises(AgentUsageStorageUnavailable, match="storage missing"):
        await service.get_summary(
            runtime_id="runtime", app_name="agent", page=1, page_size=20
        )


@pytest.mark.asyncio
async def test_background_write_error_does_not_escape_close() -> None:
    service = AgentUsageService(_FailingRepository())
    service.record_success(
        invocation_id="call-1",
        runtime_id="runtime",
        app_name="agent",
        user_id="user",
    )

    await service.close()


@pytest.mark.asyncio
async def test_invalid_usage_event_does_not_interrupt_the_caller() -> None:
    repository = _Repository()
    service = AgentUsageService(repository)

    service.record_success(
        invocation_id="",
        runtime_id="runtime",
        app_name="agent",
        user_id="user",
    )

    repository.release.set()
    await service.close()
    assert repository.events == []


def test_route_authorizes_runtime_and_returns_stable_contract() -> None:
    repository = _Repository()
    repository.release.set()
    service = AgentUsageService(repository)
    app = FastAPI()
    authorized: list[tuple[str, str]] = []
    mount_routes(
        app,
        service,
        lambda _request, runtime_id, region: authorized.append((runtime_id, region)),
    )

    response = TestClient(app).get(
        "/web/agent-usage",
        params={
            "runtimeId": "runtime",
            "region": "cn-beijing",
            "appName": "agent",
            "page": 1,
            "pageSize": 20,
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "runtimeId": "runtime",
        "appName": "agent",
        "totalInvocations": 0,
        "totalUsers": 0,
        "page": 1,
        "pageSize": 20,
        "totalPages": 0,
        "users": [],
    }
    assert authorized == [("runtime", "cn-beijing")]


def test_route_keeps_auth_error() -> None:
    app = FastAPI()
    mount_routes(
        app,
        AgentUsageService(None, unavailable_reason="missing"),
        lambda *_: (_ for _ in ()).throw(HTTPException(status_code=403)),
    )

    response = TestClient(app).get(
        "/web/agent-usage",
        params={
            "runtimeId": "runtime",
            "region": "cn-beijing",
            "appName": "agent",
        },
    )
    assert response.status_code == 403


def test_route_returns_503_when_storage_is_not_configured(monkeypatch) -> None:
    monkeypatch.delenv("VEADK_STUDIO_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)
    monkeypatch.delenv("VEADK_VIDEO_ASSET_STORAGE", raising=False)
    monkeypatch.delenv("VEADK_MEDIA_STORAGE", raising=False)
    app = FastAPI()
    mount_routes(app, create_service(), lambda *_: None)

    response = TestClient(app).get(
        "/web/agent-usage",
        params={
            "runtimeId": "runtime",
            "region": "cn-beijing",
            "appName": "agent",
        },
    )
    assert response.status_code == 503
    assert response.json()["detail"]


def test_route_hides_storage_read_errors() -> None:
    app = FastAPI()
    mount_routes(app, AgentUsageService(_FailingRepository()), lambda *_: None)

    response = TestClient(app).get(
        "/web/agent-usage",
        params={
            "runtimeId": "runtime",
            "region": "cn-beijing",
            "appName": "agent",
        },
    )

    assert response.status_code == 502
    assert response.json() == {"detail": "无法读取 Agent 用量统计，请稍后重试。"}


@pytest.mark.parametrize(
    ("provider", "region", "endpoint"),
    [
        ("volcengine", "cn-beijing", "tos-cn-beijing.volces.com"),
        ("byteplus", "ap-southeast-1", "tos-ap-southeast-1.bytepluses.com"),
    ],
)
def test_shared_tos_factory_uses_provider_endpoint(
    monkeypatch,
    provider: str,
    region: str,
    endpoint: str,
) -> None:
    captured: dict[str, object] = {}

    class _Client:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "tos", SimpleNamespace(TosClientV2=_Client))
    config = StudioStorageConfig.from_env(
        provider,  # type: ignore[arg-type]
        {
            "VEADK_STUDIO_TOS_BUCKET": "studio",
            "VEADK_STUDIO_TOS_REGION": region,
        },
    )
    factory = create_tos_client_factory(config, lambda: ("ak", "sk", "token"))

    factory()

    assert captured == {
        "ak": "ak",
        "sk": "sk",
        "security_token": "token",
        "endpoint": endpoint,
        "region": region,
    }
