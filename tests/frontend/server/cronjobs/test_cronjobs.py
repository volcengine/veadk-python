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

import io
import json
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from frontend.server.cronjobs import (
    CronjobAccessDenied,
    CronjobConflict,
    CronjobIdentity,
    CronjobRunQueueUnavailable,
    CronjobService,
    OwnerOnlyAccessPolicy,
    TosCronjobRepository,
    mount_routes,
    mount_storage_unavailable_routes,
)
from frontend.server.cronjobs.schemas import (
    CreateCronjobRequest,
    Cronjob,
    CronjobRun,
    UpdateCronjobRequest,
)
from frontend.service.studio_scheduler.models import (
    CronJob as SchedulerCronJob,
)
from frontend.service.studio_scheduler.models import (
    ScheduledRun,
)


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS {status_code}")
        self.status_code = status_code


class _Object(io.BytesIO):
    def __init__(self, content: bytes, etag: str) -> None:
        super().__init__(content)
        self.etag = etag


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}
        self.put_calls: list[dict[str, Any]] = []
        self._version = 0

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: Any,
        forbid_overwrite: bool = False,
        if_match: str | None = None,
        **_: Any,
    ) -> SimpleNamespace:
        object_key = (bucket, key)
        current = self.objects.get(object_key)
        if forbid_overwrite and current is not None:
            raise _TosError(409)
        if if_match is not None and (current is None or current[1] != if_match):
            raise _TosError(412)
        data = content.read() if hasattr(content, "read") else bytes(content)
        self._version += 1
        etag = f'"v{self._version}"'
        self.objects[object_key] = (data, etag)
        self.put_calls.append(
            {
                "key": key,
                "forbid_overwrite": forbid_overwrite,
                "if_match": if_match,
            }
        )
        return SimpleNamespace(etag=etag)

    def get_object(self, *, bucket: str, key: str) -> _Object:
        try:
            content, etag = self.objects[(bucket, key)]
        except KeyError as error:
            raise _TosError(404) from error
        return _Object(content, etag)

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        keys = sorted(
            key
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        )
        start = int(continuation_token or 0)
        page = keys[start : start + max_keys]
        next_index = start + len(page)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in page],
            is_truncated=next_index < len(keys),
            next_continuation_token=(
                str(next_index) if next_index < len(keys) else None
            ),
        )

    def delete_object(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


class _DuePublisher:
    def __init__(self) -> None:
        self.next_jobs: list[tuple[object, datetime]] = []
        self.run_now: list[tuple[str, str, int, datetime]] = []

    async def publish_next(self, job: object, *, after: datetime) -> object:
        self.next_jobs.append((job, after))
        return SimpleNamespace(scheduled_at=after)

    async def publish_run_now(
        self,
        *,
        user_id: str,
        job_id: str,
        revision: int,
        scheduled_at: datetime,
    ) -> str:
        self.run_now.append((user_id, job_id, revision, scheduled_at))
        return "manual-run-id"


NOW = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)


def _create_body(name: str = "Daily report") -> CreateCronjobRequest:
    return CreateCronjobRequest.model_validate(
        {
            "name": name,
            "runtimeId": "runtime-1",
            "runtimeName": "Report runtime",
            "agentName": "report_agent",
            "region": "cn-beijing",
            "prompt": "Summarize yesterday's incidents.",
            "schedule": {
                "type": "daily",
                "timezone": "Asia/Shanghai",
                "time": "09:30",
            },
            "enabled": True,
        }
    )


def _repository(client: _FakeTosClient) -> TosCronjobRepository:
    return TosCronjobRepository(bucket="studio", client_factory=lambda: client)


def _service(
    client: _FakeTosClient,
    *,
    access_policy: Any | None = None,
    due_publisher: Any | None = None,
) -> CronjobService:
    ids = iter(
        [
            "00000000-0000-4000-8000-000000000001",
            "00000000-0000-4000-8000-000000000002",
            "00000000-0000-4000-8000-000000000003",
            "00000000-0000-4000-8000-000000000004",
            "00000000-0000-4000-8000-000000000005",
        ]
    )
    return CronjobService(
        _repository(client),
        access_policy=access_policy or OwnerOnlyAccessPolicy(),
        due_publisher=due_publisher or _DuePublisher(),
        clock=lambda: NOW,
        id_factory=lambda: next(ids),
    )


def test_schedule_contract_validates_timezone_and_variants() -> None:
    assert _create_body().schedule.type == "daily"
    assert (
        CreateCronjobRequest.model_validate(
            {
                **_create_body().model_dump(by_alias=True),
                "schedule": {
                    "type": "once",
                    "timezone": "UTC",
                    "onceAt": "2026-08-21T09:00",
                },
            }
        ).schedule.type
        == "once"
    )
    assert (
        CreateCronjobRequest.model_validate(
            {
                **_create_body().model_dump(by_alias=True),
                "schedule": {
                    "type": "weekly",
                    "timezone": "Asia/Shanghai",
                    "weekday": 4,
                    "time": "10:15",
                },
            }
        ).schedule.type
        == "weekly"
    )
    assert (
        CreateCronjobRequest.model_validate(
            {
                **_create_body().model_dump(by_alias=True),
                "schedule": {
                    "type": "cron",
                    "timezone": "Asia/Shanghai",
                    "cron": "*/5 * * * *",
                },
            }
        ).schedule.type
        == "cron"
    )

    with pytest.raises(ValidationError, match="timezone"):
        CreateCronjobRequest.model_validate(
            {
                **_create_body().model_dump(by_alias=True),
                "schedule": {
                    "type": "daily",
                    "timezone": "Mars/Olympus",
                    "time": "09:00",
                },
            }
        )
    with pytest.raises(ValidationError, match="five fields"):
        CreateCronjobRequest.model_validate(
            {
                **_create_body().model_dump(by_alias=True),
                "schedule": {
                    "type": "cron",
                    "timezone": "UTC",
                    "cron": "* * *",
                },
            }
        )


@pytest.mark.asyncio
async def test_repository_uses_user_namespace_and_conditional_writes() -> None:
    client = _FakeTosClient()
    repository = _repository(client)
    job = Cronjob(
        jobId="job-1",
        ownerId="owner@example.com",
        **_create_body().model_dump(by_alias=True),
        revision=1,
        createdAt=NOW,
        updatedAt=NOW,
    )

    stored = await repository.create_job(job)
    assert stored.value == job
    key = "veadk-studio/v1/users/owner%40example.com/cronjobs/job-1/job.json"
    assert client.put_calls[-1] == {
        "key": key,
        "forbid_overwrite": True,
        "if_match": None,
    }
    persisted = json.loads(client.objects[("studio", key)][0])
    scheduler_job = SchedulerCronJob.from_dict(persisted)
    assert scheduler_job.user_id == "owner@example.com"
    assert scheduler_job.runtime.runtime_id == "runtime-1"
    assert scheduler_job.schedule.kind == "daily"
    assert (scheduler_job.schedule.hour, scheduler_job.schedule.minute) == (9, 30)

    updated = job.model_copy(update={"name": "Updated", "revision": 2})
    await repository.update_job(updated, stored.etag)
    assert client.put_calls[-1]["key"] == key
    assert client.put_calls[-1]["if_match"] == stored.etag

    with pytest.raises(CronjobConflict):
        await repository.update_job(updated, stored.etag)


@pytest.mark.asyncio
async def test_service_enforces_owner_policy_and_supports_admin_policy() -> None:
    client = _FakeTosClient()
    service = _service(client)
    alice = CronjobIdentity(ownerId="alice")
    bob = CronjobIdentity(ownerId="bob")
    job = await service.create(alice, _create_body())

    assert [item.id for item in await service.list(alice)] == [job.id]
    with pytest.raises(CronjobAccessDenied):
        await service.get(bob, job.id, owner_id="alice")

    class _AdminPolicy:
        def resolve_owner(
            self, identity: CronjobIdentity, requested_owner_id: str | None
        ) -> str:
            if identity.owner_id == "admin" and requested_owner_id:
                return requested_owner_id
            return OwnerOnlyAccessPolicy().resolve_owner(identity, requested_owner_id)

    admin_service = _service(client, access_policy=_AdminPolicy())
    admin = CronjobIdentity(ownerId="admin")
    assert (await admin_service.get(admin, job.id, owner_id="alice")).id == job.id


@pytest.mark.asyncio
async def test_crud_pause_resume_run_now_cancel_and_delete_cascade() -> None:
    client = _FakeTosClient()
    due_publisher = _DuePublisher()
    service = _service(client, due_publisher=due_publisher)
    identity = CronjobIdentity(ownerId="owner")
    job = await service.create(identity, _create_body())
    assert job.next_run_at == datetime(2026, 8, 21, 1, 30, tzinfo=timezone.utc)

    updated = await service.update(
        identity,
        job.id,
        UpdateCronjobRequest(name="Renamed", prompt="Use the new prompt."),
    )
    assert updated.name == "Renamed"
    assert updated.prompt == "Use the new prompt."
    assert updated.revision == 2

    paused = await service.disable(identity, job.id)
    assert paused.enabled is False
    assert paused.next_run_at is None
    resumed = await service.enable(identity, job.id)
    assert resumed.enabled is True
    assert resumed.next_run_at == datetime(2026, 8, 21, 1, 30, tzinfo=timezone.utc)
    assert len(due_publisher.next_jobs) == 3
    scheduled_job, scheduled_after = due_publisher.next_jobs[-1]
    assert isinstance(scheduled_job, SchedulerCronJob)
    assert scheduled_job.revision == resumed.revision
    assert scheduled_after == NOW

    run = await service.request_run(identity, job.id)
    assert run.status == "queued"
    assert run.session_id
    assert run.session_id == run.id
    assert due_publisher.run_now == [("owner", job.id, resumed.revision, NOW)]
    assert await service.list_runs(identity, job.id) == [run]

    run_key = f"veadk-studio/v1/users/owner/cronjobs/{job.id}/runs/{run.id}.json"
    scheduler_run = ScheduledRun.from_dict(
        json.loads(client.objects[("studio", run_key)][0])
    )
    assert scheduler_run.run_id == run.id

    cancelling = await service.cancel(identity, job.id, run.id)
    assert cancelling.status == "queued"
    assert cancelling.cancellation_requested_at == NOW

    await service.delete(identity, job.id)
    assert not [
        key
        for bucket, key in client.objects
        if bucket == "studio"
        and key.startswith(f"veadk-studio/v1/users/owner/cronjobs/{job.id}/")
    ]


@pytest.mark.asyncio
async def test_service_updates_schedule_without_flattening_nested_model() -> None:
    client = _FakeTosClient()
    due_publisher = _DuePublisher()
    service = _service(client, due_publisher=due_publisher)
    identity = CronjobIdentity(ownerId="owner")
    job = await service.create(identity, _create_body())

    updated = await service.update(
        identity,
        job.id,
        UpdateCronjobRequest(
            schedule={
                "type": "once",
                "timezone": "Asia/Shanghai",
                "onceAt": "2026-08-20T18:30",
            }
        ),
    )

    assert updated.schedule.type == "once"
    assert updated.next_run_at == datetime(2026, 8, 20, 10, 30, tzinfo=timezone.utc)
    assert isinstance(due_publisher.next_jobs[-1][0], SchedulerCronJob)
    assert due_publisher.next_jobs[-1][0].schedule.kind == "once"


@pytest.mark.asyncio
async def test_run_request_requires_due_publisher_and_cleans_up_publish_failure() -> (
    None
):
    client = _FakeTosClient()
    identity = CronjobIdentity(ownerId="owner")
    service = _service(client)
    job = await service.create(identity, _create_body())
    service._due_publisher = None

    with pytest.raises(CronjobRunQueueUnavailable, match="尚未配置"):
        await service.request_run(identity, job.id)
    assert await service.list_runs(identity, job.id) == []

    class _FailingPublisher(_DuePublisher):
        async def publish_run_now(self, **kwargs: Any) -> str:
            raise RuntimeError("TOS unavailable")

    failing_service = _service(client, due_publisher=_FailingPublisher())
    with pytest.raises(CronjobRunQueueUnavailable, match="无法提交"):
        await failing_service.request_run(identity, job.id)

    assert await failing_service.list_runs(identity, job.id) == []
    assert await failing_service.repository.get_lock("owner", job.id) is None


def test_routes_expose_stable_management_contract() -> None:
    client = _FakeTosClient()
    app = FastAPI()
    service = _service(client)
    mount_routes(
        app,
        service,
        lambda request: CronjobIdentity(ownerId=request.headers["X-Owner"]),
    )
    http = TestClient(app)

    created = http.post(
        "/web/cronjobs",
        headers={"X-Owner": "owner"},
        json=_create_body().model_dump(mode="json", by_alias=True),
    )
    assert created.status_code == 201
    job = created.json()
    assert job["ownerId"] == "owner"

    assert (
        http.get("/web/cronjobs", headers={"X-Owner": "owner"}).json()["items"][0][
            "jobId"
        ]
        == job["jobId"]
    )
    updated = http.post(
        f"/web/cronjobs/{job['jobId']}/update",
        headers={"X-Owner": "owner"},
        json={"name": "Updated through gateway-compatible route"},
    )
    assert updated.status_code == 200
    assert updated.json()["name"] == "Updated through gateway-compatible route"
    assert (
        http.post(
            f"/web/cronjobs/{job['jobId']}/disable", headers={"X-Owner": "owner"}
        ).json()["enabled"]
        is False
    )
    assert (
        http.post(
            f"/web/cronjobs/{job['jobId']}/enable", headers={"X-Owner": "owner"}
        ).json()["enabled"]
        is True
    )

    run_response = http.post(
        f"/web/cronjobs/{job['jobId']}/run", headers={"X-Owner": "owner"}
    )
    assert run_response.status_code == 202
    run = run_response.json()
    assert run["status"] == "queued"
    run_items = http.get(
        f"/web/cronjobs/{job['jobId']}/runs", headers={"X-Owner": "owner"}
    ).json()["items"]
    assert [item["status"] for item in run_items] == ["queued"]
    assert (
        http.post(
            f"/web/cronjobs/{job['jobId']}/runs/{run['runId']}/cancel",
            headers={"X-Owner": "owner"},
        ).json()["status"]
        == "queued"
    )

    denied = http.get(
        f"/web/cronjobs/{job['jobId']}",
        params={"ownerId": "owner"},
        headers={"X-Owner": "other"},
    )
    assert denied.status_code == 403


def test_models_forbid_unknown_fields_and_empty_patch() -> None:
    with pytest.raises(ValidationError):
        _create_body().model_copy(update={"unexpected": True}).model_validate(
            {**_create_body().model_dump(), "unexpected": True}
        )
    with pytest.raises(ValidationError, match="At least one"):
        UpdateCronjobRequest()
    assert CronjobRun.model_fields["session_id"].alias == "sessionId"


def test_unmounted_storage_keeps_cronjob_routes_json_and_actionable() -> None:
    app = FastAPI()
    mount_storage_unavailable_routes(app)
    http = TestClient(app)

    for method, path in (
        ("get", "/web/cronjobs"),
        ("post", "/web/cronjobs/job-1/run"),
    ):
        response = getattr(http, method)(path)
        assert response.status_code == 503
        assert response.headers["content-type"].startswith("application/json")
        detail = response.json()["detail"]
        assert "未挂载 TOS 持久化存储" in detail
        assert "VEADK_STUDIO_TOS_BUCKET" in detail
        assert "VEADK_STUDIO_TOS_REGION" in detail


def test_unreachable_tos_returns_actionable_storage_error() -> None:
    class _UnavailableTosClient(_FakeTosClient):
        def list_objects_type2(self, **_: Any) -> SimpleNamespace:
            raise RuntimeError("connection refused")

    app = FastAPI()
    mount_routes(
        app,
        _service(_UnavailableTosClient()),
        lambda request: CronjobIdentity(ownerId="owner"),
    )
    response = TestClient(app).get("/web/cronjobs")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert "无法连接定时任务使用的 TOS 持久化存储" in detail
    assert "Bucket、Region、Endpoint、访问凭据和网络连通性" in detail
    assert "connection refused" not in detail
