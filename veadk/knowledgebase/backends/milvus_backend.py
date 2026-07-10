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

import json
import re
from typing import Any

from pydantic import Field
from typing_extensions import override

import veadk.config  # noqa E401
from veadk.configs.database_configs import MilvusConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend


class MilvusKnowledgeBackend(BaseKnowledgebaseBackend):
    """Milvus-based backend for knowledgebase.

    Milvus backend stores embedded chunks in a Milvus collection through
    LlamaIndex's Milvus vector store. ``index`` maps directly to the Milvus
    collection name.
    """

    milvus_config: MilvusConfig = Field(default_factory=MilvusConfig)
    """Milvus connection config."""

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )
    """Embedding model configs."""

    def model_post_init(self, __context: Any) -> None:
        self.precheck_index_naming()
        self._precheck_milvus_uri()

        try:
            from llama_index.core import StorageContext, VectorStoreIndex
            from llama_index.vector_stores.milvus import MilvusVectorStore
            from veadk.models.ark_embedding import create_embedding_model
        except ImportError as e:
            raise ImportError(
                "Please install VeADK extensions\npip install veadk-python[extensions]"
            ) from e

        self._embed_model = create_embedding_model(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

        vector_store_kwargs: dict[str, Any] = {
            "uri": self.milvus_config.uri,
            "collection_name": self.index,
            "dim": self.embedding_config.dim,
            "overwrite": self.milvus_config.overwrite,
        }

        token = self._resolve_token()
        if token:
            vector_store_kwargs["token"] = token

        if self.milvus_config.db_name:
            vector_store_kwargs["db_name"] = self.milvus_config.db_name

        if self.milvus_config.timeout is not None:
            vector_store_kwargs["timeout"] = self.milvus_config.timeout

        output_fields = self._resolve_output_fields()
        if output_fields:
            vector_store_kwargs["output_fields"] = output_fields

        self._vector_store = MilvusVectorStore(**vector_store_kwargs)
        self._storage_context = StorageContext.from_defaults(
            vector_store=self._vector_store
        )
        self._vector_index = VectorStoreIndex(
            nodes=[],
            storage_context=self._storage_context,
            embed_model=self._embed_model,
        )

    @override
    def precheck_index_naming(self) -> None:
        if not isinstance(self.index, str) or not self.index:
            raise ValueError("Milvus collection name must not be empty.")
        if len(self.index) > 255:
            raise ValueError("Milvus collection name is too long.")
        if not re.fullmatch(r"^[A-Za-z_][A-Za-z0-9_]*$", self.index):
            raise ValueError(
                "Milvus collection name must start with a letter or underscore "
                "and contain only letters, numbers, and underscores."
            )

    def _precheck_milvus_uri(self) -> None:
        if not self.milvus_config.uri:
            raise ValueError(
                "Milvus uri must be configured via DATABASE_MILVUS_URI or "
                "MilvusConfig(uri=...)."
            )

    @override
    def add_from_directory(self, directory: str) -> bool:
        from llama_index.core import SimpleDirectoryReader

        documents = SimpleDirectoryReader(input_dir=directory).load_data()
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def add_from_files(self, files: list[str]) -> bool:
        from llama_index.core import SimpleDirectoryReader

        documents = SimpleDirectoryReader(input_files=files).load_data()
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def add_from_text(self, text: str | list[str]) -> bool:
        from llama_index.core import Document

        if isinstance(text, str):
            documents = [Document(text=text)]
        else:
            documents = [Document(text=t) for t in text]
        nodes = self._split_documents(documents)
        self._vector_index.insert_nodes(nodes)
        return True

    @override
    def search(self, query: str, top_k: int = 5) -> list[str]:
        self._ensure_collection_loaded()
        _retriever = self._vector_index.as_retriever(similarity_top_k=top_k)
        retrieved_nodes = _retriever.retrieve(query)
        return [node.text for node in retrieved_nodes]

    def _resolve_token(self) -> str | None:
        if self.milvus_config.token:
            return self.milvus_config.token
        if self.milvus_config.user and self.milvus_config.password:
            return f"{self.milvus_config.user}:{self.milvus_config.password}"
        return None

    def _resolve_output_fields(self) -> list[str]:
        output_fields = self.milvus_config.output_fields
        if isinstance(output_fields, str):
            output_fields = output_fields.strip()
            if not output_fields:
                return []
            if output_fields.startswith("["):
                parsed_output_fields = json.loads(output_fields)
                if not isinstance(parsed_output_fields, list) or not all(
                    isinstance(field, str) for field in parsed_output_fields
                ):
                    raise ValueError("Milvus output_fields must be a list of strings.")
                output_fields = parsed_output_fields
            else:
                output_fields = output_fields.split(",")

        return [field.strip() for field in output_fields if field.strip()]

    def _ensure_collection_loaded(self) -> None:
        vector_store = getattr(self, "_vector_store", None)
        client = getattr(vector_store, "client", None)
        collection_name = getattr(vector_store, "collection_name", self.index)
        if client is None or not collection_name:
            return

        try:
            load_state = client.get_load_state(collection_name=collection_name)
        except Exception:
            client.load_collection(collection_name=collection_name)
            return

        state = load_state.get("state") if isinstance(load_state, dict) else load_state
        if "loaded" not in str(state).lower():
            client.load_collection(collection_name=collection_name)

    def _split_documents(self, documents: list[Any]) -> list[Any]:
        """Split document into chunks."""
        from veadk.knowledgebase.backends.utils import get_llama_index_splitter

        nodes = []
        for document in documents:
            splitter = get_llama_index_splitter(document.metadata.get("file_path", ""))
            _nodes = splitter.get_nodes_from_documents([document])
            nodes.extend(_nodes)
        return nodes
