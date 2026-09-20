"""Persistent per-agent databases on an existing PostgreSQL instance."""

from __future__ import annotations

import hashlib
import json
import uuid
from contextlib import asynccontextmanager

from cryptography.fernet import Fernet
from sqlalchemy import JSON, Column, MetaData, String, Table, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import create_async_engine

from veadk.integrations.mpa.managed.registry import SharedAPIGRegistry

metadata = MetaData()
agent_deployments = Table(
    "mpa_agent_deployment",
    metadata,
    Column("account_id", String(128), primary_key=True),
    Column("region", String(64), primary_key=True),
    Column("agent_id", String(128), primary_key=True),
    Column("record", JSON, nullable=False),
)
account_networks = Table(
    "mpa_account_network",
    metadata,
    Column("account_id", String(128), primary_key=True),
    Column("region", String(64), primary_key=True),
    Column("record", JSON, nullable=False),
)


class DeploymentError(RuntimeError):
    """Safe, operator-facing error with no credentials."""


def agent_suffix(account_id: str, region: str, agent_id: str) -> str:
    if not all(
        isinstance(v, str) and v.strip() and len(v) <= 128
        for v in (account_id, region, agent_id)
    ):
        raise DeploymentError(
            "Account, region and agent ID must be nonempty and at most 128 characters"
        )
    value = json.dumps(
        [account_id, region, agent_id], separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(value.encode()).hexdigest()[:24]


def database_name(account_id: str, region: str, agent_id: str) -> str:
    return "mpa_agent_" + agent_suffix(account_id, region, agent_id)


def database_marker(account_id: str, region: str, agent_id: str) -> str:
    return "mpa-agent-database:v1:" + agent_suffix(account_id, region, agent_id)


def identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def postgres_engine(url, **kwargs):
    parsed = make_url(url)
    if parsed.get_backend_name() != "postgresql":
        raise DeploymentError("Deployment storage requires PostgreSQL")
    query = dict(parsed.query)
    if "sslmode" in query:
        query["ssl"] = query.pop("sslmode")
    return create_async_engine(
        parsed.set(drivername="postgresql+asyncpg", query=query),
        hide_parameters=True,
        **kwargs,
    )


class AgentDeploymentRegistry:
    def __init__(self, url: str):
        self.shared = SharedAPIGRegistry(postgres_engine(url))

    async def initialize(self):
        await self.shared.initialize()
        async with self.shared.engine.begin() as conn:
            await conn.execute(text("SELECT pg_advisory_xact_lock(783435789211)"))
            await conn.run_sync(metadata.create_all)

    @asynccontextmanager
    async def lock(self, account: str, region: str, agent_id: str):
        # Share the account/region provisioning lock with APIG. Release before
        # waiting for Runtime readiness, which itself may need this same lock.
        async with self.shared.lock(account, region) as entry:
            yield AgentDeploymentEntry(entry.conn, account, region, agent_id)

    async def close(self):
        await self.shared.close()


class AgentDeploymentEntry:
    def __init__(self, conn, account, region, agent_id):
        self.conn = conn
        self.keys = dict(account_id=account, region=region, agent_id=agent_id)

    def network_entry(self):
        # Same connection and account/region lock as Runtime and APIG creation.
        return AccountNetworkEntry(
            self.conn, self.keys["account_id"], self.keys["region"]
        )

    async def read(self):
        query = select(agent_deployments.c.record)
        for key, value in self.keys.items():
            query = query.where(agent_deployments.c[key] == value)
        row = await self.conn.scalar(query)
        await self.conn.commit()
        return dict(row or {})

    async def save(self, record):
        query = insert(agent_deployments).values(**self.keys, record=record)
        query = query.on_conflict_do_update(
            index_elements=list(self.keys), set_={"record": record}
        )
        await self.conn.execute(query)
        await self.conn.commit()


class AccountNetworkEntry:
    def __init__(self, conn, account, region):
        self.conn = conn
        self.keys = dict(account_id=account, region=region)

    async def read(self):
        row = await self.conn.scalar(
            select(account_networks.c.record).filter_by(**self.keys)
        )
        await self.conn.commit()
        return dict(row or {})

    async def save(self, record):
        query = insert(account_networks).values(**self.keys, record=record)
        await self.conn.execute(
            query.on_conflict_do_update(
                index_elements=list(self.keys),
                set_={"record": record},
            )
        )
        await self.conn.commit()

    async def gateway(self):
        from veadk.integrations.mpa.managed.registry import RegistryEntry

        return await RegistryEntry(self.conn, **self.keys).read()


class AgentDatabaseProvisioner:
    def __init__(self, *, admin_url: str, runtime_env: dict[str, str]):
        self.admin_url = make_url(admin_url)
        self.env = dict(runtime_env)
        for key in ("PGHOST", "PGUSER", "PGPASSWORD"):
            if not self.env.get(key):
                raise DeploymentError(f"Runtime template requires {key}")
        if (self.admin_url.host, self.admin_url.port or 5432) != (
            self.env["PGHOST"],
            int(self.env.get("PGPORT", "5432")),
        ):
            raise DeploymentError(
                "Database administrator and Runtime must target the same PostgreSQL host/port"
            )
        self.admin = postgres_engine(self.admin_url, isolation_level="AUTOCOMMIT")

    def runtime_url(self, name: str):
        return URL.create(
            "postgresql+asyncpg",
            username=self.env["PGUSER"],
            password=self.env["PGPASSWORD"],
            host=self.env["PGHOST"],
            port=int(self.env.get("PGPORT", "5432")),
            database=name,
            query={"ssl": self.env.get("PGSSLMODE", "require")},
        )

    async def check(self):
        """Check deployment DB privileges before preparing paid cloud resources."""
        async with self.admin.connect() as conn:
            allowed = await conn.scalar(
                text(
                    "SELECT rolcreatedb OR rolsuper FROM pg_roles WHERE rolname=current_user"
                )
            )
            owner_exists = await conn.scalar(
                text("SELECT EXISTS(SELECT 1 FROM pg_roles WHERE rolname=:owner)"),
                {"owner": self.env["PGUSER"]},
            )
            if not allowed or not owner_exists:
                raise DeploymentError(
                    "Database administrator requires CREATEDB and an existing business database owner"
                )
            can_assign = await conn.scalar(
                text(
                    "SELECT pg_has_role(current_user, :owner, 'MEMBER') OR "
                    "(SELECT rolsuper FROM pg_roles WHERE rolname=current_user)"
                ),
                {"owner": self.env["PGUSER"]},
            )
            if not can_assign:
                raise DeploymentError(
                    "Database administrator cannot assign the configured business database owner"
                )

    async def ensure(self, entry, *, account: str, region: str, agent_id: str):
        name = database_name(account, region, agent_id)
        marker = database_marker(account, region, agent_id)
        record = await entry.read()
        identity = {
            "database_name": name,
            "database_host": self.env["PGHOST"],
            "database_port": int(self.env.get("PGPORT", "5432")),
            "database_owner": self.env["PGUSER"],
        }
        if any(
            key in record and record[key] != value for key, value in identity.items()
        ):
            raise DeploymentError(
                "Registered agent database differs from requested configuration"
            )
        async with self.admin.connect() as conn:
            row = (
                (
                    await conn.execute(
                        text(
                            "SELECT pg_get_userbyid(datdba) AS owner, shobj_description(oid, 'pg_database') AS marker FROM pg_database WHERE datname=:name"
                        ),
                        {"name": name},
                    )
                )
                .mappings()
                .first()
            )
            if row:
                if row["owner"] != self.env["PGUSER"] or row["marker"] != marker:
                    raise DeploymentError(
                        "Database name already exists without matching ownership; refusing to use it"
                    )
            else:
                if record.get("database_ready"):
                    raise DeploymentError(
                        "Registered business database is missing; restore it rather than create an empty replacement"
                    )
                record.update(identity, database_create_requested=True)
                await entry.save(record)
                await conn.execute(
                    text(
                        f"CREATE DATABASE {identifier(name)} OWNER {identifier(self.env['PGUSER'])}"
                    )
                )
                # A crash between CREATE and COMMENT leaves an unmarked database:
                # a retry refuses adoption until an operator verifies ownership.
                await conn.execute(
                    text(f"COMMENT ON DATABASE {identifier(name)} IS '{marker}'")
                )
        record.update(identity, database_ready=True)
        record.setdefault("client_token", str(uuid.uuid4()))
        await entry.save(record)
        return name

    async def encryption_key(self, name: str, *, existing_key: str = "") -> str:
        """Recover an old channel key for legacy reads; never generate a new one."""
        if existing_key:
            try:
                Fernet(existing_key.encode())
            except (ValueError, TypeError):
                raise DeploymentError(
                    "Existing Runtime channel encryption key is invalid"
                ) from None
        engine = postgres_engine(self.runtime_url(name))
        try:
            async with engine.connect() as conn:
                table = await conn.scalar(
                    text("SELECT to_regclass('mpa_deployment_settings')")
                )
                key = (
                    await conn.scalar(
                        text(
                            "SELECT value FROM mpa_deployment_settings WHERE name='channel_state_encryption_key'"
                        )
                    )
                    if table
                    else None
                )
                if not key:
                    return existing_key
                try:
                    Fernet(key.encode())
                except (ValueError, TypeError, AttributeError):
                    raise DeploymentError(
                        "Stored channel encryption key is invalid; restore it rather than rotate it"
                    ) from None
                if existing_key and existing_key != key:
                    raise DeploymentError(
                        "Stored channel encryption key differs from the active Runtime; refusing to rotate it"
                    )
                return key
        finally:
            await engine.dispose()

    async def seed_runtime(self, name: str, agent_id: str, runtime_id: str):
        from veadk.integrations.mpa.managed.metadata import MpaMetaStore

        store = MpaMetaStore(postgres_engine(self.runtime_url(name)))
        try:
            await store.ensure_schema()
            existing = await store.get(agent_id)
            if existing and existing.get("runtime_id") not in (None, "", runtime_id):
                raise DeploymentError(
                    "Business database belongs to another Runtime; explicit migration is required"
                )
            await store.fill_empty(
                mpa_agent_id=agent_id, values={"runtime_id": runtime_id}
            )
        finally:
            await store.close()

    async def close(self):
        await self.admin.dispose()
