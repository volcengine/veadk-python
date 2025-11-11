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
    SimpleDirectoryReader,
    StorageContext,
    VectorStoreIndex,
)
from llama_index.core.schema import BaseNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from typing_extensions import Any, override

import veadk.config  # noqa E401
from veadk.configs.database_configs import RedisConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.utils import get_llama_index_splitter

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


class RedisKnowledgeBackend(BaseKnowledgebaseBackend):
    """Redis based backend for knowledgebase.

    Redis backend stores embedded text in a redis database by Llama-index.

    Attributes:
        redis_config (RedisConfig):
            Redis database configurations.
            Mainly contains redis database host, port, etc.
        embedding_config (EmbeddingModelConfig):
            Embedding configurations for text embedding and search.
            Embedding config contains embedding model name and the corresponding dim.

    Notes:
        Please ensure that your redis database supports Redisaearch stack.

    Examples:
        Init a knowledgebase based on redis backend.

        ```python
        knowledgebase = Knowledgebase(backend="redis")
        ```

        With more configurations:

        ```python
        ...
        ```
    """

    redis_config: RedisConfig = Field(default_factory=RedisConfig)

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )

    def model_post_init(self, __context: Any) -> None:
        # We will use `from_url` to init Redis client once the
        # AK/SK -> STS token is ready.
        # self._redis_client = Redis.from_url(url=...)

        self._redis_client = Redis(
            host=self.redis_config.host,
            port=self.redis_config.port,
            db=self.redis_config.db,
            username=self.redis_config.username,
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
    def precheck_index_naming(self) -> None:
        # Checking is not needed
        pass

    @override
    def add_from_directory(self, directory: str) -> bool:
        documents = SimpleDirectoryReader(input_dir=directory).load_data()
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def add_from_files(self, files: list[str]) -> bool:
        documents = SimpleDirectoryReader(input_files=files).load_data()
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def add_from_text(self, text: str | list[str]) -> bool:
        if isinstance(text, str):
            documents = [Document(text=text)]
        else:
            documents = [Document(text=t) for t in text]
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def search(self, query: str, top_k: int = 5) -> list[str]:
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
