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

from llama_index.core import Document, VectorStoreIndex
from llama_index.core.schema import BaseNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from typing_extensions import Any, override

import veadk.config  # noqa E401
from veadk.configs.database_configs import OpensearchConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.utils import get_llama_index_splitter
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.utils.logger import get_logger

try:
    from llama_index.vector_stores.opensearch import (
        OpensearchVectorClient,
        OpensearchVectorStore,
    )
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )

logger = get_logger(__name__)


class OpensearchLTMBackend(BaseLongTermMemoryBackend):
    opensearch_config: OpensearchConfig = Field(default_factory=OpensearchConfig)
    """Opensearch client configs"""

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )
    """Embedding model configs"""

    def model_post_init(self, __context: Any) -> None:
        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

    def precheck_index_naming(self, index: str):
        if not (
            isinstance(index, str)
            and not index.startswith(("_", "-"))
            and index.islower()
            and re.match(r"^[a-z0-9_\-.]+$", index)
        ):
            raise ValueError(
                f"The index name {index} does not conform to the naming rules of OpenSearch"
            )

    def _create_vector_index(self, index: str) -> VectorStoreIndex:
        logger.info(f"Create OpenSearch vector index with index={index}")

        self.precheck_index_naming(index)

        opensearch_client = OpensearchVectorClient(
            endpoint=self.opensearch_config.host,
            port=self.opensearch_config.port,
            http_auth=(
                self.opensearch_config.username,
                self.opensearch_config.password,
            ),
            use_ssl=True,
            verify_certs=False,
            dim=self.embedding_config.dim,
            index=index,
        )
        vector_store = OpensearchVectorStore(client=opensearch_client)
        return VectorStoreIndex.from_vector_store(
            vector_store=vector_store, embed_model=self._embed_model
        )

    @override
    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        index = f"{self.index}_{user_id}"
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
        index = f"{self.index}_{user_id}"

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
