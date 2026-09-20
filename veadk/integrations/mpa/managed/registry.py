"""Account/region registry. All provisioners must use the same PostgreSQL DB."""

from __future__ import annotations

import asyncio
import hashlib
import sys

if sys.version_info >= (3, 11):
    from asyncio import timeout
else:
    from async_timeout import timeout
from contextlib import asynccontextmanager
from typing import Any

from sqlalchemy import JSON, Column, MetaData, String, Table, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

metadata = MetaData()
shared_apig = Table(
    "mpa_account_apig",
    metadata,
    Column("account_id", String(128), primary_key=True),
    Column("region", String(64), primary_key=True),
    Column("record", JSON, nullable=False),
)


class SharedAPIGRegistry:
    def __init__(self, engine: AsyncEngine):
        if engine.dialect.name != "postgresql":
            raise ValueError("Shared APIG registry requires PostgreSQL")
        self.engine = engine

    @classmethod
    def from_url(cls, url: str) -> SharedAPIGRegistry:
        if not url:
            raise ValueError(
                "SHARED_APIG_DATABASE_URL is required for automatic APIG provisioning"
            )
        parsed = make_url(url)
        if parsed.get_backend_name() != "postgresql":
            raise ValueError("SHARED_APIG_DATABASE_URL must use PostgreSQL")
        return cls(
            create_async_engine(
                parsed.set(drivername="postgresql+asyncpg"),
                pool_pre_ping=True,
                hide_parameters=True,
            )
        )

    async def initialize(self):
        async with self.engine.begin() as conn:
            # Serialize concurrent first-time schema setup too.
            await conn.execute(text("SELECT pg_advisory_xact_lock(783435789210)"))
            await conn.run_sync(metadata.create_all)

    @asynccontextmanager
    async def lock(self, account_id: str, region: str):
        key = int.from_bytes(
            hashlib.sha256(f"mpa-apig:{account_id}:{region}".encode()).digest()[:8],
            "big",
            signed=True,
        )
        async with self.engine.connect() as conn:
            acquired = False
            try:
                async with timeout(60):
                    while not acquired:
                        acquired = bool(
                            await conn.scalar(
                                text("SELECT pg_try_advisory_lock(:key)"), {"key": key}
                            )
                        )
                        await conn.commit()
                        if not acquired:
                            await asyncio.sleep(0.5)
                yield RegistryEntry(conn, account_id, region)
            finally:
                # Session locks survive commits so creation intent is durable
                # before a cloud call. Never return a locked session to the pool.
                try:
                    await conn.rollback()
                    # Also unlock after cancellation during acquisition: the
                    # server may have acquired it before the client saw success.
                    await conn.execute(
                        text("SELECT pg_advisory_unlock(:key)"), {"key": key}
                    )
                    await conn.commit()
                except BaseException:
                    await conn.invalidate()
                    raise

    async def close(self):
        await self.engine.dispose()


class RegistryEntry:
    def __init__(self, conn: AsyncConnection, account_id: str, region: str):
        self.conn, self.account_id, self.region = conn, account_id, region

    async def read(self) -> dict[str, Any]:
        row = await self.conn.scalar(
            select(shared_apig.c.record).where(
                shared_apig.c.account_id == self.account_id,
                shared_apig.c.region == self.region,
            )
        )
        await self.conn.commit()
        return dict(row or {})

    async def save(self, record: dict[str, Any]):
        stmt = (
            insert(shared_apig)
            .values(
                account_id=self.account_id,
                region=self.region,
                record=record,
            )
            .on_conflict_do_update(
                index_elements=["account_id", "region"],
                set_={"record": record},
            )
        )
        await self.conn.execute(stmt)
        await self.conn.commit()
