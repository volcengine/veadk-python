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

import hashlib
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.cronjobs import (
    CreateCronjobRequest,
    CronjobIdentity,
    CronjobService,
    TosCronjobRepository,
)
from frontend.service.studio_scheduler import DuePublisher, TosSchedulerRepository
from frontend.service.studio_scheduler.dispatcher import Dispatcher
from frontend.service.studio_scheduler.models import ExecutionResult


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _SharedFakeTos:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], tuple[bytes, str]] = {}

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: Any,
        forbid_overwrite: bool | None = None,
        if_match: str | None = None,
        **_: Any,
    ) -> SimpleNamespace:
        current = self.objects.get((bucket, key))
        if forbid_overwrite and current is not None:
            raise _TosError(409)
        if if_match is not None and (current is None or current[1] != if_match):
            raise _TosError(412)
        body = content.read() if hasattr(content, "read") else bytes(content)
        etag = hashlib.sha256(body).hexdigest()
        self.objects[(bucket, key)] = (body, etag)
        return SimpleNamespace(etag=etag)

    def get_object(self, *, bucket: str, key: str) -> SimpleNamespace:
        try:
            content, etag = self.objects[(bucket, key)]
        except KeyError as error:
            raise _TosError(404) from error
        return SimpleNamespace(read=lambda *_: content, etag=etag)

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        del continuation_token, max_keys
        keys = sorted(
            key
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        )
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in keys],
            is_truncated=False,
            next_continuation_token=None,
        )

    def delete_object(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)


@pytest.mark.asyncio
async def test_management_to_due_dispatch_history_and_delete_flow() -> None:
    now = datetime(2026, 8, 20, 10, 35, 42, tzinfo=timezone.utc)
    tos = _SharedFakeTos()

    def factory() -> _SharedFakeTos:
        return tos

    scheduler_repository = TosSchedulerRepository(
        bucket="studio",
        client_factory=factory,
        provider="volcengine",
    )
    service = CronjobService(
        TosCronjobRepository(bucket="studio", client_factory=factory),
        due_publisher=DuePublisher(scheduler_repository),
        clock=lambda: now,
        id_factory=lambda: "job-1",
    )
    identity = CronjobIdentity(ownerId="owner-1")
    job = await service.create(
        identity,
        CreateCronjobRequest.model_validate(
            {
                "name": "Daily summary",
                "runtimeId": "runtime-1",
                "runtimeName": "Summary Agent",
                "agentName": "summary_agent",
                "region": "cn-beijing",
                "prompt": "Summarize the latest incidents.",
                "schedule": {
                    "type": "daily",
                    "timezone": "Asia/Shanghai",
                    "time": "09:30",
                },
                "enabled": True,
            }
        ),
    )
    pending = await service.request_run(identity, job.id)
    assert pending.status == "queued"

    class _Executor:
        async def execute(self, request: Any, control: Any) -> ExecutionResult:
            assert request.session_id == pending.session_id
            assert await control.is_cancel_requested() is False
            return ExecutionResult(output="Summary ready", runtime_version="7")

    dispatcher = Dispatcher(
        scheduler_repository,
        _Executor(),
        replica_id="local-e2e",
    )
    scan_summary = await dispatcher.dispatch_minute(now + timedelta(minutes=1))
    summary = await dispatcher.execute_ready(now + timedelta(minutes=1))

    assert scan_summary.queued == 1
    assert summary.started == 1
    runs = await service.list_runs(identity, job.id)
    assert [(run.status, run.output, run.runtime_version) for run in runs] == [
        ("success", "Summary ready", "7")
    ]
    assert (await service.disable(identity, job.id)).enabled is False
    assert (await service.enable(identity, job.id)).enabled is True

    await service.delete(identity, job.id)
    user_prefix = "veadk-studio/v1/users/owner-1/cronjobs/job-1/"
    assert not [
        key
        for bucket, key in tos.objects
        if bucket == "studio" and key.startswith(user_prefix)
    ]
