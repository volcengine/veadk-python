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
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict

from veadk.consts import DEFAULT_TOS_BUCKET_NAME
from veadk.integrations.ve_tos.ve_tos import VeTOS


class OpensearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_OPENSEARCH_")

    host: str = ""

    port: int = 9200

    username: str = ""

    password: str = ""

    secret_token: str = ""


class MysqlConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_MYSQL_")

    host: str = ""

    user: str = ""

    password: str = ""

    database: str = ""

    charset: str = "utf8"

    secret_token: str = ""
    """STS token for MySQL auth, not supported yet."""


class PostgreSqlConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_POSTGRESQL_")

    host: str = ""

    port: int = 5432

    user: str = ""

    password: str = ""

    database: str = ""

    secret_token: str = ""


class RedisConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_REDIS_")

    host: str = ""

    port: int = 6379

    password: str = ""

    db: int = 0

    secret_token: str = ""
    """STS token for Redis auth, not supported yet."""


class VikingKnowledgebaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_VIKING_")

    project: str = "default"
    """User project in Volcengine console web."""

    region: str = "cn-beijing"


class TOSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_TOS_")

    endpoint: str = "tos-cn-beijing.volces.com"

    region: str = "cn-beijing"

    @cached_property
    def bucket(self) -> str:
        _bucket = os.getenv("DATABASE_TOS_BUCKET") or DEFAULT_TOS_BUCKET_NAME

        VeTOS(bucket_name=_bucket).create_bucket()
        return _bucket
