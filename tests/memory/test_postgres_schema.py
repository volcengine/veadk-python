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

from unittest.mock import patch

import pytest

from veadk.configs.database_configs import PostgreSqlConfig
from veadk.memory.short_term_memory_backends.postgresql_backend import (
    PostgreSqlSTMBackend,
    _validate_schema,
    _with_search_path,
)

_PKG = "veadk.memory.short_term_memory_backends.postgresql_backend"


def _config(schema=""):
    return PostgreSqlConfig(
        host="h", port=5432, user="u", password="p", database="db", schema=schema
    )


def test_schema_env(monkeypatch):
    """The schema is populated from DATABASE_POSTGRESQL_SCHEMA."""
    monkeypatch.setenv("DATABASE_POSTGRESQL_SCHEMA", "tenant_42")
    assert PostgreSqlConfig().schema == "tenant_42"


def test_with_search_path_pins_via_server_settings():
    """search_path is pinned through the asyncpg startup parameter."""
    out = _with_search_path({}, "tenant_42")
    assert out["connect_args"]["server_settings"]["search_path"] == "tenant_42"


def test_with_search_path_preserves_existing_connect_args():
    """Existing connect_args / server_settings are kept, not clobbered."""
    given = {
        "pool_size": 3,
        "connect_args": {"server_settings": {"application_name": "veadk"}},
    }
    out = _with_search_path(given, "tenant_42")
    assert out["pool_size"] == 3
    ss = out["connect_args"]["server_settings"]
    assert ss["application_name"] == "veadk"
    assert ss["search_path"] == "tenant_42"
    # original dict is not mutated
    assert given["connect_args"]["server_settings"] == {"application_name": "veadk"}


@pytest.mark.parametrize("bad", ["has-dash", "has space", "1leading", 'quote";x', ""])
def test_invalid_schema_rejected(bad):
    with pytest.raises(ValueError):
        _validate_schema(bad)


def test_backend_pins_when_schema_set():
    """With a schema: create it, then build the service with search_path pinned."""
    with (
        patch(f"{_PKG}._ensure_schema") as ensure,
        patch(f"{_PKG}.DatabaseSessionService") as dss,
    ):
        backend = PostgreSqlSTMBackend(postgresql_config=_config(schema="tenant_42"))
        _ = backend.session_service
        ensure.assert_called_once_with(backend._db_url, "tenant_42")
        kwargs = dss.call_args.kwargs
        assert kwargs["connect_args"]["server_settings"]["search_path"] == "tenant_42"


def test_backend_plain_without_schema():
    """Without a schema: legacy behavior, no schema creation, no search_path."""
    with (
        patch(f"{_PKG}._ensure_schema") as ensure,
        patch(f"{_PKG}.DatabaseSessionService") as dss,
    ):
        backend = PostgreSqlSTMBackend(postgresql_config=_config(schema=""))
        _ = backend.session_service
        ensure.assert_not_called()
        assert "connect_args" not in dss.call_args.kwargs
