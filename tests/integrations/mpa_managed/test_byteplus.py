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

"""Provider isolation for managed creation; no real cloud operations."""

import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server import mpa_creation
from veadk.integrations.mpa.managed.config import (
    ConfigurationError,
    load_studio_profile,
)
from veadk.integrations.mpa.managed.credentials import load_volcengine_credentials
from veadk.integrations.mpa.managed.studio_profile import studio_profile_values
from veadk.integrations.mpa.managed.tasks import CreationTasks


def test_byteplus_profile_is_separate_from_domestic_defaults(monkeypatch):
    domestic = studio_profile_values()
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    assert studio_profile_values() == domestic
    profile = load_studio_profile(provider="byteplus", region="ap-southeast-1")
    assert profile.provider == "byteplus"
    assert profile.values["model_name"] == "dola-seed-2-1-turbo-260628"
    assert (
        profile.values["model_api_base"].rstrip("/")
        == "https://ark.ap-southeast.bytepluses.com/api/v3"
    )
    env = profile.managed.runtime.env
    assert env["CLOUD_PROVIDER"] == env["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
    assert env["APIG_TOP_ENDPOINT"] == "apig.ap-southeast-1.byteplusapi.com"
    domestic_pg = load_studio_profile().managed.postgres
    assert profile.managed.postgres is not None and domestic_pg is not None
    assert profile.managed.postgres.bootstrap_path != domestic_pg.bootstrap_path
    assert profile.image_defaults() == load_studio_profile().image_defaults()
    assert profile.summary()["configured"] is True


@pytest.mark.parametrize(
    "provider,region", [("byteplus", "cn-beijing"), ("volcengine", "ap-southeast-1")]
)
def test_provider_region_mismatch_fails_before_cloud(provider, region):
    with pytest.raises(ConfigurationError, match="selected region"):
        load_studio_profile(provider=provider, region=region)


def test_byteplus_never_reads_domestic_credentials(monkeypatch):
    from veadk.integrations.mpa.managed.credentials import load_provider_credentials

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "domestic-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "domestic-sk")
    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    monkeypatch.setattr(Path, "read_text", lambda *_: (_ for _ in ()).throw(OSError()))
    with pytest.raises(ValueError):
        load_provider_credentials("byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "overseas-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "overseas-sk")
    monkeypatch.setenv("BYTEPLUS_SESSION_TOKEN", "overseas-token")
    cred = load_provider_credentials("byteplus")
    assert (cred.access_key_id, cred.session_token) == ("overseas-ak", "overseas-token")
    assert load_volcengine_credentials().access_key_id == "domestic-ak"


def test_byteplus_routes_keep_provider_server_owned(tmp_path, monkeypatch):
    monkeypatch.setattr(mpa_creation, "load_provider_credentials", lambda *_: None)
    tasks = CreationTasks(tmp_path / "tasks.db")
    tasks.start = AsyncMock(return_value={"taskId": "mock"})
    app = FastAPI()
    mpa_creation.mount_mpa_creation_routes(
        app, owner=lambda _: "local", service=tasks, provider="byteplus"
    )
    body = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "name": "test-agent",
        "region": "ap-southeast-1",
    }
    with TestClient(app) as client:
        assert (
            client.get("/web/mpa-creation/config?region=ap-southeast-1").json()[
                "configured"
            ]
            is True
        )
        assert (
            client.get("/web/mpa-creation/config?region=cn-beijing").json()[
                "configured"
            ]
            is False
        )
        assert (
            client.post(
                "/web/mpa-creation/tasks", json={**body, "provider": "volcengine"}
            ).status_code
            == 422
        )
        assert client.post("/web/mpa-creation/tasks", json=body).status_code == 202
    assert tasks.start.await_args is not None
    assert tasks.start.await_args.args[1]["provider"] == "byteplus"
    assert (
        mpa_creation._studio_task_path("byteplus") != mpa_creation._studio_task_path()
    )


def test_runtime_sts_and_sdk_are_selected_inside_worker_thread(monkeypatch):
    from agentkit.auth import sts
    from agentkit.platform.context import get_default_cloud_provider
    from agentkit.sdk.runtime import client

    from veadk.integrations.mpa.managed.runtime import RuntimeCloud

    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-sk")
    calls = []

    def identity(*args, **kwargs):
        calls.append(kwargs)
        return {"AccountId": "test-account"}

    monkeypatch.setattr(sts, "get_caller_identity", identity)
    monkeypatch.setattr(
        client,
        "AgentkitRuntimeClient",
        lambda **kwargs: calls.append(get_default_cloud_provider()),
    )
    cloud = RuntimeCloud(
        region="ap-southeast-1", credential_file="", provider="byteplus"
    )
    assert asyncio.run(cloud.account_id()) == "test-account"
    assert calls[0]["host"] == "open.byteplusapi.com"
    assert calls[1] == "byteplus"


@pytest.mark.parametrize(
    "provider,region,expected",
    [
        (
            "volcengine",
            "cn-beijing",
            {
                "vpc": "vpc.cn-beijing.volcengineapi.com",
                "ecs": "ecs.cn-beijing.volcengineapi.com",
                "apig": "apig.cn-beijing.volcengineapi.com",
                "aidap": "open.volcengineapi.com",
                "ark": "open.volcengineapi.com",
                "sts": "sts.volcengineapi.com",
                "iam": "iam.volcengineapi.com",
            },
        ),
        (
            "byteplus",
            "ap-southeast-1",
            {
                "vpc": "vpc.ap-southeast-1.byteplusapi.com",
                "ecs": "ecs.ap-southeast-1.byteplusapi.com",
                "apig": "apig.ap-southeast-1.byteplusapi.com",
                "aidap": "open.byteplusapi.com",
                "ark": "ark.ap-southeast-1.byteplusapi.com",
                "sts": "open.byteplusapi.com",
                "iam": "open.byteplusapi.com",
            },
        ),
    ],
)
def test_managed_service_hosts_are_provider_scoped(
    monkeypatch, provider, region, expected
):
    from veadk.integrations.mpa.managed.provider import managed_host

    for key in (
        "APIG_OPENAPI_HOST",
        "IAM_OPENAPI_HOST",
        "VEADK_MPA_BYTEPLUS_AIDAP_HOST",
    ):
        monkeypatch.delenv(key, raising=False)
    assert {
        service: managed_host(service, region, provider) for service in expected
    } == expected


@pytest.mark.asyncio
async def test_byteplus_sdk_transports_use_overseas_hosts(monkeypatch):
    import volcenginesdkaidap
    import volcenginesdkcore
    import volcenginesdkecs
    import volcenginesdkvpc
    from volcenginesdkcore import universal

    from veadk.integrations.mpa.managed.gateway_cloud import GatewayCloud
    from veadk.integrations.mpa.managed.network_cloud import NetworkCloud
    from veadk.integrations.mpa.managed.pg_cloud import PGCloud

    configs = []
    credential = SimpleNamespace(
        access_key_id="test-ak", secret_access_key="test-sk", session_token="test-token"
    )

    def api(config):
        configs.append(config)
        return SimpleNamespace(
            rest_client=SimpleNamespace(
                pool_manager=SimpleNamespace(clear=lambda: None)
            )
        )

    monkeypatch.setattr(volcenginesdkcore, "ApiClient", api)

    def client(_):
        def result(*args, **kwargs):
            return SimpleNamespace(
                to_dict=lambda: {
                    "zones": [{"zone_id": "ap-southeast-1a"}],
                    "workspaces": [],
                    "vpc_id": "test-vpc",
                }
            )

        return SimpleNamespace(
            describe_zones=result,
            describe_vpc_attributes=result,
            describe_workspaces=result,
        )

    monkeypatch.setattr(volcenginesdkecs, "ECSApi", client)
    monkeypatch.setattr(volcenginesdkvpc, "VPCApi", client)
    monkeypatch.setattr(volcenginesdkaidap, "AIDAPApi", client)
    monkeypatch.setattr(
        universal,
        "UniversalApi",
        lambda _: SimpleNamespace(
            do_call=lambda *a, **kw: {
                "Result": {"AvailableZones": ["ap-southeast-1a", "ap-southeast-1b"]}
            }
        ),
    )
    network = NetworkCloud(
        region="ap-southeast-1", credentials=lambda: credential, provider="byteplus"
    )
    await network.zones()
    await network.vpc("test-vpc")
    await PGCloud(
        region="ap-southeast-1", credentials=lambda: credential, provider="byteplus"
    ).call("describe_workspaces", "DescribeWorkspacesRequest")
    gateway = GatewayCloud(
        SimpleNamespace(
            region="ap-southeast-1",
            provider="byteplus",
            _credentials=lambda: credential,
        )
    )
    await gateway.call("GetGatewayAvailableZones", {})
    assert [config.host for config in configs] == [
        "ecs.ap-southeast-1.byteplusapi.com",
        "vpc.ap-southeast-1.byteplusapi.com",
        "open.byteplusapi.com",
        "apig.ap-southeast-1.byteplusapi.com",
    ]
    assert all(
        config.region == "ap-southeast-1" and config.session_token == "test-token"
        for config in configs
    )


@pytest.mark.asyncio
async def test_byteplus_iam_client_has_overseas_host_and_signing_region(monkeypatch):
    from volcengine.iam.IamService import IamService

    from veadk.integrations.mpa.managed.iam import IamCloud

    seen = []

    def role(self, params):
        seen.append((self.service_info.host, self.service_info.credentials.region))
        return {"Result": {}}

    monkeypatch.setattr(IamService, "get_role", role)
    cloud = IamCloud(
        SimpleNamespace(
            region="ap-southeast-1",
            provider="byteplus",
            _credentials=lambda: SimpleNamespace(
                access_key_id="test", secret_access_key="test", session_token=""
            ),
        )
    )
    await cloud.call("get_role", RoleName="test-role")
    assert seen == [("open.byteplusapi.com", "ap-southeast-1")]


@pytest.mark.asyncio
async def test_provider_fingerprint_and_child_survive_retry(tmp_path):
    import json
    import sys

    from veadk.integrations.mpa.managed.tasks import TaskError

    service = CreationTasks(tmp_path / "tasks.sqlite3")
    received = tmp_path / "child.json"
    service.command = lambda: [
        sys.executable,
        "-c",
        f"import sys,pathlib; pathlib.Path({str(received)!r}).write_text(sys.stdin.read()); raise SystemExit(1)",
    ]
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "description": "",
        "region": "ap-southeast-1",
        "provider": "byteplus",
    }
    try:
        task = await service.start("owner", payload, config_path=None, timeout=10)
        await asyncio.gather(*service.running.values())
        assert json.loads(received.read_text())["provider"] == "byteplus"
        with pytest.raises(TaskError):
            await service.start(
                "owner",
                {**payload, "provider": "volcengine"},
                config_path=None,
                timeout=10,
            )
        retry = await service.start("owner", payload, config_path=None, timeout=10)
        assert retry["taskId"] == task["taskId"]
        await asyncio.gather(*service.running.values())
        assert json.loads(received.read_text())["provider"] == "byteplus"
    finally:
        await service.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "zones",
    [["ap-southeast-1a", "ap-southeast-1b"], ["ap-southeast-1-a", "ap-southeast-1-b"]],
)
async def test_byteplus_gateway_preserves_provider_zone_ids(zones):
    from veadk.integrations.mpa.managed.gateway_cloud import GatewayCloud

    cloud = GatewayCloud(SimpleNamespace(region="ap-southeast-1", provider="byteplus"))
    cloud.call = AsyncMock(return_value={"AvailableZones": zones})
    assert await cloud.available_zones() == zones


def test_byteplus_without_environment_requires_explicit_iam_file(monkeypatch):
    from veadk.integrations.mpa.managed.credentials import load_provider_credentials

    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    monkeypatch.setattr(
        Path,
        "read_text",
        lambda *_: '{"AccessKeyId":"other-cloud","SecretAccessKey":"other-cloud","SessionToken":"other-cloud"}',
    )
    with pytest.raises(ValueError):
        load_provider_credentials("byteplus")
    assert (
        load_provider_credentials("byteplus", "/explicit/iam").access_key_id
        == "other-cloud"
    )


@pytest.mark.asyncio
async def test_real_sdk_clients_keep_separate_hosts_under_concurrent_providers(
    monkeypatch,
):
    from agentkit.sdk.tools.client import AgentkitToolsClient
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud
    from veadk.integrations.mpa.managed.worker import WorkerCloud
    from veadk.integrations.mpa.managed.credentials import Credentials

    hosts = []

    def tool(self, request):
        hosts.append(self.host)
        return SimpleNamespace(model_dump=lambda **_: {})

    monkeypatch.setattr(AgentkitToolsClient, "get_tool", tool)

    async def clients(provider, region):
        cloud = RuntimeCloud(region=region, credential_file="", provider=provider)
        cloud._credentials = lambda: Credentials("test-ak", "test-sk")
        runtime = await asyncio.to_thread(cloud._client)
        skills = await asyncio.to_thread(lambda: cloud._client(skills=True))
        await WorkerCloud(cloud).get("t-test")
        try:
            assert runtime.host == skills.host
            return runtime.host
        finally:
            runtime.session.close()
            skills.session.close()

    overseas, domestic = await asyncio.gather(
        clients("byteplus", "ap-southeast-1"), clients("volcengine", "cn-beijing")
    )
    assert overseas == "agentkit.ap-southeast-1.byteplusapi.com"
    assert domestic == "open.volcengineapi.com"
    assert set(hosts) == {overseas, domestic}


@pytest.mark.asyncio
async def test_model_key_request_uses_byteplus_control_endpoint(monkeypatch):
    from veadk.integrations.mpa.managed import model_key
    from veadk.integrations.mpa.managed.credentials import Credentials

    seen = []
    monkeypatch.setattr(
        model_key,
        "volcengine_signed_request",
        lambda **kwargs: seen.append(kwargs) or {"Result": {}},
    )
    profile = load_studio_profile(provider="byteplus")

    class Cloud:
        def _credentials(self):
            return Credentials("test-ak", "test-sk")

    await model_key._read(
        Cloud(),
        profile,
        "ListApiKeys",
        {},
    )
    assert seen[0]["host"] == "ark.ap-southeast-1.byteplusapi.com"
    assert seen[0]["region"] == "ap-southeast-1"


def test_child_loads_byteplus_profile_and_injects_overseas_runtime_values(monkeypatch):
    import io
    import json
    from dataclasses import replace
    from veadk.integrations.mpa.managed import runner, service

    result = {
        "runtime_id": "r-test",
        "skill_space_id": "ss-test",
        "gateway_id": "gw-test",
        "agent_id": "mi-test",
        "region": "ap-southeast-1",
        "state": "ready",
    }
    provision = AsyncMock(return_value=result)
    monkeypatch.setattr(runner, "provision", provision)
    monkeypatch.setattr(
        runner.sys,
        "stdin",
        io.StringIO(
            json.dumps(
                {
                    "config": None,
                    "region": "ap-southeast-1",
                    "provider": "byteplus",
                    "agentId": "mi-test",
                    "owner": "local",
                    "description": "",
                }
            )
        ),
    )
    assert runner.run() == 0
    assert provision.await_args is not None
    selected = provision.await_args.args[0]
    assert selected.provider == "byteplus"
    selected = replace(
        selected,
        values={
            **selected.values,
            "pg_host": "test-db",
            "pg_user": "test-user",
            "pg_password": "test-password",
            "model_api_key": "test-model-key",
        },
    )
    template = service.fresh_template(selected, "mi-123456789abc", "test-account")
    service.apply_runtime_settings(template, selected.managed.runtime)
    env = {item["Key"]: item["Value"] for item in template["Envs"]}
    assert env["MODEL_AGENT_API_BASE"].startswith(
        "https://ark.ap-southeast.bytepluses.com/"
    )
    assert env["CLOUD_PROVIDER"] == env["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
    assert env["IDENTITY_REGION"] == env["BYTEPLUS_REGION"] == "ap-southeast-1"


@pytest.mark.asyncio
async def test_byteplus_worker_mount_and_environment_are_overseas():
    from tests.integrations.mpa_managed.test_agent_deployment import Registry
    from veadk.integrations.mpa.managed.database import DeploymentError
    from veadk.integrations.mpa.managed.worker import ensure_worker

    profile = load_studio_profile(provider="byteplus")
    profile.managed.worker.tos_access_key = "test-ak"
    profile.managed.worker.tos_secret_key = "test-sk"
    profile.managed.worker.tos_bucket = "test-bucket"
    cloud = SimpleNamespace(
        runtime=SimpleNamespace(provider="byteplus"),
        find=AsyncMock(return_value=[]),
        create=AsyncMock(side_effect=DeploymentError("request captured")),
    )
    with pytest.raises(DeploymentError, match="request captured"):
        await ensure_worker(
            Registry(),
            cloud,
            profile.managed.worker,
            account="test-account",
            region="ap-southeast-1",
            agent_id="mi-test",
        )
    request = cloud.create.await_args.args[0]
    assert (
        request["TosMountConfig"]["MountPoints"][0]["Endpoint"]
        == "https://tos-ap-southeast-1.bytepluses.com"
    )
    assert {item["Key"]: item["Value"] for item in request["Envs"]}[
        "CLOUD_PROVIDER"
    ] == "byteplus"


@pytest.mark.parametrize(
    "host",
    [
        "https://example.com",
        "example.com/path",
        "user:secret@example.com",
        "example.com?token=test",
    ],
)
def test_byteplus_aidap_override_rejects_urls_and_userinfo(monkeypatch, host):
    monkeypatch.setenv("VEADK_MPA_BYTEPLUS_AIDAP_HOST", host)
    with pytest.raises(ConfigurationError):
        load_studio_profile(provider="byteplus")


def test_byteplus_image_overrides_do_not_change_domestic_defaults(monkeypatch):
    monkeypatch.setenv(
        "VEADK_MPA_BYTEPLUS_RUNTIME_IMAGE", "example.com/test/mpa:custom"
    )
    monkeypatch.setenv(
        "VEADK_MPA_BYTEPLUS_WORKER_IMAGE", "example.com/test/worker:custom"
    )
    overseas = load_studio_profile(provider="byteplus").image_defaults()
    assert overseas == {
        "runtimeImage": "example.com/test/mpa:custom",
        "workerImage": "example.com/test/worker:custom",
    }
    assert load_studio_profile().image_defaults() != overseas


def test_managed_byteplus_iam_retains_trusted_host_override(monkeypatch):
    from veadk.integrations.mpa.managed.provider import managed_host

    monkeypatch.setenv("IAM_OPENAPI_HOST", "https://iam-test.byteplusapi.com/")
    assert (
        managed_host("iam", "ap-southeast-1", "byteplus") == "iam-test.byteplusapi.com"
    )
    assert managed_host("iam", "cn-beijing", "volcengine") == "iam.volcengineapi.com"
