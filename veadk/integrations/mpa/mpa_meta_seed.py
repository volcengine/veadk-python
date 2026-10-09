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

"""Seed the mpa-agent ``mpa_meta`` table so the runtime skips ``GetMpaInstanceConf``.

The veadk-version ``mpa-agent`` needs no control-plane ``mi-*`` record. On
startup ``app/services/mpa_meta.py`` skips the Arkclaw TOP call once the
``mpa_meta`` row already carries the required instance-config fields
(``mpa_instance_conf_ready``). This module writes that row directly with
fill-empty semantics equivalent to the runtime's ``MpaMetaStore.fill_empty``.

The table definition mirrors ``mpa-agent`` ``app/stores/mpa_meta.py`` exactly
(column names, types, and server defaults). If the runtime's table shape
changes, update this definition in the same change.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import (
    Column,
    DateTime,
    MetaData,
    String,
    Table,
    func,
    insert,
    select,
)
from sqlalchemy.engine import Engine

# The seven fields that ``mpa_instance_conf_ready`` requires to be non-empty
# (mirrors ``MpaInstanceConf.to_record`` in mpa-agent's arkclaw client).
REQUIRED_META_FIELDS: tuple[str, ...] = (
    "account_id",
    "resource_account_id",
    "runtime_id",
    "public_endpoint",
    "private_endpoint",
    "runtime_api_key",
    "apig_instance_id",
)

metadata = MetaData()

# Mirrors mpa-agent app/stores/mpa_meta.py:mpa_meta (columns, types, defaults).
mpa_meta_table = Table(
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

# Columns the seeder may fill, excluding the primary key and timestamps.
_SEEDABLE_COLUMNS: tuple[str, ...] = tuple(
    column.name
    for column in mpa_meta_table.columns
    if column.name not in {"mpa_agent_id", "created_at", "updated_at"}
)


class MpaMetaSeedError(RuntimeError):
    """Raised when the mpa_meta row cannot be seeded."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def seed_mpa_meta(
    engine: Engine,
    *,
    mpa_agent_id: str,
    values: dict[str, Any],
    require_complete: bool = True,
) -> dict[str, Any]:
    """Seed one ``mpa_meta`` row with fill-empty, idempotent semantics.

    Args:
        engine: A synchronous SQLAlchemy engine pointing at the mpa-agent
            PostgreSQL database (or an equivalent sqlite engine in tests).
        mpa_agent_id: The ``mi-*`` instance id (primary key). Required.
        values: Field values to write. Only keys in the seedable column set are
            considered; unknown keys are ignored.
        require_complete: When True (default), assert that all seven
            ``REQUIRED_META_FIELDS`` are present and non-empty before writing;
            abort with :class:`MpaMetaSeedError` otherwise, leaving no row.

    Returns:
        The resulting row as a dict.

    Behavior:
        - Never overwrites a non-empty existing field (fill-empty).
        - Creates the table if it does not exist (matches runtime ``ensure_schema``).
        - Idempotent: re-seeding a complete row is a no-op for its values.
    """
    mpa_agent_id = (mpa_agent_id or "").strip()
    if not mpa_agent_id:
        raise MpaMetaSeedError("mpa_agent_id is required")

    sanitized = {
        key: str(values.get(key) or "").strip()
        for key in _SEEDABLE_COLUMNS
        if key in values
    }

    if require_complete:
        missing = [
            field
            for field in REQUIRED_META_FIELDS
            if not sanitized.get(field, "").strip()
        ]
        if missing:
            raise MpaMetaSeedError(
                "cannot seed mpa_meta: unresolved required field(s): "
                + ", ".join(missing)
            )

    metadata.create_all(engine, tables=[mpa_meta_table])

    now = _utc_now()
    with engine.begin() as conn:
        existing = (
            conn.execute(
                select(mpa_meta_table).where(
                    mpa_meta_table.c.mpa_agent_id == mpa_agent_id
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
                conn.execute(
                    mpa_meta_table.update()
                    .where(mpa_meta_table.c.mpa_agent_id == mpa_agent_id)
                    .values(**updates)
                )
        else:
            initial = {key: sanitized.get(key, "") for key in _SEEDABLE_COLUMNS}
            conn.execute(
                insert(mpa_meta_table).values(
                    mpa_agent_id=mpa_agent_id,
                    created_at=now,
                    updated_at=now,
                    **initial,
                )
            )
        row = (
            conn.execute(
                select(mpa_meta_table).where(
                    mpa_meta_table.c.mpa_agent_id == mpa_agent_id
                )
            )
            .mappings()
            .one()
        )
    return dict(row)


def overwrite_mpa_meta(
    engine: Engine,
    *,
    mpa_agent_id: str,
    values: dict[str, Any],
) -> dict[str, Any]:
    """Overwrite ``mpa_meta`` fields on an existing row with **non-empty** values.

    Used after the runtime is Ready to swap phase-1 placeholders
    (runtime_id/endpoints/api_key/apig_instance_id) for the real
    deploy-resolved values. Empty resolved values are intentionally skipped so
    they never clear a phase-1 placeholder — the seven required fields must stay
    non-empty for ``mpa_instance_conf_ready`` (FR-19). The row must already exist
    (created in phase 1).

    Args:
        engine: A synchronous SQLAlchemy engine.
        mpa_agent_id: The ``mi-*`` instance id (primary key). Required.
        values: Field values to overwrite; empty values are ignored.

    Returns:
        The resulting row as a dict.
    """
    mpa_agent_id = (mpa_agent_id or "").strip()
    if not mpa_agent_id:
        raise MpaMetaSeedError("mpa_agent_id is required")

    # Only overwrite with non-empty values; empty resolved fields keep the
    # phase-1 placeholder so readiness (7 non-empty fields) is never broken.
    sanitized = {
        key: str(values.get(key) or "").strip()
        for key in _SEEDABLE_COLUMNS
        if key in values and str(values.get(key) or "").strip()
    }

    metadata.create_all(engine, tables=[mpa_meta_table])

    now = _utc_now()
    with engine.begin() as conn:
        existing = (
            conn.execute(
                select(mpa_meta_table).where(
                    mpa_meta_table.c.mpa_agent_id == mpa_agent_id
                )
            )
            .mappings()
            .first()
        )
        if not existing:
            raise MpaMetaSeedError(
                f"overwrite_mpa_meta: no row found for {mpa_agent_id}; "
                "phase-1 seed must run first"
            )
        if sanitized:
            updates = dict(sanitized)
            updates["updated_at"] = now
            conn.execute(
                mpa_meta_table.update()
                .where(mpa_meta_table.c.mpa_agent_id == mpa_agent_id)
                .values(**updates)
            )
        row = (
            conn.execute(
                select(mpa_meta_table).where(
                    mpa_meta_table.c.mpa_agent_id == mpa_agent_id
                )
            )
            .mappings()
            .one()
        )
    return dict(row)
