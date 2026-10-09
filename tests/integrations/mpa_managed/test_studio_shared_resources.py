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

"""Exercise the built-in entry point with simulated cloud/PG persistence."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.engine import make_url

from tests.integrations.mpa_managed.fakes_deployment_network import (
    NetworkCloud,
    NetworkEntry,
)
from tests.integrations.mpa_managed.test_agent_deployment import (
    Cloud,
    Databases,
    Registry,
)
from tests.integrations.mpa_managed.test_auto_pg import FakePG
from tests.integrations.mpa_managed.test_gateway import (
    Cloud as GatewayCloud,
)
from tests.integrations.mpa_managed.test_gateway import (
    Registry as GatewayRegistry,
)
from veadk.integrations.mpa.managed import pg_bootstrap, pg_cloud, service
from veadk.integrations.mpa.managed.config import load_studio_profile


@pytest.mark.asyncio
@pytest.mark.parametrize("existing", ["none", "network", "gateway", "both"])
async def test_studio_creates_missing_shared_resources_then_reuses_admin_registry(
    tmp_path, monkeypatch, existing
):
    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    profile = load_studio_profile(region="cn-beijing")
    profile.values["account_id"] = "account"
    assert profile.managed.postgres is not None
    profile.managed.postgres.bootstrap_path = str(tmp_path / "bootstrap.sqlite3")
    pg = FakePG()
    initialize = AsyncMock()
    monkeypatch.setattr(pg_cloud, "PGCloud", lambda **kw: pg)
    monkeypatch.setattr(pg_bootstrap, "initialize_admin_database", initialize)

    network = NetworkCloud(existing=existing != "none")
    network_entry = NetworkEntry()
    gateways = GatewayRegistry()
    gateway_cloud = GatewayCloud(account="account")
    scope = ("account", profile.region)
    if existing in {"network", "both"}:
        network_entry.row = {"vpc_id": "vpc-one", "subnet_ids": ["subnet-one"]}
    if existing in {"gateway", "both"}:
        gateways.rows[scope] = {"vpc_id": "vpc-one", "gateway_id": "gw-registered"}
        gateway_cloud.gateways["gw-registered"] = {
            "Id": "gw-registered",
            "Name": "previous-gateway",
            "Region": profile.region,
            "Type": "standard",
            "Status": "Running",
            "NetworkSpec": {"VpcId": "vpc-one"},
        }
        gateway_cloud.im = True
    network_entry.gateway = AsyncMock(side_effect=lambda: gateways.rows.get(scope, {}))
    monkeypatch.setattr(service, "GatewayCloud", lambda _: gateway_cloud)
    monkeypatch.setattr(service, "ensure_worker", AsyncMock(return_value="t-worker"))
    initialize_identity = AsyncMock(
        side_effect=lambda _profile, _cloud, agent_id: SimpleNamespace(
            workload_pool_name="agentkit-studio-workload",
            workload_identity_name=f"{agent_id}-studio",
        )
    )
    monkeypatch.setattr(service, "ensure_workload_identity", initialize_identity)

    registry_urls = []
    runtime_networks = []
    expected_vpc = "vpc-auto" if existing == "none" else "vpc-one"
    expected_subnet = "subnet-auto" if existing == "none" else "subnet-one"
    for agent_id in ("mi-000000000001", "mi-000000000002"):
        entry = Registry()
        entry.network = network_entry
        entry.shared = gateways
        cloud = Cloud(entry)
        cloud.network = network
        monkeypatch.setattr(cloud, "_credentials", lambda: None, raising=False)
        monkeypatch.setattr(service, "RuntimeCloud", lambda cloud=cloud, **kw: cloud)

        def registry_factory(url, entry=entry):
            registry_urls.append(url)
            return entry

        def database_factory(**kwargs):
            assert make_url(kwargs["admin_url"]).host == "ws-2.example"
            assert kwargs["runtime_env"]["PGHOST"] == "ws-2.example"
            return Databases()

        monkeypatch.setattr(service, "AgentDeploymentRegistry", registry_factory)
        monkeypatch.setattr(service, "AgentDatabaseProvisioner", database_factory)
        result = await service.provision(profile, agent_id=agent_id, owner="user")
        initialize_identity.assert_awaited_with(profile, cloud, agent_id)
        assert result["gateway_id"] == gateways.rows[scope]["gateway_id"]
        assert entry.row["admin_workspace_id"] == "ws-1"
        assert entry.row["business_workspace_id"] == "ws-2"
        runtime_networks.append(cloud.creates[0]["NetworkConfiguration"])
        runtime_env = service.env_map(cloud.creates[0])
        assert runtime_env["MPA_WORKLOAD_POOL_NAME"] == "agentkit-studio-workload"
        assert runtime_env["MPA_WORKLOAD_IDENTITY_NAME"] == f"{agent_id}-studio"
        runtime_registry = make_url(runtime_env["SHARED_APIG_DATABASE_URL"])
        assert runtime_registry.set(query={}) == make_url(registry_urls[-1]).set(
            query={}
        )
        assert runtime_registry.query == {"ssl": "require"}

    assert pg.created == 2
    assert initialize_identity.await_count == 2
    assert initialize.await_count == 2
    assert len(set(registry_urls)) == 1
    assert make_url(registry_urls[0]).host == "ws-1.example"
    assert make_url(registry_urls[0]).database == "mpa_admin_db"
    assert network_entry.row["vpc_id"] == expected_vpc
    assert network_entry.row["subnet_ids"] == [expected_subnet]
    assert gateways.rows[scope]["vpc_id"] == expected_vpc
    assert gateways.rows[scope]["im_gateway_service_id"] == "service-1"
    assert gateways.rows[scope]["state"] == "ready"
    assert runtime_networks[0] == runtime_networks[1]
    assert runtime_networks[0]["VpcConfiguration"]["VpcId"] == expected_vpc
    assert [kind for kind, _ in network.calls] == (
        ["vpc", "subnet"] if existing == "none" else []
    )
    assert (
        gateway_cloud.created
        == gateway_cloud.im_created
        == (0 if existing in {"gateway", "both"} else 1)
    )
