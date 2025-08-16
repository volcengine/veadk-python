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

from __future__ import annotations

from typing import Any

import redis
from pydantic import BaseModel, Field
from typing_extensions import override

from veadk.config import getenv
from veadk.utils.logger import get_logger

from ..base_database import BaseDatabase

logger = get_logger(__name__)


class RedisDatabaseConfig(BaseModel):
    host: str = Field(
        default_factory=lambda: getenv("DATABASE_REDIS_HOST"),
        description="Redis host",
    )
    port: int = Field(
        default_factory=lambda: int(getenv("DATABASE_REDIS_PORT")),
        description="Redis port",
    )
    db: int = Field(
        default_factory=lambda: int(getenv("DATABASE_REDIS_DB")),
        description="Redis db",
    )
    password: str = Field(
        default_factory=lambda: getenv("DATABASE_REDIS_PASSWORD"),
        description="Redis password",
    )
    decode_responses: bool = Field(
        default=True,
        description="Redis decode responses",
    )


class RedisDatabase(BaseModel, BaseDatabase):
    config: RedisDatabaseConfig = Field(default_factory=RedisDatabaseConfig)

    def model_post_init(self, context: Any, /) -> None:
        try:
            self._client = redis.StrictRedis(
                host=self.config.host,
                port=self.config.port,
                db=self.config.db,
                password=self.config.password,
                decode_responses=self.config.decode_responses,
            )

            self._client.ping()
            logger.info("Connected to Redis successfully.")
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise e

    @override
    def add(self, key: str, value: str, **kwargs):
        try:
            self._client.rpush(key, value)
        except Exception as e:
            logger.error(f"Failed to add value to Redis list key `{key}`: {e}")
            raise e

    @override
    def query(self, key: str, query: str = "", **kwargs) -> list:
        try:
            result = self._client.lrange(key, 0, -1)
            return result  # type: ignore
        except Exception as e:
            logger.error(f"Failed to search from Redis list key '{key}': {e}")
            raise e

    @override
    def delete(self, **kwargs):
        """Delete Redis list key based on app_name, user_id and session_id, or directly by key."""
        key = kwargs.get("key")
        if key is None:
            app_name = kwargs.get("app_name")
            user_id = kwargs.get("user_id")
            session_id = kwargs.get("session_id")
            key = f"{app_name}:{user_id}:{session_id}"

        try:
            # For simple key deletion
            # We use sync Redis client to delete the key
            # so the result will be `int`
            result = self._client.delete(key)

            if result > 0:  # type: ignore
                logger.info(f"Deleted key `{key}` from Redis.")
            else:
                logger.info(f"Key `{key}` not found in Redis. Skipping deletion.")
        except Exception as e:
            logger.error(f"Failed to delete key `{key}`: {e}")
            raise e
