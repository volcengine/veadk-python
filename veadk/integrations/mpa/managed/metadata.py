"""SQLAlchemy store for MPA instance metadata."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
)


metadata = MetaData()


mpa_meta = Table(
    "mpa_meta",
    metadata,
    Column("mpa_agent_id", String(128), primary_key=True),
    Column("account_id", String(128), nullable=False, server_default=""),
    Column("resource_account_id", String(128), nullable=False, server_default=""),
    Column("runtime_id", String(128), nullable=False, server_default=""),
    Column("public_endpoint", String(1024), nullable=False, server_default=""),
    Column("private_endpoint", String(1024), nullable=False, server_default=""),
    Column("runtime_api_key", String(512), nullable=False, server_default=""),
    Column("apig_instance_id", String(128), nullable=False, server_default=""),
    Column("im_gateway_endpoint", String(1024), nullable=False, server_default=""),
    Column("im_gateway_service_id", String(128), nullable=False, server_default=""),
    Column("im_gateway_upstream_id", String(128), nullable=False, server_default=""),
    Column("im_gateway_route_id", String(128), nullable=False, server_default=""),
    Column("agentkit_mode", Boolean, nullable=False, server_default="false"),
    Column("workspace_id", String(128), nullable=False, server_default=""),
    Column(
        "bootstrap_manifest_revision", String(128), nullable=False, server_default=""
    ),
    Column("readiness_phase", String(64), nullable=False, server_default="prepared"),
    Column("finalization_operation_id", String(128), nullable=False, server_default=""),
    Column("last_error_code", String(128), nullable=False, server_default=""),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
    Column(
        "updated_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    ),
)

_META_COLUMNS = tuple(
    column.name
    for column in mpa_meta.columns
    if column.name not in {"mpa_agent_id", "created_at", "updated_at"}
)

_BOOLEAN_COLUMNS = frozenset({"agentkit_mode"})
_CLEARABLE_COLUMNS = frozenset({"last_error_code"})


def _sanitize_meta_value(key: str, value: Any) -> Any:
    if key in _BOOLEAN_COLUMNS:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    return str(value or "").strip()


def _meta_default(key: str) -> Any:
    if key in _BOOLEAN_COLUMNS:
        return False
    if key == "readiness_phase":
        return "prepared"
    return ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class MpaMetaStore:
    """Persistent store for MPA instance metadata."""

    def __init__(self, engine: AsyncEngine) -> None:
        self.engine = engine
        self.sessionmaker = async_sessionmaker(engine, expire_on_commit=False)

    async def ensure_schema(self) -> None:
        async with self.engine.begin() as conn:
            await conn.run_sync(metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def get(self, mpa_agent_id: str) -> dict[str, Any] | None:
        async with self.sessionmaker() as session:
            row = (
                (
                    await session.execute(
                        select(mpa_meta).where(mpa_meta.c.mpa_agent_id == mpa_agent_id)
                    )
                )
                .mappings()
                .first()
            )
        return dict(row) if row else None

    async def fill_empty(
        self,
        *,
        mpa_agent_id: str,
        values: dict[str, Any],
    ) -> dict[str, Any]:
        mpa_agent_id = mpa_agent_id.strip()
        if not mpa_agent_id:
            raise ValueError("mpa_agent_id is required")
        now = utc_now()
        sanitized = {
            key: _sanitize_meta_value(key, values.get(key))
            for key in _META_COLUMNS
            if key in values
        }
        async with self.engine.begin() as conn:
            existing = (
                (
                    await conn.execute(
                        select(mpa_meta).where(mpa_meta.c.mpa_agent_id == mpa_agent_id)
                    )
                )
                .mappings()
                .first()
            )
            if existing:
                current = dict(existing)
                updates = {
                    key: value
                    for key, value in sanitized.items()
                    if value and not str(current.get(key) or "").strip()
                }
                if updates:
                    updates["updated_at"] = now
                    await conn.execute(
                        mpa_meta.update()
                        .where(mpa_meta.c.mpa_agent_id == mpa_agent_id)
                        .values(**updates)
                    )
                row = (
                    (
                        await conn.execute(
                            select(mpa_meta).where(
                                mpa_meta.c.mpa_agent_id == mpa_agent_id
                            )
                        )
                    )
                    .mappings()
                    .one()
                )
                return dict(row)

            initial = {
                key: sanitized.get(key, _meta_default(key)) for key in _META_COLUMNS
            }
            await conn.execute(
                insert(mpa_meta).values(
                    mpa_agent_id=mpa_agent_id,
                    **initial,
                    created_at=now,
                    updated_at=now,
                )
            )
            row = (
                (
                    await conn.execute(
                        select(mpa_meta).where(mpa_meta.c.mpa_agent_id == mpa_agent_id)
                    )
                )
                .mappings()
                .one()
            )
            return dict(row)
