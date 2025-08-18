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

from typing import BinaryIO, Literal, TextIO

from veadk.database.database_adapter import get_knowledgebase_database_adapter
from veadk.database.database_factory import DatabaseFactory
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def build_knowledgebase_index(app_name: str):
    return f"veadk_kb_{app_name}"


class KnowledgeBase:
    def __init__(
        self,
        backend: Literal["local", "opensearch", "viking", "redis", "mysql"] = "local",
        top_k: int = 10,
        db_config=None,
    ):
        logger.info(f"Initializing knowledgebase: backend={backend} top_k={top_k}")

        self.backend = backend
        self.top_k = top_k

        self.db_client = DatabaseFactory.create(backend=backend, config=db_config)
        self.adapter = get_knowledgebase_database_adapter(self.db_client)

        logger.info(
            f"Initialized knowledgebase: db_client={self.db_client.__class__.__name__} adapter={self.adapter}"
        )

    def add(
        self,
        data: str | list[str] | TextIO | BinaryIO | bytes,
        app_name: str,
        **kwargs,
    ):
        """
        Add documents to the vector database.
        You can only upload files or file characters when the adapter type used is vikingdb.
        In addition, if you upload data of the bytes type,
            for example, if you read the file stream of a pdf, then you need to pass an additional parameter file_ext = '.pdf'.
        """
        if self.backend != "viking" and not (
            isinstance(data, str) or isinstance(data, list)
        ):
            raise ValueError(
                "Only vikingdb supports uploading files or file characters."
            )

        index = build_knowledgebase_index(app_name)

        logger.info(f"Adding documents to knowledgebase: index={index}")

        self.adapter.add(data=data, index=index)

    def search(self, query: str, app_name: str, top_k: int | None = None) -> list[str]:
        top_k = self.top_k if top_k is None else top_k

        logger.info(
            f"Searching knowledgebase: app_name={app_name} query={query} top_k={top_k}"
        )
        index = build_knowledgebase_index(app_name)
        result = self.adapter.query(query=query, index=index, top_k=top_k)
        if len(result) == 0:
            logger.warning(f"No documents found in knowledgebase. Query: {query}")
        return result
