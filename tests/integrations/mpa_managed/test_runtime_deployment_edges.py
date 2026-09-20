"""Cloud adapters and deployment recovery guards without live services."""

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from veadk.integrations.mpa.managed import runtime as mod
from veadk.integrations.mpa.managed import skills
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_agent_deployment import (
    Cloud,
    Registry,
    deployer,
    template,
)


def test_cloud_sdk_credentials_are_checked_on_every_call(monkeypatch):
    from agentkit.auth import sts
    from agentkit.sdk.runtime import client as runtime_sdk
    from agentkit.sdk.skills import client as skill_sdk

    from veadk.integrations.mpa.managed import credentials as iam_credentials

    monkeypatch.setattr(
        iam_credentials,
        "load_volcengine_credentials",
        lambda _: SimpleNamespace(
            access_key_id="ak", secret_access_key="sk", session_token="token"
        ),
    )
    accounts = iter(["a", "a", "other"])
    monkeypatch.setattr(
        sts, "get_caller_identity", lambda *a, **kw: {"AccountId": next(accounts)}
    )
    monkeypatch.setattr(
        runtime_sdk, "AgentkitRuntimeClient", lambda **kw: ("runtime", kw)
    )
    monkeypatch.setattr(skill_sdk, "AgentkitSkillsClient", lambda **kw: ("skills", kw))
    cloud = mod.RuntimeCloud(region="cn-beijing", credential_file="iam")
    assert asyncio.run(cloud.account_id()) == "a"
    kind, kw = cloud._client(skills=True)
    assert kind == "skills" and kw["session_token"] == "token"
    with pytest.raises(DeploymentError, match="accounts"):
        cloud._client()


def test_cloud_wrappers_validate_requests_and_parse_ids(monkeypatch):
    cloud = mod.RuntimeCloud(region="cn-beijing", credential_file="iam")
    calls = []

    class Client:
        def __getattr__(self, method):
            def invoke(req):
                calls.append((method, req.model_dump(by_alias=True)))
                return SimpleNamespace(
                    model_dump=lambda **kw: {"RuntimeId": "r-one", "Id": "ss-one"}
                )

            return invoke

    monkeypatch.setattr(cloud, "_client", lambda **kw: Client())

    async def run():
        assert (await cloud.get("r-one"))["RuntimeId"] == "r-one"
        assert await cloud.create({**template(), "Name": "agent"}) == "r-one"
        await cloud.update({"RuntimeId": "r-one", "ArtifactUrl": "image:v2"})
        assert await cloud.create_skill_space({"Name": "skills"}) == "ss-one"
        assert (await cloud.get_skill_space("ss-one"))["Id"] == "ss-one"
        assert [c[0] for c in calls] == [
            "get_runtime",
            "create_runtime",
            "update_runtime",
            "create_skill_space",
            "get_skill_space",
        ]
        monkeypatch.setattr(cloud, "call", AsyncMock(return_value={}))
        with pytest.raises(DeploymentError, match="no ID"):
            await cloud.create({**template(), "Name": "agent"})

    asyncio.run(run())


@pytest.mark.parametrize("outcome", [200, 503, "network"])
def test_application_readiness_sends_auth_and_handles_unavailable(monkeypatch, outcome):
    class Client:
        def __init__(self, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def get(self, url, headers):
            assert url == "https://public/readiness"
            assert headers == {"Authorization": "Bearer key"}
            if outcome == "network":
                raise httpx.ConnectError("offline")
            return SimpleNamespace(status_code=outcome)

    monkeypatch.setattr(mod.httpx, "AsyncClient", Client)
    runtime = {
        "NetworkConfigurations": [
            {"NetworkType": "Public", "Endpoint": "https://public"}
        ],
        "AuthorizerConfiguration": {"KeyAuth": {"ApiKey": "Bearer key"}},
    }
    cloud = mod.RuntimeCloud(region="r", credential_file="iam")
    assert asyncio.run(cloud.is_ready(runtime)) is (outcome == 200)


@pytest.mark.parametrize(
    "field,value,error",
    [
        ("MPA_AGENT_ID", "other", "different agent"),
        ("PGDATABASE", "other", "different agent"),
        ("PGHOST", "other", "PGHOST"),
        ("PGPORT", "6543", "PGPORT"),
        ("PGUSER", "other", "PGUSER"),
        ("RoleName", "other", "IAM role"),
        ("NetworkConfigurations", [], "endpoints"),
    ],
)
def test_validate_runtime_rejects_identity_or_network_drift(field, value, error):
    async def run():
        svc, _, cloud, _ = deployer()
        result = await svc.deploy(template())
        rt = copy.deepcopy(cloud.runtimes[result["runtime_id"]])
        if field == "NetworkConfigurations":
            rt[field] = rt[field][:1]
        elif field == "RoleName":
            rt[field] = value
        else:
            rt["Envs"].append({"Key": field, "Value": value})
        with pytest.raises(DeploymentError, match=error):
            mod.validate_runtime(
                rt,
                agent_id="agent-one",
                database=result["database_name"],
                template=template(),
            )

    asyncio.run(run())


@pytest.mark.parametrize(
    "status,error", [("Failed", "failed"), ("Creating", "pending")]
)
def test_platform_wait_stops_on_error_or_timeout(status, error):
    async def run():
        svc, _, cloud, _ = deployer()
        svc.timeout = 0.001
        cloud.get = AsyncMock(return_value={"Status": status})
        with pytest.raises(DeploymentError, match=error):
            await svc.wait_platform("r-one")

    asyncio.run(run())


def test_deployment_rejects_incomplete_network_before_creating_resources():
    async def run():
        svc, registry, cloud, _ = deployer()
        payload = template()
        payload["NetworkConfiguration"]["EnablePrivateNetwork"] = False
        with pytest.raises(DeploymentError, match="public/private"):
            await svc.deploy(payload)
        assert not registry.row and not cloud.creates

    asyncio.run(run())


@pytest.mark.parametrize(
    "mode", ["missing_key", "registration_wait", "registration_finish", "unready"]
)
def test_partial_deployment_stays_pending_and_rejects_concurrent_change(mode):
    async def run():
        svc, registry, cloud, _ = deployer()
        original_wait = svc.wait_platform

        async def wait(*args, **kw):
            result = await original_wait(*args, **kw)
            if mode == "missing_key":
                result["AuthorizerConfiguration"] = {}
            if mode == "registration_wait":
                registry.row["request_hash"] = "changed"
            return result

        svc.wait_platform = wait

        async def ready(runtime):
            if mode == "registration_finish":
                registry.row["request_hash"] = "changed"
            return mode != "unready"

        cloud.is_ready = ready
        if mode == "unready":
            svc.timeout = 0.002
        with pytest.raises(DeploymentError):
            await svc.deploy(template())
        assert registry.row["pending"]
        assert len(cloud.creates) == 1

    asyncio.run(run())


def test_skill_space_pending_and_invalid_responses():
    async def run():
        registry = Registry()
        cloud = Cloud(registry)
        registry.row = {"pending": True}
        with pytest.raises(DeploymentError, match="previous deployment"):
            await skills.ensure_skill_space(
                registry, cloud, account="a", region="r", agent_id="i"
            )
        registry.row = {}
        cloud.create_skill_space = AsyncMock(return_value="")
        with pytest.raises(DeploymentError, match="no ID"):
            await skills.ensure_skill_space(
                registry,
                cloud,
                account="a",
                region="r",
                agent_id="i",
                project_name="project",
            )
        assert registry.row["skill_space_create_requested"]
        assert registry.row["skill_space_request"]["ProjectName"] == "project"

    asyncio.run(run())
    for space, project in [
        ({"Id": "ss", "Status": "Failed"}, ""),
        ({"Id": "ss", "ProjectName": "other"}, "project"),
    ]:
        with pytest.raises(DeploymentError):
            skills.validate_space(space, "ss", project)
