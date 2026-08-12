from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from frontend.server.vibe_task import VibeTaskService, mount_vibe_task_routes


def _app() -> tuple[FastAPI, VibeTaskService]:
    app = FastAPI()

    def owner(request: Request) -> str:
        value = request.headers.get("x-owner", "")
        if not value:
            raise HTTPException(status_code=401, detail="identity required")
        if value == "user":
            raise HTTPException(status_code=403, detail="management required")
        return value

    service = mount_vibe_task_routes(app, owner)
    return app, service


def test_routes_cover_capabilities_task_intent_credentials_and_delete() -> None:
    app, _ = _app()
    with TestClient(app) as client:
        assert client.get("/web/vibe/capabilities").status_code == 401
        assert client.get("/web/vibe/capabilities", headers={"x-owner": "user"}).status_code == 403
        capabilities = client.get("/web/vibe/capabilities", headers={"x-owner": "owner"}).json()
        assert capabilities["sandboxTtlSeconds"] == 28_800
        assert capabilities["evaluationEnabled"] is False

        response = client.post(
            "/web/vibe/tasks",
            headers={"x-owner": "owner"},
            json={"goal": "Build an Agent"},
        )
        assert response.status_code == 200
        task = response.json()
        task_id = task["taskId"]
        assert client.get("/web/vibe/tasks", headers={"x-owner": "owner"}).json()["tasks"]
        assert client.get(f"/web/vibe/tasks/{task_id}", headers={"x-owner": "other"}).status_code == 404

        credential_response = client.post(
            f"/web/vibe/tasks/{task_id}/credentials",
            headers={"x-owner": "owner"},
            json={"accessKeyId": "access-secret", "secretAccessKey": "secret-secret"},
        )
        rendered = credential_response.text
        assert credential_response.status_code == 200
        assert "access-secret" not in rendered
        assert "secret-secret" not in rendered

        intent = client.get(
            f"/web/vibe/tasks/{task_id}/intent-summary", headers={"x-owner": "owner"}
        ).json()
        update = client.put(
            f"/web/vibe/tasks/{task_id}/intent-summary",
            headers={"x-owner": "owner"},
            json={
                "expectedRevision": intent["revision"],
                "summary": {"goal": "Build an Agent", "openQuestions": ["Which tool?"]},
            },
        )
        assert update.status_code == 200
        assert update.json()["revision"] == intent["revision"] + 1

        assert client.delete(f"/web/vibe/tasks/{task_id}", headers={"x-owner": "owner"}).status_code == 204
        assert client.delete(f"/web/vibe/tasks/{task_id}", headers={"x-owner": "owner"}).status_code == 404


def test_sse_replays_ids_and_terminal_event() -> None:
    app, _ = _app()
    with TestClient(app) as client:
        task = client.post(
            "/web/vibe/tasks", headers={"x-owner": "owner"}, json={"goal": "Build"}
        ).json()
        task_id = task["taskId"]
        client.post(f"/web/vibe/tasks/{task_id}/stop", headers={"x-owner": "owner"})
        response = client.get(
            f"/web/vibe/tasks/{task_id}/events",
            headers={"x-owner": "owner", "last-event-id": "1"},
        )
        assert response.status_code == 200
        assert "id: 2" in response.text
        assert "event: task.cancelled" in response.text
        data_line = next(line for line in response.text.splitlines() if line.startswith("data: "))
        assert json.loads(data_line[6:])["eventType"] == "task.cancelled"
        assert client.get(
            f"/web/vibe/tasks/{task_id}/events",
            headers={"x-owner": "owner", "last-event-id": "invalid"},
        ).status_code == 400
