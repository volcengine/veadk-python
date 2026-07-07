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

import sys
import types

import pytest

from veadk.configs.database_configs import MilvusConfig
from veadk.configs.model_configs import NormalEmbeddingModelConfig
from veadk.knowledgebase.knowledgebase import _get_backend_cls


@pytest.fixture
def fake_milvus_dependencies(monkeypatch):
    captured: dict = {}

    llama_index = types.ModuleType("llama_index")
    llama_index_core = types.ModuleType("llama_index.core")
    llama_index_vector_stores = types.ModuleType("llama_index.vector_stores")
    llama_index_milvus = types.ModuleType("llama_index.vector_stores.milvus")
    ark_embedding = types.ModuleType("veadk.models.ark_embedding")

    class FakeMilvusVectorStore:
        def __init__(self, **kwargs):
            captured["vector_store_kwargs"] = kwargs
            self.client = FakeMilvusClient()
            self.collection_name = kwargs["collection_name"]

    class FakeMilvusClient:
        def get_load_state(self, collection_name):
            captured.setdefault("client_events", []).append(
                ("get_load_state", collection_name)
            )
            return captured.get("load_state", {"state": "Loaded"})

        def load_collection(self, collection_name):
            captured.setdefault("client_events", []).append(
                ("load_collection", collection_name)
            )

    class FakeStorageContext:
        @classmethod
        def from_defaults(cls, **kwargs):
            captured["storage_context_kwargs"] = kwargs
            return cls()

    class FakeNode:
        text = "Milvus stores vector knowledge."

    class FakeRetriever:
        def retrieve(self, query):
            captured.setdefault("client_events", []).append(("retrieve", query))
            captured["query"] = query
            return [FakeNode()]

    class FakeVectorStoreIndex:
        def __init__(self, **kwargs):
            captured["vector_index_kwargs"] = kwargs

        def as_retriever(self, similarity_top_k):
            captured["similarity_top_k"] = similarity_top_k
            return FakeRetriever()

    def fake_create_embedding_model(**kwargs):
        captured["embedding_kwargs"] = kwargs
        return "fake-embedding-model"

    llama_index_core.StorageContext = FakeStorageContext
    llama_index_core.VectorStoreIndex = FakeVectorStoreIndex
    llama_index_milvus.MilvusVectorStore = FakeMilvusVectorStore
    ark_embedding.create_embedding_model = fake_create_embedding_model

    monkeypatch.setitem(sys.modules, "llama_index", llama_index)
    monkeypatch.setitem(sys.modules, "llama_index.core", llama_index_core)
    monkeypatch.setitem(
        sys.modules, "llama_index.vector_stores", llama_index_vector_stores
    )
    monkeypatch.setitem(
        sys.modules, "llama_index.vector_stores.milvus", llama_index_milvus
    )
    monkeypatch.setitem(sys.modules, "veadk.models.ark_embedding", ark_embedding)

    return captured


def test_get_backend_cls_returns_milvus_backend():
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    assert _get_backend_cls("milvus") is MilvusKnowledgeBackend


def test_milvus_config_defaults():
    config = MilvusConfig()

    assert config.uri == ""
    assert config.token == ""
    assert config.user == ""
    assert config.password == ""
    assert config.db_name == "default"
    assert config.overwrite is False
    assert config.timeout is None
    assert config.output_fields == []


def test_milvus_config_reads_environment(monkeypatch):
    monkeypatch.setenv("DATABASE_MILVUS_URI", "./milvus_test.db")
    monkeypatch.setenv("DATABASE_MILVUS_TOKEN", "token")
    monkeypatch.setenv("DATABASE_MILVUS_DB_NAME", "kb")
    monkeypatch.setenv("DATABASE_MILVUS_OVERWRITE", "true")
    monkeypatch.setenv("DATABASE_MILVUS_TIMEOUT", "3.5")
    monkeypatch.setenv("DATABASE_MILVUS_OUTPUT_FIELDS", "text,metadata")

    config = MilvusConfig()

    assert config.uri == "./milvus_test.db"
    assert config.token == "token"
    assert config.db_name == "kb"
    assert config.overwrite is True
    assert config.timeout == 3.5
    assert config.output_fields == "text,metadata"


def test_milvus_backend_initializes_vector_store(fake_milvus_dependencies):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(
            uri="./milvus.db",
            user="user",
            password="password",
            db_name="kb",
            overwrite=True,
            timeout=5.0,
        ),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    assert fake_milvus_dependencies["vector_store_kwargs"] == {
        "uri": "./milvus.db",
        "collection_name": "company_faq",
        "dim": 128,
        "overwrite": True,
        "token": "user:password",
        "db_name": "kb",
        "timeout": 5.0,
    }
    assert fake_milvus_dependencies["embedding_kwargs"] == {
        "model_name": "embedding",
        "api_key": "key",
        "api_base": "https://example.test/api/v3/",
    }


def test_milvus_backend_prefers_explicit_token(fake_milvus_dependencies):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(
            uri="./milvus.db",
            token="explicit",
            user="user",
            password="password",
        ),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    assert fake_milvus_dependencies["vector_store_kwargs"]["token"] == "explicit"


def test_milvus_backend_passes_output_fields(fake_milvus_dependencies):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(
            uri="./milvus.db",
            output_fields=["text", "metadata"],
        ),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    assert fake_milvus_dependencies["vector_store_kwargs"]["output_fields"] == [
        "text",
        "metadata",
    ]


def test_milvus_backend_parses_output_fields_string(fake_milvus_dependencies):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(
            uri="./milvus.db",
            output_fields="text, metadata",
        ),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    assert fake_milvus_dependencies["vector_store_kwargs"]["output_fields"] == [
        "text",
        "metadata",
    ]


@pytest.mark.parametrize("index", ["", "1bad", "bad-name", "bad.name"])
def test_milvus_backend_rejects_invalid_collection_names(monkeypatch, index):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    monkeypatch.setattr(MilvusKnowledgeBackend, "model_post_init", lambda *_: None)
    backend = MilvusKnowledgeBackend(index=index)

    with pytest.raises(ValueError, match="Milvus collection name"):
        backend.precheck_index_naming()


def test_milvus_backend_requires_uri(fake_milvus_dependencies):
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    with pytest.raises(ValueError, match="Milvus uri must be configured"):
        MilvusKnowledgeBackend(
            index="company_faq",
            embedding_config=NormalEmbeddingModelConfig(
                name="embedding",
                dim=128,
                api_base="https://example.test/api/v3/",
                api_key="key",
            ),
        )


def test_knowledgebase_milvus_search_wraps_strings(
    monkeypatch, fake_milvus_dependencies
):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "key")
    monkeypatch.setenv("DATABASE_MILVUS_URI", "./milvus.db")

    from veadk.knowledgebase import KnowledgeBase
    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    kb = KnowledgeBase(backend="milvus", index="company_faq")

    assert isinstance(kb._backend, MilvusKnowledgeBackend)
    entries = kb.search("what is Milvus?", top_k=3)

    assert entries[0].content == "Milvus stores vector knowledge."
    assert fake_milvus_dependencies["query"] == "what is Milvus?"
    assert fake_milvus_dependencies["similarity_top_k"] == 3


def test_milvus_backend_loads_released_collection_before_search(
    fake_milvus_dependencies,
):
    fake_milvus_dependencies["load_state"] = {"state": "released"}

    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    backend = MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(uri="./milvus.db"),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    backend.search("what is Milvus?", top_k=3)

    assert fake_milvus_dependencies["client_events"] == [
        ("get_load_state", "company_faq"),
        ("load_collection", "company_faq"),
        ("retrieve", "what is Milvus?"),
    ]


def test_milvus_backend_does_not_load_loaded_collection(fake_milvus_dependencies):
    fake_milvus_dependencies["load_state"] = {"state": "Loaded"}

    from veadk.knowledgebase.backends.milvus_backend import MilvusKnowledgeBackend

    backend = MilvusKnowledgeBackend(
        index="company_faq",
        milvus_config=MilvusConfig(uri="./milvus.db"),
        embedding_config=NormalEmbeddingModelConfig(
            name="embedding",
            dim=128,
            api_base="https://example.test/api/v3/",
            api_key="key",
        ),
    )

    backend.search("what is Milvus?", top_k=3)

    assert fake_milvus_dependencies["client_events"] == [
        ("get_load_state", "company_faq"),
        ("retrieve", "what is Milvus?"),
    ]
