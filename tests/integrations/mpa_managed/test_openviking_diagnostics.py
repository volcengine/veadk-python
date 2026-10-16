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

import asyncio
import json
import sqlite3
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import requests

from veadk.integrations.mpa.managed.diagnostics import (
    diagnostic_scope,
    validate_diagnostic,
)
from veadk.integrations.mpa.managed.openviking import OpenVikingCloud, OpenVikingError
from veadk.integrations.mpa.managed.tasks import CreationTasks

REQUEST_ID = "20261014084601ABCDEF0123456789ABCD"


def cloud_with_response(monkeypatch, provider, response=None, error=None):
    source = SimpleNamespace(
        provider=provider,
        region="ap-southeast-1" if provider == "byteplus" else "cn-beijing",
        _credentials=lambda: SimpleNamespace(
            access_key_id="test-access",
            secret_access_key="test-secret",
            session_token="",
        ),
    )
    call = Mock(return_value=response, side_effect=error)
    if provider == "byteplus":
        monkeypatch.setattr(
            "veadk.integrations.mpa.managed.openviking_byteplus.signed_request", call
        )
    else:
        monkeypatch.setattr(
            "veadk.utils.volcengine_sign.volcengine_signed_request", call
        )
    return OpenVikingCloud(source), call


@pytest.mark.parametrize("provider", ["byteplus", "volcengine"])
@pytest.mark.parametrize(
    "operation,action",
    [
        ("create_openviking", "CreateOpenVikingCollection"),
        ("get_openviking", "GetOpenVikingCollection"),
        ("get_openviking_key", "AccessOpenVikingApiKey"),
    ],
)
def test_structured_provider_error_survives_without_response_text(
    monkeypatch, caplog, provider, operation, action
):
    response = {
        "ResponseMetadata": {
            "RequestId": REQUEST_ID,
            "Error": {
                "Code": "InvalidParameter.ModelCredential",
                "Message": "test-private-model-key",
            },
        },
        "ApiKey": "test-private-library-key",
    }
    cloud, call = cloud_with_response(monkeypatch, provider, response)
    events = []
    with diagnostic_scope(events.append), pytest.raises(OpenVikingError) as caught:
        asyncio.run(
            cloud._call(action, {}, operation, create=operation == "create_openviking")
        )
    assert events[-1]["errorCode"] == "InvalidParameter.ModelCredential"
    assert events[-1]["requestId"] == REQUEST_ID
    assert events[-1]["operation"] == operation
    assert events[-1]["category"] == "provider_error"
    assert call.call_count == 1
    assert "test-private" not in json.dumps(events) + str(caught.value) + caplog.text


def test_http_error_extracts_structured_body_and_preserves_category(monkeypatch):
    response = requests.Response()
    response.status_code = 403
    response._content = json.dumps(
        {
            "ResponseMetadata": {
                "RequestId": REQUEST_ID,
                "Error": {"Code": "AccessDenied", "Message": "test-private-error"},
            }
        }
    ).encode()
    error = requests.HTTPError("test-private-exception", response=response)
    cloud, call = cloud_with_response(monkeypatch, "byteplus", error=error)
    events = []
    with (
        diagnostic_scope(events.append),
        pytest.raises(OpenVikingError, match="openvikingPermissionDenied"),
    ):
        asyncio.run(
            cloud._call(
                "CreateOpenVikingCollection", {}, "create_openviking", create=True
            )
        )
    assert events[-1]["errorCode"] == "AccessDenied"
    assert events[-1]["requestId"] == REQUEST_ID
    assert events[-1]["category"] == "permission"
    assert call.call_count == 1
    assert "test-private" not in json.dumps(events)


@pytest.mark.parametrize(
    "bad",
    [
        "ark-test-private",
        "SK_private_token",
        "Bearer private",
        "https://private.invalid",
        "Invalid\nprivate",
        "A" * 129,
        {"Code": "Private"},
    ],
)
def test_untrusted_metadata_is_omitted(monkeypatch, bad):
    cloud, _ = cloud_with_response(
        monkeypatch,
        "byteplus",
        {
            "ResponseMetadata": {
                "RequestId": "test-private-key",
                "Error": {"Code": bad, "Message": "test-private-error"},
            }
        },
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(OpenVikingError):
        asyncio.run(
            cloud._call(
                "CreateOpenVikingCollection", {}, "create_openviking", create=True
            )
        )
    assert "errorCode" not in events[-1]
    assert "requestId" not in events[-1]
    assert "test-private" not in json.dumps(events)


def test_malformed_success_retains_request_id(monkeypatch):
    cloud, _ = cloud_with_response(
        monkeypatch,
        "byteplus",
        {
            "ResponseMetadata": {"RequestId": REQUEST_ID},
            "Result": "test-private-invalid",
        },
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(OpenVikingError):
        asyncio.run(
            cloud._call(
                "CreateOpenVikingCollection", {}, "create_openviking", create=True
            )
        )
    assert events[-1]["requestId"] == REQUEST_ID
    assert events[-1]["category"] == "protocol_error"
    assert "errorCode" not in events[-1]


def test_create_transport_failure_has_no_text_or_extra_attempt(monkeypatch):
    cloud, call = cloud_with_response(
        monkeypatch, "byteplus", error=requests.Timeout("test-private-timeout")
    )
    events = []
    with diagnostic_scope(events.append), pytest.raises(OpenVikingError):
        asyncio.run(
            cloud._call(
                "CreateOpenVikingCollection", {}, "create_openviking", create=True
            )
        )
    assert events == [
        {
            "operation": "create_openviking",
            "category": "timeout",
            "attempt": 1,
            "outcome": "failed",
        }
    ]
    assert call.call_count == 1


def test_legacy_diagnostics_and_safe_code_validation():
    old = {
        "operation": "create_openviking",
        "category": "provider_error",
        "attempt": 1,
        "outcome": "failed",
    }
    assert validate_diagnostic(old) == old
    assert validate_diagnostic(
        {**old, "errorCode": "InvalidParameter.ModelCredential"}
    ) == {**old, "errorCode": "InvalidParameter.ModelCredential"}
    assert validate_diagnostic({**old, "errorCode": "SK_private_token"}) == old
    assert validate_diagnostic({**old, "Message": "private"}) is None


def test_child_error_code_persists_and_old_sqlite_rows_survive(tmp_path, caplog):
    path = tmp_path / "tasks.sqlite3"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE task_diagnostics (id INTEGER PRIMARY KEY, task_id TEXT NOT NULL, stage TEXT NOT NULL, operation TEXT NOT NULL, category TEXT NOT NULL, attempt INTEGER NOT NULL, outcome TEXT NOT NULL, created REAL NOT NULL)"
        )
        db.execute(
            "INSERT INTO task_diagnostics VALUES (1,'old','openviking','create_openviking','provider_error',1,'failed',1)"
        )

    async def run():
        service = CreationTasks(path)
        diagnostic = {
            "operation": "create_openviking",
            "category": "provider_error",
            "attempt": 1,
            "outcome": "failed",
            "requestId": REQUEST_ID,
            "errorCode": "InvalidParameter.ModelCredential",
        }
        event = "MPA_EVENT " + json.dumps({"diagnostic": diagnostic})
        service.command = lambda: [
            sys.executable,
            "-c",
            f"print({event!r}); print('test-private-response'); raise SystemExit(1)",
        ]
        task = await service.start(
            "owner",
            {
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "mi-test",
                "description": "",
                "region": "cn-beijing",
            },
            config_path="unused",
            timeout=60,
        )
        await asyncio.gather(*service.running.values())
        assert "errorCode" not in service.get("owner", task["taskId"])
        await service.close()
        return task["taskId"]

    ident = asyncio.run(run())
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT error_code FROM task_diagnostics WHERE task_id='old'"
        ).fetchone() == ("",)
        assert db.execute(
            "SELECT error_code,request_id FROM task_diagnostics WHERE task_id=?",
            (ident,),
        ).fetchone() == ("InvalidParameter.ModelCredential", REQUEST_ID)
    assert "InvalidParameter.ModelCredential" in caplog.text
    assert "test-private-response" not in caplog.text


@pytest.mark.parametrize("valid", [True, False])
def test_sdk_exception_body_is_structured_only(monkeypatch, valid):
    class SDKError(Exception):
        body = (
            json.dumps(
                {
                    "ResponseMetadata": {
                        "RequestId": REQUEST_ID,
                        "Error": {"Code": "ModelAccessDenied", "Message": "private"},
                    }
                }
            )
            if valid
            else "private non-JSON exception body"
        )

    cloud, _ = cloud_with_response(monkeypatch, "byteplus", error=SDKError("private"))
    events = []
    with diagnostic_scope(events.append), pytest.raises(OpenVikingError):
        asyncio.run(
            cloud._call(
                "CreateOpenVikingCollection", {}, "create_openviking", create=True
            )
        )
    assert ("errorCode" in events[-1]) is valid
    assert ("requestId" in events[-1]) is valid
    if valid:
        assert events[-1]["errorCode"] == "ModelAccessDenied"
    assert "private" not in json.dumps(events)
