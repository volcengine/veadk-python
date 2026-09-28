import asyncio
import json
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server import mpa_creation
from tests.integrations.mpa_managed.test_config import profile_file
from veadk.integrations.mpa.managed.config import load_profile
from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError


def test_configured_images_and_request_overrides(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.config import with_creation_images

    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"image": "registry.example/mpa:default"}
        )
    )
    assert profile.summary()["runtimeImage"] == "registry.example/mpa:default"
    assert profile.summary()["workerImage"] == ""
    changed = with_creation_images(
        profile,
        {
            "runtimeImage": "registry.example/mpa:new",
            "workerImage": "registry.example/worker:new",
        },
    )
    assert changed.managed.runtime.image == "registry.example/mpa:new"
    assert changed.managed.worker.image == "registry.example/worker:new"
    assert changed.managed.worker.existing_id == ""
    assert profile.managed.runtime.image == "registry.example/mpa:default"
    assert profile.managed.worker.existing_id == "t-worker"
    unchanged = with_creation_images(profile, {"runtimeImage": "", "workerImage": ""})
    assert unchanged.managed == profile.managed


@pytest.mark.parametrize(
    "image",
    [
        "https://registry.example/image:tag",
        "user:password@registry/image",
        "repo/image?token=secret",
        "repo/image#secret",
        "bad image",
        "repo/image@sha256:no",
        "a" * 1025,
    ],
)
def test_request_image_validation_does_not_echo_input(image):
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        mpa_creation.CreationRequest.model_validate(
            {
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "agent",
                "region": "cn-beijing",
                "runtimeImage": image,
            }
        )


def test_blank_images_normalize_and_digest_is_accepted():
    body = mpa_creation.CreationRequest.model_validate(
        {
            "requestId": "11111111-1111-4111-8111-111111111111",
            "agentId": "agent",
            "region": "cn-beijing",
            "runtimeImage": "  ",
            "workerImage": " registry.example:5000/worker@sha256:" + "a" * 64 + " ",
        }
    )
    assert body.runtimeImage == ""
    assert body.workerImage.startswith("registry.example:5000/")


def test_authorized_config_returns_defaults_and_task_freezes_them(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(
        mpa_creation, "load_volcengine_credentials", lambda *args: object()
    )
    service = CreationTasks(tmp_path / "tasks.db")
    service.command = lambda: [sys.executable, "-c", "import time; time.sleep(30)"]
    app = FastAPI()
    mpa_creation.mount_mpa_creation_routes(
        app, owner=lambda request: "local", service=service
    )
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "agent",
        "region": "cn-beijing",
        "runtimeImage": "",
        "workerImage": "registry.example/worker:custom",
    }
    with TestClient(app) as client:
        config = client.get("/web/mpa-creation/config?region=cn-beijing").json()
        assert config["runtimeImage"].endswith(
            "/mpa_agent_studio:studio-a1f9627-20260923-172555"
        )
        response = client.post("/web/mpa-creation/tasks", json=payload)
        assert response.status_code == 202
        assert response.json()["images"] == {
            "runtimeImage": config["runtimeImage"],
            "workerImage": "registry.example/worker:custom",
        }
        rejected = client.post(
            "/web/mpa-creation/tasks",
            json={**payload, "workerImage": "https://repo?token=private"},
        )
        assert rejected.status_code == 422 and "private" not in rejected.text


def test_blank_retry_keeps_first_image_snapshot_and_runner_receives_it(tmp_path):
    async def run():
        service = CreationTasks(tmp_path / "tasks.db")
        service.command = lambda: [sys.executable, "-c", "raise SystemExit(1)"]
        payload = {
            "requestId": "11111111-1111-4111-8111-111111111111",
            "agentId": "agent",
            "region": "cn-beijing",
            "description": "",
        }
        images = {
            "runtimeImage": "registry.example/mpa:v1",
            "workerImage": "registry.example/worker:v1",
        }
        first = await service.start(
            "owner", payload, config_path="unused", timeout=30, images=images
        )
        await asyncio.gather(*service.running.values())
        result = {
            "runtime_id": "r-one",
            "skill_space_id": "ss-one",
            "gateway_id": "g-one",
            "agent_id": "agent",
            "region": "cn-beijing",
            "state": "ready",
        }
        script = (
            "import json,sys; data=json.load(sys.stdin); assert data['images']=="
            + repr(images)
            + "; print('MPA_EVENT ' + json.dumps({'result':"
            + repr(result)
            + "}))"
        )
        service.command = lambda: [sys.executable, "-c", script]
        retry = await service.start(
            "owner",
            payload,
            config_path="unused",
            timeout=30,
            images={"runtimeImage": "registry.example/mpa:v2"},
        )
        await asyncio.gather(*service.running.values())
        assert retry["taskId"] == first["taskId"]
        assert service.get("owner", retry["taskId"])["state"] == "succeeded"
        assert service.get("owner", retry["taskId"])["images"] == images
        with pytest.raises(TaskError):
            await service.start(
                "owner",
                {**payload, "runtimeImage": "registry.example/changed:v2"},
                config_path="unused",
                timeout=30,
                images=images,
            )
        await service.close()

    asyncio.run(run())


def test_runner_applies_persisted_images_without_changing_server_profile(
    tmp_path, monkeypatch
):
    import io
    from unittest.mock import AsyncMock
    from veadk.integrations.mpa.managed import runner

    profile = load_profile(profile_file(tmp_path, monkeypatch))
    fake = AsyncMock(
        return_value={
            "runtime_id": "r-one",
            "skill_space_id": "ss-one",
            "gateway_id": "g-one",
            "agent_id": "agent",
            "region": "cn-beijing",
            "state": "ready",
        }
    )
    monkeypatch.setattr(runner, "load_profile", lambda *args, **kwargs: profile)
    monkeypatch.setattr(runner, "provision", fake)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "config": "unused",
                    "region": "cn-beijing",
                    "agentId": "agent",
                    "owner": "owner",
                    "description": "",
                    "images": {
                        "runtimeImage": "repo/mpa:v2",
                        "workerImage": "repo/worker:v2",
                    },
                }
            )
        ),
    )
    assert runner.main() == 0
    actual = fake.call_args.args[0]
    assert actual.managed.runtime.image == "repo/mpa:v2"
    assert actual.managed.worker.image == "repo/worker:v2"
    assert actual.managed.worker.existing_id == ""
    assert profile.managed.worker.existing_id == "t-worker"


def test_legacy_task_schema_migration_retains_original_payload(tmp_path):
    import sqlite3

    path = tmp_path / "tasks.db"
    payload = {
        "requestId": "old-request",
        "agentId": "agent",
        "description": "",
        "region": "cn-beijing",
    }
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE tasks (id TEXT PRIMARY KEY, owner TEXT NOT NULL, request TEXT NOT NULL, payload TEXT NOT NULL, state TEXT NOT NULL, stage TEXT NOT NULL, result TEXT NOT NULL DEFAULT '{}', error TEXT NOT NULL DEFAULT '', supervisor INTEGER NOT NULL, updated REAL NOT NULL, UNIQUE(owner,request))"
        )
        db.execute(
            "INSERT INTO tasks (id,owner,request,payload,state,stage,supervisor,updated) VALUES (?,?,?,?,?,?,?,?)",
            (
                "old",
                "owner",
                "old-request",
                json.dumps(payload, sort_keys=True),
                "failed",
                "worker",
                1,
                0,
            ),
        )
    service = CreationTasks(path)
    assert service.get("owner", "old")["images"] == {}
    assert service.get("owner", "old")["agentId"] == "agent"
    # Reopening must not attempt another ALTER or erase the original request.
    assert CreationTasks(path).get("owner", "old")["requestId"] == "old-request"
