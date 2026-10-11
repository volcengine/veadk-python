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

"""Explicit embedding role separation and resumable indexing contracts."""

import asyncio

import pytest

from veadk.context.hierarchical_retriever import _QueryReuse
from veadk.context._hybrid_index import Store, Scope, prepare, search
from test_hybrid_index import FakeEmbedding


@pytest.mark.asyncio
async def test_query_and_passage_never_share_cached_vectors():
    class Roles:
        model = "roles-v1"
        dimension = 2
        batch_size = 2
        queries = 0
        passages = 0

        async def embed(self, texts):
            self.passages += 1
            return [[0.0, 1.0] for _ in texts]

        async def embed_query(self, texts):
            self.queries += 1
            return [[1.0, 0.0] for _ in texts]

    inner = Roles()
    wrapper = _QueryReuse(inner, "identical text")
    assert wrapper.batch_size == 2
    assert await wrapper.embed_query(["identical text"]) == [[1.0, 0.0]]
    assert await wrapper.embed(["identical text"]) == [[0.0, 1.0]]
    assert await wrapper.embed_query(["identical text"]) == [[1.0, 0.0]]
    assert inner.queries == inner.passages == 1
    inner.model = "roles-v2"
    await wrapper.embed_query(["identical text"])
    assert inner.queries == 2


@pytest.mark.asyncio
async def test_search_encodes_query_with_its_role(tmp_path):
    class Roles(FakeEmbedding):
        query_calls = 0

        async def embed_query(self, texts):
            self.query_calls += 1
            return await super().embed(texts)

    encoder = Roles()
    scope = Scope("app", "user", "session", "agent")
    store = Store(tmp_path / "index.sqlite3")
    try:
        store.put(scope, "source", "The warranty lasts seven years.")
        await prepare(store, scope, encoder)
        _, status = await search(store, scope, "warranty", encoder)
        assert not status["degraded"] and encoder.query_calls == 1
    finally:
        store.close()


@pytest.mark.asyncio
async def test_small_batches_commit_before_cancellation_and_resume(tmp_path):
    class Paused(FakeEmbedding):
        batch_size = 2
        block = True
        entered = asyncio.Event()
        cancelled = False
        seen = []

        async def embed(self, texts):
            self.seen.append(list(texts))
            if self.block and len(self.seen) == 2:
                self.entered.set()
                try:
                    await asyncio.Future()
                finally:
                    self.cancelled = True
            return await super().embed(texts)

    encoder = Paused()
    scope = Scope("app", "u", "s", "a")
    store = Store(tmp_path / "index.sqlite3")
    text = "\n\n".join(
        f"Evidence record {i:03d}: The original vehicle warranty remains seven years."
        for i in range(100)
    )
    try:
        store.put(scope, "source", text)
        chunks = store.chunks(scope)
        assert len(chunks) > 4
        work = asyncio.create_task(prepare(store, scope, encoder))
        await asyncio.wait_for(encoder.entered.wait(), 2)
        work.cancel()
        with pytest.raises(asyncio.CancelledError):
            await work
        assert encoder.cancelled
        cached = [
            c
            for c in chunks
            if store.vector(scope, c, encoder.model, encoder.dimension) is not None
        ]
        assert len(cached) == 2
        first = encoder.seen[0]
        encoder.block = False
        encoder.seen = []
        status = await prepare(store, scope, encoder)
        assert not status["degraded"] and status["reused"] == 2
        assert all(item not in first for batch in encoder.seen for item in batch)
        assert all(c.text == text[c.start : c.end] for c in store.chunks(scope))
    finally:
        store.close()
