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

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.schema import BaseNode
from pydantic import Field
from typing_extensions import Any, override

import veadk.config  # noqa E401
from veadk.configs.database_configs import RedisConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.utils import get_llama_index_splitter
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.models.ark_embedding import create_embedding_model
from veadk.utils.logger import get_logger

try:
    from llama_index.vector_stores.redis import RedisVectorStore
    from redis import Redis
    from redisvl.schema import IndexSchema

except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )


logger = get_logger(__name__)


class RedisLTMBackend(BaseLongTermMemoryBackend):
    redis_config: RedisConfig = Field(default_factory=RedisConfig)
    """Redis client configs"""

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )
    """Embedding model configs"""

    def model_post_init(self, __context: Any) -> None:
        self._embed_model = create_embedding_model(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

    def precheck_index_naming(self, index: str):
        # no checking
        pass

    def _create_vector_index(self, index: str) -> VectorStoreIndex:
        logger.info(f"Create Redis vector index with index={index}")

        self.precheck_index_naming(index)

        # We will use `from_url` to init Redis client once the
        # AK/SK -> STS token is ready.
        # self._redis_client = Redis.from_url(url=...)
        redis_client = Redis(
            host=self.redis_config.host,
            port=self.redis_config.port,
            db=self.redis_config.db,
            password=self.redis_config.password,
        )

        # Create an index for each user
        # Should be Optimized in the future
        schema = IndexSchema.from_dict(
            {
                "index": {"name": index, "prefix": index, "key_separator": "_"},
                "fields": [
                    {"name": "id", "type": "tag", "attrs": {"sortable": False}},
                    {"name": "doc_id", "type": "tag", "attrs": {"sortable": False}},
                    {"name": "text", "type": "text", "attrs": {"weight": 1.0}},
                    {
                        "name": "vector",
                        "type": "vector",
                        "attrs": {
                            "dims": self.embedding_config.dim,
                            "algorithm": "flat",
                            "distance_metric": "cosine",
                        },
                    },
                ],
            }
        )
        vector_store = RedisVectorStore(schema=schema, redis_client=redis_client)

        logger.info(
            f"Create vector store done, index_name={vector_store.index_name} prefix={vector_store.schema.index.prefix}"
        )

        return VectorStoreIndex.from_vector_store(
            vector_store=vector_store, embed_model=self._embed_model
        )

    @override
    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        index = f"veadk-ltm/{self.index}/{user_id}"
        vector_index = self._create_vector_index(index)

        for event_string in event_strings:
            document = Document(text=event_string)
            nodes = self._split_documents([document])
            vector_index.insert_nodes(nodes)

        return True

    @override
    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        index = f"veadk-ltm/{self.index}/{user_id}"
        vector_index = self._create_vector_index(index)

        _retriever = vector_index.as_retriever(similarity_top_k=top_k)
        retrieved_nodes = _retriever.retrieve(query)
        return [node.text for node in retrieved_nodes]

    def _split_documents(self, documents: list[Document]) -> list[BaseNode]:
        """Split document into chunks"""
        nodes = []
        for document in documents:
            splitter = get_llama_index_splitter(document.metadata.get("file_path", ""))
            _nodes = splitter.get_nodes_from_documents([document])
            nodes.extend(_nodes)
        return nodes
