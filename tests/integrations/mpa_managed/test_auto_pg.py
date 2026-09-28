"""Offline contracts for STS-backed shared PG bootstrap."""

import asyncio
import copy
from unittest.mock import AsyncMock

import pytest
import yaml

from tests.integrations.mpa_managed.test_config import profile_file
from veadk.integrations.mpa.managed.config import (
    load_profile,
    with_creation_resources,
    ConfigurationError,
)


def auto_profile(tmp_path, monkeypatch):
    path = profile_file(
        tmp_path,
        monkeypatch,
        postgres={
            "mode": "auto",
            "bootstrap-path": str(tmp_path / "bootstrap.sqlite3"),
        },
    )
    monkeypatch.delenv("TEST_MPA_ADMIN")
    monkeypatch.delenv("TEST_MPA_REGISTRY")
    return path


def test_auto_config_needs_no_pg_secrets_and_rejects_pg_inputs(tmp_path, monkeypatch):
    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    assert profile.summary()["postgresMode"] == "auto"
    assert profile.summary()["pgHost"] == ""
    assert profile.admin_url == profile.shared_url == ""
    with pytest.raises(ConfigurationError):
        with_creation_resources(
            profile, {"pgHost": "database.example", "pgPort": "5432"}
        )


def test_auto_flat_config_ignores_legacy_pg_placeholders(tmp_path, monkeypatch):
    path = auto_profile(tmp_path, monkeypatch)
    data = yaml.safe_load(path.read_text())
    data["managed"].pop("from-runtime")
    data.update(
        image="registry.example/mpa:v1",
        **{
            "pg-password": "${NO_SUCH_SECRET}",
            "model-provider": "openai",
            "model-api-base": "https://model.example",
            "model-api-key": "fake",
            "model-name": "model",
        },
    )
    path.write_text(yaml.safe_dump(data))
    assert load_profile(path).summary()["configured"] is True


def workspace(name, ident):
    return dict(
        workspace_id=ident,
        workspace_name=name,
        account_id="account",
        region_id="cn-beijing",
        project_name="default",
        engine_version="PostgreSQL_17",
        workspace_status="Running",
        workspace_tags=[],
    )


class FakePG:
    def __init__(self):
        self.rows = {}
        self.created = 0
        self.fail = False

    async def find(self, project, name):
        return [
            copy.deepcopy(r) for r in self.rows.values() if r["workspace_name"] == name
        ]

    async def detail(self, ident):
        return copy.deepcopy(self.rows[ident])

    async def create(self, name, project, tags):
        self.created += 1
        if self.fail:
            raise TimeoutError()
        ident = "ws-" + str(self.created)
        self.rows[ident] = workspace(name, ident)
        self.rows[ident]["workspace_tags"] = [
            {"key": k, "value": v} for k, v in tags.items()
        ]
        return ident

    async def connection(self, ident):
        return f"postgresql://user_admin:fake@{ident}.example:5432/aidb?sslmode=require"


@pytest.mark.asyncio
async def test_auto_waits_for_new_workspace_metadata_to_be_visible(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres

    class DelayedMetadataPG(FakePG):
        def __init__(self):
            super().__init__()
            self.reads = {}

        async def detail(self, ident):
            self.reads[ident] = self.reads.get(ident, 0) + 1
            row = await super().detail(ident)
            if self.reads[ident] == 1:
                row["workspace_tags"] = []
            return row

    cloud = DelayedMetadataPG()
    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    init = AsyncMock()
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database", init
    )
    original_sleep = asyncio.sleep

    async def instant_sleep(_):
        await original_sleep(0)

    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.asyncio.sleep", instant_sleep
    )
    resolved = await prepare_postgres(profile, cloud, "account")
    assert resolved.managed.postgres.business_workspace_id == "ws-2"
    assert cloud.reads == {"ws-1": 2, "ws-2": 2}
    assert init.await_count == 1


@pytest.mark.asyncio
async def test_auto_waits_for_new_workspace_detail_then_rejects_wrong_owner(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.database import DeploymentError
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.pg_cloud import PGCloudError

    class DelayedDetailPG(FakePG):
        def __init__(self):
            super().__init__()
            self.reads = {}
            self.wrong_owner = False

        async def detail(self, ident):
            self.reads[ident] = self.reads.get(ident, 0) + 1
            if self.reads[ident] == 1:
                raise PGCloudError("DescribeWorkspaceDetail", "ResourceNotFound")
            row = await super().detail(ident)
            if self.wrong_owner:
                row["workspace_tags"][0]["value"] = "another-scope"
            return row

    cloud = DelayedDetailPG()
    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    original_sleep = asyncio.sleep

    async def instant_sleep(_):
        await original_sleep(0)

    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.asyncio.sleep", instant_sleep
    )
    await prepare_postgres(profile, cloud, "account")
    assert cloud.reads == {"ws-1": 2, "ws-2": 2}

    cloud.wrong_owner = True
    with pytest.raises(DeploymentError, match="ownership tags differ"):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2


@pytest.mark.asyncio
async def test_auto_reuses_two_workspaces_and_keeps_secrets_off_disk(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    init = AsyncMock()
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database", init
    )
    first, second = await asyncio.gather(
        *[prepare_postgres(profile, cloud, "account") for _ in range(2)]
    )
    assert cloud.created == 2
    assert first.admin_url == second.admin_url
    assert first.managed.postgres.admin_workspace_id == "ws-1"
    assert first.managed.postgres.business_workspace_id == "ws-2"
    assert first.shared_url.endswith("/mpa_admin_db?sslmode=require")
    assert first.managed.runtime.env["PGHOST"] == "ws-2.example"
    assert b"fake" not in (tmp_path / "bootstrap.sqlite3").read_bytes()
    assert (tmp_path / "bootstrap.sqlite3").stat().st_mode & 0o777 == 0o600
    assert init.await_count == 2


@pytest.mark.asyncio
async def test_uncertain_create_does_not_create_again(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    cloud.fail = True
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account")
    cloud.fail = False
    with pytest.raises(DeploymentError, match="uncertain"):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 1


@pytest.mark.asyncio
async def test_legacy_registry_prevents_empty_cutover(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError
    from dataclasses import replace

    profile = replace(
        load_profile(auto_profile(tmp_path, monkeypatch)),
        shared_url="postgresql://u:p@old.example/registry",
    )
    cloud = FakePG()
    with pytest.raises(DeploymentError, match="migrat"):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 0


def test_connection_parameters_preserve_special_passwords():
    from veadk.integrations.mpa.managed.pg_cloud import parse_connection
    from sqlalchemy.engine import make_url

    result = parse_connection(
        {
            "connection_examples": [
                {
                    "connection_type": "Parameters",
                    "connection_example": "PGHOST='ws.example'\nPGPORT=5432\nPGDATABASE=aidb\nPGUSER=user_admin\nPGPASSWORD='a#b:@=x'\nPGSSLMODE=require",
                }
            ]
        }
    )
    assert make_url(result).password == "a#b:@=x"
    assert make_url(result).query["sslmode"] == "require"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field,value",
    [
        ("account_id", "other"),
        ("region_id", "cn-shanghai"),
        ("project_name", "other"),
        ("engine_version", "PostgreSQL_16"),
    ],
)
async def test_discovery_rejects_foreign_workspace(tmp_path, monkeypatch, field, value):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    cloud.rows["existing"] = workspace("mpa_admin_workspace", "existing")
    cloud.rows["existing"][field] = value
    with pytest.raises(DeploymentError, match="scope or engine"):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 0


@pytest.mark.asyncio
async def test_cancellation_recovers_recorded_workspace_without_recreating(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    original = cloud.connection
    entered = asyncio.Event()

    async def hanging(ident):
        entered.set()
        await asyncio.Future()

    monkeypatch.setattr(cloud, "connection", hanging)
    task = asyncio.create_task(prepare_postgres(profile, cloud, "account"))
    await asyncio.wait_for(entered.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cloud.created == 1
    cloud.connection = original
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2
    del cloud.rows["ws-1"]
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2


@pytest.mark.asyncio
async def test_lost_create_response_discovers_tagged_workspace(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    create = cloud.create

    async def lost(*args):
        await create(*args)
        raise TimeoutError()

    monkeypatch.setattr(cloud, "create", lost)
    with pytest.raises(DeploymentError, match="uncertain"):
        await prepare_postgres(profile, cloud, "account")
    cloud.create = create
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2


@pytest.mark.asyncio
async def test_explicit_adoption_and_migration_preserve_business_target(
    tmp_path, monkeypatch
):
    from dataclasses import replace
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    settings = profile.managed.postgres
    assert settings is not None
    settings.admin_workspace_id, settings.business_workspace_id = (
        "existing-admin",
        "existing-business",
    )
    cloud = FakePG()
    cloud.rows = {
        ident: workspace(name, ident)
        for name, ident in [
            ("mpa_admin_workspace", "existing-admin"),
            ("mpa_business_workspace", "existing-business"),
        ]
    }
    init = AsyncMock()
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database", init
    )
    profile = replace(
        profile,
        admin_url="postgresql://user:fake@existing-business.example/aidb",
        shared_url="postgresql://user:fake@existing-business.example/registry",
    )
    resolved = await prepare_postgres(
        profile, cloud, "account", source_url=profile.shared_url
    )
    assert init.call_args.kwargs["source_url"] == profile.shared_url
    assert "existing-business.example" in resolved.admin_url
    assert cloud.created == 0
    settings.business_workspace_id = "different"
    with pytest.raises(DeploymentError, match="recorded bootstrap"):
        await prepare_postgres(profile, cloud, "account", source_url=profile.shared_url)


@pytest.mark.asyncio
async def test_sdk_uses_refreshed_sts_and_disables_create_retry(monkeypatch):
    from types import SimpleNamespace
    from veadk.integrations.mpa.managed.pg_cloud import PGCloud
    import volcenginesdkaidap as sdk

    tokens = []
    requests = []

    def credentials():
        token = f"temporary-{len(tokens)}"
        tokens.append(token)
        return SimpleNamespace(
            access_key_id="fake-ak", secret_access_key="fake-sk", session_token=token
        )

    class Client:
        def __init__(self, client):
            assert client.configuration.auto_retry is False
            assert client.configuration.session_token == tokens[-1]
            assert client.configuration.region == "cn-beijing"

        def create_workspace(self, request, **kw):
            assert kw["_request_timeout"] == 30
            requests.append(request.to_dict())
            return sdk.CreateWorkspaceResponse(workspace_id="ws-created")

    monkeypatch.setattr(sdk, "AIDAPApi", Client)
    cloud = PGCloud(region="cn-beijing", credentials=credentials)
    for _ in range(2):
        assert (
            await cloud.create(
                "mpa_admin_workspace", "default", {"veadk-pg-purpose": "admin"}
            )
            == "ws-created"
        )
    assert len(set(tokens)) == 2
    assert requests[0]["engine_version"] == "PostgreSQL_17"
    assert requests[0]["workspace_tags"] == [
        {"key": "veadk-pg-purpose", "value": "admin"}
    ]


@pytest.mark.asyncio
async def test_sdk_connection_and_pagination_contract(monkeypatch):
    from veadk.integrations.mpa.managed.pg_cloud import PGCloud

    cloud = PGCloud(region="cn-beijing", credentials=lambda: None)
    results = {
        "describe_branches": {
            "branches": [
                {
                    "branch_id": "branch",
                    "branch_name": "main",
                    "branch_status": "Running",
                }
            ]
        },
        "describe_computes": {
            "computes": [{"compute_id": "compute", "compute_status": "Running"}]
        },
        "describe_workspace_endpoint": {
            "endpoints": [
                {"addresses": [{"address_type": "Public", "address_id": "address"}]}
            ]
        },
        "describe_db_accounts": {"accounts": [{"account_name": "user_admin"}]},
        "describe_databases": {"databases": [{"database_name": "aidb"}]},
        "describe_db_account_connection": {
            "connection_examples": [
                {
                    "connection_type": "Parameters",
                    "connection_example": "PGHOST=db.example\nPGUSER=user_admin\nPGPASSWORD=fake\nPGDATABASE=aidb",
                }
            ]
        },
    }

    async def call(method, request, **params):
        import volcenginesdkaidap as sdk

        getattr(sdk, request)(**params)
        if method == "describe_db_account_connection":
            assert params == dict(
                workspace_id="ws",
                branch_id="branch",
                compute_id="compute",
                address_id="address",
                account_name="user_admin",
                database_name="aidb",
            )
        return results[method]

    monkeypatch.setattr(cloud, "call", call)
    assert "db.example" in await cloud.connection("ws")
    calls = []

    async def pages(method, request, **params):
        calls.append(params["offset"])
        if not params["offset"]:
            return {
                "workspaces": [workspace(f"other-{n}", f"ws-{n}") for n in range(100)]
            }
        return {"workspaces": [workspace("mpa_admin_workspace", "ws-target")]}

    monkeypatch.setattr(cloud, "call", pages)
    assert (await cloud.find("default", "mpa_admin_workspace"))[0][
        "workspace_id"
    ] == "ws-target"
    assert calls == [0, 100]


@pytest.mark.asyncio
async def test_provider_errors_do_not_expose_response_secrets(monkeypatch):
    from veadk.integrations.mpa.managed.pg_cloud import PGCloud
    from veadk.integrations.mpa.managed.database import DeploymentError

    def fail():
        raise ValueError("secret-value")

    with pytest.raises(DeploymentError) as error:
        await PGCloud(region="cn-beijing", credentials=fail).detail("ws")
    assert "secret-value" not in str(error.value)


@pytest.mark.parametrize("state", ["Failed", "Deleted", "Deleting", "unknown", ""])
def test_unknown_and_failed_states_fail_closed(state):
    from veadk.integrations.mpa.managed.pg_cloud import check_ready
    from veadk.integrations.mpa.managed.database import DeploymentError

    with pytest.raises(DeploymentError):
        check_ready(state)


@pytest.mark.asyncio
async def test_definite_permission_rejection_can_retry_after_permission_fix(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.pg_cloud import PGCloudError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    create = cloud.create
    cloud.create = AsyncMock(
        side_effect=PGCloudError("create_workspace", "AccessDenied")
    )
    with pytest.raises(PGCloudError, match="AccessDenied"):
        await prepare_postgres(profile, cloud, "account")
    cloud.create = create
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("source", ["flat", "template", "reference"])
async def test_provision_resolves_pg_before_template_and_overrides_inherited_credentials(
    tmp_path, monkeypatch, source
):
    from types import SimpleNamespace
    from veadk.integrations.mpa.managed import service, pg_bootstrap, pg_cloud
    from tests.integrations.mpa_managed.test_agent_deployment import template

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    old = template()
    old["Envs"] += [
        {"Key": "PGHOST", "Value": "old.example"},
        {"Key": "PGPASSWORD", "Value": "old-password"},
    ]
    if source == "flat":
        profile.managed.from_runtime = ""
        profile.values.update(
            image="registry/image:v1",
            model_provider="openai",
            model_api_base="https://model.example",
            model_api_key="fake",
            model_name="model",
        )
    elif source == "template":
        profile.managed.from_runtime = ""
        profile.template = old
    else:
        profile.managed.from_runtime = "r-source"
    cloud = SimpleNamespace(
        account_id=AsyncMock(return_value="account"),
        _credentials=lambda: None,
        get=AsyncMock(return_value=old),
    )
    monkeypatch.setattr(service, "RuntimeCloud", lambda **kw: cloud)
    monkeypatch.setattr(pg_cloud, "PGCloud", lambda **kw: FakePG())
    monkeypatch.setattr(pg_bootstrap, "initialize_admin_database", AsyncMock())

    class Verified(Exception):
        pass

    def check(*, admin_url, runtime_env):
        assert runtime_env["PGHOST"] == "ws-2.example"
        assert runtime_env["PGPASSWORD"] == "fake"
        assert "ws-2.example" in admin_url
        raise Verified()

    monkeypatch.setattr(service, "AgentDatabaseProvisioner", check)
    stages = []
    with pytest.raises(Verified):
        await service.provision(
            profile, agent_id="mi-123456789abc", owner="owner", progress=stages.append
        )
    assert stages == [
        "checking",
        "admin_workspace",
        "business_workspace",
        "admin_database",
    ]


def test_config_route_auto_does_not_call_cloud_or_return_credentials(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from frontend.server import mpa_creation
    from veadk.integrations.mpa.managed.pg_cloud import PGCloud

    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(mpa_creation, "load_volcengine_credentials", lambda *_: None)
    start = AsyncMock(return_value={"id": "task"})
    from veadk.integrations.mpa.managed.tasks import CreationTasks

    tasks = CreationTasks(tmp_path / "tasks.sqlite3")
    monkeypatch.setattr(tasks, "start", start)
    app = FastAPI()
    mpa_creation.mount_mpa_creation_routes(
        app,
        owner=lambda request: "user",
        service=tasks,
    )
    cloud = AsyncMock(side_effect=AssertionError("No cloud calls on config inspection"))
    monkeypatch.setattr(PGCloud, "call", cloud)
    with TestClient(app) as client:
        response = client.get("/web/mpa-creation/config?region=cn-beijing")
        assert response.json()["postgresMode"] == "auto"
        assert "postgresql://" not in response.text
        payload = dict(
            requestId="11111111-1111-4111-8111-111111111111",
            agentId="mi-test",
            region="cn-beijing",
        )
        assert (
            client.post(
                "/web/mpa-creation/tasks",
                json={**payload, "pgHost": "old.example", "pgPort": "5432"},
            ).status_code
            == 400
        )
        assert client.post("/web/mpa-creation/tasks", json=payload).status_code == 202
        assert "pgHost" not in start.call_args.args[1]
    cloud.assert_not_awaited()


@pytest.mark.asyncio
async def test_bootstrap_deadline_preserves_identity_for_retry(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"timeout_seconds": 0.02}
    )
    cloud = FakePG()
    original = cloud.connection

    async def pending(ident):
        await asyncio.Future()

    monkeypatch.setattr(cloud, "connection", pending)
    with pytest.raises(DeploymentError, match="timed out"):
        await prepare_postgres(profile, cloud, "account")
    cloud.connection = original
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"timeout_seconds": 30}
    )
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 2


def test_admin_init_cli_uses_sts_auto_bootstrap_without_printing_connections(
    tmp_path, monkeypatch
):
    from click.testing import CliRunner
    from veadk.cli.cli_mpa_admin import init_admin_db
    from veadk.integrations.mpa.managed import runtime, pg_cloud, pg_bootstrap
    from types import SimpleNamespace

    path = auto_profile(tmp_path, monkeypatch)
    cloud = SimpleNamespace(
        account_id=AsyncMock(return_value="account"), _credentials=lambda: None
    )
    monkeypatch.setattr(runtime, "RuntimeCloud", lambda **kw: cloud)
    monkeypatch.setattr(pg_cloud, "PGCloud", lambda **kw: FakePG())
    init = AsyncMock()
    monkeypatch.setattr(pg_bootstrap, "initialize_admin_database", init)
    result = CliRunner().invoke(init_admin_db, ["--config", str(path)])
    assert result.exit_code == 0, result.output
    assert "mpa_admin_db" in result.output
    assert "postgresql" not in result.output and "fake" not in result.output
    assert init.await_count == 1


@pytest.mark.asyncio
async def test_ambiguous_name_is_never_adopted(tmp_path, monkeypatch):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    cloud = FakePG()
    cloud.rows = {
        ident: workspace("mpa_admin_workspace", ident) for ident in ("first", "second")
    }
    with pytest.raises(DeploymentError, match="Multiple"):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 0


@pytest.mark.asyncio
async def test_invalid_explicit_adoption_does_not_pin_foreign_identity(
    tmp_path, monkeypatch
):
    from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
    from veadk.integrations.mpa.managed.database import DeploymentError

    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    settings = profile.managed.postgres
    assert settings is not None
    settings.admin_workspace_id = "foreign"
    cloud = FakePG()
    cloud.rows["foreign"] = workspace("mpa_admin_workspace", "foreign")
    cloud.rows["foreign"]["account_id"] = "other"
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account")
    cloud.rows["correct"] = workspace("mpa_admin_workspace", "correct")
    settings.admin_workspace_id = "correct"
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.initialize_admin_database",
        AsyncMock(),
    )
    resolved = await prepare_postgres(profile, cloud, "account")
    assert resolved.managed.postgres.admin_workspace_id == "correct"


def test_existing_registry_requires_migration_before_auto_is_ready(
    tmp_path, monkeypatch
):
    profile = load_profile(auto_profile(tmp_path, monkeypatch))
    from dataclasses import replace

    profile = replace(
        profile,
        shared_url="postgresql://owner:fake@legacy.example/registry",
    )
    summary = profile.summary()
    assert summary["postgresMode"] == "auto"
    assert summary["pgHost"] == ""
    assert summary["configured"] is False
    assert summary["postgresMigrationRequired"] is True
    assert "fake" not in str(summary)


def test_auto_mode_can_explicitly_ignore_legacy_pg_urls(tmp_path, monkeypatch):
    path = auto_profile(tmp_path, monkeypatch)
    data = yaml.safe_load(path.read_text())
    data["managed"]["postgres"]["legacy-urls"] = "ignore"
    path.write_text(yaml.safe_dump(data))
    monkeypatch.setenv(
        "DEPLOYMENT_DATABASE_ADMIN_URL", "postgresql://owner:fake@legacy.example/aidb"
    )
    monkeypatch.setenv(
        "SHARED_APIG_DATABASE_URL", "postgresql://owner:fake@legacy.example/registry"
    )

    profile = load_profile(path)
    assert profile.admin_url == profile.shared_url == ""
    assert profile.summary()["configured"] is True
    assert "postgresMigrationRequired" not in profile.summary()
    assert with_creation_resources(profile, {}).shared_url == ""
