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
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from typing_extensions import Any, override

from veadk.configs.model_configs import EmbeddingModelConfig
from veadk.knowledgebase.backends.utils import get_llama_index_splitter
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)


class InMemoryLTMBackend(BaseLongTermMemoryBackend):
    embedding_config: EmbeddingModelConfig = Field(default_factory=EmbeddingModelConfig)
    """Embedding model configs"""

    def precheck_index_naming(self):
        # no checking
        pass

    def model_post_init(self, __context: Any) -> None:
        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )
        self._vector_index = VectorStoreIndex([], embed_model=self._embed_model)

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
