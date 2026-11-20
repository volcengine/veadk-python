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

"""Mem0LTMBackend must scope memories by LongTermMemory.index (app_name).

Other LTM backends (VikingDB collection, Redis/OpenSearch index name,
OpenViking app_name, TOS ContextBucket name) all use ``index`` to keep
distinct apps under the same credentials from sharing memories. Mem0
accepts the same isolation via ``agent_id``; without it, two
``LongTermMemory(backend="mem0", app_name=...)`` instances that share a
Mem0 project leak memories across apps for the same user_id.
"""

from __future__ import annotations

from typing import Any

import pytest

from veadk.configs.database_configs import Mem0Config
from veadk.memory.long_term_memory_backends import mem0_backend
from veadk.memory.long_term_memory_backends.mem0_backend import Mem0LTMBackend


class _FakeMemoryClient:
    """Shared in-memory stand-in that records add/search kwargs like Mem0 1.x.

    Class-level ``_store`` simulates one Mem0 project shared by every client
    created with the same credentials.
    """

    _store: dict[tuple[str, str | None], list[str]] = {}

    def __init__(self, host: str | None = None, api_key: str | None = None):
        self.host = host
        self.api_key = api_key
        self.add_calls: list[dict[str, Any]] = []
        self.search_calls: list[dict[str, Any]] = []

    def add(self, messages, **kwargs):
        self.add_calls.append({"messages": messages, **kwargs})
        user_id = kwargs.get("user_id", "default_user")
        agent_id = kwargs.get("agent_id")
        key = (user_id, agent_id)
        for message in messages:
            self._store.setdefault(key, []).append(message["content"])
        return {"results": []}

    def search(self, query: str, **kwargs):
        self.search_calls.append({"query": query, **kwargs})
        user_id = kwargs.get("user_id", "default_user")
        agent_id = kwargs.get("agent_id")
        memories = list(self._store.get((user_id, agent_id), []))
        top_k = kwargs.get("top_k", len(memories))
        return {"results": [{"memory": m} for m in memories[:top_k]]}


@pytest.fixture
def fake_mem0(monkeypatch):
    _FakeMemoryClient._store = {}
    monkeypatch.setattr(mem0_backend, "MemoryClient", _FakeMemoryClient)
    return _FakeMemoryClient


def _backend(index: str) -> Mem0LTMBackend:
    return Mem0LTMBackend(
        index=index,
        mem0_config=Mem0Config(api_key="test-key", base_url="https://mem0.example"),
    )


def test_save_and_search_pass_index_as_agent_id(fake_mem0):
    backend = _backend("app_alpha")

    assert backend.save_memory(user_id="u1", event_strings=["alpha secret"])
    results = backend.search_memory(user_id="u1", query="secret", top_k=5)

    assert backend._mem0_client.add_calls[0]["agent_id"] == "app_alpha"
    assert backend._mem0_client.search_calls[0]["agent_id"] == "app_alpha"
    assert results == ["alpha secret"]


def test_different_indexes_do_not_share_memories_for_same_user(fake_mem0):
    alpha = _backend("app_alpha")
    beta = _backend("app_beta")

    alpha.save_memory(user_id="u1", event_strings=["alpha-only memory"])
    beta.save_memory(user_id="u1", event_strings=["beta-only memory"])

    assert alpha.search_memory(user_id="u1", query="memory", top_k=5) == [
        "alpha-only memory"
    ]
    assert beta.search_memory(user_id="u1", query="memory", top_k=5) == [
        "beta-only memory"
    ]


def test_save_memory_signature_matches_base_backend(fake_mem0):
    """BaseLongTermMemoryBackend.save_memory(user_id, event_strings, ...).

    Callers (and LongTermMemory) may pass args positionally; Mem0 must not
    swap the parameters.
    """
    backend = _backend("app_alpha")

    # positional: user_id first, then event_strings (base-class order)
    assert backend.save_memory("u1", ["positional ok"]) is True
    assert backend._mem0_client.add_calls[0]["user_id"] == "u1"
    assert backend._mem0_client.add_calls[0]["messages"] == [
        {"role": "user", "content": "positional ok"}
    ]
