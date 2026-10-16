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

"""Per-request MPA scaling survives validation, task recovery and deployment."""

import asyncio
import io
import json
import sys
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.mpa_creation import CreationRequest, mount_mpa_creation_routes
from veadk.integrations.mpa.managed.config import ConfigurationError, load_profile
from veadk.integrations.mpa.managed.tasks import CreationTasks, TaskError
from tests.integrations.mpa_managed.test_config import profile_file


def selected_profile(tmp_path, monkeypatch, value):
    from veadk.integrations.mpa.managed.config import with_creation_scaling

    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"min-instance": 1, "max-instance": 1}
        )
    )
    return profile, with_creation_scaling(profile, value)


def test_scaling_is_optional_and_does_not_mutate_config(tmp_path, monkeypatch):
    profile, selected = selected_profile(tmp_path, monkeypatch, 20)
    assert selected.managed.runtime.max_instance == 20
    assert profile.managed.runtime.max_instance == 1
    from veadk.integrations.mpa.managed.config import with_creation_scaling

    assert with_creation_scaling(profile, None) is profile


@pytest.mark.parametrize("value", [0, -1, 1.2, True, "20", 2**53])
def test_scaling_rejects_invalid_integer_values(tmp_path, monkeypatch, value):
    with pytest.raises(ConfigurationError):
        selected_profile(tmp_path, monkeypatch, value)


def test_scaling_rejects_below_configured_minimum(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.config import with_creation_scaling

    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"min-instance": 3, "max-instance": 4}
        )
    )
    with pytest.raises(ConfigurationError, match="[Mm]inimum"):
        with_creation_scaling(profile, 2)


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")]
)
def test_creation_accepts_explicit_maximum_and_keeps_legacy_payload(
    tmp_path, monkeypatch, provider, region
):
    from frontend.server import mpa_creation

    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    monkeypatch.setattr(mpa_creation, "load_provider_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock(return_value={"taskId": "fixture"})
    app = FastAPI()
    mount_mpa_creation_routes(
        app, owner=lambda _request: "local", service=service, provider=provider
    )
    body = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "name": "test-name",
        "region": region,
    }
    with TestClient(app) as client:
        assert (
            client.post(
                "/web/mpa-creation/tasks", json={**body, "maxInstance": 35}
            ).status_code
            == 202
        )
        call = service.start.await_args
        assert call is not None
        assert call.args[1]["maxInstance"] == 35
        assert client.post("/web/mpa-creation/tasks", json=body).status_code == 202
        call = service.start.await_args
        assert call is not None
        assert "maxInstance" not in call.args[1]
        assert (
            client.post(
                "/web/mpa-creation/tasks", json={**body, "maxInstance": None}
            ).status_code
            == 202
        )
        call = service.start.await_args
        assert call is not None
        assert "maxInstance" not in call.args[1]


@pytest.mark.parametrize("value", [0, -1, 1.2, True, "20", 2**53])
def test_creation_schema_rejects_invalid_maximum(value):
    with pytest.raises(ValueError):
        CreationRequest.model_validate(
            {
                "requestId": "11111111-1111-4111-8111-111111111111",
                "name": "test-name",
                "region": "cn-beijing",
                "maxInstance": value,
            }
        )


@pytest.mark.asyncio
async def test_task_pins_and_forwards_selected_maximum(tmp_path):
    tasks = CreationTasks(tmp_path / "tasks.db")
    received = tmp_path / "stdin.json"
    tasks.command = lambda: [
        sys.executable,
        "-c",
        "import json,sys,pathlib; data=json.loads(sys.stdin.read()); "
        + f"pathlib.Path({str(received)!r}).write_text(json.dumps(data)); "
        + "print('MPA_EVENT '+json.dumps({'error':'creationFailed'}))",
    ]
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "name": "test-name",
        "description": "",
        "region": "cn-beijing",
        "maxInstance": 35,
    }
    try:
        task = await tasks.start("owner", payload, config_path=None, timeout=60)
        await asyncio.gather(*tasks.running.values())
        assert json.loads(received.read_text())["maxInstance"] == 35
        assert tasks.get("owner", task["taskId"])["maxInstance"] == 35
        with pytest.raises(TaskError, match="different inputs"):
            await tasks.start(
                "owner", {**payload, "maxInstance": 20}, config_path=None, timeout=60
            )
        await tasks.start("owner", payload, config_path=None, timeout=60)
        await asyncio.gather(*tasks.running.values())
        assert json.loads(received.read_text())["maxInstance"] == 35
    finally:
        await tasks.close()


def test_runner_applies_explicit_maximum_before_provision(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed import runner

    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"min-instance": 1, "max-instance": 1}
        )
    )
    monkeypatch.setattr(runner, "load_profile", lambda *_args, **_kwargs: profile)
    monkeypatch.setattr(runner, "emit", lambda **_kwargs: None)
    result = {
        "runtime_id": "r-test",
        "skill_space_id": "ss-test",
        "gateway_id": "gw-test",
        "agent_id": "mi-test",
        "region": "cn-beijing",
        "state": "ready",
    }
    provision = AsyncMock(return_value=result)
    monkeypatch.setattr(runner, "provision", provision)
    data = {
        "config": None,
        "agentId": "mi-test",
        "owner": "owner",
        "description": "",
        "region": "cn-beijing",
        "maxInstance": 35,
    }
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(data)))
    assert runner.run() == 0
    call = provision.await_args
    assert call is not None
    assert call.args[0].managed.runtime.max_instance == 35


@pytest.mark.asyncio
async def test_selected_maximum_reaches_create_and_retry_runtime_payload(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.service import apply_runtime_settings
    from tests.integrations.mpa_managed.test_agent_deployment import deployer, template

    _, profile = selected_profile(tmp_path, monkeypatch, 35)
    svc, _, cloud, _ = deployer()
    request = template()
    apply_runtime_settings(request, profile.managed.runtime)
    await svc.deploy(request)
    await svc.deploy(request)
    assert cloud.creates[0]["MaxInstance"] == 35
    assert cloud.updates[0]["MaxInstance"] == 35
    assert len(cloud.creates) == 1


def test_bff_rejects_below_minimum_before_starting_task(tmp_path, monkeypatch):
    from frontend.server import mpa_creation

    profile = load_profile(
        profile_file(
            tmp_path, monkeypatch, runtime={"min-instance": 3, "max-instance": 4}
        )
    )
    monkeypatch.setattr(mpa_creation, "load_studio_profile", lambda **_kwargs: profile)
    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    service = CreationTasks(tmp_path / "tasks.db")
    service.start = AsyncMock()
    app = FastAPI()
    mount_mpa_creation_routes(app, owner=lambda _request: "local", service=service)
    with TestClient(app) as client:
        response = client.post(
            "/web/mpa-creation/tasks",
            json={
                "requestId": "11111111-1111-4111-8111-111111111111",
                "agentId": "mi-test",
                "name": "test-name",
                "region": "cn-beijing",
                "maxInstance": 2,
            },
        )
    assert response.status_code == 400
    service.start.assert_not_awaited()
