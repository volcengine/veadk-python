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

from llama_index.core import Document, SimpleDirectoryReader, VectorStoreIndex
from llama_index.core.schema import BaseNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from typing_extensions import Any, override

from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.utils import get_llama_index_splitter


class InMemoryKnowledgeBackend(BaseKnowledgebaseBackend):
    """A in-memory implementation backend for knowledgebase.

    In-memory backend stores embedded text in a vector storage from Llama-index.

    Attributes:
        embedding_config (EmbeddingModelConfig):
            Embedding config for text embedding and search.
            Embedding config contains embedding model name and the corresponding dim.
    """

    embedding_config: NormalEmbeddingModelConfig | EmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )

    def model_post_init(self, __context: Any) -> None:
        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )
        self._vector_index = VectorStoreIndex([], embed_model=self._embed_model)

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
