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

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from frontend.server.intelligent_development_runs.repository import RunRepository
from frontend.server.intelligent_development_runs.routes import mount_run_routes
from frontend.server.intelligent_development_runs.service import RunService


@pytest.fixture
def client(tmp_path):
    repository = RunRepository(tmp_path / "runs.db")

    async def execute(run, token):
        await repository.append_event(
            run.owner_id, run.id, token, "delta", {"text": "private output"}
        )
        await repository.finish(run.owner_id, run.id, token, 1)

    async def prepare(session, owner):
        if session != f"{owner}-environment":
            raise HTTPException(404, "Environment not found")
        return "thread-1"

    service = RunService(repository, execute)
    app = FastAPI()
    mount_run_routes(
        app,
        prefix="/build",
        service=service,
        owner_resolver=lambda request: request.headers.get("x-user", ""),
        prepare=prepare,
        redact_message=lambda message: message,
    )
    app.router.on_startup.append(service.start)
    app.router.on_shutdown.append(service.close)
    with TestClient(app) as client:
        yield client


def test_submission_replay_and_every_control_are_owner_scoped(client):
    alice, bob = {"x-user": "alice"}, {"x-user": "bob"}
    body = {"message": "build", "requestId": "request"}
    assert (
        client.post(
            "/build/sessions/alice-environment/runs", json=body, headers=bob
        ).status_code
        == 404
    )
    accepted = client.post(
        "/build/sessions/alice-environment/runs", json=body, headers=alice
    )
    assert accepted.status_code == 202
    run = accepted.json()
    assert not ({"owner_id", "lease_token", "checkpoint"} & run.keys())
    run_id = run["runId"]
    retry = client.post(
        "/build/sessions/alice-environment/runs", json=body, headers=alice
    )
    assert retry.json()["runId"] == run_id
    assert client.get("/build/sessions/alice-environment/runs", headers=bob).json() == {
        "runs": []
    }
    assert client.get(
        "/build/sessions/alice-environment/runs/current", headers=bob
    ).json() == {"run": None}
    for method, suffix, payload in [
        ("GET", "", None),
        ("GET", "/events", None),
        ("POST", "/stop", None),
        ("POST", "/resume", None),
        ("POST", "/inputs", {"message": "steer", "clientId": "b"}),
        ("DELETE", "", None),
    ]:
        denied = client.request(
            method, f"/build/runs/{run_id}{suffix}", headers=bob, json=payload
        )
        assert denied.status_code == 404
        assert "private output" not in denied.text
    replay = client.get(f"/build/runs/{run_id}/events", headers=alice)
    assert replay.status_code == 200
    assert "private output" in replay.text and "event: done" in replay.text
    assert (
        client.get(f"/build/runs/{run_id}/events?after=-1", headers=alice).status_code
        == 422
    )


@pytest.mark.parametrize(
    "body",
    [
        {},
        [],
        {"message": "", "requestId": "r"},
        {"message": "x", "requestId": "r", "owner": "alice"},
    ],
)
def test_untrusted_submission_body_is_rejected(client, body):
    response = client.post(
        "/build/sessions/alice-environment/runs", headers={"x-user": "alice"}, json=body
    )
    assert response.status_code == 422


def test_unauthenticated_replay_is_rejected_before_sse_headers(client):
    response = client.get("/build/runs/unknown/events")
    assert response.status_code == 401
    assert not response.headers["content-type"].startswith("text/event-stream")
