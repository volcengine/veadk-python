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

"""Named Studio creation keeps Runtime display names separate from identity."""

import asyncio
import io
import json
import re
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server import mpa_creation
from tests.integrations.mpa_managed.test_agent_deployment import deployer, template
from veadk.integrations.mpa.managed import runner
from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError


def named_request(**values):
    return {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "name": "support-agent",
        "region": "cn-beijing",
        **values,
    }


@pytest.fixture
def routes(tmp_path, monkeypatch):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "test-task"})
    app = FastAPI()

    def mount_owner(request):
        return request.headers.get("x-test-owner", "local")

    mpa_creation.mount_mpa_creation_routes(app, owner=mount_owner, service=service)
    with TestClient(app) as client:
        yield client, service


def test_new_creation_generates_owner_scoped_id_and_latest_images(routes):
    client, service = routes
    ids = []
    for owner, request_id in [
        ("local", "11111111-1111-4111-8111-111111111111"),
        ("local", "11111111-1111-4111-8111-111111111111"),
        ("another", "11111111-1111-4111-8111-111111111111"),
        ("local", "22222222-2222-4222-8222-222222222222"),
    ]:
        response = client.post(
            "/web/mpa-creation/tasks",
            json=named_request(name="  support-agent  ", requestId=request_id),
            headers={"x-test-owner": owner},
        )
        assert response.status_code == 202
        call = service.start.await_args
        payload = call.args[1]
        assert payload["name"] == "support-agent"
        assert re.fullmatch(r"mi-[0-9a-f]{24}", payload["agentId"])
        ids.append(payload["agentId"])
        assert "runtimeImage" not in payload and "workerImage" not in payload
        assert call.kwargs["images"] == {
            field: f"registry.example/{field}@sha256:" + "a" * 64
            for field in ("runtimeImage", "workerImage")
        }
    assert ids[0] == ids[1]
    assert len(set(ids)) == 3


@pytest.mark.parametrize(
    "name", ["", "   ", "abc", "a" * 65, "中文名称", "bad/name", "bad\nname"]
)
def test_invalid_name_fails_before_task_creation(routes, name):
    client, service = routes
    assert (
        client.post(
            "/web/mpa-creation/tasks", json=named_request(name=name)
        ).status_code
        == 422
    )
    service.start.assert_not_called()


def test_legacy_request_keeps_exact_payload_without_name(routes):
    client, service = routes
    legacy = named_request(
        agentId="mi-existing", runtimeImage="registry.example/mpa:v1"
    )
    legacy.pop("name")
    assert client.post("/web/mpa-creation/tasks", json=legacy).status_code == 202
    assert service.start.await_args.args[1] == {**legacy, "description": ""}


def test_named_runtime_preserves_generated_identity_and_existing_name():
    async def run():
        svc, _, cloud, _ = deployer()
        await svc.deploy(template(), runtime_name="support-agent")
        assert cloud.creates[0]["Name"] == "support-agent"
        assert {item["Key"]: item["Value"] for item in cloud.creates[0]["Envs"]}[
            "MPA_AGENT_ID"
        ] == "agent-one"
        await svc.deploy(template(), runtime_name="different-name")
        assert len(cloud.creates) == 1
        assert cloud.runtimes["r-agent"]["Name"] == "support-agent"

    asyncio.run(run())


@pytest.mark.parametrize("name", ["support-agent", ""])
def test_runner_forwards_optional_runtime_name(monkeypatch, name):
    profile = SimpleNamespace(managed=SimpleNamespace(timeout_seconds=60))
    monkeypatch.setattr(runner, "load_profile", lambda *a, **kw: profile)
    for method in (
        "with_creation_images",
        "with_creation_resources",
        "with_creation_tos",
    ):
        monkeypatch.setattr(runner, method, lambda value, *_: value)
    provision = AsyncMock(
        return_value={
            key: "test"
            for key in (
                "runtime_id",
                "skill_space_id",
                "gateway_id",
                "agent_id",
                "region",
                "state",
            )
        }
    )
    monkeypatch.setattr(runner, "provision", provision)
    data = dict(
        config=None,
        region="cn-beijing",
        agentId="mi-test",
        owner="local",
        description="",
    )
    if name:
        data["name"] = name
    monkeypatch.setattr(runner.sys, "stdin", io.StringIO(json.dumps(data)))
    assert runner.run() == 0
    assert provision.await_args is not None
    assert provision.await_args.kwargs["runtime_name"] == name


def test_missing_name_and_legacy_id_is_rejected(routes):
    client, service = routes
    payload = named_request()
    payload.pop("name")
    assert client.post("/web/mpa-creation/tasks", json=payload).status_code == 422
    service.start.assert_not_called()


def test_task_preserves_name_in_child_protocol_and_rejects_changed_retry(tmp_path):
    async def run():
        service = CreationTasks(tmp_path / "tasks.db")
        received = tmp_path / "received.json"
        code = (
            "import json,sys,pathlib; data=json.loads(sys.stdin.read()); "
            f"pathlib.Path({str(received)!r}).write_text(json.dumps(data)); "
            "print('MPA_EVENT '+json.dumps({'result': {'runtime_id':'r-test',"
            "'agent_id':data['agentId'],'skill_space_id':'ss-test',"
            "'gateway_id':'gw-test','region':'cn-beijing','state':'ready'}}))"
        )
        service.command = lambda: [sys.executable, "-c", code]
        payload = named_request(agentId="mi-generated", description="")
        try:
            task = await service.start("owner", payload, config_path=None, timeout=60)
            with pytest.raises(TaskError):
                await service.start(
                    "owner",
                    {**payload, "name": "changed-name"},
                    config_path=None,
                    timeout=60,
                )
            await asyncio.gather(*service.running.values())
            assert service.get("owner", task["taskId"])["state"] == "succeeded"
            data = json.loads(received.read_text())
            assert data["name"] == "support-agent"
            assert data["agentId"] == "mi-generated"
            duplicate = await service.start(
                "owner", payload, config_path=None, timeout=60
            )
            assert duplicate["taskId"] == task["taskId"]
        finally:
            await service.close()

    asyncio.run(run())
