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
Knowledgebase may use different databases, so we need to create
an adapter to abstract the database operations.
"""

import re
import time
from typing import BinaryIO, TextIO

from pydantic import BaseModel, ConfigDict

from veadk.database.base_database import BaseDatabase
from veadk.database.database_factory import DatabaseBackend
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def format_collection_name(collection_name: str) -> str:
    replaced_str = re.sub(r"[- ]", "_", collection_name)
    return re.sub(r"[^a-z0-9_]", "", replaced_str).lower()


def get_knowledgebase_adapter(backend: str):
    if backend == DatabaseBackend.REDIS:
        return KnowledgebaseKVDatabaseAdapter
    elif backend == DatabaseBackend.MYSQL:
        return KnowledgebaseRelationalDatabaseAdapter
    elif backend == DatabaseBackend.OPENSEARCH:
        return KnowledgebaseVectorDatabaseAdapter
    elif backend == DatabaseBackend.LOCAL:
        return KnowledgebaseLocalDatabaseAdapter
    elif backend == DatabaseBackend.VIKING:
        return KnowledgebaseVikingDatabaseAdapter
    else:
        raise ValueError(f"Unknown backend: {backend}")


class KnowledgebaseKVDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        """Add texts to Redis.

        Key: app_name
        Field: app_name:user_id
        Value: text in List
        """
        # key = f"{app_name}:{user_id}"
        key = f"{app_name}"

        try:
            for _content in content:
                self.database_client.add(key, _content)
            logger.debug(
                f"Successfully added {len(content)} texts to Redis list key `{key}`."
            )
        except Exception as e:
            logger.error(f"Failed to add texts to Redis list key `{key}`: {e}")
            raise e

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        # key = f"{app_name}:{user_id}"
        key = f"{app_name}"
        top_k = 10

        try:
            result = self.database_client.query(key, query)
            return result[-top_k:]
        except Exception as e:
            logger.error(f"Failed to search from Redis list key '{key}': {e}")
            raise e

    def delete(self, app_name: str, user_id: str, session_id: str):
        try:
            # key = f"{app_name}:{user_id}:{session_id}"
            key = f"{app_name}"
            self.database_client.delete(key=key)
            logger.info(f"Successfully deleted data for app {app_name}")
        except Exception as e:
            logger.error(f"Failed to delete data: {e}")
            raise e


class KnowledgebaseRelationalDatabaseAdapter(BaseModel):
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
        table = app_name

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

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        """Search content from table app_name."""
        table = app_name
        top_k = 10

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
        table = app_name
        try:
            self.database_client.delete(table=table)
            logger.info(f"Successfully deleted data from table {app_name}")
        except Exception as e:
            logger.error(f"Failed to delete data: {e}")
            raise e


class KnowledgebaseVectorDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        # knowledgebase  is application specific
        collection_name = format_collection_name(f"{app_name}")
        self.database_client.add(content, collection_name=collection_name)

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        # knowledgebase  is application specific
        collection_name = format_collection_name(f"{app_name}")
        return self.database_client.query(
            query, collection_name=collection_name, **kwargs
        )

    def delete(self, app_name: str, user_id: str, session_id: str):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        # knowledgebase  is application specific
        collection_name = format_collection_name(f"{app_name}")
        try:
            self.database_client.delete(collection_name=collection_name)
            logger.info(
                f"Successfully deleted vector database collection for app {app_name}"
            )
        except Exception as e:
            logger.error(f"Failed to delete vector database collection: {e}")
            raise e


class KnowledgebaseLocalDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def add(self, content: list[str], app_name: str, user_id: str, session_id: str):
        self.database_client.add(content)

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        return self.database_client.query(query, **kwargs)

    def delete(self, app_name: str, user_id: str, session_id: str):
        try:
            self.database_client.delete()
            logger.info(f"Successfully cleared local database for app {app_name}")
        except Exception as e:
            logger.error(f"Failed to clear local database: {e}")
            raise e


class KnowledgebaseVikingDatabaseAdapter(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    database_client: BaseDatabase

    def get_or_create_collection(self, collection_name: str):
        if not self.database_client.collection_exists(collection_name):
            self.database_client.create_collection(collection_name)
        count = 0
        while not self.database_client.collection_exists(collection_name):
            time.sleep(1)
            count += 1
            if count > 50:
                raise TimeoutError(
                    f"Collection {collection_name} not created after 50 seconds"
                )

    def add(
        self,
        content: str | list[str] | TextIO | BinaryIO | bytes,
        app_name: str,
        user_id: str,
        session_id: str,
        **kwargs,
    ):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        collection_name = format_collection_name(f"{app_name}")
        self.get_or_create_collection(collection_name)
        self.database_client.add(content, collection_name=collection_name, **kwargs)

    def query(self, query: str, app_name: str, user_id: str, **kwargs):
        collection_name = format_collection_name(f"{app_name}")
        if not self.database_client.collection_exists(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist")
        return self.database_client.query(
            query, collection_name=collection_name, **kwargs
        )

    def delete(self, app_name: str, user_id: str, session_id: str):
        # collection_name = format_collection_name(f"{app_name}_{user_id}")
        collection_name = format_collection_name(f"{app_name}")
        try:
            self.database_client.delete(collection_name=collection_name)
            logger.info(
                f"Successfully deleted vector database collection for app {app_name}"
            )
        except Exception as e:
            logger.error(f"Failed to delete vector database collection: {e}")
            raise e
