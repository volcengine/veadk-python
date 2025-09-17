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
from veadk.configs.database_configs import OpensearchConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.utils import get_llama_index_splitter

try:
    from llama_index.vector_stores.opensearch import (
        OpensearchVectorClient,
        OpensearchVectorStore,
    )
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )


class OpensearchKnowledgeBackend(BaseKnowledgebaseBackend):
    opensearch_config: OpensearchConfig = Field(default_factory=OpensearchConfig)
    """Opensearch client configs"""

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )
    """Embedding model configs"""

    def model_post_init(self, __context: Any) -> None:
        self.precheck_index_naming()
        self._opensearch_client = OpensearchVectorClient(
            endpoint=self.opensearch_config.host,
            port=self.opensearch_config.port,
            http_auth=(
                self.opensearch_config.username,
                self.opensearch_config.password,
            ),
            use_ssl=True,
            verify_certs=False,
            dim=self.embedding_config.dim,
            index=self.index,  # collection name
        )

        self._vector_store = OpensearchVectorStore(client=self._opensearch_client)

        self._storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store
        )

        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

        self._vector_index = VectorStoreIndex.from_documents(
            documents=[],
            storage_context=self._storage_context,
            embed_model=self._embed_model,
        )

    @override
    def precheck_index_naming(self) -> None:
        if not (
            isinstance(self.index, str)
            and not self.index.startswith(("_", "-"))
            and self.index.islower()
            and re.match(r"^[a-z0-9_\-.]+$", self.index)
        ):
            raise ValueError(
                "The index name does not conform to the naming rules of OpenSearch"
            )

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
