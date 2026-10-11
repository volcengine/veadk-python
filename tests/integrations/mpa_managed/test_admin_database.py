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

"""Offline coverage for the explicit registry initialization/copy command."""

import asyncio
import copy
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from veadk.integrations.mpa.managed import admin_database as admin
from veadk.integrations.mpa.managed.config import (
    ConfigurationError,
    load_profile,
    management_admin_url,
)
from veadk.integrations.mpa.managed.database import DeploymentError
from tests.integrations.mpa_managed.test_config import split_profile_file
from tests.integrations.mpa_managed.test_deployment_database_unit import (
    Connection,
    Engine,
)


def test_maintenance_connection_is_separate_and_validated(tmp_path, monkeypatch):
    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    assert management_admin_url(profile).endswith("@management/aidb")
    for url in (
        "postgresql://owner:fake@business/aidb",
        "postgresql://owner:fake@management/mpa_admin_db",
        "postgresql://owner:fake@management:6543/aidb",
        "not-a-url",
    ):
        monkeypatch.setenv("TEST_REGISTRY_ADMIN", url)
        with pytest.raises(ConfigurationError) as error:
            management_admin_url(profile)
        assert "fake" not in str(error.value)


def row(agent_id="mi-one", **record) -> dict:
    return dict(
        account_id="account",
        region="cn-beijing",
        agent_id=agent_id,
        record={"studio_owner": "owner-hash", "database_host": "business", **record},
    )


def test_copy_is_idempotent_and_preserves_all_record_fields():
    original = row(runtime_id="r-one", database_name="mpa_agent_existing")
    other = row("mi-two")
    assert admin.missing_rows(admin.TABLES[2], [original, other], [original]) == [other]
    assert admin.missing_rows(admin.TABLES[2], [original], [original]) == []
    assert original["record"]["database_name"] == "mpa_agent_existing"


@pytest.mark.parametrize("target", [[row(runtime_id="r-wrong")], [row("mi-extra")]])
def test_copy_refuses_conflicting_or_extra_target_rows(target):
    with pytest.raises(DeploymentError, match="conflict"):
        admin.missing_rows(admin.TABLES[2], [row()], target)


def test_foreign_or_missing_registry_tables_are_not_adopted():
    known = {table.name for table in admin.TABLES}
    admin.validate_tables(known, source=True)
    admin.validate_tables(set(), source=False)
    with pytest.raises(DeploymentError):
        admin.validate_tables(known - {"mpa_account_apig"}, source=True)
    with pytest.raises(DeploymentError):
        admin.validate_tables(known | {"sessions"}, source=False)


def test_pending_runtime_payload_is_not_rebound_to_new_registry():
    with pytest.raises(DeploymentError, match="pending Runtime"):
        admin.missing_rows(
            admin.TABLES[2], [row(pending=True, request_hash="old-payload")], []
        )


def test_initialization_error_is_redacted_and_engines_are_closed(tmp_path, monkeypatch):
    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    engine = AsyncMock()
    monkeypatch.setattr(admin, "postgres_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(
        admin, "create_database", AsyncMock(side_effect=RuntimeError("secret-url"))
    )
    with pytest.raises(DeploymentError) as error:
        asyncio.run(admin.initialize_admin_database(profile))
    assert "secret-url" not in str(error.value)
    engine.dispose.assert_awaited()


def test_cancellation_closes_engines_and_is_not_success(tmp_path, monkeypatch):
    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    engine = AsyncMock()
    monkeypatch.setattr(admin, "postgres_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(
        admin, "create_database", AsyncMock(side_effect=asyncio.CancelledError)
    )
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(admin.initialize_admin_database(profile))
    engine.dispose.assert_awaited()


@pytest.mark.parametrize(
    "owners, creates", [([None, "registry"], 1), (["registry"], 0)]
)
def test_database_initialization_can_resume_without_recreating(owners, creates):
    engine = Engine(Connection(scalars=owners))
    asyncio.run(admin.create_database(engine, "registry"))
    assert (
        sum(sql.startswith("CREATE DATABASE") for sql, _ in engine.conn.sql) == creates
    )


def test_database_initialization_rejects_foreign_owner():
    engine = Engine(Connection(scalars=["foreign"]))
    with pytest.raises(DeploymentError, match="owner"):
        asyncio.run(admin.create_database(engine, "registry"))
    assert not any(sql.startswith("CREATE") for sql, _ in engine.conn.sql)


class RegistryEngine:
    """Transaction model: commit only on successful context exit."""

    def __init__(self, rows):
        self.rows = copy.deepcopy(rows)
        self.sql = []
        self.dispose = AsyncMock()
        self.commits = 0
        self.rollbacks = 0

    @asynccontextmanager
    async def begin(self):
        pending = copy.deepcopy(self.rows)
        engine = self

        class Conn:
            async def execute(self, statement, params=None):
                sql = str(statement)
                engine.sql.append(sql)
                if "FROM pg_class" in sql:
                    return SimpleNamespace(scalars=lambda: list(pending))
                if sql.startswith("SELECT mpa_"):
                    return SimpleNamespace(
                        mappings=lambda: pending[statement.get_final_froms()[0].name]
                    )
                if sql.startswith("INSERT"):
                    pending[statement.table.name].extend(copy.deepcopy(params))

            async def run_sync(self, fn):
                pass

        try:
            yield Conn()
        except BaseException:
            self.rollbacks += 1
            raise
        else:
            self.rows = pending
            self.commits += 1


@pytest.mark.parametrize("conflict", [False, True])
def test_three_table_copy_is_atomic_and_source_untouched(
    tmp_path, monkeypatch, conflict
):
    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    data = {
        "mpa_account_apig": [
            dict(
                account_id="account",
                region="cn-beijing",
                record={"gateway_id": "gw-one"},
            )
        ],
        "mpa_account_network": [
            dict(
                account_id="account", region="cn-beijing", record={"vpc_id": "vpc-one"}
            )
        ],
        "mpa_agent_deployment": [row(runtime_id="r-one")],
    }
    source = RegistryEngine(data)
    target = RegistryEngine({table.name: [] for table in admin.TABLES})
    if conflict:
        target.rows["mpa_agent_deployment"] = [row(runtime_id="r-other")]
    before = copy.deepcopy(target.rows)
    maintenance = AsyncMock()
    monkeypatch.setattr(admin, "create_database", AsyncMock())
    monkeypatch.setattr(
        admin,
        "postgres_engine",
        lambda url, **kw: source
        if "@old/" in url
        else target
        if "mpa_admin_db" in url
        else maintenance,
    )

    async def run():
        return await admin.initialize_admin_database(
            profile, source_url="postgresql://reader:fake@old/registry"
        )

    if conflict:
        with pytest.raises(DeploymentError, match="conflict"):
            asyncio.run(run())
        assert target.rows == before
        assert target.rollbacks == 1
    else:
        result = asyncio.run(run())
        assert target.rows == data
        assert result["rows"] == {table.name: 1 for table in admin.TABLES}
        asyncio.run(run())
        assert target.rows == data
    assert source.rows == data
    assert not any(
        sql.startswith(("INSERT", "UPDATE", "DELETE", "CREATE")) for sql in source.sql
    )
    assert any("SHARE MODE" in sql for sql in source.sql)
    assert any("lock_timeout" in sql for sql in target.sql)
    target.dispose.assert_awaited()
    source.dispose.assert_awaited()


def test_timeout_is_redacted_and_disposes_connections(tmp_path, monkeypatch):
    profile = load_profile(split_profile_file(tmp_path, monkeypatch))
    engine = AsyncMock()
    monkeypatch.setattr(admin, "postgres_engine", lambda *a, **kw: engine)
    monkeypatch.setattr(
        admin, "create_database", AsyncMock(side_effect=TimeoutError("secret"))
    )
    with pytest.raises(DeploymentError, match="preparation failed") as error:
        asyncio.run(admin.initialize_admin_database(profile))
    assert "secret" not in str(error.value)
    engine.dispose.assert_awaited()


def test_cli_accepts_secret_reference_and_redacts_provider_errors(
    tmp_path, monkeypatch
):
    from click.testing import CliRunner
    from veadk.cli.cli_mpa import mpa

    path = split_profile_file(tmp_path, monkeypatch)
    initialize = AsyncMock(return_value={"database": "mpa_admin_db", "copied": True})
    monkeypatch.setattr(admin, "initialize_admin_database", initialize)
    monkeypatch.setenv("OLD_REGISTRY", "postgresql://reader:fake@old/registry")
    args = ["init-admin-db", "--config", str(path), "--source-url-env", "OLD_REGISTRY"]
    result = CliRunner().invoke(mpa, args)
    assert result.exit_code == 0, result.output
    assert "mpa_admin_db" in result.output
    assert "fake" not in result.output
    initialize.assert_awaited_once()
    initialize.side_effect = RuntimeError("provider secret")
    result = CliRunner().invoke(mpa, args)
    assert result.exit_code == 1
    assert "provider secret" not in result.output
