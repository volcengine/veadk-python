import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed import service
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_agent_deployment import (
    Registry,
    Cloud,
    Databases,
    template,
)


def test_network_gateway_worker_precede_runtime(monkeypatch):
    async def run():
        entry = Registry()
        cloud = Cloud(entry)
        events = []
        profile = SimpleNamespace(
            region="cn-beijing",
            values={},
            template=template(),
            admin_url="fake",
            shared_url="shared",
            managed=SimpleNamespace(
                from_runtime="",
                credential_file="",
                timeout_seconds=60,
                network=SimpleNamespace(
                    vpc_cidr="172.20.0.0/16",
                    subnet_prefix=24,
                    zone="",
                    vpc_id="",
                    subnet_ids=[],
                ),
                apig=SimpleNamespace(adopt_id=""),
                worker=object(),
            ),
        )
        monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
        monkeypatch.setattr(service, "AgentDeploymentRegistry", lambda url: entry)
        databases = Databases()
        databases.check = AsyncMock()
        databases.close = AsyncMock()
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
        entry.shared = object()
        cloud_create = cloud.create

        async def create(request):
            assert events == ["gateway", "worker"]
            assert request["ToolId"] == "t-one"
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
        profile = SimpleNamespace(
            region="cn-beijing",
            values={},
            template=template(),
            admin_url="fake",
            shared_url="shared",
            managed=SimpleNamespace(
                from_runtime="",
                credential_file="",
                timeout_seconds=60,
                network=SimpleNamespace(
                    vpc_cidr="172.20.0.0/16",
                    subnet_prefix=24,
                    zone="",
                    vpc_id="",
                    subnet_ids=[],
                ),
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
