from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.mpa_creation import mount_mpa_creation_routes
from veadk.integrations.mpa.managed.tasks import CreationTasks


def test_creation_routes_require_management_authorization(tmp_path):
    app = FastAPI()

    def denied(request):
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


def test_missing_server_profile_is_actionable_and_safe(tmp_path, monkeypatch):
    monkeypatch.setenv(
        "VEADK_MPA_CREATE_CONFIG", str(tmp_path / "private-missing.yaml")
    )
    app = FastAPI()
    mount_mpa_creation_routes(
        app, owner=lambda request: "local", service=CreationTasks(tmp_path / "tasks.db")
    )
    with TestClient(app) as client:
        result = client.get("/web/mpa-creation/config?region=cn-beijing")
        assert result.status_code == 200
        assert result.json()["configured"] is False
        assert "VEADK_MPA_CREATE_CONFIG" in result.json()["error"]
        assert "configuration file was not found" in result.json()["error"]
        assert "private-missing" not in result.text
        assert (
            client.post(
                "/web/mpa-creation/tasks", json={"command": "arbitrary"}
            ).status_code
            == 422
        )
