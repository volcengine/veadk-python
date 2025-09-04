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

import os
from typing import Any, Literal, Optional

from opensearchpy import OpenSearch, Urllib3HttpConnection, helpers
from pydantic import BaseModel, Field, PrivateAttr
from typing_extensions import override

from veadk.config import getenv
from veadk.utils.logger import get_logger

from ..base_database import BaseDatabase
from .type import Embeddings

logger = get_logger(__name__)


class OpenSearchVectorDatabaseConfig(BaseModel):
    host: str = Field(
        default_factory=lambda: getenv("DATABASE_OPENSEARCH_HOST"),
        description="OpenSearch host",
    )

    port: str | int = Field(
        default_factory=lambda: getenv("DATABASE_OPENSEARCH_PORT"),
        description="OpenSearch port",
    )

    username: Optional[str] = Field(
        default_factory=lambda: getenv("DATABASE_OPENSEARCH_USERNAME"),
        description="OpenSearch username",
    )

    password: Optional[str] = Field(
        default_factory=lambda: getenv("DATABASE_OPENSEARCH_PASSWORD"),
        description="OpenSearch password",
    )

    secure: bool = Field(default=True, description="Whether enable SSL")

    verify_certs: bool = Field(default=False, description="Whether verify SSL certs")

    auth_method: Literal["basic", "aws_managed_iam"] = Field(
        default="basic", description="OpenSearch auth method"
    )

    def to_opensearch_params(self) -> dict[str, Any]:
        params = {
            "hosts": [{"host": self.host, "port": int(self.port)}],
            "use_ssl": self.secure,
            "verify_certs": self.verify_certs,
            "connection_class": Urllib3HttpConnection,
            "pool_maxsize": 20,
        }
        ca_cert_path = os.getenv("OPENSEARCH_CA_CERT")
        if self.verify_certs and ca_cert_path:
            params["ca_certs"] = ca_cert_path

        params["http_auth"] = (self.username, self.password)

        return params


class OpenSearchVectorDatabase(BaseModel, BaseDatabase):
    config: OpenSearchVectorDatabaseConfig = Field(
        default_factory=OpenSearchVectorDatabaseConfig
    )

    _embedding_client: Embeddings = PrivateAttr()
    _opensearch_client: OpenSearch = PrivateAttr()

    def model_post_init(self, context: Any, /) -> None:
        self._embedding_client = Embeddings()
        self._opensearch_client = OpenSearch(**self.config.to_opensearch_params())

        self._type = "opensearch"

    def _get_settings(self) -> dict:
        settings = {"index": {"knn": True}}
        return settings

    def _get_mappings(self, dim: int = 2560) -> dict:
        mappings = {
            "properties": {
                "page_content": {
                    "type": "text",
                },
                "vector": {
                    "type": "knn_vector",
                    "dimension": dim,
                    "method": {
                        "name": "hnsw",
                        "space_type": "l2",
                        "engine": "faiss",
                        "parameters": {"ef_construction": 64, "m": 8},
                    },
                },
            }
        }
        return mappings

    def create_collection(
        self,
        collection_name: str,
        embedding_dim: int,
    ):
        if not self._opensearch_client.indices.exists(index=collection_name):
            self._opensearch_client.indices.create(
                index=collection_name,
                body={
                    "mappings": self._get_mappings(dim=embedding_dim),
                    "settings": self._get_settings(),
                },
            )
        else:
            logger.warning(f"Collection {collection_name} already exists.")

        self._opensearch_client.indices.refresh(index=collection_name)
        return

    def _search_by_vector(
        self, collection_name: str, query_vector: list[float], **kwargs: Any
    ) -> list[str]:
        top_k = kwargs.get("top_k", 5)
        query = {
            "size": top_k,
            "query": {"knn": {"vector": {"vector": query_vector, "k": top_k}}},
        }
        response = self._opensearch_client.search(index=collection_name, body=query)

        result_list = []
        for hit in response["hits"]["hits"]:
            result_list.append(hit["_source"]["page_content"])

        return result_list

    def get_health(self):
        response = self._opensearch_client.cat.health()
        logger.info(response)

    def add(self, texts: list[str], **kwargs):
        collection_name = kwargs.get("collection_name")
        assert collection_name is not None, "Collection name is required."
        if not self._opensearch_client.indices.exists(index=collection_name):
            self.create_collection(
                embedding_dim=self._embedding_client.get_embedding_dim(),
                collection_name=collection_name,
            )

        actions = []
        embeddings = self._embedding_client.embed_documents(texts)
        for i in range(len(texts)):
            action = {
                "_op_type": "index",
                "_index": collection_name,
                "_source": {
                    "page_content": texts[i],
                    "vector": embeddings[i],
                },
            }
            actions.append(action)

        helpers.bulk(
            client=self._opensearch_client,
            actions=actions,
            timeout=30,
            max_retries=3,
        )

        self._opensearch_client.indices.refresh(index=collection_name)
        return

    @override
    def query(self, query: str, **kwargs: Any) -> list[str]:
        collection_name = kwargs.get("collection_name")
        top_k = kwargs.get("top_k", 5)
        assert collection_name is not None, "Collection name is required."
        if not self._opensearch_client.indices.exists(index=collection_name):
            logger.warning(
                f"querying {query}, but collection {collection_name} does not exist. return a empty list."
            )
            return []
        query_vector = self._embedding_client.embed_query(query)
        return self._search_by_vector(
            collection_name=collection_name, query_vector=query_vector, top_k=top_k
        )

    @override
    def delete(self, collection_name: str, **kwargs: Any):
        """drop index"""
        if not self._opensearch_client.indices.exists(index=collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")
        self._opensearch_client.indices.delete(index=collection_name)

    def is_empty(self, collection_name: str) -> bool:
        response = self._opensearch_client.count(index=collection_name)
        return response["count"] == 0

    def collection_exists(self, collection_name: str) -> bool:
        return self._opensearch_client.indices.exists(index=collection_name)

    def list_all_collection(self) -> list:
        """List all index name of OpenSearch."""
        response = self._opensearch_client.indices.get_alias()
        return list(response.keys())

    def list_docs(
        self, collection_name: str, offset: int = 0, limit: int = 10000
    ) -> list[dict]:
        """Match all docs in one index of OpenSearch"""
        if not self.collection_exists(collection_name):
            logger.warning(
                f"Get all docs, but collection {collection_name} does not exist. return a empty list."
            )
            return []

        query = {"size": limit, "from": offset, "query": {"match_all": {}}}
        response = self._opensearch_client.search(index=collection_name, body=query)
        return [
            {
                "id": hit["_id"],
                "content": hit["_source"]["page_content"],
            }
            for hit in response["hits"]["hits"]
        ]

    def delete_by_query(self, collection_name: str, query: str) -> Any:
        """Delete docs by query in one index of OpenSearch"""
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")

        query_payload = {"query": {"match": {"page_content": query}}}
        response = self._opensearch_client.delete_by_query(
            index=collection_name, body=query_payload
        )

        self._opensearch_client.indices.refresh(index=collection_name)
        return response

    def delete_by_id(self, collection_name: str, id: str):
        """Delete docs by id in index of OpenSearch"""
        if not self.collection_exists(collection_name):
            raise ValueError(f"Collection {collection_name} does not exist.")

        response = self._opensearch_client.delete(index=collection_name, id=id)
        self._opensearch_client.indices.refresh(index=collection_name)
        return response
