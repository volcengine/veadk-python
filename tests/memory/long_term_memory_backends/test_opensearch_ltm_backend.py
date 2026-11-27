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

"""OpensearchLTMBackend must not map distinct (index, user_id) pairs to one index.

``f"{self.index}_{user_id}"`` is ambiguous: backends with
``index="app"`` / ``user_id="u1_x"`` and ``index="app_u1"`` / ``user_id="x"``
both resolve to ``app_u1_x`` and therefore share memories.
"""

from __future__ import annotations

import pytest
from llama_index.core.embeddings import MockEmbedding

from veadk.configs.database_configs import OpensearchConfig
from veadk.memory.long_term_memory_backends import opensearch_backend
from veadk.memory.long_term_memory_backends.opensearch_backend import (
    OpensearchLTMBackend,
)


@pytest.fixture
def patch_embed(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "test-key")
    monkeypatch.setattr(
        opensearch_backend,
        "create_embedding_model",
        lambda **_: MockEmbedding(embed_dim=8),
    )


def _backend(index: str) -> OpensearchLTMBackend:
    return OpensearchLTMBackend(
        index=index,
        opensearch_config=OpensearchConfig(
            host="localhost",
            port=9200,
            username="admin",
            password="admin",
            use_ssl=False,
        ),
    )


def test_underscore_join_collides_for_nested_index_and_user_id():
    """Document the bug shape before the scoped-index helper is applied."""
    assert f"{'app'}_{'u1_x'}" == f"{'app_u1'}_{'x'}" == "app_u1_x"


def test_user_scoped_index_disambiguates_nested_underscore_pairs(patch_embed):
    app = _backend("app")
    app_u1 = _backend("app_u1")

    left = app._user_scoped_index("u1_x")
    right = app_u1._user_scoped_index("x")

    assert left != right
    assert left.islower()
    assert right.islower()
    assert not left.startswith(("_", "-"))
    assert not right.startswith(("_", "-"))


def test_user_scoped_index_is_stable_for_same_pair(patch_embed):
    backend = _backend("my-app")

    assert backend._user_scoped_index("alice") == backend._user_scoped_index("alice")


def test_user_scoped_index_differs_for_raw_values_that_sanitize_alike(patch_embed):
    """Sanitizing alone would collapse ``u1_x`` and ``u1-x``; digests must not."""
    backend = _backend("app")

    assert backend._user_scoped_index("u1_x") != backend._user_scoped_index("u1-x")


def test_save_and_search_use_the_same_scoped_index(patch_embed, monkeypatch):
    backend = _backend("app")
    seen: list[str] = []

    def fake_create(index: str):
        seen.append(index)

        class _Index:
            def insert_nodes(self, nodes):
                return None

            def as_retriever(self, similarity_top_k: int):
                class _Retriever:
                    def retrieve(self, query):
                        return []

                return _Retriever()

        return _Index()

    monkeypatch.setattr(backend, "_create_vector_index", fake_create)

    backend.save_memory(user_id="u1_x", event_strings=["hello"])
    backend.search_memory(user_id="u1_x", query="hello", top_k=3)

    assert seen == [
        backend._user_scoped_index("u1_x"),
        backend._user_scoped_index("u1_x"),
    ]


def test_distinct_backends_do_not_share_scoped_index_on_collision_pair(
    patch_embed, monkeypatch
):
    app = _backend("app")
    app_u1 = _backend("app_u1")
    seen: list[str] = []

    def fake_create(index: str):
        seen.append(index)

        class _Index:
            def insert_nodes(self, nodes):
                return None

        return _Index()

    monkeypatch.setattr(app, "_create_vector_index", fake_create)
    monkeypatch.setattr(app_u1, "_create_vector_index", fake_create)

    app.save_memory(user_id="u1_x", event_strings=["from-app"])
    app_u1.save_memory(user_id="x", event_strings=["from-app-u1"])

    assert seen[0] != seen[1]
