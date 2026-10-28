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

import os
from unittest.mock import Mock

import pytest
from sqlalchemy.engine import make_url

from veadk.configs.database_configs import PostgreSqlConfig
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.memory.short_term_memory_backends.postgresql_backend import (
    PostgreSqlSTMBackend,
)

BACKEND = "veadk.memory.short_term_memory_backends.postgresql_backend"


@pytest.fixture(autouse=True)
def isolated_database_environment(monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("DATABASE_POSTGRESQL_"):
            monkeypatch.delenv(key)


@pytest.mark.parametrize("async_driver", [False, True])
@pytest.mark.parametrize(
    "host,port,expected_host,expected_port",
    [
        ("db.example.test", 5432, "db.example.test", 5432),
        ("db.example.test", 6543, "db.example.test", 6543),
        ("db.example.test:5432", 5432, "db.example.test", 5432),
        ("db.example.test:6543", 5432, "db.example.test", 6543),
        ("db.example.test:6543", 7654, "db.example.test", 6543),
        ("127.0.0.1:5432", 5432, "127.0.0.1", 5432),
        ("db.example.test:1", 5432, "db.example.test", 1),
        ("db.example.test:65535", 5432, "db.example.test", 65535),
    ],
)
def test_endpoint(host, port, expected_host, expected_port, async_driver, monkeypatch):
    monkeypatch.setattr(f"{BACKEND}.should_use_async_db_drivers", lambda: async_driver)
    config = PostgreSqlConfig(
        host=host, port=port, user="fixture-user", password="fixture@:/", database="db"
    )
    backend = PostgreSqlSTMBackend(postgresql_config=config)
    url = make_url(backend._db_url)
    assert (url.host, url.port) == (expected_host, expected_port)
    assert url.drivername == ("postgresql+asyncpg" if async_driver else "postgresql")
    assert (url.username, url.password, url.database) == (
        "fixture-user",
        "fixture@:/",
        "db",
    )
    assert (config.host, config.port) == (host, port)


@pytest.mark.parametrize(
    "host",
    [
        "db.example.test:",
        "db.example.test:abc",
        "db.example.test:0",
        "db.example.test:-1",
        "db.example.test:65536",
        "db.example.test:5432.0",
        "db.example.test:１２３",
        ":5432",
    ],
)
def test_invalid_embedded_port(host):
    with pytest.raises(ValueError, match="PostgreSQL"):
        PostgreSqlSTMBackend(postgresql_config=PostgreSqlConfig(host=host))


def test_environment_reaches_session_service(monkeypatch):
    monkeypatch.setenv("DATABASE_POSTGRESQL_HOST", "db.example.test:6543")
    monkeypatch.setenv("DATABASE_POSTGRESQL_PORT", "7654")
    service = Mock()
    monkeypatch.setattr(f"{BACKEND}.DatabaseSessionService", service)
    ShortTermMemory(backend="postgresql")
    url = make_url(service.call_args.kwargs["db_url"])
    assert (url.host, url.port) == ("db.example.test", 6543)


@pytest.mark.asyncio
async def test_explicit_db_url_bypasses_host_configuration(monkeypatch):
    monkeypatch.setenv("DATABASE_POSTGRESQL_HOST", "db.example.test:invalid")
    url = "sqlite+aiosqlite:///:memory:"
    service = ShortTermMemory(db_url=url).session_service
    try:
        # Assert URL precedence through the owned service, not its internal constructor.
        assert service.db_engine.url == make_url(url)
        session = await service.create_session(app_name="app", user_id="user")
        reloaded = await service.get_session(
            app_name="app", user_id="user", session_id=session.id
        )
        assert reloaded is not None and reloaded.id == session.id
    finally:
        await service.db_engine.dispose()
