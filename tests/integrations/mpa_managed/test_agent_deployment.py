"""Deployment lifecycle without external resources."""

import asyncio
import copy
import re
from contextlib import asynccontextmanager

import pytest
from cryptography.fernet import Fernet

from veadk.integrations.mpa.managed.database import (
    DeploymentError,
    agent_suffix,
    database_name,
)
from veadk.integrations.mpa.managed.runtime import AgentRuntimeDeployer, env_map
from tests.integrations.mpa_managed.fakes_deployment_network import (
    NetworkCloud,
    NetworkEntry,
)


def test_names_are_stable_scoped_and_postgres_safe():
    name = database_name("1000000000", "cn-beijing", "my-agent")
    assert name == database_name("1000000000", "cn-beijing", "my-agent")
    assert len(name) < 63 and name.startswith("mpa_agent_")
    assert all(c in "abcdefghijklmnopqrstuvwxyz0123456789_" for c in name)
    assert (
        len(
            {
                database_name(a, r, i)
                for a, r, i in [
                    ("a", "r", "i"),
                    ("a2", "r", "i"),
                    ("a", "r2", "i"),
                    ("a", "r", "i2"),
                ]
            }
        )
        == 4
    )
    with pytest.raises(DeploymentError):
        agent_suffix("account", "region", "")


class Registry:
    def __init__(self):
        self.row = {}
        self.mutex = asyncio.Lock()
        self.network = NetworkEntry()

    def network_entry(self):
        return self.network

    async def initialize(self):
        pass

    @asynccontextmanager
    async def lock(self, *args):
        async with self.mutex:
            yield self

    async def read(self):
        return copy.deepcopy(self.row)

    async def save(self, row):
        self.row = copy.deepcopy(row)

    async def close(self):
        pass


class Databases:
    def __init__(self):
        self.key = ""
        self.seeded = []

    async def ensure(self, entry, *, account, region, agent_id):
        row = await entry.read()
        row.setdefault("client_token", "persistent-token")
        await entry.save(row)
        return database_name(account, region, agent_id)

    async def encryption_key(self, name, *, existing_key=""):
        assert not existing_key or existing_key == self.key
        return self.key

    async def seed_runtime(self, name, agent_id, runtime_id):
        self.seeded.append((name, agent_id, runtime_id))


class Cloud:
    def __init__(self, registry):
        self.registry = registry
        self.runtimes = {}
        self.creates = []
        self.updates = []
        self.lose_create_response = False
        self.spaces = {}
        self.space_creates = []
        self.lose_space_response = False
        self.hide_spaces = False
        self.network = NetworkCloud(existing=True)

    async def create_skill_space(self, request):
        from agentkit.sdk.skills.types import CreateSkillSpaceRequest

        CreateSkillSpaceRequest.model_validate(request)
        # Enforce the live API constraint, which the generated SDK omits.
        assert re.fullmatch(r"[a-z0-9_]+", request["Name"])
        self.space_creates.append(copy.deepcopy(request))
        space_id = "space-" + str(len(self.space_creates))
        self.spaces[space_id] = {
            **copy.deepcopy(request),
            "Id": space_id,
            "Status": "Ready",
        }
        if self.lose_space_response:
            self.lose_space_response = False
            raise TimeoutError("space response lost")
        return space_id

    async def get_skill_space(self, space_id):
        return copy.deepcopy(self.spaces.get(space_id, {}))

    async def find_skill_spaces(self, name, project_name):
        if self.hide_spaces:
            return []
        return copy.deepcopy([s for s in self.spaces.values() if s["Name"] == name])

    async def account_id(self):
        return "account"

    async def create(self, request):
        self.creates.append(copy.deepcopy(request))
        self.runtimes.setdefault(
            "r-agent",
            {
                **request,
                "RuntimeId": "r-agent",
                "Status": "Ready",
                "NetworkConfigurations": [
                    {
                        "NetworkType": "private",
                        "Endpoint": "https://private.example",
                        "VpcConfiguration": request["NetworkConfiguration"][
                            "VpcConfiguration"
                        ],
                    },
                    {"NetworkType": "public", "Endpoint": "https://public.example"},
                ],
                "AuthorizerConfiguration": {
                    "KeyAuth": {"ApiKey": "Bearer runtime-key"}
                },
            },
        )
        if self.lose_create_response:
            self.lose_create_response = False
            raise TimeoutError("response lost")
        return "r-agent"

    async def get(self, runtime_id):
        return copy.deepcopy(self.runtimes[runtime_id])

    async def update(self, request):
        self.updates.append(request)
        self.runtimes[request["RuntimeId"]].update(request)

    async def is_ready(self, runtime):
        assert not self.registry.mutex.locked(), (
            "APIG startup must be able to acquire account lock"
        )
        return True


def template():
    return {
        "ArtifactType": "Image",
        "ArtifactUrl": "registry/image:v1",
        "RoleName": "runtime-role",
        "NetworkConfiguration": {
            "EnablePublicNetwork": True,
            "EnablePrivateNetwork": True,
            "VpcConfiguration": {"VpcId": "vpc-one", "SubnetIds": ["subnet-one"]},
        },
        "Envs": [
            {"Key": k, "Value": v}
            for k, v in {
                "MPA_AGENT_ID": "agent-one",
                "PGHOST": "pg.example",
                "PGUSER": "app",
                "PGPASSWORD": "password",
                "DEPLOYMENT_DATABASE_ADMIN_URL": "must-not-reach-runtime",
            }.items()
        ],
    }


def deployer():
    registry = Registry()
    cloud = Cloud(registry)
    databases = Databases()
    svc = AgentRuntimeDeployer(
        registry=registry,
        databases=databases,
        cloud=cloud,
        region="cn-beijing",
        shared_database_url="postgresql://registry",
        timeout=1,
        interval=0,
    )
    return svc, registry, cloud, databases


@pytest.mark.parametrize("legacy", [False, True])
def test_create_and_repeat_deployment_preserve_only_legacy_channel_key(legacy):
    async def run():
        svc, registry, cloud, databases = deployer()
        if legacy:
            databases.key = Fernet.generate_key().decode()
        first = await svc.deploy(template())
        cloud.runtimes["r-agent"]["Tags"].append(
            {"Key": "sys:tag:createdBy", "Value": "cloud-owner"}
        )
        second = await svc.deploy(template())
        assert first == second
        assert len(cloud.creates) == 1 and len(cloud.updates) == 1
        assert registry.row["state"] == "ready" and not registry.row["pending"]
        env = env_map(cloud.runtimes["r-agent"])
        assert env["PGDATABASE"] == database_name("account", "cn-beijing", "agent-one")
        assert env["AGENTKIT_RUNTIME_ID"] == "r-agent"
        assert (
            env["SKILL_SPACE_ID"]
            == first["skill_space_id"]
            == registry.row["skill_space_id"]
        )
        assert env.get("CHANNEL_STATE_ENCRYPTION_KEY", "") == databases.key
        assert ("CHANNEL_STATE_ENCRYPTION_KEY" in env) is legacy
        assert "DEPLOYMENT_DATABASE_ADMIN_URL" not in env
        assert "password" not in str(first)
        assert not databases.key or databases.key not in str(registry.row)
        changed = template()
        changed["ArtifactUrl"] = "registry/image:v2"
        await svc.deploy(changed)
        assert len(cloud.creates) == 1 and len(cloud.updates) == 2
        assert len(cloud.space_creates) == 1
        assert (
            env_map(cloud.runtimes["r-agent"]).get("CHANNEL_STATE_ENCRYPTION_KEY", "")
            == databases.key
        )

    asyncio.run(run())


def test_lost_create_response_reuses_client_token_and_rejects_changed_retry():
    async def run():
        svc, registry, cloud, _ = deployer()
        cloud.lose_create_response = True
        with pytest.raises(TimeoutError):
            await svc.deploy(template())
        changed = template()
        changed["ArtifactUrl"] = "different:image"
        with pytest.raises(DeploymentError, match="unfinished"):
            await svc.deploy(changed)
        await svc.deploy(template())
        assert len(cloud.runtimes) == 1
        assert cloud.creates[0]["ClientToken"] == cloud.creates[1]["ClientToken"]

    asyncio.run(run())


def test_runtime_or_network_identity_conflicts_never_create_replacement():
    async def run():
        svc, registry, cloud, _ = deployer()
        await svc.deploy(template())
        with pytest.raises(DeploymentError, match="another Runtime"):
            await svc.deploy(template(), runtime_id="r-other")
        changed = template()
        changed["NetworkConfiguration"]["VpcConfiguration"]["VpcId"] = "other-vpc"
        with pytest.raises(DeploymentError, match="VPC"):
            await svc.deploy(changed)
        assert len(cloud.creates) == 1

    asyncio.run(run())


def test_reference_template_does_not_copy_agent_or_bot_credentials():
    from veadk.integrations.mpa.managed.runtime import template_from_runtime

    reference = {
        **template(),
        "RuntimeId": "r-reference",
        "NetworkConfigurations": [
            {"NetworkType": "public", "Endpoint": "https://public"},
            {
                "NetworkType": "private",
                "VpcConfiguration": {"VpcId": "vpc-one", "SubnetIds": ["subnet-one"]},
            },
        ],
    }
    reference["Envs"] += [
        {"Key": k, "Value": "reference-secret"}
        for k in [
            "CHANNEL_STATE_ENCRYPTION_KEY",
            "FEISHU_APP_ID",
            "FEISHU_APP_SECRET",
            "AGENTKIT_RUNTIME_ID",
            "A2A_PUBLIC_URL",
            "SKILL_SPACE_ID",
        ]
    ]
    result = template_from_runtime(reference, "another-agent")
    assert env_map(result)["MPA_AGENT_ID"] == "another-agent"
    assert "reference-secret" not in str(result)
    assert result["NetworkConfiguration"]["EnablePrivateNetwork"]


def test_lost_skill_space_response_recovers_without_duplicate_or_blind_retry():
    async def run():
        svc, registry, cloud, _ = deployer()
        cloud.lose_space_response = True
        with pytest.raises(TimeoutError):
            await svc.deploy(template())
        assert not cloud.creates and registry.row["skill_space_create_requested"]
        changed = template()
        changed["ProjectName"] = "another-project"
        with pytest.raises(DeploymentError, match="different inputs"):
            await svc.deploy(changed)
        cloud.hide_spaces = True
        with pytest.raises(DeploymentError, match="outcome is unknown"):
            await svc.deploy(template())
        assert len(cloud.space_creates) == 1
        cloud.hide_spaces = False
        result = await svc.deploy(template())
        assert result["skill_space_id"] == "space-1"
        assert len(cloud.space_creates) == 1

    asyncio.run(run())


def test_missing_registered_skill_space_does_not_create_empty_replacement():
    async def run():
        svc, registry, cloud, _ = deployer()
        await svc.deploy(template())
        cloud.spaces.clear()
        with pytest.raises(DeploymentError, match="missing"):
            await svc.deploy(template())
        assert len(cloud.space_creates) == 1 and len(cloud.updates) == 1

    asyncio.run(run())


def test_existing_runtime_space_is_adopted_and_never_overridden_by_template():
    async def run():
        svc, registry, cloud, _ = deployer()
        # Simulate a Runtime deployed before the deployment registry knew spaces.
        await svc.deploy(template())
        registry.row = {
            k: v for k, v in registry.row.items() if not k.startswith("skill_space_")
        }
        result = await svc.deploy(template())
        assert result["skill_space_id"] == "space-1"
        assert not registry.row["skill_space_managed"]
        changed = template()
        changed["Envs"].append(
            {"Key": "SKILL_SPACE_ID", "Value": "someone-elses-space"}
        )
        with pytest.raises(DeploymentError, match="differ"):
            await svc.deploy(changed)
        assert len(cloud.space_creates) == 1 and len(cloud.updates) == 1

    asyncio.run(run())


def test_explicit_shared_space_reused_without_taking_ownership():
    async def run():
        svc, registry, cloud, _ = deployer()
        cloud.spaces["shared-space"] = {
            "Id": "shared-space",
            "Name": "Shared",
            "Status": "Ready",
        }
        supplied = template()
        supplied["Envs"].append({"Key": "SKILL_SPACE_ID", "Value": "shared-space"})
        result = await svc.deploy(supplied)
        assert result["skill_space_id"] == "shared-space"
        assert not cloud.space_creates and not registry.row["skill_space_managed"]

    asyncio.run(run())


def test_space_recovery_rejects_name_collision_or_wrong_owner():
    async def run():
        svc, registry, cloud, _ = deployer()
        name = "mpa_skills_" + agent_suffix("account", "cn-beijing", "agent-one")
        cloud.spaces["foreign"] = {"Id": "foreign", "Name": name}
        with pytest.raises(DeploymentError, match="name already exists"):
            await svc.deploy(template())
        assert not cloud.space_creates and not cloud.creates
        cloud.spaces.clear()
        cloud.lose_space_response = True
        with pytest.raises(TimeoutError):
            await svc.deploy(template())
        cloud.spaces["space-1"]["Tags"] = []
        with pytest.raises(DeploymentError, match="ownership"):
            await svc.deploy(template())
        assert len(cloud.space_creates) == 1 and not cloud.creates

    asyncio.run(run())


def test_agent_spaces_are_independent():
    from veadk.integrations.mpa.managed.skills import ensure_skill_space

    async def run():
        svc, registry, cloud, _ = deployer()
        await svc.deploy(template())
        other = Registry()
        async with other.lock() as entry:
            second_id = await ensure_skill_space(
                entry,
                cloud,
                account="account",
                region="cn-beijing",
                agent_id="agent-two",
            )
        assert second_id != registry.row["skill_space_id"]
        assert cloud.space_creates[0]["Name"] != cloud.space_creates[1]["Name"]

    asyncio.run(run())


def test_skill_space_discovery_paginates_and_requires_exact_name(monkeypatch):
    from veadk.integrations.mpa.managed.runtime import RuntimeCloud
    from agentkit.sdk.skills.types import ListSkillSpacesRequest

    async def run():
        cloud = RuntimeCloud(region="cn-beijing", credential_file="unused")
        pages = []

        async def call(method, request, *, skills=False):
            assert method == "list_skill_spaces" and skills
            assert isinstance(request, ListSkillSpacesRequest)
            data = request.model_dump(by_alias=True)
            assert data["ProjectName"] == "my-project" and data["Filter"] is None
            pages.append(data["PageNumber"])
            if data["PageNumber"] == 1:
                return {
                    "TotalCount": 101,
                    "Items": [
                        {"Id": str(i), "Name": "wanted-prefix"} for i in range(100)
                    ],
                }
            return {"TotalCount": 101, "Items": [{"Id": "exact", "Name": "wanted"}]}

        monkeypatch.setattr(cloud, "call", call)
        assert await cloud.find_skill_spaces("wanted", "my-project") == [
            {"Id": "exact", "Name": "wanted"}
        ]
        assert pages == [1, 2]

    asyncio.run(run())


def test_fresh_runtime_without_network_bootstraps_and_updates_idempotently():
    async def run():
        svc, registry, cloud, _ = deployer()
        cloud.network = NetworkCloud()
        payload = template()
        payload.pop("NetworkConfiguration")
        payload["ApmplusEnable"] = True
        payload["Envs"] += [
            {"Key": "MPA_META_STARTUP_ENABLED", "Value": "false"},
            {"Key": "OTEL_SERVICE_NAME", "Value": "old-runtime.old-name"},
        ]
        original = copy.deepcopy(payload)
        first = await svc.deploy(payload)
        second = await svc.deploy(payload)
        assert first == second
        assert payload == original
        assert len(cloud.network.calls) == 2
        assert len(cloud.creates) == 1 and len(cloud.updates) == 1
        assert first["network"]["VpcConfiguration"]["VpcId"] == "vpc-auto"
        env = env_map(cloud.runtimes[first["runtime_id"]])
        assert env["MPA_META_STARTUP_ENABLED"] == "true"
        assert env["IM_GATEWAY_STARTUP_ENABLED"] == "true"
        assert env["OTEL_SERVICE_NAME"] == "r-agent." + first["runtime_name"]
        assert registry.network.row["state"] == "ready"

    asyncio.run(run())


def test_reference_without_private_network_uses_account_bootstrap():
    from veadk.integrations.mpa.managed.runtime import template_from_runtime

    result = template_from_runtime(
        {**template(), "NetworkConfigurations": [{"NetworkType": "public"}]},
        "new-agent",
    )
    assert "NetworkConfiguration" not in result


def test_concurrent_agents_share_one_network_and_have_distinct_runtimes():
    class MultiRegistry(Registry):
        def __init__(self):
            super().__init__()
            self.agents = {}

        @asynccontextmanager
        async def lock(self, account, region, agent_id):
            async with self.mutex:
                entry = self.agents.setdefault(agent_id, Registry())
                entry.network = self.network
                yield entry

    class MultiCloud(Cloud):
        async def create(self, request):
            rid = "r-" + env_map(request)["MPA_AGENT_ID"]
            self.creates.append(copy.deepcopy(request))
            self.runtimes[rid] = {
                **copy.deepcopy(request),
                "RuntimeId": rid,
                "Status": "Ready",
                "NetworkConfigurations": [
                    {
                        "NetworkType": "private",
                        "Endpoint": "https://private.example",
                        "VpcConfiguration": request["NetworkConfiguration"][
                            "VpcConfiguration"
                        ],
                    },
                    {"NetworkType": "public", "Endpoint": "https://public.example"},
                ],
                "AuthorizerConfiguration": {"KeyAuth": {"ApiKey": "runtime-key"}},
            }
            return rid

    async def run():
        registry = MultiRegistry()
        cloud = MultiCloud(registry)
        cloud.network = NetworkCloud()
        svc = AgentRuntimeDeployer(
            registry=registry,
            databases=Databases(),
            cloud=cloud,
            region="cn-beijing",
            shared_database_url="postgresql://registry",
            timeout=1,
            interval=0,
        )
        one = template()
        one.pop("NetworkConfiguration")
        two = copy.deepcopy(one)
        two["Envs"] = [
            {
                "Key": e["Key"],
                "Value": "agent-two" if e["Key"] == "MPA_AGENT_ID" else e["Value"],
            }
            for e in two["Envs"]
        ]
        results = await asyncio.gather(svc.deploy(one), svc.deploy(two))
        assert len({r["runtime_id"] for r in results}) == 2
        assert len({r["database_name"] for r in results}) == 2
        assert results[0]["network"] == results[1]["network"]
        assert [c[0] for c in cloud.network.calls] == ["vpc", "subnet"]

    asyncio.run(run())


def test_network_conflict_stops_deployment_before_database_or_runtime_creation():
    from unittest.mock import AsyncMock

    async def run():
        svc, registry, cloud, databases = deployer()
        registry.network.gateway_row = {"vpc_id": "vpc-other"}
        databases.ensure = AsyncMock()
        with pytest.raises(DeploymentError, match="shared APIG"):
            await svc.deploy(template())
        databases.ensure.assert_not_awaited()
        assert not cloud.creates and not cloud.space_creates and not cloud.network.calls

    asyncio.run(run())


def test_new_runtime_name_is_agent_id_even_with_named_template():
    async def run():
        svc, _, cloud, _ = deployer()
        source = template()
        source["Name"] = "reference-name"
        result = await svc.deploy(source)
        assert cloud.creates[0]["Name"] == "agent-one"
        assert result["runtime_name"] == "agent-one"

    asyncio.run(run())


def test_existing_legacy_runtime_retains_name_and_resources():
    async def run():
        svc, registry, cloud, _ = deployer()
        first = await svc.deploy(template())
        legacy = "mpa-agent-" + agent_suffix("account", "cn-beijing", "agent-one")
        cloud.runtimes["r-agent"]["Name"] = legacy
        second = await svc.deploy(template())
        assert second["runtime_name"] == legacy
        assert first["runtime_id"] == second["runtime_id"]
        assert first["skill_space_id"] == second["skill_space_id"]
        assert len(cloud.creates) == 1
        assert not registry.row["pending"]

    asyncio.run(run())


def test_legacy_lost_response_resumes_exact_payload_and_rejects_changed_inputs():
    import hashlib
    import json

    async def run():
        svc, registry, cloud, _ = deployer()
        cloud.lose_create_response = True
        with pytest.raises(TimeoutError):
            await svc.deploy(template())
        original = cloud.creates[0]
        original["Name"] = "mpa-agent-" + agent_suffix(
            "account", "cn-beijing", "agent-one"
        )
        cloud.runtimes["r-agent"]["Name"] = original["Name"]
        desired = {k: v for k, v in original.items() if k != "ClientToken"}
        registry.row["request_hash"] = hashlib.sha256(
            json.dumps(desired, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        changed = template()
        changed["ArtifactUrl"] = "registry/image:v2"
        with pytest.raises(DeploymentError, match="unfinished"):
            await svc.deploy(changed)
        result = await svc.deploy(template())
        assert cloud.creates == [original, original]
        assert result["runtime_name"] == original["Name"]
        assert len(cloud.runtimes) == 1
        assert not registry.row["pending"]

    asyncio.run(run())
