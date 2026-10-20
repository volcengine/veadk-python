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

"""Explicit management database setup and non-destructive registry copying."""

from __future__ import annotations

import asyncio

from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from .config import ADMIN_DATABASE_NAME, Profile, management_admin_url
from .database import (
    DeploymentError,
    account_networks,
    agent_deployments,
    identifier,
    postgres_engine,
)
from .registry import shared_apig

TABLES = (shared_apig, account_networks, agent_deployments)


def validate_tables(names: set[str], *, source: bool):
    expected = {table.name for table in TABLES}
    if source and not expected.issubset(names):
        raise DeploymentError("Source registry is missing required tables")
    if not source and names - expected:
        raise DeploymentError("Management database contains unrelated public objects")


def missing_rows(table, source: list[dict], target: list[dict]) -> list[dict]:
    if table is agent_deployments and any(
        row["record"].get("pending") for row in source
    ):
        raise DeploymentError(
            "Finish or reconcile pending Runtime deployments with the original registry before migration"
        )
    keys = [column.name for column in table.primary_key]
    original = {tuple(row[key] for key in keys): row for row in source}
    existing = {tuple(row[key] for key in keys): row for row in target}
    if any(original.get(key) != row for key, row in existing.items()):
        raise DeploymentError(
            "Target registry conflict; no registry records were copied"
        )
    return [row for key, row in original.items() if key not in existing]


async def create_database(engine, owner: str):
    async with engine.connect() as conn:
        await conn.execute(text("SET statement_timeout = '30s'"))
        query = text(
            "SELECT pg_get_userbyid(datdba) FROM pg_database WHERE datname = :name"
        )
        actual = await conn.scalar(query, {"name": ADMIN_DATABASE_NAME})
        if actual is None:
            try:
                await conn.execute(
                    text(
                        f"CREATE DATABASE {identifier(ADMIN_DATABASE_NAME)} OWNER {identifier(owner)}"
                    )
                )
            except DBAPIError as exc:
                # Another initializer may have created the same fixed database.
                if getattr(exc.orig, "sqlstate", None) != "42P04":
                    raise
            actual = await conn.scalar(query, {"name": ADMIN_DATABASE_NAME})
        if actual != owner:
            raise DeploymentError("Management database belongs to another owner")


async def prepare_transaction(conn):
    await conn.execute(text("SET LOCAL search_path = public"))
    await conn.execute(text("SET LOCAL lock_timeout = '5s'"))
    await conn.execute(text("SET LOCAL statement_timeout = '30s'"))


async def table_names(conn):
    result = await conn.execute(
        text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')"
        )
    )
    return set(result.scalars())


async def copy_records(source, target) -> dict[str, int]:
    """The caller owns the destination transaction; never write to the source."""
    await prepare_transaction(source)
    validate_tables(await table_names(source), source=True)
    names = ", ".join(f"public.{identifier(table.name)}" for table in TABLES)
    # SHARE blocks source DML without modifying source rows. Writers must remain
    # stopped after this transaction until all consumers have switched endpoints.
    await source.execute(text(f"LOCK TABLE {names} IN SHARE MODE"))
    await target.execute(text(f"LOCK TABLE {names} IN EXCLUSIVE MODE"))
    counts = {}
    for table in TABLES:
        original = [
            dict(row) for row in (await source.execute(select(table))).mappings()
        ]
        existing = [
            dict(row) for row in (await target.execute(select(table))).mappings()
        ]
        missing = missing_rows(table, original, existing)
        if missing:
            await target.execute(table.insert(), missing)
        counts[table.name] = len(original)
    return counts


async def initialize_admin_database(
    profile: Profile, *, source_url: str = "", maintenance_url: str = ""
):
    """Create the fixed database; optionally copy all registry rows atomically."""
    maintenance = management_admin_url(profile, maintenance_url)
    target_url = make_url(profile.shared_url)
    if source_url:
        try:
            source = make_url(source_url)
            if (
                source.get_backend_name() != "postgresql"
                or not source.host
                or not source.database
            ):
                raise ValueError
            if (source.host.lower(), source.port or 5432, source.database) == (
                (target_url.host or "").lower(),
                target_url.port or 5432,
                target_url.database,
            ):
                raise ValueError
        except Exception:
            raise DeploymentError(
                "Source must be a different PostgreSQL registry database"
            ) from None
    engines = []
    try:
        admin = postgres_engine(
            maintenance, isolation_level="AUTOCOMMIT", connect_args={"timeout": 10}
        )
        engines.append(admin)

        async def initialize():
            await create_database(admin, target_url.username or "")
            target = postgres_engine(profile.shared_url, connect_args={"timeout": 10})
            engines.append(target)
            async with target.begin() as conn:
                await prepare_transaction(conn)
                # Serialize schema setup and copy jobs, with the same lock timeout.
                await conn.execute(text("SELECT pg_advisory_xact_lock(783435789212)"))
                validate_tables(await table_names(conn), source=False)
                for table in TABLES:
                    await conn.run_sync(
                        lambda sync, t=table: t.create(sync, checkfirst=True)
                    )
                if not source_url:
                    return {"database": ADMIN_DATABASE_NAME, "copied": False}
                source_engine = postgres_engine(
                    source_url, connect_args={"timeout": 10}
                )
                engines.append(source_engine)
                async with source_engine.begin() as source_conn:
                    counts = await copy_records(source_conn, conn)
                return {"database": ADMIN_DATABASE_NAME, "copied": True, "rows": counts}

        return await asyncio.wait_for(initialize(), timeout=120)
    except DeploymentError:
        raise
    except Exception:
        raise DeploymentError(
            "Management database preparation failed; check connectivity, owner/CREATEDB permissions, "
            "source tables and active writers, then retry. No source records were changed"
        ) from None
    finally:
        for engine in reversed(engines):
            await engine.dispose()
