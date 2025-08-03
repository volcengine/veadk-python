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

from veadk.utils.logger import get_logger

from .base_database import BaseDatabase

logger = get_logger(__name__)


class DatabaseBackend:
    OPENSEARCH = "opensearch"
    LOCAL = "local"
    MYSQL = "mysql"
    REDIS = "redis"
    VIKING = "viking"
    VIKING_MEM = "viking_mem"

    @classmethod
    def get_attr(cls) -> set[str]:
        return {
            value
            for attr, value in cls.__dict__.items()
            if not attr.startswith("__") and attr != "get_attr"
        }


class DatabaseFactory:
    @staticmethod
    def create(backend: str, config=None) -> BaseDatabase:
        if backend not in DatabaseBackend.get_attr():
            logger.warning(f"Unknown backend: {backend}), change backend to `local`")
            backend = "local"

        if backend == DatabaseBackend.LOCAL:
            from .local_database import LocalDataBase

            return LocalDataBase()
        if backend == DatabaseBackend.OPENSEARCH:
            from .vector.opensearch_vector_database import OpenSearchVectorDatabase

            return (
                OpenSearchVectorDatabase()
                if config is None
                else OpenSearchVectorDatabase(config=config)
            )
        if backend == DatabaseBackend.MYSQL:
            from .relational.mysql_database import MysqlDatabase

            return MysqlDatabase() if config is None else MysqlDatabase(config=config)
        if backend == DatabaseBackend.REDIS:
            from .kv.redis_database import RedisDatabase

            return RedisDatabase() if config is None else RedisDatabase(config=config)
        if backend == DatabaseBackend.VIKING:
            from .viking.viking_database import VikingDatabase

            return VikingDatabase() if config is None else VikingDatabase(config=config)

        if backend == DatabaseBackend.VIKING_MEM:
            from .viking.viking_memory_db import VikingDatabaseMemory

            return (
                VikingDatabaseMemory()
                if config is None
                else VikingDatabaseMemory(config=config)
            )
        else:
            raise ValueError(f"Unsupported database type: {backend}")
