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
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from agentkit.toolkit.errors import ApiError

from veadk.integrations.mpa.managed import diagnostics as diag
from veadk.integrations.mpa.managed.runtime import RuntimeCloud


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize(
    "method",
    ["create_skill_space", "get_skill_space", "list_skill_spaces", "get_runtime"],
)
def test_resource_failure_keeps_identifiers_without_changing_call(
    monkeypatch, provider, region, method
):
    error = ApiError("private request body", error_code="ExceededQuota")
    error.__dict__["request_id"] = "20261020123456ABCDEF0123456789ABCD"
    call = Mock(side_effect=error)
    cloud = RuntimeCloud(region=region, credential_file="", provider=provider)
    monkeypatch.setattr(
        cloud, "_client", lambda **kwargs: SimpleNamespace(**{method: call})
    )
    events = []
    with diag.diagnostic_scope(events.append), pytest.raises(ApiError) as raised:
        asyncio.run(cloud.call(method, object(), skills="skill" in method))
    assert raised.value is error
    assert call.call_count == 1
    assert events[-1]["operation"] == method
    assert events[-1]["errorCode"] == "ExceededQuota"
    assert "private" not in str(events)


def test_outer_failure_preserves_origin_and_never_copies_exception_text():
    error = RuntimeError("private database password details")
    events = []
    with diag.diagnostic_scope(events.append):
        detail = diag.report(
            "create_worker",
            "permission",
            error_code="AccessDenied",
            request_id="20261020123456ABCDEF0123456789ABCD",
        )
        diag.with_diagnostic(error, detail)
        wrapper = RuntimeError("wrapper contains secret")
        wrapper.__cause__ = error
        diag.report_failure("provision", wrapper)
    assert events[-1] == events[0]
    assert "secret" not in str(events) and "password" not in str(events)


def test_sql_failure_is_safe_and_unrelated_error_does_not_inherit_diagnostic():
    error = RuntimeError("SQL and private connection details")
    error.__dict__["orig"] = SimpleNamespace(sqlstate="28P01")
    events = []
    with diag.diagnostic_scope(events.append):
        diag.report_failure("provision", error)
        diag.report_failure("provision", ValueError("secret"))
    assert events[0]["operation"] == "prepare_database"
    assert events[0]["category"] == "permission"
    assert events[0]["errorCode"] == "PostgreSQL.28P01"
    assert events[1]["operation"] == "provision"
    assert "errorCode" not in events[1]
    assert "private" not in str(events) and "secret" not in str(events)


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")]
)
@pytest.mark.parametrize("resource", ["network", "gateway"])
def test_sdk_wrappers_preserve_safe_metadata_at_final_boundary(
    monkeypatch, provider, region, resource
):
    import json
    import volcenginesdkcore
    import volcenginesdkvpc
    from volcenginesdkcore import universal
    from veadk.integrations.mpa.managed.gateway_cloud import (
        GatewayCloud,
        APIGClientError,
    )
    from veadk.integrations.mpa.managed.network_cloud import (
        NetworkCloud,
        NetworkCloudError,
    )

    request_id = "20261020123456ABCDEF0123456789ABCD"
    credentials = SimpleNamespace(
        access_key_id="fake", secret_access_key="fake", session_token="fake"
    )
    error = RuntimeError("private payload")
    error.__dict__["body"] = json.dumps(
        {
            "ResponseMetadata": {
                "RequestId": request_id,
                "Error": {"Code": "ExceededQuota", "Message": "private token"},
            }
        }
    )
    call = Mock(side_effect=error)
    monkeypatch.setattr(volcenginesdkcore, "ApiClient", lambda config: config)
    monkeypatch.setattr(
        volcenginesdkvpc, "VPCApi", lambda client: SimpleNamespace(create_vpc=call)
    )
    monkeypatch.setattr(
        universal, "UniversalApi", lambda client: SimpleNamespace(do_call=call)
    )
    if resource == "network":
        cloud = NetworkCloud(
            region=region, credentials=lambda: credentials, provider=provider
        )
        invoke = cloud.call(
            "create_vpc", "CreateVpcRequest", cidr_block="172.20.0.0/16"
        )
        expected, exception = "create_vpc", NetworkCloudError
    else:
        cloud = GatewayCloud(
            SimpleNamespace(
                region=region, provider=provider, _credentials=lambda: credentials
            )
        )
        invoke = cloud.call("CreateGateway", {})
        expected, exception = "CreateGateway", APIGClientError
    events = []
    with diag.diagnostic_scope(events.append):
        with pytest.raises(exception) as failure:
            asyncio.run(invoke)
        diag.report_failure("provision", failure.value)
    assert call.call_count == 1
    assert events[-1]["operation"] == expected
    assert events[-1]["requestId"] == request_id
    assert events[-1]["errorCode"] == "ExceededQuota"
    assert "private" not in str(events)


def test_pg_and_iam_terminal_failures_keep_original_operations():
    from veadk.integrations.mpa.managed.pg_cloud import PGCloudError
    from veadk.integrations.mpa.managed.iam import IamError

    errors = [
        PGCloudError("create_workspace", "AccessDenied"),
        IamError("AccessDenied", operation="create_role"),
    ]
    events = []
    with diag.diagnostic_scope(events.append):
        for error in errors:
            diag.report_failure("provision", error)
    assert [e["operation"] for e in events] == [
        "aidap_create_workspace",
        "iam_create_role",
    ]
    assert all(e["errorCode"] == "AccessDenied" for e in events)
    assert all(e["category"] == "permission" for e in events)


def test_retry_hides_previous_attempt_without_erasing_history(tmp_path, monkeypatch):
    import sys
    import json
    from veadk.integrations.mpa.managed.tasks import CreationTasks

    async def run():
        service = CreationTasks(tmp_path / "tasks.db")
        detail = {
            "operation": "create_skill_space",
            "category": "provider_error",
            "outcome": "failed",
            "attempt": 1,
            "errorCode": "ExceededQuota",
        }
        events = [{"stage": "skills"}, {"diagnostic": detail}]
        script = (
            "import json; events="
            + repr(events)
            + "; [print('MPA_EVENT '+json.dumps(e)) for e in events]; raise SystemExit(1)"
        )
        service.command = lambda: [sys.executable, "-c", script]
        payload = {
            "requestId": "11111111-1111-4111-8111-111111111111",
            "agentId": "agent",
            "region": "cn-beijing",
            "description": "",
        }
        task = await service.start("owner", payload, config_path=None, timeout=60)
        await asyncio.gather(*service.running.values())
        assert (
            service.get("owner", task["taskId"])["latestDiagnostic"]["errorCode"]
            == "ExceededQuota"
        )
        gate = asyncio.Event()

        async def paused(*args, **kwargs):
            await gate.wait()

        monkeypatch.setattr(service, "_run", paused)
        retry = await service.start("owner", payload, config_path=None, timeout=60)
        assert retry["taskId"] == task["taskId"]
        assert "latestDiagnostic" not in retry
        # Even if the new attempt reaches the same stage, its old error stays hidden.
        service._update(task["taskId"], stage="skills")
        assert "latestDiagnostic" not in service.get("owner", task["taskId"])
        with service.db() as db:
            assert (
                db.execute("SELECT COUNT(*) FROM task_diagnostics").fetchone()[0] == 1
            )
        service.record_diagnostic(
            task["taskId"], {**detail, "errorCode": "AccessDenied"}
        )
        assert (
            service.get("owner", task["taskId"])["latestDiagnostic"]["errorCode"]
            == "AccessDenied"
        )
        assert "private" not in json.dumps(service.get("owner", task["taskId"]))
        gate.set()
        await asyncio.gather(*service.running.values())
        reopened = CreationTasks(tmp_path / "tasks.db")
        assert (
            reopened._latest_diagnostic(task["taskId"])["latestDiagnostic"]["errorCode"]
            == "AccessDenied"
        )

    asyncio.run(run())


def test_malformed_exception_metadata_does_not_replace_original_error():
    error = RuntimeError("private payload")
    error.__dict__.update(operation={}, category=[], code={}, request_id=[])
    events = []
    with diag.diagnostic_scope(events.append):
        diag.report_failure("provision", error)
    assert events == [
        {
            "operation": "provision",
            "category": "unknown",
            "exceptionType": "RuntimeError",
            "attempt": 1,
            "outcome": "failed",
        }
    ]


def test_http_cause_details_survive_wrapper_and_task_restart(tmp_path):
    import json
    import requests
    from agentkit.toolkit.errors import ApiError
    from veadk.integrations.mpa.managed.tasks import CreationTasks

    response = requests.Response()
    response.status_code = 502
    response.headers.update(
        {
            "Content-Type": "text/html; charset=utf-8",
            "X-Request-Id": "20261020123456ABCDEF0123456789ABCD",
            "Set-Cookie": "private",
        }
    )
    response._content = b"<html>private credential</html>"
    inner = requests.HTTPError("private url", response=response)
    original = ApiError("private key")
    original.__cause__ = inner
    wrapped = RuntimeError("private wrapper")
    diag.preserve_exception_details(wrapped, original)
    events = []
    with diag.diagnostic_scope(events.append):
        diag.report_failure("iam_get_role", wrapped)
    detail = events[-1]
    assert detail["exceptionType"] == "ApiError -> HTTPError"
    assert detail["httpStatus"] == 502
    assert detail["responseType"] == "text/html"
    assert detail["requestId"] == response.headers["X-Request-Id"]
    assert "private" not in json.dumps(events)
    service = CreationTasks(tmp_path / "tasks.db")
    with service.db() as db:
        db.execute(
            "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated) VALUES (?,?,?,?,?,?,?,?)",
            ("task", "owner", "request", "{}", "failed", "iam_role", 1, 0),
        )
    service.record_diagnostic("task", detail)
    persisted = CreationTasks(tmp_path / "tasks.db").get("owner", "task")[
        "latestDiagnostic"
    ]
    assert persisted == {**detail, "stage": "iam_role"}


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_sts_setup_failure_keeps_origin_and_exception(monkeypatch, provider):
    import agentkit.auth.sts
    from agentkit.toolkit.errors import ApiError
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud

    error = ApiError("private STS payload")
    call = Mock(side_effect=error)
    monkeypatch.setattr(agentkit.auth.sts, "get_caller_identity", call)
    cloud = RuntimeCloud(
        region="cn-beijing" if provider == "volcengine" else "ap-southeast-1",
        provider=provider,
        credential_file="",
        credentials=lambda: SimpleNamespace(
            access_key_id="fake", secret_access_key="fake", session_token=""
        ),
    )
    events = []
    with diag.diagnostic_scope(events.append), pytest.raises(ApiError) as caught:
        asyncio.run(cloud.account_id())
    assert caught.value is error
    assert call.call_count == 1
    assert events[-1]["operation"] == "get_caller_identity"
    assert events[-1]["exceptionType"] == "ApiError"
    assert "private" not in str(events)


def test_safe_details_reject_arbitrary_names_headers_and_status():
    secret_type = type("PrivateCredential", (Exception,), {})
    error = secret_type("private key")
    error.__dict__["response"] = SimpleNamespace(
        status_code="502 private", headers={"Content-Type": "private"}
    )
    details = diag.exception_details(error)
    assert details == {"exceptionType": "Exception", "responseType": "other"}
    validated = diag.validate_diagnostic(
        dict(
            operation="get_runtime",
            category="provider_error",
            outcome="failed",
            attempt=1,
            exceptionType="PrivateCredential",
            httpStatus=True,
            responseType="secret",
        )
    )
    assert validated == dict(
        operation="get_runtime", category="provider_error", outcome="failed", attempt=1
    )


def test_json_decode_chain_is_bounded_and_no_body_is_retained():
    import json
    from agentkit.toolkit.errors import ApiError

    error = ApiError("private body")
    cause = json.JSONDecodeError("private", "private", 0)
    error.__cause__ = cause
    cause.__cause__ = error
    details = diag.exception_details(error)
    assert details["exceptionType"] == "ApiError -> JSONDecodeError"
    assert "private" not in str(details)


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_iam_wrapper_keeps_safe_original_cause_before_suppression(
    monkeypatch, provider
):
    import requests
    from volcengine.iam.IamService import IamService
    from veadk.integrations.mpa.managed.iam import IamCloud, IamError

    response = requests.Response()
    response.status_code = 503
    response.headers["Content-Type"] = "text/html"
    response._content = b"private response body"
    original = requests.HTTPError("private request URL", response=response)
    call = Mock(side_effect=original)
    monkeypatch.setattr(IamService, "get_role", call)
    cloud = IamCloud(
        SimpleNamespace(
            provider=provider,
            region="cn-beijing" if provider == "volcengine" else "ap-southeast-1",
            _credentials=lambda: SimpleNamespace(
                access_key_id="fake", secret_access_key="fake", session_token=""
            ),
        )
    )
    events = []
    with diag.diagnostic_scope(events.append), pytest.raises(IamError) as caught:
        asyncio.run(cloud.call("get_role", RoleName="test"))
    assert caught.value.category == "unavailable"
    assert caught.value.__cause__ is None
    assert call.call_count == 1
    with diag.diagnostic_scope(events.append):
        diag.report_failure("provision", caught.value)
    assert events[-1]["exceptionType"] == "HTTPError"
    assert events[-1]["httpStatus"] == 503
    assert events[-1]["operation"] == "iam_get_role"
    assert "private" not in str(events)


def test_old_diagnostic_table_migrates_without_changing_legacy_rows(tmp_path):
    import sqlite3
    from veadk.integrations.mpa.managed.tasks import CreationTasks

    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE task_diagnostics (id INTEGER PRIMARY KEY,task_id TEXT,stage TEXT,operation TEXT,category TEXT,attempt INTEGER,outcome TEXT,created REAL)"
        )
        db.execute(
            "INSERT INTO task_diagnostics VALUES (1,'old','verifying','get_runtime','provider_error',1,'failed',0)"
        )
    service = CreationTasks(path)
    with service.db() as db:
        row = db.execute("SELECT * FROM task_diagnostics").fetchone()
        assert row["details"] == "{}"
        assert row["operation"] == "get_runtime"
        assert row["error_code"] == ""
