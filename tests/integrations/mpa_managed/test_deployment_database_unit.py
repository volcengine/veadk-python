"""Offline database lifecycle contracts, including loss/collision recovery."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from cryptography.fernet import Fernet
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.asyncio import AsyncEngine

from veadk.integrations.mpa.managed import database as mod
from veadk.integrations.mpa.managed import registry as shared
from tests.integrations.mpa_managed.test_agent_deployment import Registry


class Connection:
    def __init__(self, *, row=None, scalars=()):
        self.row = row
        self.scalars = iter(scalars)
        self.sql = []
        self.commit = AsyncMock()
        self.rollback = AsyncMock()
        self.invalidate = AsyncMock()
        self.run_sync = AsyncMock()

    async def execute(self, statement, params=None):
        self.sql.append((str(statement.compile(dialect=postgresql.dialect())), params))
        return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: self.row))

    async def scalar(self, statement, params=None):
        self.sql.append((str(statement.compile(dialect=postgresql.dialect())), params))
        result = next(self.scalars)
        if isinstance(result, BaseException):
            raise result
        return result


class Engine:
    dialect = SimpleNamespace(name="postgresql")

    def __init__(self, conn):
        self.conn = conn
        self.dispose = AsyncMock()

    @asynccontextmanager
    async def connect(self):
        yield self.conn

    begin = connect


@pytest.fixture
def db_factory(monkeypatch):
    def make(*, row=None, scalars=()):
        engine = Engine(Connection(row=row, scalars=scalars))
        monkeypatch.setattr(mod, "postgres_engine", lambda *a, **kw: engine)
        db = mod.AgentDatabaseProvisioner(
            admin_url="postgresql://admin:pw@db/postgres",
            runtime_env={"PGHOST": "db", "PGUSER": "agent", "PGPASSWORD": "private"},
        )
        return db, engine

    return make


def test_create_database_records_intent_before_ddl_and_keeps_identity(db_factory):
    async def run():
        db, engine = db_factory()
        entry = Registry()
        execute = engine.conn.execute

        async def inspect(statement, params=None):
            if str(statement).startswith("CREATE DATABASE"):
                assert entry.row["database_create_requested"]
                assert not entry.row.get("database_ready")
            return await execute(statement, params)

        engine.conn.execute = inspect
        name = await db.ensure(entry, account="a", region="r", agent_id="i")
        assert name == mod.database_name("a", "r", "i")
        assert entry.row["database_ready"] and entry.row["client_token"]
        assert any(
            f'CREATE DATABASE "{name}" OWNER "agent"' in s for s, _ in engine.conn.sql
        )
        assert any(mod.database_marker("a", "r", "i") in s for s, _ in engine.conn.sql)
        assert "private" not in str(entry.row)
        assert db.runtime_url(name).database == name
        await db.close()
        engine.dispose.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "row,record,error",
    [
        (
            {"owner": "other", "marker": mod.database_marker("a", "r", "i")},
            {},
            "ownership",
        ),
        ({"owner": "agent", "marker": None}, {}, "ownership"),
        (None, {"database_ready": True}, "missing"),
        (None, {"database_host": "different"}, "differs"),
    ],
)
def test_database_conflicts_never_issue_ddl(db_factory, row, record, error):
    async def run():
        db, engine = db_factory(row=row)
        entry = Registry()
        entry.row = record.copy()
        with pytest.raises(mod.DeploymentError, match=error):
            await db.ensure(entry, account="a", region="r", agent_id="i")
        assert not any(s.startswith(("CREATE", "COMMENT")) for s, _ in engine.conn.sql)
        assert entry.row == record

    asyncio.run(run())


def test_existing_marked_database_is_reused_without_ddl(db_factory):
    async def run():
        db, engine = db_factory(
            row={"owner": "agent", "marker": mod.database_marker("a", "r", "i")}
        )
        entry = Registry()
        entry.row = {"client_token": "keep-token"}
        await db.ensure(entry, account="a", region="r", agent_id="i")
        assert entry.row["client_token"] == "keep-token"
        assert len(engine.conn.sql) == 1

    asyncio.run(run())


@pytest.mark.parametrize(
    "mode", ["recover", "existing", "invalid_existing", "invalid_stored", "mismatch"]
)
def test_encryption_key_never_silently_rotates(db_factory, mode):
    async def run():
        key = Fernet.generate_key().decode()
        stored = "broken" if mode == "invalid_stored" else key
        db, engine = db_factory(scalars=["mpa_deployment_settings", stored])
        existing = {
            "existing": key,
            "invalid_existing": "broken",
            "mismatch": Fernet.generate_key().decode(),
        }.get(mode, "")
        if mode in {"recover", "existing"}:
            assert await db.encryption_key("business", existing_key=existing) == key
            assert all(sql.startswith("SELECT") for sql, _ in engine.conn.sql)
        else:
            with pytest.raises(mod.DeploymentError):
                await db.encryption_key("business", existing_key=existing)
        if mode != "invalid_existing":
            engine.dispose.assert_awaited_once()
        else:
            assert not engine.conn.sql

    asyncio.run(run())


@pytest.mark.parametrize(
    "existing",
    [None, {"runtime_id": ""}, {"runtime_id": "r-one"}, {"runtime_id": "r-other"}],
)
def test_runtime_seed_preserves_existing_binding(db_factory, monkeypatch, existing):
    from veadk.integrations.mpa.managed import metadata as mpa_meta

    async def run():
        db, _engine = db_factory()
        store = SimpleNamespace(
            ensure_schema=AsyncMock(),
            get=AsyncMock(return_value=existing),
            fill_empty=AsyncMock(),
            close=AsyncMock(),
        )
        monkeypatch.setattr(mpa_meta, "MpaMetaStore", lambda _: store)
        if existing and existing["runtime_id"] == "r-other":
            with pytest.raises(mod.DeploymentError, match="another Runtime"):
                await db.seed_runtime("db", "agent", "r-one")
            store.fill_empty.assert_not_awaited()
        else:
            await db.seed_runtime("db", "agent", "r-one")
            store.fill_empty.assert_awaited_once_with(
                mpa_agent_id="agent", values={"runtime_id": "r-one"}
            )
        store.close.assert_awaited_once()

    asyncio.run(run())


def test_engine_conversion_and_template_validation(monkeypatch):
    calls = []
    monkeypatch.setattr(
        mod, "create_async_engine", lambda url, **kw: calls.append((url, kw))
    )
    mod.postgres_engine("postgresql://user:pw@db/app?sslmode=require")
    assert calls[0][0].drivername == "postgresql+asyncpg"
    assert calls[0][0].query == {"ssl": "require"}
    assert calls[0][1]["hide_parameters"]
    with pytest.raises(mod.DeploymentError, match="PostgreSQL"):
        mod.postgres_engine("sqlite:///db")
    for env in (
        {},
        {"PGHOST": "db"},
        {"PGHOST": "db", "PGUSER": "u"},
        {"PGHOST": "other", "PGUSER": "u", "PGPASSWORD": "pw"},
    ):
        with pytest.raises(mod.DeploymentError):
            mod.AgentDatabaseProvisioner(
                admin_url="postgresql://user:pw@db/app", runtime_env=env
            )
    assert mod.identifier('a"b') == '"a""b"'


def test_registries_initialize_and_durably_save_scoped_records(monkeypatch):
    async def run():
        conn = Connection(scalars=[True, None, {"runtime_id": "r-one"}])
        engine = Engine(conn)
        monkeypatch.setattr(mod, "postgres_engine", lambda *a, **kw: engine)
        registry = mod.AgentDeploymentRegistry("postgresql://db/app")
        await registry.initialize()
        assert conn.run_sync.await_count == 2
        async with registry.lock("account", "region", "agent") as entry:
            assert await entry.read() == {}
            await entry.save({"runtime_id": "r-one"})
            assert await entry.read() == {"runtime_id": "r-one"}
        sql = "\n".join(s for s, _ in conn.sql)
        assert (
            "mpa_agent_deployment.account_id" in sql
            and "mpa_agent_deployment.agent_id" in sql
        )
        assert "ON CONFLICT (account_id, region, agent_id) DO UPDATE" in sql
        assert "pg_advisory_unlock" in sql
        await registry.close()
        engine.dispose.assert_awaited_once()

    asyncio.run(run())


@pytest.mark.parametrize(
    "failure", [None, RuntimeError("consumer failed"), asyncio.CancelledError()]
)
def test_account_lock_waits_and_always_unlocks(monkeypatch, failure):
    async def run():
        conn = Connection(scalars=[False, True, None])
        registry = shared.SharedAPIGRegistry(
            Mock(spec=AsyncEngine, wraps=Engine(conn), dialect=Engine.dialect)
        )
        sleep = AsyncMock()
        monkeypatch.setattr(shared.asyncio, "sleep", sleep)

        async def use():
            async with registry.lock("a", "r") as entry:
                assert await entry.read() == {}
                await entry.save({"gateway_id": "gw"})
                if failure:
                    raise failure

        if failure:
            with pytest.raises(type(failure)):
                await use()
        else:
            await use()
        sleep.assert_awaited_once_with(0.5)
        conn.rollback.assert_awaited_once()
        assert "pg_advisory_unlock" in conn.sql[-1][0]
        assert any(
            "ON CONFLICT (account_id, region) DO UPDATE" in s for s, _ in conn.sql
        )
        conn.invalidate.assert_not_awaited()

    asyncio.run(run())


def test_failed_unlock_invalidates_pooled_connection():
    async def run():
        conn = Connection(scalars=[True])
        conn.rollback.side_effect = OSError("connection lost")
        registry = shared.SharedAPIGRegistry(
            Mock(spec=AsyncEngine, wraps=Engine(conn), dialect=Engine.dialect)
        )
        with pytest.raises(OSError):
            async with registry.lock("a", "r"):
                pass
        conn.invalidate.assert_awaited_once()

    asyncio.run(run())


def test_network_registry_shares_connection_but_is_scoped_by_account_and_region():
    async def run():
        conn = Connection(scalars=[None, {"vpc_id": "vpc-one"}, {"gateway_id": "gw"}])
        entry = mod.AgentDeploymentEntry(
            conn, "account", "region", "agent"
        ).network_entry()
        assert entry.conn is conn
        assert entry.keys == {"account_id": "account", "region": "region"}
        assert await entry.read() == {}
        await entry.save({"vpc_id": "vpc-one"})
        assert await entry.read() == {"vpc_id": "vpc-one"}
        assert await entry.gateway() == {"gateway_id": "gw"}
        sql = "\n".join(s for s, _ in conn.sql)
        assert "mpa_account_network.account_id" in sql
        assert "mpa_account_network.region" in sql
        assert "ON CONFLICT (account_id, region) DO UPDATE" in sql
        assert "mpa_account_apig" in sql
        assert "agent_id" not in sql
        assert conn.commit.await_count == 4

    asyncio.run(run())


@pytest.mark.parametrize("table_exists", [False, True])
@pytest.mark.parametrize("keep_existing", [False, True])
def test_channel_key_lookup_never_generates_or_persists_a_new_key(
    db_factory, table_exists, keep_existing
):
    async def run():
        existing = Fernet.generate_key().decode() if keep_existing else ""
        scalars = ["mpa_deployment_settings", None] if table_exists else [None]
        db, engine = db_factory(scalars=scalars)
        assert await db.encryption_key("business", existing_key=existing) == existing
        assert all(sql.startswith("SELECT") for sql, _ in engine.conn.sql)
        engine.dispose.assert_awaited_once()

    asyncio.run(run())
