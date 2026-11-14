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

import pytest
from llama_index.core.embeddings import MockEmbedding
from redis.exceptions import ResponseError
from redisvl.index.storage import BaseStorage

from veadk.memory.long_term_memory_backends import redis_backend
from veadk.memory.long_term_memory_backends.redis_backend import RedisLTMBackend


class _FakeSearch:
    def __init__(self, indexes, name):
        self._indexes, self._name = indexes, name

    def info(self):
        if self._name not in self._indexes:
            raise ResponseError("Unknown index name")
        return {"index_definition": ["prefixes", [self._indexes[self._name]]]}

    def dropindex(self, delete_documents=False):
        assert delete_documents is False
        del self._indexes[self._name]


class _FakeRedis:
    indexes: dict = {}

    def __init__(self, **_):
        pass

    def ft(self, name):
        return _FakeSearch(self.indexes, name)


class _FakeRedisVectorStore:
    def __init__(self, schema, redis_client):
        self.schema = schema
        self.index_name = schema.index.name


@pytest.fixture
def schemas(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(
        redis_backend,
        "create_embedding_model",
        lambda **_: MockEmbedding(embed_dim=8),
    )
    captured = {}

    def fake_from_vector_store(vector_store, embed_model):
        captured[vector_store.schema.index.name] = vector_store.schema
        return None

    _FakeRedis.indexes = {}
    monkeypatch.setattr(redis_backend, "Redis", _FakeRedis)
    monkeypatch.setattr(redis_backend, "RedisVectorStore", _FakeRedisVectorStore)
    monkeypatch.setattr(
        redis_backend.VectorStoreIndex,
        "from_vector_store",
        staticmethod(fake_from_vector_store),
    )
    backend = RedisLTMBackend(index="app")
    backend._create_vector_index("veadk-ltm/app/u1")
    backend._create_vector_index("veadk-ltm/app/u10")
    return captured


def _key(schema, node_id: str) -> str:
    return BaseStorage._key(node_id, schema.index.prefix, schema.index.key_separator)


def test_user_index_prefix_does_not_match_keys_of_other_users(schemas):
    u1 = schemas["veadk-ltm/app/u1"]
    u10 = schemas["veadk-ltm/app/u10"]

    # RediSearch indexes every hash whose key starts with the index prefix.
    assert not _key(u10, "node").startswith(u1.index.prefix)
    assert _key(u1, "node").startswith(u1.index.prefix)


def test_user_keys_keep_existing_format(schemas):
    u1 = schemas["veadk-ltm/app/u1"]

    assert _key(u1, "node") == "veadk-ltm/app/u1_node"


def test_index_created_with_old_prefix_is_redefined_without_deleting_data(schemas):
    _FakeRedis.indexes = {"veadk-ltm/app/u1": "veadk-ltm/app/u1"}
    backend = RedisLTMBackend(index="app")

    backend._create_vector_index("veadk-ltm/app/u1")

    # Only the stale index definition was dropped (documents kept), so the
    # vector store recreates it with the new prefix.
    assert "veadk-ltm/app/u1" not in _FakeRedis.indexes


def test_index_with_current_prefix_is_kept(schemas):
    _FakeRedis.indexes = {"veadk-ltm/app/u1": "veadk-ltm/app/u1_"}
    backend = RedisLTMBackend(index="app")

    backend._create_vector_index("veadk-ltm/app/u1")

    assert _FakeRedis.indexes == {"veadk-ltm/app/u1": "veadk-ltm/app/u1_"}
