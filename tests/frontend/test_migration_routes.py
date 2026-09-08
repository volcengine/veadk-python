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

import time
from types import SimpleNamespace
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


def app_for(service: Any, evaluation_service: Any = None) -> FastAPI:
    app = FastAPI()

    def owner(request: Request) -> str:
        return request.headers.get("x-owner", "owner-1")

    mount_migration_routes(
        app,
        service,
        owner_resolver=owner,
        creator_resolver=lambda _request: "Owner",
        evaluation_service=evaluation_service,
    )
    return app


class RouteEvaluationService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def record(self, name: str, *values: object) -> dict[str, object]:
        self.calls.append((name, values))
        return {"operation": name}

    def capabilities(self) -> dict[str, object]:
        return {"available": True, "dimensions": []}

    def ensure_available(self, enabled: bool) -> None:
        self.calls.append(("ensure_available", (enabled,)))

    def attach(
        self,
        task: dict[str, object],
        owner_id: str,
        *,
        advance: bool = False,
    ) -> dict[str, object]:
        self.calls.append(("attach", (task, owner_id, advance)))
        return {**task, "evaluation": {"enabled": True, "state": "pending"}}

    def assert_dataset_locked(self, task_id: str, owner_id: str) -> None:
        self.calls.append(("assert_dataset_locked", (task_id, owner_id)))

    def put_dataset(self, task_id: str, owner_id: str, body: object):
        return self.record("put_dataset", task_id, owner_id, body)

    def get_dataset(self, task_id: str, owner_id: str):
        return self.record("get_dataset", task_id, owner_id)

    def advance(self, task_id: str, owner_id: str, *, task: object = None) -> None:
        self.calls.append(("advance", (task_id, owner_id, task)))

    def snapshot(self, task_id: str, owner_id: str, *, task: object = None):
        return self.record("snapshot", task_id, owner_id, task)

    def get_report(self, task_id: str, owner_id: str):
        return self.record("get_report", task_id, owner_id)

    def download_report(self, task_id: str, owner_id: str):
        self.calls.append(("download_report", (task_id, owner_id)))
        return b"# report\n", "evaluation.md"

    def resume(self, task_id: str, owner_id: str, body: object):
        return self.record("resume", task_id, owner_id, body)

    def retry(self, task_id: str, owner_id: str):
        return self.record("retry", task_id, owner_id)

    def cancel(self, task_id: str, owner_id: str):
        return self.record("cancel", task_id, owner_id)


def app_for_with_projects(service: Any, project_service: Any) -> FastAPI:
    app = FastAPI()
    mount_migration_routes(
        app,
        service,
        owner_resolver=lambda _request: "owner-1",
        creator_resolver=lambda _request: "Owner",
        project_service=project_service,
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


def test_evaluation_routes_delegate_without_blocking_upload_or_status_reads() -> None:
    service = RouteService()
    evaluation = RouteEvaluationService()
    with TestClient(app_for(service, evaluation)) as client:
        created = client.post(
            "/web/agent-migrations/tasks",
            json={
                "taskId": TASK_ID,
                "sourceFileName": "source.zip",
                "evaluation": {"enabled": True},
            },
        )
        dataset = client.put(
            f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/dataset",
            json={"cases": [{"caseId": "case-1", "userInput": "hello"}]},
        )
        loaded_dataset = client.get(
            f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/dataset"
        )
        status = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/evaluation")
        report = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/report")
        report_download = client.get(
            f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/report/download"
        )
        resumed = client.post(
            f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/resume",
            json={"environment": {"ARK_API_KEY": "secret"}},
        )
        retried = client.post(f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/retry")
        uploaded = client.put(
            f"/web/agent-migrations/tasks/{TASK_ID}/source",
            headers={"content-type": "application/zip"},
            content=b"zip",
        )

    assert all(
        response.status_code == 200
        for response in (
            created,
            dataset,
            loaded_dataset,
            status,
            report,
            report_download,
            resumed,
            retried,
            uploaded,
        )
    )
    names = [name for name, _ in evaluation.calls]
    assert "ensure_available" in names
    assert names.count("put_dataset") == 1
    assert names.count("get_dataset") == 1
    assert names.count("snapshot") >= 1
    assert names.count("get_report") == 1
    assert names.count("download_report") == 1
    assert names.count("resume") == 1
    assert names.count("retry") == 1
    assert names.count("assert_dataset_locked") == 0
    assert names.count("advance") == 0
    assert report_download.content == b"# report\n"
    assert report_download.headers["cache-control"] == "no-store"
    assert [name for name, _ in service.calls].index("create_task") < names.index(
        "attach"
    )


def test_retry_starts_background_evaluation_watcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class TerminalService(RouteService):
        def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("get_task", (task_id, owner_id)))
            return {
                "id": task_id,
                "state": "succeeded",
                "evaluation": {"enabled": True},
            }

    class CompletingEvaluation(RouteEvaluationService):
        def snapshot(self, task_id: str, owner_id: str, *, task: object = None):
            return {
                "enabled": True,
                "state": "completed",
                "message": "done",
            }

    async def immediate_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr(routes.asyncio, "sleep", immediate_sleep)
    service = TerminalService()
    evaluation = CompletingEvaluation()
    with TestClient(app_for(service, evaluation)) as client:
        response = client.post(
            f"/web/agent-migrations/tasks/{TASK_ID}/evaluation/retry"
        )
        for _ in range(100):
            if any(name == "advance" for name, _ in evaluation.calls):
                break
            time.sleep(0.001)

    assert response.status_code == 200
    assert any(name == "advance" for name, _ in evaluation.calls)


@pytest.mark.parametrize("unexpected", [False, True])
def test_evaluation_failures_do_not_hide_task_stop_or_artifact(
    unexpected: bool,
) -> None:
    class DurableRouteService(RouteService):
        @staticmethod
        def task(task_id: str, state: str) -> dict[str, object]:
            return {
                "id": task_id,
                "state": state,
                "canStop": state == "running",
                "artifact": {"downloadReady": True},
                "evaluation": {
                    "enabled": True,
                    "preset": "standard",
                    "dimensions": ["semantic_fidelity"],
                },
            }

        def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("get_task", (task_id, owner_id)))
            return self.task(task_id, "running")

        def stop(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("stop", (task_id, owner_id)))
            return self.task(task_id, "cancelled")

        def artifact(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("artifact", (task_id, owner_id)))
            return {"artifact": {"sha256": "a" * 64, "downloadReady": True}}

    class FailingEvaluationService(RouteEvaluationService):
        def attach(
            self,
            task: dict[str, object],
            owner_id: str,
            *,
            advance: bool = False,
        ) -> dict[str, object]:
            self.calls.append(("attach", (task, owner_id, advance)))
            if unexpected:
                raise RuntimeError("evaluation bug")
            raise MigrationError(
                "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE",
                "evaluation storage unavailable",
                status_code=503,
                retryable=True,
            )

    service = DurableRouteService()
    evaluation = FailingEvaluationService()
    with TestClient(app_for(service, evaluation)) as client:
        task = client.get(f"/web/agent-migrations/tasks/{TASK_ID}")
        stopped = client.post(f"/web/agent-migrations/tasks/{TASK_ID}/stop")
        artifact = client.get(f"/web/agent-migrations/tasks/{TASK_ID}/artifact")

    assert task.status_code == 200
    assert task.json()["state"] == "running"
    assert stopped.status_code == 200
    assert stopped.json()["state"] == "cancelled"
    assert artifact.status_code == 200
    assert artifact.json()["artifact"]["sha256"] == "a" * 64
    expected_code = (
        "MIGRATION_EVALUATION_INTERNAL"
        if unexpected
        else "MIGRATION_EVALUATION_STORAGE_UNAVAILABLE"
    )
    assert task.json()["evaluation"]["error"]["code"] == expected_code
    assert stopped.json()["evaluation"]["error"]["code"] == expected_code
    assert [name for name, _ in service.calls] == [
        "get_task",
        "get_task",
        "stop",
        "artifact",
    ]
    assert [name for name, _ in evaluation.calls].count("cancel") == 1
    assert [values[2] for name, values in evaluation.calls if name == "attach"] == [
        False,
        False,
    ]


def test_stop_cancels_active_evaluation_after_migration_is_terminal() -> None:
    class TerminalRouteService(RouteService):
        def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("get_task", (task_id, owner_id)))
            return {
                "id": task_id,
                "state": "succeeded",
                "canStop": False,
                "evaluation": {
                    "enabled": True,
                    "state": "executing",
                },
            }

    class ActiveEvaluationService(RouteEvaluationService):
        def attach(
            self,
            task: dict[str, object],
            owner_id: str,
            *,
            advance: bool = False,
        ) -> dict[str, object]:
            self.calls.append(("attach", (task, owner_id, advance)))
            return {
                **task,
                "evaluation": {"enabled": True, "state": "cancelled"},
            }

    service = TerminalRouteService()
    evaluation = ActiveEvaluationService()
    with TestClient(app_for(service, evaluation)) as client:
        response = client.post(f"/web/agent-migrations/tasks/{TASK_ID}/stop")

    assert response.status_code == 200
    assert response.json()["state"] == "succeeded"
    assert response.json()["evaluation"]["state"] == "cancelled"
    assert [name for name, _ in service.calls] == ["get_task"]
    assert [name for name, _ in evaluation.calls] == ["cancel", "attach"]


def test_terminal_task_saves_source_without_blocking_the_status_response() -> None:
    class TerminalService(RouteService):
        state = "succeeded"

        def get_task(self, task_id: str, owner_id: str) -> dict[str, object]:
            self.calls.append(("get_task", (task_id, owner_id)))
            return {
                "id": task_id,
                "state": self.state,
                "artifact": {"downloadReady": True},
            }

        def persistence_bundle(self, task_id: str, owner_id: str):
            self.calls.append(("persistence_bundle", (task_id, owner_id)))
            return SimpleNamespace(
                task_id=task_id,
                project_name="travel-agent",
                artifact=b"zip",
                result={},
                result_bytes=b"{}",
                environment_defaults={},
            )

    class ProjectService:
        async def persist_migration(self, **_kwargs):
            return (
                SimpleNamespace(project_id="a" * 32),
                SimpleNamespace(version_id="b" * 32),
            )

    service = TerminalService()
    with TestClient(app_for_with_projects(service, ProjectService())) as client:
        first = client.get(f"/web/agent-migrations/tasks/{TASK_ID}")
        assert first.status_code == 200
        assert first.json()["persistence"]["state"] == "saving"

        saved = None
        for _ in range(20):
            response = client.get(f"/web/agent-migrations/tasks/{TASK_ID}")
            if response.json()["persistence"]["state"] == "saved":
                saved = response.json()["persistence"]
                break
            time.sleep(0.01)

        service.state = "expired"
        expired = client.get(f"/web/agent-migrations/tasks/{TASK_ID}")

    assert saved == {
        "state": "saved",
        "projectId": "a" * 32,
        "versionId": "b" * 32,
        "message": "源码已保存到已迁移项目。",
    }
    assert expired.status_code == 200
    assert expired.json()["persistence"] == saved
    assert [name for name, _ in service.calls].count("persistence_bundle") == 1


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
