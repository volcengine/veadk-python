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

"""Tests for the mpa_meta seeder (FR-4, VC-6/VC-7/VC-8/VC-9)."""

import pytest
from sqlalchemy import create_engine, select

from veadk.integrations.mpa.mpa_meta_seed import (
    REQUIRED_META_FIELDS,
    MpaMetaSeedError,
    mpa_meta_table,
    seed_mpa_meta,
)


def _engine():
    # File-less shared in-memory sqlite for a single test.
    return create_engine("sqlite://")


def _complete_values() -> dict:
    return {
        "account_id": "2100000001",
        "resource_account_id": "2100000001",
        "runtime_id": "app-abc",
        "public_endpoint": "https://app.example.com",
        "private_endpoint": "https://app.example.com",
        "runtime_api_key": "rk-xyz",
        "apig_instance_id": "gw-123",
    }


def _row(engine, mpa_agent_id: str) -> dict | None:
    from sqlalchemy.exc import OperationalError

    with engine.connect() as conn:
        try:
            row = (
                conn.execute(
                    select(mpa_meta_table).where(
                        mpa_meta_table.c.mpa_agent_id == mpa_agent_id
                    )
                )
                .mappings()
                .first()
            )
        except OperationalError:
            # Table never created (e.g. seeding aborted before write).
            return None
    return dict(row) if row else None


def test_seed_writes_seven_required_fields_on_empty_table() -> None:
    """VC-6: an empty table gets all seven required fields written correctly."""
    engine = _engine()
    values = _complete_values()

    seed_mpa_meta(engine, mpa_agent_id="mi-1", values=values)

    row = _row(engine, "mi-1")
    assert row is not None
    for field in REQUIRED_META_FIELDS:
        assert row[field] == values[field]


def test_seed_private_can_mirror_public() -> None:
    """VC-7/FR-11: private_endpoint equal to public_endpoint is persisted as-is."""
    engine = _engine()
    values = _complete_values()
    values["private_endpoint"] = values["public_endpoint"]

    seed_mpa_meta(engine, mpa_agent_id="mi-1", values=values)

    row = _row(engine, "mi-1")
    assert row["private_endpoint"] == row["public_endpoint"]


def test_seed_is_idempotent_and_does_not_overwrite_nonempty() -> None:
    """VC-9: complete row is not overwritten; partial row fills only empty fields."""
    engine = _engine()
    first = _complete_values()
    seed_mpa_meta(engine, mpa_agent_id="mi-1", values=first)

    # Second seed with a different key must not overwrite the existing non-empty
    # runtime_api_key, and unrelated fields stay intact.
    second = dict(first)
    second["runtime_api_key"] = "rk-should-not-replace"
    seed_mpa_meta(engine, mpa_agent_id="mi-1", values=second)

    row = _row(engine, "mi-1")
    assert row["runtime_api_key"] == "rk-xyz"


def test_seed_fills_only_empty_fields_on_partial_row() -> None:
    """VC-9: a pre-existing partial row only gets its empty fields filled."""
    engine = _engine()
    # Insert a partial row directly (runtime_api_key + apig empty).
    partial = _complete_values()
    partial["runtime_api_key"] = ""
    partial["apig_instance_id"] = ""
    # Seeding a partial set should not assert-fail; it fills what it can and the
    # caller is responsible for completeness. Use the incremental API.
    seed_mpa_meta(
        engine,
        mpa_agent_id="mi-1",
        values=partial,
        require_complete=False,
    )
    # Now complete it.
    seed_mpa_meta(engine, mpa_agent_id="mi-1", values=_complete_values())

    row = _row(engine, "mi-1")
    assert row["runtime_api_key"] == "rk-xyz"
    assert row["apig_instance_id"] == "gw-123"
    # A field already set on the first pass keeps its original value.
    assert row["runtime_id"] == "app-abc"


def test_seed_aborts_when_required_field_unresolved() -> None:
    """VC-8: a missing/empty required field aborts before writing any row."""
    engine = _engine()
    values = _complete_values()
    values["runtime_api_key"] = ""

    with pytest.raises(MpaMetaSeedError, match="runtime_api_key"):
        seed_mpa_meta(engine, mpa_agent_id="mi-1", values=values)

    # Nothing should have been written.
    assert _row(engine, "mi-1") is None


def test_seed_requires_mpa_agent_id() -> None:
    """A blank mpa_agent_id is rejected."""
    engine = _engine()
    with pytest.raises(MpaMetaSeedError, match="mpa_agent_id"):
        seed_mpa_meta(engine, mpa_agent_id="  ", values=_complete_values())
