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
