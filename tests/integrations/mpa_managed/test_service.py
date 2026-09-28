import asyncio
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed import service
from veadk.integrations.mpa.managed.config import (
    Managed,
    Profile,
    Runtime,
    Worker,
    with_creation_resources,
)
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_agent_deployment import (
    Registry,
    Cloud,
    Databases,
    template,
)


@pytest.mark.parametrize("source", ["reference", "template", "flat"])
@pytest.mark.parametrize("image", [None, "registry.example/mpa:pinned"])
@pytest.mark.parametrize("split_workspaces", [False, True])
@pytest.mark.parametrize("openviking", [False, True])
def test_network_gateway_worker_precede_runtime(
    monkeypatch, source, image, split_workspaces, openviking
):
    async def run():
        entry = Registry()
        cloud = Cloud(entry)
        events = []
        identity_values = {
            "user_pool_name": "studio-pool",
            "user_pool_client_name": "studio-client",
            "identity_callback_url": "https://studio.example.com/oauth/callback",
        }
        profile = Profile(
            region="cn-beijing",
            values=identity_values,
            template=template(),
            admin_url="fake",
            shared_url="postgresql://registry.example/shared",
            managed=Managed(
                version=1,
                runtime=Runtime(),
                worker=Worker(existing_id="t-one"),
                timeout_seconds=60,
            ),
        )
        profile.managed.runtime.image = image
        profile.managed.runtime.env.update(
            OPENVIKING_URL="https://old.example.test/openviking",
            OPENVIKING_RESOURCE_ID="ov-old",
            OPENVIKING_API_KEY="old-key",
            OPENVIKING_USER="old-user",
            OPENVIKING_EXTRA="old-extra",
        )
        profile.template["Envs"].extend(
            [
                {
                    "Key": "OPENVIKING_URL",
                    "Value": "https://template.example.test/openviking",
                },
                {"Key": "OPENVIKING_API_KEY", "Value": "template-key"},
                {"Key": "OPENVIKING_USER", "Value": "template-user"},
            ]
        )
        if split_workspaces:
            from veadk.integrations.mpa.managed.config import PostgresWorkspaces

            profile.managed.postgres = PostgresWorkspaces(
                admin_workspace_id="ws-admin", business_workspace_id="ws-business"
            )
            profile.admin_url = "postgresql://app:fake@pg.example/aidb"
            profile.shared_url = "postgresql://registry:fake@management/mpa_admin_db"
        if source == "reference":
            profile.managed.from_runtime = "r-source"
            cloud.runtimes["r-source"] = template()
            cloud.runtimes["r-source"]["Envs"].extend(
                [
                    {
                        "Key": "OPENVIKING_URL",
                        "Value": "https://reference.example.test/openviking",
                    },
                    {"Key": "OPENVIKING_API_KEY", "Value": "reference-key"},
                    {"Key": "OPENVIKING_USER", "Value": "reference-user"},
                ]
            )
        elif source == "flat":
            profile.template = None
            profile.values = {
                **identity_values,
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
        profile = with_creation_resources(
            profile,
            {
                "openvikingUrl": "https://selected.example.test/openviking",
                "openvikingResourceId": "ov-selected",
                "openvikingApiKey": "selected-key",
            }
            if openviking
            else {},
        )
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
            openviking_env = {
                key: value
                for key, value in service.env_map(request).items()
                if key.startswith("OPENVIKING_")
            }
            assert openviking_env == (
                {
                    "OPENVIKING_URL": "https://selected.example.test/openviking",
                    "OPENVIKING_RESOURCE_ID": "ov-selected",
                    "OPENVIKING_API_KEY": "selected-key",
                    "OPENVIKING_USER": "default",
                }
                if openviking
                else {}
            )
            assert request["ArtifactUrl"] == (image or "registry/image:v1")
            env = service.env_map(request)
            assert env["MPA_USER_POOL_NAME"] == "studio-pool"
            assert env["MPA_USER_POOL_CLIENT_NAME"] == "studio-client"
            assert env["IDENTITY_CALLBACK_URL"] == (
                "https://studio.example.com/oauth/callback"
            )
            if image:
                assert request["ArtifactType"] == "image"
            if source == "flat":
                runtime_env = service.env_map(request)
                assert runtime_env["DISABLE_JWT_AUTH"] == "false"
                assert runtime_env["ENABLE_A2A"] == "true"
                assert runtime_env["A2A_TIP_VERIFY_ENABLED"] == "false"
                assert (
                    request["AuthorizerConfiguration"]["AuthorizerType"] == "key_auth"
                )
            if split_workspaces:
                runtime_env = service.env_map(request)
                assert runtime_env["SHARED_APIG_DATABASE_URL"] == profile.shared_url
                assert runtime_env["PGDATABASE"].startswith("mpa_agent_")
            return await cloud_create(request)

        cloud.create = create
        result = await service.provision(
            profile, agent_id="mi-123456789abc", owner="user-a"
        )
        assert result["runtime_id"] == "r-agent"
        assert result["gateway_id"] == "gw-one"
        if split_workspaces:
            assert entry.row["admin_workspace_id"] == "ws-admin"
            assert entry.row["business_workspace_id"] == "ws-business"
            assert profile.managed.postgres is not None
            profile.managed.postgres.business_workspace_id = "ws-other"
            with pytest.raises(DeploymentError, match="Workspace"):
                await service.provision(
                    profile, agent_id="mi-123456789abc", owner="user-a"
                )
        with pytest.raises(DeploymentError, match="owner"):
            await service.provision(profile, agent_id="mi-123456789abc", owner="user-b")

    asyncio.run(run())


@pytest.mark.parametrize(
    "existing",
    [
        {"admin_workspace_id": "ws-other"},
        {"business_workspace_id": "ws-other"},
        {"database_host": "old-business"},
        {"database_port": 6543},
    ],
)
def test_retry_does_not_rebind_existing_database(tmp_path, monkeypatch, existing):
    from veadk.integrations.mpa.managed.config import load_profile
    from tests.integrations.mpa_managed.test_config import split_profile_file

    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    record = dict(existing)
    with pytest.raises(DeploymentError):
        service.bind_postgres_workspaces(profile, record)
    assert record == existing


def test_verified_legacy_binding_preserves_database_identity(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.config import load_profile
    from tests.integrations.mpa_managed.test_config import split_profile_file

    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    record = {
        "database_host": "business",
        "database_port": 5432,
        "database_name": "mpa_agent_existing",
    }
    service.bind_postgres_workspaces(profile, record)
    assert record["database_name"] == "mpa_agent_existing"
    assert record["business_workspace_id"] == "ws-business"
    profile.managed.postgres = None
    with pytest.raises(DeploymentError):
        service.bind_postgres_workspaces(profile, record)


def test_two_agents_use_one_business_workspace_and_one_management_registry(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.config import load_profile
    from tests.integrations.mpa_managed.test_config import split_profile_file

    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    profile.managed.from_runtime = ""
    profile.template = template()
    for item in profile.template["Envs"]:
        if item["Key"] == "PGHOST":
            item["Value"] = "business"
    profile.template["Envs"].append(
        {"Key": "TEST_REGISTRY_ADMIN", "Value": "must-not-reach-runtime"}
    )
    environments = []
    urls = []

    async def run():
        for agent_id in ("mi-one", "mi-two"):
            registry = Registry()
            cloud = Cloud(registry)
            monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)

            def registry_factory(url):
                urls.append(url)
                return registry

            def databases_factory(**kwargs):
                assert kwargs["admin_url"] == profile.admin_url
                assert kwargs["runtime_env"]["PGHOST"] == "business"
                assert "TEST_REGISTRY_ADMIN" not in kwargs["runtime_env"]
                return Databases()

            monkeypatch.setattr(service, "AgentDeploymentRegistry", registry_factory)
            monkeypatch.setattr(service, "AgentDatabaseProvisioner", databases_factory)
            gateway = AsyncMock()
            gateway.ensure.return_value = {"gateway_id": "gw-shared"}
            monkeypatch.setattr(service, "SharedAPIGService", lambda **kw: gateway)
            monkeypatch.setattr(
                service, "ensure_worker", AsyncMock(return_value="t-one")
            )
            await service.provision(profile, agent_id=agent_id, owner="user")
            environments.append(service.env_map(cloud.creates[0]))

    asyncio.run(run())
    assert urls == [profile.shared_url, profile.shared_url]
    assert {env["PGHOST"] for env in environments} == {"business"}
    assert len({env["PGDATABASE"] for env in environments}) == 2
    assert {env["SHARED_APIG_DATABASE_URL"] for env in environments} == {
        profile.shared_url
    }


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


def test_managed_identity_settings_override_template_and_require_complete_pair():
    from veadk.integrations.mpa.managed.config import ConfigurationError

    source = template()
    service.apply_identity_settings(
        source,
        {
            "user_pool_name": "studio-pool",
            "user_pool_client_name": "studio-client",
            "identity_callback_url": "https://studio.example.com/oauth/callback",
            "identity_region": "cn-shanghai",
        },
    )
    env = service.env_map(source)
    assert env["MPA_USER_POOL_NAME"] == "studio-pool"
    assert env["MPA_USER_POOL_CLIENT_NAME"] == "studio-client"
    assert env["IDENTITY_CALLBACK_URL"] == "https://studio.example.com/oauth/callback"
    assert env["IDENTITY_REGION"] == "cn-shanghai"
    assert env["IDENTITY_STARTUP_ENABLED"] == "true"

    with pytest.raises(ConfigurationError, match="MPA_USER_POOL_CLIENT_NAME"):
        service.apply_identity_settings(template(), {"user_pool_name": "studio-pool"})


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
