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

from llama_index.core import (
    Document,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.schema import BaseNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from redis import Redis
from typing_extensions import Any, override

from veadk.configs.database_configs import RedisConfig
from veadk.configs.model_configs import EmbeddingModelConfig
from veadk.knowledgebase.backends.utils import get_llama_index_splitter
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)

try:
    from llama_index.vector_stores.redis import RedisVectorStore
    from llama_index.vector_stores.redis.schema import (
        RedisIndexInfo,
        RedisVectorStoreSchema,
    )
    from redis import Redis
    from redisvl.schema.fields import BaseVectorFieldAttributes
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )


class RedisLTMBackend(BaseLongTermMemoryBackend):
    redis_config: RedisConfig = Field(default_factory=RedisConfig)
    """Redis client configs"""

    embedding_config: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)
    """Embedding model configs"""

    def precheck_index_naming(self):
        # no checking
        pass

    def model_post_init(self, __context: Any) -> None:
        # We will use `from_url` to init Redis client once the
        # AK/SK -> STS token is ready.
        # self._redis_client = Redis.from_url(url=...)

        self._redis_client = Redis(
            host=self.redis_config.host,
            port=self.redis_config.port,
            db=self.redis_config.db,
            password=self.redis_config.password,
        )

        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

        self._schema = RedisVectorStoreSchema(
            index=RedisIndexInfo(name=self.index),
        )
        if "vector" in self._schema.fields:
            vector_field = self._schema.fields["vector"]
            if (
                vector_field
                and vector_field.attrs
                and isinstance(vector_field.attrs, BaseVectorFieldAttributes)
            ):
                vector_field.attrs.dims = self.embedding_config.dim
        self._vector_store = RedisVectorStore(
            schema=self._schema,
            redis_client=self._redis_client,
            overwrite=True,
            collection_name=self.index,
        )

        self._storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store
        )

        self._vector_index = VectorStoreIndex.from_documents(
            documents=[],
            storage_context=self._storage_context,
            embed_model=self._embed_model,
        )

    @override
    def save_memory(self, event_strings: list[str], **kwargs) -> bool:
        for event_string in event_strings:
            document = Document(text=event_string)
            nodes = self._split_documents([document])
            self._vector_index.insert_nodes(nodes)
        return True

    @override
    def search_memory(self, query: str, top_k: int, **kwargs) -> list[str]:
        _retriever = self._vector_index.as_retriever(similarity_top_k=top_k)
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
