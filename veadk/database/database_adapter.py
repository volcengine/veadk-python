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

import re
import time
from typing import BinaryIO, TextIO
from veadk.database.base_database import BaseDatabase

from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class KVDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.kv.redis_database import RedisDatabase

        self.client: RedisDatabase = client

    def add(self, data: list[str], index: str):
        logger.debug(f"Adding documents to Redis database: index={index}")

        try:
            for _data in data:
                self.client.add(key=index, value=_data)
            logger.debug(f"Added {len(data)} texts to Redis database: index={index}")
        except Exception as e:
            logger.error(
                f"Failed to add data to Redis database: index={index} error={e}"
            )
            raise e

    def query(self, query: str, index: str, top_k: int = 0) -> list[str]:
        logger.debug(f"Querying Redis database: index={index} query={query}")

        # ignore top_k, as KV search only return one result
        _ = top_k

        try:
            result = self.client.query(key=index, query=query)
            return result
        except Exception as e:
            logger.error(f"Failed to search from Redis: index={index} error={e}")
            raise e


class RelationalDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.relational.mysql_database import MysqlDatabase

        self.client: MysqlDatabase = client

    def create_table(self, table_name: str):
        logger.debug(f"Creating table for SQL database: table_name={table_name}")

        sql = f"""
            CREATE TABLE `{table_name}` (
                `id` BIGINT AUTO_INCREMENT PRIMARY KEY,
                `data` TEXT NOT NULL,
                `created_at` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET={self.client.config.charset};
        """
        self.client.add(sql)

    def add(self, data: list[str], index: str):
        logger.debug(
            f"Adding documents to SQL database: table_name={index} data_len={len(data)}"
        )

        if not self.client.table_exists(index):
            logger.warning(f"Table {index} does not exist, creating a new table.")
            self.create_table(index)

        for _data in data:
            sql = f"""
                INSERT INTO `{index}` (`data`)
                VALUES (%s);
                """
            self.client.add(sql, params=(_data,))
        logger.debug(f"Added {len(data)} texts to table {index}.")

    def query(self, query: str, index: str, top_k: int) -> list[str]:
        logger.debug(
            f"Querying SQL database: table_name={index} query={query} top_k={top_k}"
        )

        if not self.client.table_exists(index):
            logger.warning(
                f"Querying SQL database, but table `{index}` does not exist, returning empty list."
            )
            return []

        sql = f"""
            SELECT `data` FROM `{index}` ORDER BY `created_at` DESC LIMIT {top_k};
            """
        results = self.client.query(sql)

        return [item["data"] for item in results]


class VectorDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.vector.opensearch_vector_database import (
            OpenSearchVectorDatabase,
        )

        self.client: OpenSearchVectorDatabase = client

    def _validate_index(self, index: str):
        """
        Verify whether the string conforms to the naming rules of index_name in OpenSearch.
        https://docs.opensearch.org/2.8/api-reference/index-apis/create-index/
        """
        if not (
            isinstance(index, str)
            and not index.startswith(("_", "-"))
            and index.islower()
            and re.match(r"^[a-z0-9_\-.]+$", index)
        ):
            raise ValueError(
                "The index name does not conform to the naming rules of OpenSearch"
            )

    def add(self, data: list[str], index: str):
        self._validate_index(index)

        logger.debug(
            f"Adding documents to vector database: index={index} data_len={len(data)}"
        )

        self.client.add(data, collection_name=index)

    def query(self, query: str, index: str, top_k: int) -> list[str]:
        logger.debug(
            f"Querying vector database: collection_name={index} query={query} top_k={top_k}"
        )

        return self.client.query(
            query=query,
            collection_name=index,
            top_k=top_k,
        )


class VikingDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.viking.viking_database import VikingDatabase

        self.client: VikingDatabase = client

    def _validate_index(self, index: str):
        """
        Only English letters, numbers, and underscores (_) are allowed.
        It must start with an English letter and cannot be empty. Length requirement: [1, 128].
        For details, please see: https://www.volcengine.com/docs/84313/1254542?lang=zh
        """
        if not (
            isinstance(index, str)
            and 0 < len(index) <= 128
            and re.fullmatch(r"^[a-zA-Z][a-zA-Z0-9_]*$", index)
        ):
            raise ValueError(
                "The index name does not conform to the rules: it must start with an English letter, contain only letters, numbers, and underscores, and have a length of 1-128."
            )

    def get_or_create_collection(self, collection_name: str):
        if not self.client.collection_exists(collection_name):
            logger.warning(
                f"Collection {collection_name} does not exist, creating a new collection."
            )
            self.client.create_collection(collection_name)

        # After creation, it is necessary to wait for a while.
        count = 0
        while not self.client.collection_exists(collection_name):
            print("here")
            time.sleep(1)
            count += 1
            if count > 60:
                raise TimeoutError(
                    f"Collection {collection_name} not created after 50 seconds"
                )

    def add(
        self, data: str | list[str] | TextIO | BinaryIO | bytes, index: str, **kwargs
    ):
        self._validate_index(index)

        logger.debug(f"Adding documents to Viking database: collection_name={index}")

        self.get_or_create_collection(index)
        self.client.add(data, collection_name=index, **kwargs)

    def query(self, query: str, index: str, top_k: int) -> list[str]:
        self._validate_index(index)

        logger.debug(f"Querying Viking database: collection_name={index} query={query}")

        if not self.client.collection_exists(index):
            return []

        return self.client.query(query, collection_name=index, top_k=top_k)


class VikingMemoryDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.viking.viking_memory_db import VikingMemoryDatabase

        self.client: VikingMemoryDatabase = client

    def _validate_index(self, index: str):
        if not (
            isinstance(index, str)
            and 1 <= len(index) <= 128
            and re.fullmatch(r"^[a-zA-Z][a-zA-Z0-9_]*$", index)
        ):
            raise ValueError(
                "The index name does not conform to the rules: it must start with an English letter, contain only letters, numbers, and underscores, and have a length of 1-128."
            )

    def add(self, data: list[str], index: str, **kwargs):
        self._validate_index(index)

        logger.debug(
            f"Adding documents to Viking database memory: collection_name={index} data_len={len(data)}"
        )

        self.client.add(data, collection_name=index, **kwargs)

    def query(self, query: str, index: str, top_k: int, **kwargs):
        self._validate_index(index)

        logger.debug(
            f"Querying Viking database memory: collection_name={index} query={query} top_k={top_k}"
        )

        result = self.client.query(query, collection_name=index, top_k=top_k, **kwargs)
        return result


class LocalDatabaseAdapter:
    def __init__(self, client):
        from veadk.database.local_database import LocalDataBase

        self.client: LocalDataBase = client

    def add(self, data: list[str], **kwargs):
        self.client.add(data)

    def query(self, query: str, **kwargs):
        return self.client.query(query, **kwargs)


MAPPING = {
    "RedisDatabase": KVDatabaseAdapter,
    "MysqlDatabase": RelationalDatabaseAdapter,
    "LocalDataBase": LocalDatabaseAdapter,
    "VikingDatabase": VikingDatabaseAdapter,
    "OpenSearchVectorDatabase": VectorDatabaseAdapter,
    "VikingMemoryDatabase": VikingMemoryDatabaseAdapter,
}


def get_knowledgebase_database_adapter(database_client: BaseDatabase):
    return MAPPING[type(database_client).__name__](client=database_client)


def get_long_term_memory_database_adapter(database_client: BaseDatabase):
    return MAPPING[type(database_client).__name__](client=database_client)
