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

"""Offline regression for agent-scoped business Workspace provisioning."""

import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.engine import make_url

from tests.integrations.mpa_managed.test_auto_pg import recovery_setup
from veadk.integrations.mpa.managed.config import (
    ConfigurationError,
    with_creation_resources,
)
from veadk.integrations.mpa.managed.database import DeploymentError, database_name
from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres


def setup(tmp_path, monkeypatch, provider="volcengine"):
    profile, cloud, store, scope = recovery_setup(tmp_path, monkeypatch, provider)
    assert profile.managed.postgres is not None
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"business_workspace_mode": "per-agent"}
    )
    read = AsyncMock(return_value={})
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.registered_business_binding", read
    )
    return profile, cloud, store, scope, read


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
async def test_distinct_business_workspaces_share_admin_and_retry(
    tmp_path, monkeypatch, provider
):
    profile, cloud, store, scope, read = setup(tmp_path, monkeypatch, provider)
    first, second = await asyncio.gather(
        prepare_postgres(profile, cloud, "account", agent_id="mi-first"),
        prepare_postgres(profile, cloud, "account", agent_id="mi-second"),
    )
    retried = await prepare_postgres(profile, cloud, "account", agent_id="mi-first")
    assert cloud.created == 3
    assert first.shared_url == second.shared_url == retried.shared_url
    assert first.admin_url == retried.admin_url != second.admin_url
    assert store.read(scope, "business") is None
    for resolved, ident in [(first, "mi-first"), (second, "mi-second")]:
        settings = resolved.managed.postgres
        assert settings.business_workspace_mode == "per-agent"
        assert cloud.rows[settings.business_workspace_id][
            "workspace_name"
        ] == database_name("account", profile.region, ident)
        assert (
            resolved.managed.runtime.env["PGHOST"] == make_url(resolved.admin_url).host
        )
    assert read.await_count == 3
    assert "fake" not in store.path.read_bytes().decode(errors="ignore")


@pytest.mark.asyncio
async def test_legacy_registered_agent_retains_shared_workspace(tmp_path, monkeypatch):
    profile, cloud, store, scope = recovery_setup(tmp_path, monkeypatch)
    shared = await prepare_postgres(profile, cloud, "account")
    assert profile.managed.postgres is not None
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"business_workspace_mode": "per-agent"}
    )
    monkeypatch.setattr(
        "veadk.integrations.mpa.managed.pg_bootstrap.registered_business_binding",
        AsyncMock(
            return_value={
                "admin_workspace_id": "ws-1",
                "business_workspace_id": "ws-2",
                "database_host": "ws-2.example",
                "database_port": 5432,
            }
        ),
    )
    retried = await prepare_postgres(profile, cloud, "account", agent_id="mi-old")
    assert retried.admin_url == shared.admin_url
    assert retried.managed.postgres.business_workspace_mode == "shared"
    assert cloud.created == 2
    assert store.read(scope, "business")[1] == "ws-2"


@pytest.mark.asyncio
async def test_registry_error_prevents_business_purchase(tmp_path, monkeypatch):
    profile, cloud, _, _, read = setup(tmp_path, monkeypatch)
    read.side_effect = RuntimeError("connection unavailable")
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    assert cloud.created == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "binding",
    [
        {"business_workspace_id": "old", "admin_workspace_id": "wrong"},
        {
            "business_workspace_id": "old",
            "admin_workspace_id": "ws-1",
            "business_workspace_mode": "unknown",
        },
        {"database_name": "old"},
        {"state": "deleted"},
    ],
)
async def test_invalid_old_binding_fails_before_purchase(
    tmp_path, monkeypatch, binding
):
    profile, cloud, _, _, read = setup(tmp_path, monkeypatch)
    read.return_value = binding
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account", agent_id="mi-old")
    assert cloud.created == 1


@pytest.mark.asyncio
async def test_business_unknown_create_does_not_duplicate(tmp_path, monkeypatch):
    profile, cloud, _, _, _ = setup(tmp_path, monkeypatch)
    create = cloud.create

    async def uncertain(name, project, tags):
        if tags["veadk-pg-purpose"] == "business":
            cloud.created += 1
            raise TimeoutError()
        return await create(name, project, tags)

    cloud.create = uncertain
    for _ in range(2):
        with pytest.raises(DeploymentError, match="uncertain"):
            await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    assert cloud.created == 2


@pytest.mark.asyncio
async def test_per_agent_requires_id_before_cloud_mutation(tmp_path, monkeypatch):
    profile, cloud, _, _, _ = setup(tmp_path, monkeypatch)
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account")
    assert cloud.created == 0


def test_creation_mode_is_additive_and_validated(tmp_path, monkeypatch):
    profile, _, _, _ = recovery_setup(tmp_path, monkeypatch)
    shared = with_creation_resources(profile, {}).managed.postgres
    independent = with_creation_resources(
        profile, {"businessWorkspaceMode": "per-agent"}
    ).managed.postgres
    assert shared is not None and shared.business_workspace_mode == "shared"
    assert (
        independent is not None and independent.business_workspace_mode == "per-agent"
    )
    with pytest.raises(ConfigurationError):
        with_creation_resources(profile, {"businessWorkspaceMode": "invalid"})


@pytest.mark.asyncio
async def test_registered_per_agent_identity_reused_after_bootstrap_loss(
    tmp_path, monkeypatch
):
    profile, cloud, store, _, read = setup(tmp_path, monkeypatch)
    first = await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    read.return_value = {
        "admin_workspace_id": first.managed.postgres.admin_workspace_id,
        "business_workspace_id": first.managed.postgres.business_workspace_id,
        "business_workspace_mode": "per-agent",
        "database_host": make_url(first.admin_url).host,
        "database_port": 5432,
    }
    with store.connection() as db:
        db.execute("DELETE FROM workspaces WHERE purpose='business'")
    second = await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    assert second.admin_url == first.admin_url
    assert cloud.created == 2


@pytest.mark.asyncio
async def test_unowned_name_collision_is_not_adopted(tmp_path, monkeypatch):
    from tests.integrations.mpa_managed.test_auto_pg import workspace

    profile, cloud, _, _, _ = setup(tmp_path, monkeypatch)
    cloud.rows["foreign"] = workspace(
        database_name("account", profile.region, "mi-new"), "foreign"
    )
    with pytest.raises(DeploymentError):
        await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    assert cloud.created == 1


@pytest.mark.asyncio
async def test_registered_reader_closes_registry_on_error(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace
    from veadk.integrations.mpa.managed import pg_bootstrap

    @asynccontextmanager
    async def lock(*args):
        yield SimpleNamespace(read=AsyncMock(side_effect=RuntimeError("unavailable")))

    registry = SimpleNamespace(lock=lock, close=AsyncMock())
    monkeypatch.setattr(pg_bootstrap, "AgentDeploymentRegistry", lambda *_: registry)
    with pytest.raises(RuntimeError):
        await pg_bootstrap.registered_business_binding(
            "unused", "account", "region", "agent"
        )
    registry.close.assert_awaited_once()


def test_per_agent_profile_rejects_shared_adoption_and_manual_mode():
    from pydantic import ValidationError
    from veadk.integrations.mpa.managed.config import PostgresWorkspaces

    for values in [
        {"mode": "auto", "business_workspace_id": "shared"},
        {
            "mode": "manual",
            "admin_workspace_id": "admin",
            "business_workspace_id": "business",
        },
    ]:
        with pytest.raises(ValidationError):
            PostgresWorkspaces.model_validate(
                {"business_workspace_mode": "per-agent", **values}
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("runtime_name", ["test-mpa", "1234", "Case_Name", "x" * 64])
async def test_aidb_layout_uses_readable_workspace_and_pins_name(
    tmp_path, monkeypatch, runtime_name
):
    profile, cloud, store, _, _ = setup(tmp_path, monkeypatch)
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"business_database_name": "aidb"}
    )
    first = await prepare_postgres(
        profile, cloud, "account", agent_id="mi-new", runtime_name=runtime_name
    )
    second = await prepare_postgres(
        profile, cloud, "account", agent_id="mi-new", runtime_name=runtime_name
    )
    assert cloud.created == 2
    assert first.admin_url == second.admin_url
    assert first.managed.postgres.business_workspace_name == "mpa_agent_" + runtime_name
    assert first.managed.postgres.business_database_name == "aidb"
    assert cloud.rows["ws-2"]["workspace_name"] == "mpa_agent_" + runtime_name
    assert "aidb" in store.path.read_bytes().decode(errors="ignore")


@pytest.mark.asyncio
async def test_new_aidb_selection_does_not_upgrade_existing_hash_bootstrap(
    tmp_path, monkeypatch
):
    profile, cloud, _, _, _ = setup(tmp_path, monkeypatch)
    old = await prepare_postgres(profile, cloud, "account", agent_id="mi-new")
    assert profile.managed.postgres is not None
    profile.managed.postgres = profile.managed.postgres.model_copy(
        update={"business_database_name": "aidb"}
    )
    retried = await prepare_postgres(
        profile, cloud, "account", agent_id="mi-new", runtime_name="new-name"
    )
    assert retried.admin_url == old.admin_url
    assert retried.managed.postgres.business_database_name == ""
    assert (
        retried.managed.postgres.business_workspace_name
        == old.managed.postgres.business_workspace_name
    )
    assert cloud.created == 2
