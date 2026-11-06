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

from veadk.memory.long_term_memory_backends import in_memory_backend
from veadk.memory.long_term_memory_backends.in_memory_backend import (
    InMemoryLTMBackend,
)


@pytest.fixture
def backend(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(
        in_memory_backend,
        "create_embedding_model",
        lambda **_: MockEmbedding(embed_dim=8),
    )
    return InMemoryLTMBackend(index="test")


def test_search_memory_only_returns_memories_of_the_given_user(backend):
    backend.save_memory(user_id="alice", event_strings=["alice likes tea"])
    backend.save_memory(user_id="bob", event_strings=["bob likes coffee"])

    assert backend.search_memory(user_id="alice", query="likes", top_k=5) == [
        "alice likes tea"
    ]
    assert backend.search_memory(user_id="bob", query="likes", top_k=5) == [
        "bob likes coffee"
    ]


def test_search_memory_for_user_without_memories_is_empty(backend):
    backend.save_memory(user_id="alice", event_strings=["alice likes tea"])

    assert backend.search_memory(user_id="carol", query="likes", top_k=5) == []
