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

"""
Longterm memory may use different databases, so we need to create
an adapter to abstract the database operations.
"""

import re

from pydantic import BaseModel, ConfigDict

from veadk.database.base_database import BaseDatabase
from veadk.database.database_factory import DatabaseBackend
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def format_collection_name(collection_name: str) -> str:
    replaced_str = re.sub(r"[- ]", "_", collection_name)
    return re.sub(r"[^a-z0-9_]", "", replaced_str).lower()


def build_index(**kwargs):
    """
    Build the index name for the long-term memory.
    """
    # TODO
    ...


def get_memory_adapter(backend: str):
    if backend == DatabaseBackend.REDIS:
        return MemoryKVDatabaseAdapter
    elif backend == DatabaseBackend.MYSQL:
        return MemoryRelationalDatabaseAdapter
    elif backend == DatabaseBackend.OPENSEARCH:
        return MemoryVectorDatabaseAdapter
    elif backend == DatabaseBackend.LOCAL:
        return MemoryLocalDatabaseAdapter
    elif backend == DatabaseBackend.VIKING_MEM:
        return MemoryVikingDBAdapter
    else:
        raise ValueError(f"Unknown backend: {backend}")


class MemoryKVDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        """Add texts to Redis.

        Key: app_name
        Field: app_name:user_id
        Value: text in List
        """
        key = f"{app_name}:{user_id}"

        try:
            for _content in content:
                self.database_client.add(key, _content)
            logger.debug(
                f"Successfully added {len(content)} texts to Redis list key `{key}`."
            )
        except Exception as e:
            logger.error(f"Failed to add texts to Redis list key `{key}`: {e}")
            raise e

    def query(self, query: str, app_name: str, user_id: str):
        key = f"{app_name}:{user_id}"
        top_k = 10

        try:
            result = self.database_client.query(key, query)
            # Get latest top_k records.
            # The data is stored in a Redis list, and the latest data is at the end of the list.
            return result[-top_k:]
        except Exception as e:
            logger.error(f"Failed to search from Redis list key '{key}': {e}")
            raise e

    def delete(self, app_name: str, user_id: str, session_id: str):
        try:
            self.database_client.delete(
                app_name=app_name, user_id=user_id, session_id=session_id
            )
            logger.info(
                f"Successfully deleted memory data for app {app_name}, user {user_id}, session {session_id}"
            )
        except Exception as e:
            logger.error(f"Failed to delete memory data: {e}")
            raise e


class MemoryRelationalDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def create_table(self, table_name: str):
        sql = f"""
            CREATE TABLE `{table_name}` (
                `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
                `data` TEXT NOT NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET={self.database_client.config.charset};
        """
        self.database_client.add(sql)

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        table = f"{app_name}_{user_id}"

        if not self.database_client.table_exists(table):
            logger.warning(f"Table {table} does not exist, creating...")
            self.create_table(table)

        for _content in content:
            sql = f"""
                INSERT INTO `{table}` (`data`)
                VALUES (%s);
                """
            self.database_client.add(sql, params=(_content,))
        logger.info(f"Successfully added {len(content)} texts to table {table}.")

    def query(self, query: str, app_name: str, user_id: str):
        """Search content from table app_name_user_id."""
        top_k = 10
        table = f"{app_name}_{user_id}"

        if not self.database_client.table_exists(table):
            logger.warning(
                f"querying {query}, but table `{table}` does not exist, returning empty list."
            )
            return []

        sql = f"""
            SELECT `data` FROM `{table}` ORDER BY `created_at` DESC LIMIT {top_k};
            """
        results = self.database_client.query(sql)
        return [item["data"] for item in results]

    def delete(self, app_name: str, user_id: str, session_id: str):
        table = f"{app_name}_{user_id}"
        try:
            self.database_client.delete(table=table)
            logger.info(f"Successfully deleted memory data from table {table}")
        except Exception as e:
            logger.error(f"Failed to delete memory data: {e}")
            raise e


class MemoryVectorDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        collection_name = format_collection_name(f"{app_name}_{user_id}")
        self.database_client.add(content, collection_name=collection_name)

    def query(self, query: str, app_name: str, user_id: str):
        collection_name = format_collection_name(f"{app_name}_{user_id}")
        top_k = 10
        return self.database_client.query(
            query, collection_name=collection_name, top_k=top_k
        )

    def delete(self, app_name: str, user_id: str, session_id: str):
        collection_name = format_collection_name(f"{app_name}_{user_id}")
        try:
            self.database_client.delete(collection_name=collection_name)
            logger.info(
                f"Successfully deleted vector memory database collection for app {app_name}"
            )
        except Exception as e:
            logger.error(f"Failed to delete vector memory database collection: {e}")
            raise e


class MemoryLocalDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        self.database_client.add(content)

    def query(self, query: str, app_name: str, user_id: str):
        return self.database_client.query(query)

    def delete(self, app_name: str, user_id: str, session_id: str):
        try:
            self.database_client.delete()
            logger.info(
                f"Successfully cleared local memory database for app {app_name}"
            )
        except Exception as e:
            logger.error(f"Failed to clear local memory database: {e}")
            raise e


class MemoryVikingDBAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(
        self, content: list[str], app_name: str, user_id: str, session_id: str, **kwargs
    ):
        kwargs.pop("user_id", None)

        collection_name = format_collection_name(f"{app_name}_{user_id}")
        self.database_client.add(
            content, collection_name=collection_name, user_id=user_id, **kwargs
        )

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        kwargs.pop("user_id", None)

        collection_name = format_collection_name(f"{app_name}_{user_id}")
        result = self.database_client.query(
            query, collection_name=collection_name, user_id=user_id, **kwargs
        )
        return result

    def delete(self, app_name: str, user_id: str, session_id: str):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        # todo: delete viking memory db
        ...
