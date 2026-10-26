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

"""IAM transient recovery without real cloud calls."""

import asyncio
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import requests

from veadk.integrations.mpa.managed import iam
from veadk.integrations.mpa.managed.diagnostics import (
    diagnostic_scope,
    validate_diagnostic,
)
from veadk.integrations.mpa.managed.tasks import CreationTasks
from tests.integrations.mpa_managed.test_iam import FakeIAM

REQUEST_ID = "20261014064128489F845912CDFFF9B5DB"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "category", ["timeout", "connection", "throttled", "unavailable"]
)
async def test_transient_reconciliation_retries_and_keeps_safe_diagnostics(
    monkeypatch, category
):
    cloud = FakeIAM()
    await iam.ensure_runtime_role(cloud, "123", poll_interval=0)
    original = cloud.call
    attempts = 0

    async def call(method, **params):
        nonlocal attempts
        if method == "get_role":
            attempts += 1
            if attempts < 3:
                raise iam.IamError(
                    category=category, operation=method, request_id=REQUEST_ID
                )
        return await original(method, **params)

    cloud.call = call
    delay = AsyncMock()
    monkeypatch.setattr(iam.asyncio, "sleep", delay)
    events = []
    with diagnostic_scope(events.append):
        await iam.ensure_runtime_role(cloud, "123")
    assert attempts == 4  # Two failed reads followed by initial/final readback.
    assert [x.args[0] for x in delay.await_args_list] == [1, 2]
    assert events == [
        dict(
            operation="iam_get_role",
            category=category,
            attempt=i,
            outcome="retrying",
            exceptionType="RuntimeError",
            requestId=REQUEST_ID,
        )
        for i in [1, 2]
    ]


@pytest.mark.asyncio
async def test_transient_exhaustion_stops_at_four_attempts(monkeypatch):
    cloud = FakeIAM()
    calls = []

    async def call(method, **params):
        calls.append(method)
        raise iam.IamError(category="timeout", operation=method, request_id=REQUEST_ID)

    cloud.call = call
    delay = AsyncMock()
    monkeypatch.setattr(iam.asyncio, "sleep", delay)
    events = []
    with (
        diagnostic_scope(events.append),
        pytest.raises(iam.IamError, match="iamTemporaryFailure"),
    ):
        await iam.ensure_runtime_role(cloud, "123")
    assert calls == ["get_role"] * 4
    assert [x.args[0] for x in delay.await_args_list] == [1, 2, 4]
    assert events[-1]["outcome"] == "failed" and events[-1]["attempt"] == 4


@pytest.mark.asyncio
async def test_lost_create_response_reads_existing_role_before_retry(monkeypatch):
    cloud = FakeIAM()
    original = cloud.call
    lost = False

    async def call(method, **params):
        nonlocal lost
        result = await original(method, **params)
        if method == "create_role" and not lost:
            lost = True
            raise iam.IamError(category="connection", operation=method)
        return result

    cloud.call = call
    monkeypatch.setattr(iam.asyncio, "sleep", AsyncMock())
    await iam.ensure_runtime_role(cloud, "123")
    assert len([m for m, _ in cloud.calls if m == "create_role"]) == 1
    assert cloud.role and cloud.policy


@pytest.mark.asyncio
@pytest.mark.parametrize("code", ["AccessDenied", "UnexpectedPrivateError"])
async def test_permanent_and_unknown_errors_do_not_retry(monkeypatch, code):
    cloud = FakeIAM()
    call = AsyncMock(
        side_effect=iam.IamError(code, operation="get_role", request_id=REQUEST_ID)
    )
    cloud.call = call
    delay = AsyncMock()
    monkeypatch.setattr(iam.asyncio, "sleep", delay)
    events = []
    with diagnostic_scope(events.append), pytest.raises(iam.IamError) as error:
        await iam.ensure_runtime_role(cloud, "123")
    assert error.value.key == (
        "iamPermissionDenied" if code == "AccessDenied" else "iamVerificationFailed"
    )
    call.assert_awaited_once()
    delay.assert_not_awaited()
    assert events[-1]["requestId"] == REQUEST_ID


@pytest.mark.asyncio
async def test_deadline_is_temporary_and_cancellation_dispatches_no_more_calls():
    cloud = FakeIAM()

    async def slow(method, **params):
        await asyncio.sleep(10)

    call = AsyncMock(side_effect=slow)
    cloud.call = call
    with pytest.raises(iam.IamError, match="iamTemporaryFailure"):
        await iam.ensure_runtime_role(cloud, "123", timeout=0.01)
    task = asyncio.create_task(iam.ensure_runtime_role(cloud, "123"))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    count = call.await_count
    await asyncio.sleep(0.01)
    assert call.await_count == count


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "problem,category",
    [
        (requests.Timeout("private-token"), "timeout"),
        (requests.ConnectionError("private-token"), "connection"),
        (
            Exception(
                json.dumps(
                    {
                        "ResponseMetadata": {
                            "RequestId": REQUEST_ID,
                            "Error": {"Code": "Throttling", "Message": "private-token"},
                        }
                    }
                )
            ),
            "throttled",
        ),
    ],
)
async def test_sdk_retains_safe_category_and_request_id(monkeypatch, problem, category):
    from volcengine.iam.IamService import IamService

    monkeypatch.setattr(IamService, "__init__", lambda self: None)
    for setter in [
        "set_ak",
        "set_sk",
        "set_session_token",
        "set_scheme",
        "set_connection_timeout",
        "set_socket_timeout",
    ]:
        monkeypatch.setattr(IamService, setter, lambda self, value: None)

    def fail(self, params):
        raise problem

    monkeypatch.setattr(IamService, "get_role", fail)
    source = SimpleNamespace(
        _credentials=lambda: SimpleNamespace(
            access_key_id="test", secret_access_key="test", session_token="test"
        )
    )
    with pytest.raises(iam.IamError) as error:
        await iam.IamCloud(source).call("get_role", RoleName=iam.ROLE_NAME)
    assert error.value.category == category
    assert error.value.operation == "iam_get_role"
    assert error.value.request_id == (REQUEST_ID if category == "throttled" else "")
    assert "private-token" not in str(error.value)


def test_diagnostics_migrate_request_id_and_drop_untrusted_values(tmp_path, caplog):
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE task_diagnostics (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, stage TEXT NOT NULL, operation TEXT NOT NULL, category TEXT NOT NULL, attempt INTEGER NOT NULL, outcome TEXT NOT NULL, created REAL NOT NULL)"
        )
        db.execute(
            "INSERT INTO task_diagnostics VALUES (1,'old-task','worker','get_worker','timeout',1,'failed',0)"
        )
    tasks = CreationTasks(path)
    with tasks.db() as db:
        db.execute(
            "INSERT INTO tasks(id,owner,request,payload,state,stage,supervisor,updated) VALUES ('test-task','owner','request','{}','failed','iam_role',0,0)"
        )
        assert (
            db.execute("SELECT request_id FROM task_diagnostics WHERE id=1").fetchone()[
                0
            ]
            == ""
        )
    base = dict(
        operation="iam_get_role", category="timeout", attempt=1, outcome="failed"
    )
    tasks.record_diagnostic("test-task", dict(base, requestId=REQUEST_ID))
    tasks.record_diagnostic("test-task", dict(base, requestId="private-token\nsecret"))
    with tasks.db() as db:
        rows = db.execute(
            "SELECT request_id FROM task_diagnostics WHERE task_id='test-task' ORDER BY id"
        ).fetchall()
        assert [r[0] for r in rows] == [REQUEST_ID, ""]
    assert "private-token" not in caplog.text
    assert validate_diagnostic(dict(base, requestId="private-token")) == base
    assert (
        validate_diagnostic(
            dict(
                operation="get_worker", category="timeout", attempt=1, outcome="failed"
            )
        )
        is not None
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "status,category",
    [
        (429, "throttled"),
        (500, "unavailable"),
        (503, "unavailable"),
        (403, "permission"),
    ],
)
async def test_http_status_is_classified_with_request_id(monkeypatch, status, category):
    from volcengine.iam.IamService import IamService

    response = requests.Response()
    response.status_code = status
    response._content = json.dumps(
        {"ResponseMetadata": {"RequestId": REQUEST_ID}}
    ).encode()
    problem = requests.HTTPError("private-provider-message", response=response)
    monkeypatch.setattr(IamService, "__init__", lambda self: None)
    for setter in [
        "set_ak",
        "set_sk",
        "set_session_token",
        "set_scheme",
        "set_connection_timeout",
        "set_socket_timeout",
    ]:
        monkeypatch.setattr(IamService, setter, lambda self, value: None)

    def fail(self, params):
        raise problem

    monkeypatch.setattr(IamService, "get_role", fail)
    source = SimpleNamespace(
        _credentials=lambda: SimpleNamespace(
            access_key_id="test", secret_access_key="test", session_token="test"
        )
    )
    with pytest.raises(iam.IamError) as error:
        await iam.IamCloud(source).call("get_role", RoleName=iam.ROLE_NAME)
    assert error.value.category == category
    assert error.value.request_id == REQUEST_ID
    assert "private-provider-message" not in str(error.value)


@pytest.mark.asyncio
async def test_cancelled_sdk_thread_does_not_dispatch_later_requests(monkeypatch):
    import threading
    from volcengine.iam.IamService import IamService

    started, release, finished = threading.Event(), threading.Event(), threading.Event()
    calls = []
    monkeypatch.setattr(IamService, "__init__", lambda self: None)
    for setter in [
        "set_ak",
        "set_sk",
        "set_session_token",
        "set_scheme",
        "set_connection_timeout",
        "set_socket_timeout",
    ]:
        monkeypatch.setattr(IamService, setter, lambda self, value: None)

    def late(self, params):
        calls.append("get_role")
        started.set()
        release.wait(2)
        finished.set()
        return {"Result": {}}

    monkeypatch.setattr(IamService, "get_role", late)
    source = SimpleNamespace(
        _credentials=lambda: SimpleNamespace(
            access_key_id="test", secret_access_key="test", session_token="test"
        )
    )
    task = asyncio.create_task(iam.ensure_runtime_role(iam.IamCloud(source), "123"))
    try:
        assert await asyncio.to_thread(started.wait, 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 2)
    await asyncio.sleep(0)
    assert calls == ["get_role"]
