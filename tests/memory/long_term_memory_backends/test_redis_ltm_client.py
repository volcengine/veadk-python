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

from veadk.configs.database_configs import RedisConfig
from veadk.memory.long_term_memory_backends import redis_backend
from veadk.memory.long_term_memory_backends.redis_backend import RedisLTMBackend


@pytest.fixture
def redis_kwargs(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(
        redis_backend,
        "create_embedding_model",
        lambda **_: MockEmbedding(embed_dim=8),
    )
    captured = []

    class _FakeRedis:
        def __init__(self, **kwargs):
            captured.append(kwargs)

    class _FakeRedisVectorStore:
        def __init__(self, schema, redis_client):
            self.schema = schema
            self.index_name = schema.index.name

    monkeypatch.setattr(redis_backend, "Redis", _FakeRedis)
    monkeypatch.setattr(redis_backend, "RedisVectorStore", _FakeRedisVectorStore)
    monkeypatch.setattr(
        redis_backend.VectorStoreIndex,
        "from_vector_store",
        staticmethod(lambda vector_store, embed_model: None),
    )
    return captured


def test_redis_client_uses_configured_username(redis_kwargs):
    config = RedisConfig(
        host="redis.example", port=6380, username="ltm-user", password="pw", db=2
    )
    backend = RedisLTMBackend(index="app", redis_config=config)

    backend._create_vector_index("veadk-ltm/app/u1")

    assert redis_kwargs == [
        {
            "host": "redis.example",
            "port": 6380,
            "db": 2,
            "username": "ltm-user",
            "password": "pw",
        }
    ]


def test_redis_username_is_read_from_env(redis_kwargs, monkeypatch):
    monkeypatch.setenv("DATABASE_REDIS_HOST", "redis.example")
    monkeypatch.setenv("DATABASE_REDIS_USERNAME", "ltm-user")
    monkeypatch.setenv("DATABASE_REDIS_PASSWORD", "pw")
    backend = RedisLTMBackend(index="app")

    backend._create_vector_index("veadk-ltm/app/u1")

    assert redis_kwargs[0]["username"] == "ltm-user"
    assert redis_kwargs[0]["password"] == "pw"
