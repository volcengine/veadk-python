import asyncio
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed import service
from veadk.integrations.mpa.managed.config import Managed, Profile, Runtime, Worker
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_agent_deployment import (
    Registry,
    Cloud,
    Databases,
    template,
)


@pytest.mark.parametrize("source", ["reference", "template", "flat"])
@pytest.mark.parametrize("image", [None, "registry.example/mpa:pinned"])
def test_network_gateway_worker_precede_runtime(monkeypatch, source, image):
    async def run():
        entry = Registry()
        cloud = Cloud(entry)
        events = []
        profile = Profile(
            region="cn-beijing",
            values={},
            template=template(),
            admin_url="fake",
            shared_url="shared",
            managed=Managed(
                version=1,
                runtime=Runtime(),
                worker=Worker(existing_id="t-one"),
                timeout_seconds=60,
            ),
        )
        profile.managed.runtime.image = image
        if source == "reference":
            profile.managed.from_runtime = "r-source"
            cloud.runtimes["r-source"] = template()
        elif source == "flat":
            profile.template = None
            profile.values = {
                "pg_host": "pg.example",
                "pg_user": "app",
                "pg_password": "fake",
                "model_provider": "openai",
                "model_api_base": "https://model.example",
                "model_api_key": "fake",
                "model_name": "model",
            }
            if image is None:
                profile.values["image"] = "registry/image:v1"
        monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
        monkeypatch.setattr(service, "AgentDeploymentRegistry", lambda url: entry)
        databases = Databases()
        monkeypatch.setattr(service, "AgentDatabaseProvisioner", lambda **kw: databases)

        class Gateway:
            def __init__(self, **kw):
                pass

            async def ensure(self, **kw):
                assert not entry.mutex.locked()
                assert entry.network.row.get("vpc_id")
                events.append("gateway")
                return {"gateway_id": "gw-one"}

        async def worker(*a, **kw):
            assert events == ["gateway"]
            events.append("worker")
            return "t-one"

        monkeypatch.setattr(service, "SharedAPIGService", Gateway)
        monkeypatch.setattr(service, "ensure_worker", worker)
        cloud_create = cloud.create

        async def create(request):
            assert events == ["gateway", "worker"]
            assert request["ToolId"] == "t-one"
            assert request["ArtifactUrl"] == (image or "registry/image:v1")
            if image:
                assert request["ArtifactType"] == "image"
            return await cloud_create(request)

        cloud.create = create
        result = await service.provision(profile, agent_id="agent", owner="user-a")
        assert result["runtime_id"] == "r-agent"
        assert result["gateway_id"] == "gw-one"
        with pytest.raises(DeploymentError, match="owner"):
            await service.provision(profile, agent_id="agent", owner="user-b")

    asyncio.run(run())


def test_database_preflight_failure_prevents_network_and_gateway_mutations(monkeypatch):
    async def run():
        profile = Profile(
            region="cn-beijing",
            values={},
            template=template(),
            admin_url="fake",
            shared_url="shared",
            managed=Managed(
                version=1,
                runtime=Runtime(),
                worker=Worker(existing_id="t-one"),
                timeout_seconds=60,
            ),
        )
        cloud = AsyncMock()
        cloud.account_id.return_value = "account"
        registry = AsyncMock()
        databases = AsyncMock()
        databases.check.side_effect = DeploymentError("CREATEDB required")
        monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
        monkeypatch.setattr(service, "AgentDeploymentRegistry", lambda *a: registry)
        monkeypatch.setattr(service, "AgentDatabaseProvisioner", lambda **kw: databases)
        with pytest.raises(DeploymentError, match="CREATEDB"):
            await service.provision(profile, agent_id="agent", owner="user")
        registry.initialize.assert_not_called()
        cloud.create.assert_not_called()
        databases.close.assert_awaited_once()

    asyncio.run(run())


def test_runtime_settings_override_source_without_losing_other_environment():
    from veadk.integrations.mpa.managed.config import Runtime

    source = template()
    source["ApmplusEnable"] = True
    options = Runtime.model_validate(
        {
            "image": "registry.example/pinned:v1",
            "role-name": "explicit-role",
            "cpu-milli": 4000,
            "memory-mb": 8192,
            "min-instance": 0,
            "max-instance": 2,
            "max-concurrency": 20,
            "apmplus-enable": False,
            "project-name": "project",
            "env": {"MODEL_AGENT_NAME": "explicit-model", "PGHOST": "explicit-db"},
        }
    )
    service.apply_runtime_settings(source, options)
    assert {
        k: source[k]
        for k in (
            "ArtifactType",
            "ArtifactUrl",
            "RoleName",
            "CpuMilli",
            "MemoryMb",
            "MinInstance",
            "MaxInstance",
            "MaxConcurrency",
            "ApmplusEnable",
            "ProjectName",
        )
    } == {
        "ArtifactType": "image",
        "ArtifactUrl": "registry.example/pinned:v1",
        "RoleName": "explicit-role",
        "CpuMilli": 4000,
        "MemoryMb": 8192,
        "MinInstance": 0,
        "MaxInstance": 2,
        "MaxConcurrency": 20,
        "ApmplusEnable": False,
        "ProjectName": "project",
    }
    env = service.env_map(source)
    assert env["MODEL_AGENT_NAME"] == "explicit-model"
    assert env["PGHOST"] == "explicit-db"
    assert env["PGUSER"] == "app"


def test_omitted_runtime_settings_preserve_source():
    import copy
    from veadk.integrations.mpa.managed.config import Runtime

    source = template()
    original = copy.deepcopy(source)
    service.apply_runtime_settings(source, Runtime())
    assert source == original


@pytest.mark.parametrize(
    "settings,source_values",
    [
        ({"min-instance": 3}, {"MaxInstance": 2}),
        ({"max-instance": 1}, {"MinInstance": 2}),
    ],
)
def test_effective_scaling_conflict_fails_before_provisioning(settings, source_values):
    from veadk.integrations.mpa.managed.config import Runtime, ConfigurationError

    with pytest.raises(ConfigurationError, match="instance"):
        service.apply_runtime_settings(source_values, Runtime.model_validate(settings))
