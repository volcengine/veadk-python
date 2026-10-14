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

from pathlib import Path
from unittest.mock import AsyncMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.mpa_creation import (
    CreationRequest,
    _studio_task_path,
    mount_mpa_creation_routes,
)
from veadk.integrations.mpa.managed.tasks import CreationTasks


def test_studio_task_path_uses_tmp_by_default_and_honors_override(
    tmp_path, monkeypatch
):
    monkeypatch.delenv("VEADK_MPA_TASK_DB", raising=False)
    assert _studio_task_path() == Path("/tmp/veadk-studio/mpa-creation.sqlite3")

    override = tmp_path / "tasks.sqlite3"
    monkeypatch.setenv("VEADK_MPA_TASK_DB", str(override))
    assert _studio_task_path() == override


def test_config_exposes_only_safe_workspace_summary(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    app = FastAPI()
    mount_mpa_creation_routes(
        app, owner=lambda request: "local", service=CreationTasks(tmp_path / "tasks.db")
    )
    with TestClient(app) as client:
        result = client.get("/web/mpa-creation/config?region=cn-beijing")
    data = result.json()
    assert data["postgresLayout"] == "split-workspaces"
    assert data["adminDatabaseName"] == "mpa_admin_db"
    assert data["postgresMode"] == "auto"
    assert data["pgHost"] == ""
    assert "test-model-key" not in result.text
    assert "postgresql" not in result.text


def test_studio_creation_ignores_missing_yaml_path(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    monkeypatch.setenv("VEADK_MPA_CREATE_CONFIG", str(tmp_path / "missing.yaml"))
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "test-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)

    with TestClient(app) as client:
        config = client.get("/web/mpa-creation/config?region=cn-beijing")
        result = client.post(
            "/web/mpa-creation/tasks",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "mi-test",
                "region": "cn-beijing",
            },
        )

    assert config.status_code == 200
    assert config.json()["configured"] is True
    assert result.status_code == 202
    start_call = service.start.await_args
    assert start_call is not None
    assert start_call.kwargs["config_path"] is None
    assert start_call.kwargs["studio_runtime_owner"] == "local"


def test_creation_routes_require_management_authorization(tmp_path):
    app = FastAPI()

    def denied(_request):
        raise HTTPException(403, "Denied")

    mount_mpa_creation_routes(
        app, owner=denied, service=CreationTasks(tmp_path / "tasks.db")
    )
    with TestClient(app) as client:
        for method, path in [
            ("get", "/web/mpa-creation/config?region=cn-beijing"),
            ("post", "/web/mpa-creation/tasks"),
            ("get", "/web/mpa-creation/tasks/unknown"),
            ("post", "/web/mpa-creation/tasks/unknown/cancel"),
        ]:
            assert getattr(client, method)(path).status_code == 403


def test_model_key_discovery_needs_no_secret_for_local_inspection(
    tmp_path, monkeypatch
):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setenv(
        "VEADK_MPA_CREATE_CONFIG", str(tmp_path / "private-missing.yaml")
    )
    monkeypatch.delenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", raising=False)
    app = FastAPI()
    mount_mpa_creation_routes(
        app, owner=lambda request: "local", service=CreationTasks(tmp_path / "tasks.db")
    )
    with TestClient(app) as client:
        result = client.get("/web/mpa-creation/config?region=cn-beijing")
        assert result.status_code == 200
        assert result.json()["configured"] is True
        assert "VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY" not in result.text
        assert "private-missing" not in result.text
        assert (
            client.post(
                "/web/mpa-creation/tasks", json={"command": "arbitrary"}
            ).status_code
            == 422
        )


def test_creation_request_rejects_invalid_dependency_fields():
    base = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "description": "",
        "region": "cn-beijing",
    }
    for invalid in (
        {"pgHost": "db.example/path"},
        {"pgPort": "0"},
        {"pgPort": "not-a-port"},
        {"openvikingUrl": "https://api.example.test/?token=private"},
        {"openvikingResourceId": "ov bad"},
        {
            "openvikingUrl": "https://api.example.test/openviking",
            "openvikingResourceId": "ov-test",
        },
        {"openvikingApiKey": "test-key"},
        {"tosAccessKey": "ak-only"},
        {"tosAccessKey": "ak", "tosSecretKey": "sk"},
    ):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CreationRequest.model_validate({**base, **invalid})


def test_creation_key_is_passed_separately_from_stored_payload(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "test-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    with TestClient(app) as client:
        response = client.post(
            "/web/mpa-creation/tasks",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "mi-test",
                "description": "",
                "region": "cn-beijing",
                "openvikingUrl": "https://api.example.test/openviking",
                "openvikingResourceId": "ov-test",
                "openvikingApiKey": "private-ov-key-for-test",
            },
        )
    assert response.status_code == 202
    assert "private-ov-key-for-test" not in response.text
    start_call = service.start.await_args
    assert start_call is not None
    args, kwargs = start_call
    assert "openvikingApiKey" not in args[1]
    assert kwargs["secrets"] == {"openvikingApiKey": "private-ov-key-for-test"}


def test_auto_openviking_mode_reaches_task_and_has_no_browser_secret(
    tmp_path, monkeypatch
):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "test-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    with TestClient(app) as client:
        config = client.get("/web/mpa-creation/config?region=cn-beijing")
        assert config.json()["openvikingMode"] == "auto"
        result = client.post(
            "/web/mpa-creation/tasks",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "name": "test-agent",
                "region": "cn-beijing",
                "openvikingMode": "auto",
            },
        )
    assert result.status_code == 202
    call = service.start.await_args
    assert call is not None
    payload = call.args[1]
    assert payload["openvikingMode"] == "auto"
    assert "openvikingApiKey" not in payload
    assert call.kwargs["secrets"] == {"openvikingApiKey": ""}


def test_business_workspace_request_mode_and_legacy_omission(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "test-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    with TestClient(app) as client:
        assert (
            client.get("/web/mpa-creation/config?region=cn-beijing").json()[
                "businessWorkspaceMode"
            ]
            == "per-agent"
        )
        for mode in [None, "shared", "per-agent"]:
            payload = {
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "mi-test",
                "region": "cn-beijing",
            }
            if mode is not None:
                payload["businessWorkspaceMode"] = mode
            response = client.post("/web/mpa-creation/tasks", json=payload)
            assert response.status_code == 202
            call = service.start.await_args
            assert call is not None
            passed = call.args[1]
            if mode == "per-agent":
                assert passed["businessWorkspaceMode"] == mode
            else:
                assert "businessWorkspaceMode" not in passed


def test_new_layout_checks_name_before_accepting_task_and_returns_only_codes(
    tmp_path, monkeypatch
):
    from types import SimpleNamespace
    from frontend.server import mpa_creation
    from veadk.integrations.mpa.managed.names import NameCheckError

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setattr(mpa_creation, "RuntimeCloud", lambda **kw: SimpleNamespace())
    check = AsyncMock(return_value="test-account")
    monkeypatch.setattr(mpa_creation, "check_creation_name", check)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "new-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "region": "cn-beijing",
        "name": "test-name",
        "businessWorkspaceMode": "per-agent",
        "businessDatabaseName": "aidb",
    }
    with TestClient(app) as client:
        for key, status in [("runtimeNameTaken", 409), ("runtimeNameCheckFailed", 503)]:
            check.side_effect = NameCheckError(key)
            result = client.post("/web/mpa-creation/tasks", json=payload)
            assert result.status_code == status
            assert result.json()["detail"] == {"code": key}
            service.start.assert_not_awaited()
        check.side_effect = None
        result = client.post(
            "/web/mpa-creation/name-check",
            json={k: payload[k] for k in ["requestId", "name", "region"]},
        )
        assert result.json() == {"available": True}
        assert "test-account" not in result.text
        service.start.assert_not_awaited()
        result = client.post("/web/mpa-creation/tasks", json=payload)
        assert result.status_code == 202
        call = service.start.await_args
        assert call is not None
        assert call.kwargs["name_scope"] == {
            "provider": "volcengine",
            "region": "cn-beijing",
            "account": "test-account",
        }
        assert call.args[1]["businessDatabaseName"] == "aidb"
        assert check.await_args is not None
        assert check.await_args.kwargs["agent_id"] == call.args[1]["agentId"]


def test_name_check_requires_auth_and_valid_input(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    check = AsyncMock()
    monkeypatch.setattr(mpa_creation, "check_creation_name", check)
    app = FastAPI()

    def deny(_request):
        raise HTTPException(403, "Denied")

    mount_mpa_creation_routes(
        app, owner=deny, service=CreationTasks(tmp_path / "tasks.db")
    )
    with TestClient(app) as client:
        result = client.post(
            "/web/mpa-creation/name-check",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "name": "test-name",
                "region": "cn-beijing",
            },
        )
        assert result.status_code == 403
        result = client.post(
            "/web/mpa-creation/name-check",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "name": "bad name",
                "region": "cn-beijing",
            },
        )
        assert result.status_code == 422
    check.assert_not_awaited()


def test_new_layout_cannot_claim_another_requests_internal_identity(
    tmp_path, monkeypatch
):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    check = AsyncMock()
    monkeypatch.setattr(mpa_creation, "check_creation_name", check)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock()
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "name": "test-name",
        "agentId": "mi-other-request",
        "region": "cn-beijing",
    }
    with TestClient(app) as client:
        assert (
            client.post("/web/mpa-creation/name-check", json=payload).status_code == 400
        )
        assert (
            client.post(
                "/web/mpa-creation/tasks",
                json={
                    **payload,
                    "businessWorkspaceMode": "per-agent",
                    "businessDatabaseName": "aidb",
                },
            ).status_code
            == 400
        )
    check.assert_not_awaited()
    service.start.assert_not_awaited()


def test_retry_uses_private_scope_after_exact_payload_normalization(
    tmp_path, monkeypatch
):
    import json
    import time
    from types import SimpleNamespace
    from frontend.server import mpa_creation
    from veadk.integrations.mpa.managed.names import NameCheckError

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setattr(mpa_creation, "RuntimeCloud", lambda **kw: SimpleNamespace())
    check = AsyncMock(return_value="test-account")
    monkeypatch.setattr(mpa_creation, "check_creation_name", check)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "original-task"})
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda request: "local", service=service)
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "region": "cn-beijing",
        "name": "test-name",
        "businessWorkspaceMode": "per-agent",
        "businessDatabaseName": "aidb",
    }
    with TestClient(app) as client:
        assert client.post("/web/mpa-creation/tasks", json=payload).status_code == 202
        assert check.await_args is not None
        assert check.await_args.kwargs["verified_creation_account"] == ""
        assert service.start.await_args is not None
        owner, normalized = service.start.await_args.args
        assert service.start.await_args is not None
        scope = service.start.await_args.kwargs["name_scope"]
        with service.db() as db:
            db.execute(
                "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated,name_scope) VALUES (?,?,?,?,?,?,?,?,?)",
                (
                    "original-task",
                    owner,
                    normalized["requestId"],
                    json.dumps(normalized, sort_keys=True),
                    "failed",
                    "verifying",
                    0,
                    time.time(),
                    json.dumps(scope),
                ),
            )
        assert client.post("/web/mpa-creation/tasks", json=payload).status_code == 202
        assert check.await_args is not None
        assert check.await_args.kwargs["verified_creation_account"] == "test-account"
        count = check.await_count
        changed = client.post(
            "/web/mpa-creation/tasks", json={**payload, "description": "changed"}
        )
        assert changed.status_code == 409
        assert check.await_count == count
        check.side_effect = NameCheckError("runtimeNameTaken")
        fresh = client.post(
            "/web/mpa-creation/tasks",
            json={**payload, "requestId": "22222222-2222-4222-8222-222222222222"},
        )
        assert fresh.status_code == 409
        assert check.await_args is not None
        assert check.await_args.kwargs["verified_creation_account"] == ""
