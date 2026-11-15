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

import pytest
from sqlalchemy.engine import make_url

from veadk.configs.database_configs import MysqlConfig
from veadk.memory.short_term_memory_backends.mysql_backend import MysqlSTMBackend

BACKEND = "veadk.memory.short_term_memory_backends.mysql_backend"


@pytest.fixture(autouse=True)
def isolated_database_environment(monkeypatch):
    for key in tuple(os.environ):
        if key.startswith("DATABASE_MYSQL_"):
            monkeypatch.delenv(key)


def _backend_url(monkeypatch, async_driver, **config):
    monkeypatch.setattr(f"{BACKEND}.should_use_async_db_drivers", lambda: async_driver)
    mysql_config = MysqlConfig(
        host="db.example.test:3307",
        user="fixture-user",
        password="fixture@:/",
        database="db",
        **config,
    )
    return make_url(MysqlSTMBackend(mysql_config=mysql_config)._db_url)


@pytest.mark.parametrize("async_driver", [False, True])
def test_default_charset_is_sent_to_driver(async_driver, monkeypatch):
    url = _backend_url(monkeypatch, async_driver)
    assert url.drivername == ("mysql+aiomysql" if async_driver else "mysql+pymysql")
    assert url.query == {"charset": "utf8mb4"}
    assert (url.host, url.port, url.database) == ("db.example.test", 3307, "db")
    assert (url.username, url.password) == ("fixture-user", "fixture@:/")


@pytest.mark.parametrize("async_driver", [False, True])
def test_configured_charset_is_sent_to_driver(async_driver, monkeypatch):
    url = _backend_url(monkeypatch, async_driver, charset="latin1")
    assert url.query == {"charset": "latin1"}


def test_charset_from_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_MYSQL_CHARSET", "gbk")
    url = _backend_url(monkeypatch, False)
    assert url.query == {"charset": "gbk"}


@pytest.mark.parametrize("async_driver", [False, True])
def test_empty_charset_leaves_choice_to_driver(async_driver, monkeypatch):
    url = _backend_url(monkeypatch, async_driver, charset="")
    assert url.query == {}
