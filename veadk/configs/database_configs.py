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

    cert_path: str = ""

    use_ssl: bool = True

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

    username: str | None = None

    password: str = ""

    db: int = 0

    secret_token: str = ""
    """STS token for Redis auth, not supported yet."""


class Mem0Config(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_MEM0_")

    api_key: str = ""
    """Mem0 API key"""

    api_key_id: str = ""

    project_id: str = ""

    base_url: str = ""  # "https://api.mem0.ai/v1"


class VikingKnowledgebaseConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_VIKING_")

    project: str = "default"
    """User project in Volcengine console web."""

    region: str = "cn-beijing"


class TOSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_TOS_")

    endpoint: str = "tos-cn-beijing.volces.com"

    region: str = "cn-beijing"

    def model_post_init(self, __context) -> None:
        cloud_provider = os.getenv("CLOUD_PROVIDER", "volces").lower()

        if cloud_provider == "byteplus":
            self.endpoint = "tos-ap-southeast-1.bytepluses.com"
            self.region = "ap-southeast-1"

    @cached_property
    def bucket(self) -> str:
        _bucket = os.getenv("DATABASE_TOS_BUCKET") or DEFAULT_TOS_BUCKET_NAME

        VeTOS(bucket_name=_bucket).create_bucket()
        return _bucket


class NormalTOSConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_TOS_")

    endpoint: str = "tos-cn-beijing.volces.com"

    region: str = "cn-beijing"

    bucket: str


class TOSVectorConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="DATABASE_TOS_VECTOR_")

    endpoint: str = "tosvectors-cn-beijing.volces.com"

    region: str = "cn-beijing"

    security_token: str | None = None

    max_retry_count: int = 3

    max_connections: int = 1024

    connection_time: int = 10

    enable_verify_ssl: bool = True

    dns_cache_time: int = 15

    proxy_host: str | None = None

    proxy_port: int | None = None

    proxy_username: str | None = None

    proxy_password: str | None = None

    high_latency_log_threshold: int = 100

    socket_timeout: int = 30

    credentials_provider: object | None = None

    except100_continue_threshold: int = 65536

    user_agent_product_name: str | None = None

    user_agent_soft_name: str | None = None

    user_agent_soft_version: str | None = None

    user_agent_customized_key_values: dict[str, str] | None = None


class MSENacosConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NACOS_")

    endpoint: str
    port: str = "8848"  # hard coding by Volcengine MSE Nacos service

    username: str = "nacos"  # hard coding by Volcengine MSE Nacos service
    password: str
