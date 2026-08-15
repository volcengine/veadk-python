# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.migration import routes
from frontend.server.migration.models import (
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
    SubmitAnalysisAnswersBody,
)
from frontend.server.migration.routes import mount_migration_routes
from frontend.server.migration.service import MigrationError

TASK_ID = "migration-v1-" + "1" * 32


class RouteService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def record(self, name: str, *values: object) -> dict[str, object]:
        self.calls.append((name, values))
        return {"operation": name}

    def capabilities(self) -> dict[str, object]:
        return self.record("capabilities")

    def list_tasks(self, owner_id: str) -> dict[str, object]:
        self.calls.append(("list_tasks", (owner_id,)))
        return {"items": []}

    def create_task(
        self,
        body: CreateMigrationTaskBody,
        owner_id: str,
        creator_name: str,
    ) -> dict[str, object]:
        return self.record("create_task", body, owner_id, creator_name)

    def upload_source(
        self,
        task_id: str,
        owner_id: str,
        content: bytes,
    ) -> dict[str, object]:
        return self.record("upload_source", task_id, owner_id, content)

    def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
        return self.record("get_task", task_id, owner_id)

    def submit_answers(
        self,
        task_id: str,
        owner_id: str,
        body: SubmitAnalysisAnswersBody,
    ) -> dict[str, object]:
        return self.record("submit_answers", task_id, owner_id, body)

    def confirm(
        self,
        task_id: str,
        owner_id: str,
        body: ConfirmMigrationBody,
    ) -> dict[str, object]:
        return self.record("confirm", task_id, owner_id, body)

    def stop(self, task_id: str, owner_id: str) -> dict[str, object]:
        return self.record("stop", task_id, owner_id)

    def artifact(self, task_id: str, owner_id: str) -> dict[str, object]:
        return self.record("artifact", task_id, owner_id)

    def activity(self, task_id: str, owner_id: str) -> dict[str, object]:
        return self.record("activity", task_id, owner_id)

    def download(self, task_id: str, owner_id: str) -> tuple[bytes, str]:
        self.calls.append(("download", (task_id, owner_id)))
        return b"zip", "migration.zip"

    def preview_file(
        self,
        task_id: str,
        owner_id: str,
        path: str,
    ) -> tuple[bytes, str]:
        self.calls.append(("preview_file", (task_id, owner_id, path)))
        return b"preview", "text/plain"

    def delete(self, task_id: str, owner_id: str) -> None:
        self.calls.append(("delete", (task_id, owner_id)))


def app_for(service: Any) -> FastAPI:
    app = FastAPI()

    def owner(request: Request) -> str:
        return request.headers.get("x-owner", "owner-1")

    mount_migration_routes(
        app,
        service,
        owner_resolver=owner,
        creator_resolver=lambda _request: "Owner",
    )
    return app


def test_all_migration_routes_delegate_with_owner_and_return_artifacts() -> None:
    service = RouteService()
    client = TestClient(app_for(service))
    headers = {"x-owner": "owner-1"}

    responses = [
        client.get("/web/agent-migrations/capabilities", headers=headers),
        client.get("/web/agent-migrations/tasks", headers=headers),
        client.post(
            "/web/agent-migrations/tasks",
            headers=headers,
            json={"taskId": TASK_ID, "sourceFileName": "source.zip"},
        ),
        client.put(
            f"/web/agent-migrations/tasks/{TASK_ID}/source",
            headers={**headers, "content-type": "application/zip; charset=binary"},
            content=b"zip",
        ),
        client.get(f"/web/agent-migrations/tasks/{TASK_ID}", headers=headers),
        client.post(
            f"/web/agent-migrations/tasks/{TASK_ID}/answers",
            headers=headers,
            json={
                "analysisAttempt": 1,
                "analysisSha256": "1" * 64,
                "inputSha256": "2" * 64,
                "answers": {"question-1": "answer"},
            },
        ),
        client.post(
            f"/web/agent-migrations/tasks/{TASK_ID}/confirm",
            headers=headers,
            json={
                "framework": "any",
                "entry": None,
                "appName": "support-agent",
                "analysisAttempt": 1,
                "analysisSha256": "1" * 64,
                "inputSha256": "2" * 64,
                "boundaryConfirmed": True,
            },
        ),
        client.post(f"/web/agent-migrations/tasks/{TASK_ID}/stop", headers=headers),
        client.get(f"/web/agent-migrations/tasks/{TASK_ID}/activity", headers=headers),
        client.get(f"/web/agent-migrations/tasks/{TASK_ID}/artifact", headers=headers),
    ]
    download = client.get(
        f"/web/agent-migrations/tasks/{TASK_ID}/download",
        headers=headers,
    )
    preview = client.get(
        f"/web/agent-migrations/tasks/{TASK_ID}/artifact/file",
        headers=headers,
        params={"path": "runtime/agent.py"},
    )
    deleted = client.delete(
        f"/web/agent-migrations/tasks/{TASK_ID}",
        headers=headers,
    )

    assert all(response.status_code == 200 for response in responses)
    assert download.content == b"zip"
    assert (
        download.headers["content-disposition"]
        == 'attachment; filename="migration.zip"'
    )
    assert download.headers["cache-control"] == "no-store"
    assert preview.content == b"preview"
    assert preview.headers["content-type"].startswith("text/plain")
    assert preview.headers["cache-control"] == "no-store"
    assert deleted.json() == {"deleted": True}
    assert [name for name, _ in service.calls] == [
        "capabilities",
        "list_tasks",
        "create_task",
        "upload_source",
        "get_task",
        "submit_answers",
        "confirm",
        "stop",
        "activity",
        "artifact",
        "download",
        "preview_file",
        "delete",
    ]


@pytest.mark.parametrize(
    ("declared", "expected_code"),
    [
        ("invalid", "MIGRATION_SOURCE_LENGTH_INVALID"),
        ("-1", "MIGRATION_SOURCE_LENGTH_INVALID"),
    ],
)
def test_upload_rejects_invalid_declared_lengths(
    declared: str,
    expected_code: str,
) -> None:
    client = TestClient(app_for(RouteService()))
    response = client.put(
        f"/web/agent-migrations/tasks/{TASK_ID}/source",
        headers={"content-type": "application/zip", "content-length": declared},
        content=b"",
    )
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == expected_code


def test_upload_stream_enforces_limit_without_declared_length(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(routes, "MIGRATION_UPLOAD_MAX_BYTES", 2)
    client = TestClient(app_for(RouteService()))
    response = client.put(
        f"/web/agent-migrations/tasks/{TASK_ID}/source",
        headers={"content-type": "application/zip", "transfer-encoding": "chunked"},
        content=iter([b"ab", b"c"]),
    )
    assert response.status_code == 413
    assert response.json()["detail"]["code"] == "MIGRATION_SOURCE_TOO_LARGE"


@pytest.mark.parametrize("failure", ["migration", "internal"])
def test_invoke_maps_service_and_unexpected_failures(failure: str) -> None:
    class FailingService(RouteService):
        def capabilities(self) -> dict[str, object]:
            if failure == "migration":
                raise MigrationError(
                    "MIGRATION_EXPECTED",
                    "expected failure",
                    status_code=409,
                    retryable=False,
                )
            raise RuntimeError("unexpected")

    response = TestClient(app_for(FailingService())).get(
        "/web/agent-migrations/capabilities"
    )
    assert response.status_code == (409 if failure == "migration" else 500)
    assert response.json()["detail"]["code"] == (
        "MIGRATION_EXPECTED" if failure == "migration" else "MIGRATION_INTERNAL"
    )
