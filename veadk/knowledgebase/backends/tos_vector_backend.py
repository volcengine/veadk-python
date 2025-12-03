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
import os

from llama_index.core import (
    Document,
    SimpleDirectoryReader,
)
from llama_index.core.schema import BaseNode
from llama_index.embeddings.openai_like import OpenAILikeEmbedding
from pydantic import Field
from typing_extensions import Any, override

import veadk.config  # noqa E401
from veadk.auth.veauth.utils import get_credential_from_vefaas_iam
from veadk.configs.database_configs import TOSVectorConfig
from veadk.configs.model_configs import EmbeddingModelConfig, NormalEmbeddingModelConfig
from veadk.integrations.ve_tos.ve_tos import VeTOS
from veadk.knowledgebase.backends.base_backend import BaseKnowledgebaseBackend
from veadk.knowledgebase.backends.utils import get_llama_index_splitter
from veadk.utils.logger import get_logger

logger = get_logger()
try:
    from tos.vector_client import VectorClient
    from tos import DataType, DistanceMetricType
    from tos.exceptions import TosServerError
    from tos.models2 import Vector, VectorData
except ImportError:
    raise ImportError(
        "Please install VeADK extensions\npip install veadk-python[extensions]"
    )


class TosVectorKnowledgeBackend(BaseKnowledgebaseBackend):
    """TOS-based backend for knowledgebase."""

    volcengine_access_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_ACCESS_KEY")
    )
    volcengine_secret_key: str | None = Field(
        default_factory=lambda: os.getenv("VOLCENGINE_SECRET_KEY")
    )
    tos_vector_bucket_name: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_TOS_VECTOR_BUCKET")
    )
    tos_vector_account_id: str | None = Field(
        default_factory=lambda: os.getenv("DATABASE_TOS_VECTOR_ACCOUNT_ID")
    )
    tos_vector_config: TOSVectorConfig = Field(default_factory=TOSVectorConfig)

    session_token: str = ""

    embedding_config: EmbeddingModelConfig | NormalEmbeddingModelConfig = Field(
        default_factory=EmbeddingModelConfig
    )

    def model_post_init(self, __context: Any) -> None:
        self.precheck_index_naming()
        self._tos_vector_client = VectorClient(
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            **self.tos_vector_config.model_dump(),
        )
        # create_bucket and index if not exist
        self._create_index()

        self._tos_client = self._get_tos_client()

        self._embed_model = OpenAILikeEmbedding(
            model_name=self.embedding_config.name,
            api_key=self.embedding_config.api_key,
            api_base=self.embedding_config.api_base,
        )

    def _bucket_exists(self) -> bool:
        try:
            bucket_exist = self._tos_vector_client.get_vector_bucket(
                vector_bucket_name=self.tos_vector_bucket_name,
                account_id=self.tos_vector_account_id,
            )
            return bucket_exist.status_code == 200
        except TosServerError as e:
            if e.status_code == 404:
                return False
            else:
                raise e

    def _index_exists(self) -> bool:
        try:
            index_exist = self._tos_vector_client.get_index(
                vector_bucket_name=self.tos_vector_bucket_name,
                account_id=self.tos_vector_account_id,
                index_name=self.index,
            )
            return index_exist.status_code == 200
        except TosServerError as e:
            if e.status_code == 404:
                return False
            else:
                raise e

    def _split_documents(self, documents: list[Document]) -> list[BaseNode]:
        """Split document into chunks"""
        nodes = []
        for document in documents:
            splitter = get_llama_index_splitter(document.metadata.get("file_path", ""))
            _nodes = splitter.get_nodes_from_documents([document])
            nodes.extend(_nodes)
        return nodes

    def _create_index(self):
        self._tos_vector_client.create_vector_bucket(
            vector_bucket_name=self.tos_vector_bucket_name,
        )

        if not self._index_exists():
            self._tos_vector_client.create_index(
                vector_bucket_name=self.tos_vector_bucket_name,
                account_id=self.tos_vector_account_id,
                index_name=self.index,
                data_type=DataType.DataTypeFloat32,
                dimension=self.embedding_config.dim,
                distance_metric=DistanceMetricType.DistanceMetricCosine,
            )

    def _get_tos_client(self) -> VeTOS:
        volcengine_access_key = self.volcengine_access_key
        volcengine_secret_key = self.volcengine_secret_key
        session_token = self.session_token

        if not (volcengine_access_key and volcengine_secret_key):
            cred = get_credential_from_vefaas_iam()
            volcengine_access_key = cred.access_key_id
            volcengine_secret_key = cred.secret_access_key
            session_token = cred.session_token

        return VeTOS(
            ak=volcengine_access_key,
            sk=volcengine_secret_key,
            session_token=session_token,
            region=self.tos_vector_config.region,
            bucket_name=self.tos_vector_bucket_name,
        )

    def precheck_index_naming(self) -> None:
        pass

    def _process_and_store_documents(self, documents: list[Document]) -> bool:
        nodes = self._split_documents(documents)
        vectors = []
        for node in nodes:
            if not node.text:
                continue
            embedding = self._embed_model.get_text_embedding(node.text)
            vectors.append(
                Vector(
                    key=node.node_id,
                    data=VectorData(float32=embedding),
                    metadata={"text": node.text, "metadata": json.dumps(node.metadata)},
                )
            )
        result = self._tos_vector_client.put_vectors(
            vector_bucket_name=self.tos_vector_bucket_name,
            account_id=self.tos_vector_account_id,
            index_name=self.index,
            vectors=vectors,
        )
        return result.status_code == 200

    @override
    def add_from_directory(self, directory: str, *args, **kwargs) -> bool:
        # fixme
        logger.warning(
            "add_from_directory is not yet fully developed and may have issues such as missing images."
        )
        documents = SimpleDirectoryReader(input_dir=directory).load_data()
        return self._process_and_store_documents(documents)

    @override
    def add_from_files(self, files: list[str], *args, **kwargs) -> bool:
        # fixme
        logger.warning(
            "add_from_files is not yet fully developed and may have issues such as missing images."
        )
        documents = SimpleDirectoryReader(input_files=files).load_data()
        return self._process_and_store_documents(documents)

    @override
    def add_from_text(self, text: str | list[str], *args, **kwargs) -> bool:
        if isinstance(text, str):
            documents = [Document(text=text)]
        else:
            documents = [Document(text=t) for t in text]

        return self._process_and_store_documents(documents)

    @override
    def search(self, query: str, top_k: int = 5) -> list[str]:
        query_vector = self._embed_model.get_text_embedding(query)

        search_result = self._tos_vector_client.query_vectors(
            vector_bucket_name=self.tos_vector_bucket_name,
            account_id=self.tos_vector_account_id,
            index_name=self.index,
            query_vector=VectorData(float32=query_vector),
            top_k=top_k,
            return_metadata=True,
        )

        return [vector.metadata["text"] for vector in search_result.vectors]
