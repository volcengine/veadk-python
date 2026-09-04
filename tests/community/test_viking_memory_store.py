# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Regression tests for `VikingMemoryStore.abatch`.

`abatch` used to be a *synchronous* stub with a `...` body overriding
`BaseStore.abatch`, which is an `async def` abstract method. Every async
accessor on the base (`aget`/`asearch`/`aput`/`adelete`/`alist_namespaces`)
does a bare `await self.abatch(...)`, so the stub made all of them raise
`TypeError: object NoneType can't be used in 'await' expression`.
"""

import inspect
import json
import threading

import pytest

pytest.importorskip("langgraph")

from langgraph.store.base import (  # noqa: E402
    BaseStore,
    GetOp,
    SearchOp,
)

from veadk.community.langchain_ai.store.memory import viking_memory  # noqa: E402

INDEX = "test_index"
USER_ID = "test_user"


class _FakeVikingBackend:
    """Network-free stand-in for the (synchronous) `VikingDBLTMBackend`."""

    def __init__(self, index: str = INDEX):
        self.index = index
        self.saved: list[dict] = []
        self.searched: list[dict] = []
        self.call_threads: list[int] = []

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        self.call_threads.append(threading.get_ident())
        self.saved.append(
            {
                "user_id": user_id,
                "session_id": kwargs.get("session_id"),
                "event_strings": list(event_strings),
            }
        )
        return True

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        self.call_threads.append(threading.get_ident())
        self.searched.append({"user_id": user_id, "query": query, "top_k": top_k})
        return [f"memory about {query}"]


@pytest.fixture
def backend() -> _FakeVikingBackend:
    return _FakeVikingBackend()


@pytest.fixture
def store(monkeypatch, backend: _FakeVikingBackend):
    # `VikingDBLTMBackend.__init__` talks to VikingDB over the network, so the
    # store's only collaborator is replaced before construction.
    monkeypatch.setattr(
        viking_memory, "VikingDBLTMBackend", lambda index: backend, raising=True
    )
    return viking_memory.VikingMemoryStore(index=INDEX)


def test_abatch_is_a_coroutine_function():
    assert inspect.iscoroutinefunction(viking_memory.VikingMemoryStore.abatch)


def test_store_is_instantiable_with_both_batch_methods_defined(store):
    # `batch`/`abatch` are the only abstract methods on `BaseStore`, so defining
    # both is what makes the store constructible. A refactor that drops either
    # one turns `VikingMemoryStore` back into an abstract class.
    assert BaseStore.__abstractmethods__ == frozenset({"batch", "abatch"})
    assert "abatch" in viking_memory.VikingMemoryStore.__dict__
    assert "batch" in viking_memory.VikingMemoryStore.__dict__
    assert viking_memory.VikingMemoryStore.__abstractmethods__ == frozenset()
    assert isinstance(store, BaseStore)


@pytest.mark.asyncio
async def test_asearch_returns_results(store, backend):
    results = await store.asearch((INDEX, USER_ID), query="pizza", limit=3)

    assert results == ["memory about pizza"]
    assert backend.searched == [
        {"user_id": USER_ID, "query": "pizza", "top_k": 3},
    ]


@pytest.mark.asyncio
async def test_aget_returns_a_result(store):
    got = await store.aget((INDEX, USER_ID), "session-1")

    # `_apply_get_op` is still a placeholder; what matters here is that the
    # async accessor returns the sync result instead of raising.
    assert got is not None
    assert got == store.get((INDEX, USER_ID), "session-1")


@pytest.mark.asyncio
async def test_aput_reaches_the_backend(store, backend):
    event = {"role": "user", "parts": [{"text": "hello"}]}

    await store.aput((INDEX, USER_ID), "session-1", {"event-0": event})

    assert backend.saved == [
        {
            "user_id": USER_ID,
            "session_id": "session-1",
            "event_strings": [json.dumps(event)],
        }
    ]


@pytest.mark.asyncio
async def test_abatch_matches_batch(store):
    # Read-only ops, so running them twice is side-effect free.
    ops = [
        SearchOp(namespace_prefix=(INDEX, USER_ID), query="pizza", limit=2),
        GetOp(namespace=(INDEX, USER_ID), key="session-1"),
    ]

    assert await store.abatch(ops) == store.batch(ops)


@pytest.mark.asyncio
async def test_abatch_runs_off_the_event_loop(store, backend):
    loop_thread = threading.get_ident()

    await store.asearch((INDEX, USER_ID), query="pizza")

    assert backend.call_threads
    assert all(ident != loop_thread for ident in backend.call_threads)


def test_batch_stays_on_the_calling_thread(store, backend):
    store.search((INDEX, USER_ID), query="pizza")

    assert backend.call_threads == [threading.get_ident()]
