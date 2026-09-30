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

"""Durable progress at cancellation, provider failure and SDK history boundaries."""

import asyncio
from types import SimpleNamespace
import pytest

from veadk.context._hybrid_index import Scope, Store, prepare, search
from veadk.context.hybrid_retriever import HybridContextRetriever
from veadk.context.history_retrieval import select_history
from veadk.context import retrieval
from test_compression import content
from test_hybrid_history import scope_for


IDENTITY = ("app", "user", "session", "agent", "branch")
SCOPE = Scope(*IDENTITY)


def source_text(records=24):
    return "".join(
        f"Record {i:03}: car " + "background detail " * 60 + ".\n\n"
        for i in range(records)
    )


def saved(store, scope=SCOPE, model="offline-incremental-v1", dimension=3):
    return [
        chunk
        for chunk in store.chunks(scope)
        if store.vector(scope, chunk, model, dimension) is not None
    ]


class Embedding:
    model = "offline-incremental-v1"
    dimension = 3

    def __init__(self):
        self.requests = []

    async def embed(self, texts):
        self.requests.append(list(texts))
        return [[1.0, 0.0, 0.0] for _ in texts]


class StallAfterCompletedBatch(Embedding):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()
        self.cancelled = False

    async def embed(self, texts):
        # A call containing the whole source cannot return a partial result.
        # A bounded first batch can finish before the next provider call stalls.
        if not self.requests and len(texts) <= 16:
            return await super().embed(texts)
        self.requests.append(list(texts))
        self.waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            self.cancelled = True


@pytest.mark.asyncio
async def test_external_cancel_retains_committed_batch_and_restart_only_embeds_missing(
    tmp_path,
):
    path = tmp_path / "index.sqlite3"
    store = Store(path)
    body = source_text()
    sha = store.put(SCOPE, "source", body)
    chunks = store.chunks(SCOPE)
    assert len(chunks) > 16
    embedder = StallAfterCompletedBatch()
    task = asyncio.create_task(prepare(store, SCOPE, embedder))
    try:
        await asyncio.wait_for(embedder.waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert embedder.cancelled
        assert len(saved(store)) == 16
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        store.close()
    reopened = Store(path)
    resumed = Embedding()
    try:
        result = await prepare(reopened, SCOPE, resumed)
        assert not result["degraded"]
        assert result["indexed"] == len(chunks) - 16
        assert result["reused"] == 16
        assert [t for call in resumed.requests for t in call] == [
            c.embedding_text for c in chunks[16:]
        ]
        assert reopened.read(SCOPE, "source", sha, 0, len(body)) == body
    finally:
        reopened.close()


@pytest.mark.asyncio
async def test_internal_timeout_retains_completed_batch_but_search_stays_lexical(
    tmp_path,
):
    store = Store(tmp_path / "index.sqlite3")
    try:
        store.put(SCOPE, "source", source_text())
        embedder = StallAfterCompletedBatch()
        status = await prepare(store, SCOPE, embedder, timeout=0.1)
        assert status["degraded"] and status["indexed"] == 16
        assert len(saved(store)) == 16 and embedder.cancelled
        query = Embedding()
        ranked, result = await search(store, SCOPE, "automobile", query)
        assert result["degraded"] and result["dense_matches"] == 0
        assert ranked == [] and query.requests == []
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["count", "dimension", "nan", "zero"])
async def test_bad_later_batch_preserves_prior_commit_and_rejects_entire_bad_batch(
    tmp_path, failure
):
    class InvalidLater(Embedding):
        async def embed(self, texts):
            already = sum(len(call) for call in self.requests)
            vectors = await super().embed(texts)
            if already + len(texts) > 16:
                if failure == "count":
                    return vectors[:-1]
                vectors[-1] = {
                    "dimension": [1.0],
                    "nan": [float("nan"), 0, 0],
                    "zero": [0, 0, 0],
                }[failure]
            return vectors

    store = Store(tmp_path / "index.sqlite3")
    try:
        store.put(SCOPE, "source", source_text(45))
        chunks = store.chunks(SCOPE)
        assert len(chunks) > 32
        status = await prepare(store, SCOPE, InvalidLater())
        assert status["degraded"] and status["indexed"] == 16
        assert saved(store) == chunks[:16]
        resumed = Embedding()
        status = await prepare(store, SCOPE, resumed)
        assert not status["degraded"] and status["reused"] == 16
        assert [t for call in resumed.requests for t in call] == [
            c.embedding_text for c in chunks[16:]
        ]
    finally:
        store.close()


@pytest.mark.asyncio
async def test_chunk_allowance_advances_across_restarts_and_no_partial_dense_ranking(
    tmp_path,
):
    path = tmp_path / "index.sqlite3"
    embedder = Embedding()
    body = source_text(8)
    retriever = HybridContextRetriever(path, embedder, max_new_chunks=3)
    retriever._store.put(SCOPE, "source", body)
    total = len(retriever._store.chunks(SCOPE))
    assert total > 3
    previous = 0
    try:
        for _ in range((total + 2) // 3):
            before = len(embedder.requests)
            spans = await retriever.rank(IDENTITY, "source", body, "automobile")
            indexed = len(saved(retriever._store))
            assert indexed == min(previous + 3, total)
            new_calls = embedder.requests[before:]
            if indexed < total:
                assert retriever.last_status == "index_budget_fallback"
                assert spans == []
                assert all("automobile" not in call for call in new_calls)
            else:
                assert retriever.last_status == "hybrid" and spans
                assert new_calls[-1] == ["automobile"]
            previous = indexed
            await retriever.close()
            retriever = HybridContextRetriever(path, embedder, max_new_chunks=3)
        assert [t for call in embedder.requests for t in call if t != "automobile"] == [
            c.embedding_text for c in retriever._store.chunks(SCOPE)
        ]
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field,value", [("model", "changed-model"), ("dimension", 2)])
async def test_provider_identity_change_during_await_does_not_write_vectors(
    tmp_path, field, value
):
    class Mutating(Embedding):
        async def embed(self, texts):
            vectors = await super().embed(texts)
            setattr(self, field, value)
            return vectors

    embedder = Mutating()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "source", "car", "automobile")
        assert spans == [] and retriever.last_status == "embedding_fallback"
        assert (
            retriever._store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
            == 0
        )
        calls = len(embedder.requests)
        with pytest.raises(ValueError, match="embedding_version_changed"):
            await retriever.rank(IDENTITY, "source", "car", "automobile")
        assert len(embedder.requests) == calls
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["body", "title", "range"])
async def test_source_change_during_embedding_cannot_commit_stale_vectors(
    tmp_path, change
):
    store = Store(tmp_path / "index.sqlite3")
    store.put(SCOPE, "source", "car evidence")

    class Mutating(Embedding):
        async def embed(self, texts):
            vectors = await super().embed(texts)
            statements = {
                "body": "UPDATE sources SET body='different'",
                "title": "UPDATE sources SET title='different'",
                "range": "UPDATE chunks SET end=2",
            }
            store.db.execute(statements[change])
            store.db.commit()
            return vectors

    try:
        result = await prepare(store, SCOPE, Mutating())
        assert result["degraded"]
        assert store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0] == 0
        with pytest.raises(ValueError):
            store.chunks(SCOPE)
    finally:
        store.close()


@pytest.mark.asyncio
async def test_sdk_history_timeout_can_resume_index_without_changing_original_session(
    tmp_path, monkeypatch
):
    path = tmp_path / "derived.sqlite3"
    contents = [content("user", source_text())]
    retriever = HybridContextRetriever(path, StallAfterCompletedBatch())
    scope = scope_for(contents, retriever)
    original = scope.session.model_copy(deep=True)
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.2)
    try:
        assert await select_history(scope, contents, "automobile") == []
        assert scope.session == original
        assert (
            retriever._store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0]
            == 16
        )
    finally:
        await retriever.close()
    resumed = Embedding()
    retriever = HybridContextRetriever(path, resumed)
    # A new invocation has a fresh query cache, while the durable index survives.
    scope = scope_for(contents, retriever)
    try:
        selected = await select_history(scope, contents, "automobile")
        assert selected and retriever.last_status == "hybrid"
        assert scope.session == original
        for message, part, start, end in selected:
            assert 0 <= start < end <= len(contents[message].parts[part].text)
        chunks = retriever._store.db.execute("SELECT COUNT(*) FROM chunks").fetchone()[
            0
        ]
        assert sum(map(len, resumed.requests)) == chunks - 16 + 1
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_all_batches_share_one_timeout_instead_of_resetting_it(
    tmp_path, monkeypatch
):
    from veadk.context import _hybrid_index

    clock = [100.0]
    timeouts = []
    embedder = StallAfterCompletedBatch()

    async def bounded_batch(awaitable, timeout):
        timeouts.append(timeout)
        if len(timeouts) == 1:
            result = await asyncio.wait_for(awaitable, timeout=5)
            clock[0] += 0.2
            return result
        task = asyncio.create_task(awaitable)
        try:
            await asyncio.wait_for(embedder.waiting.wait(), timeout=5)
            clock[0] += timeout
            return await asyncio.wait_for(task, timeout=0)
        finally:
            if not task.done():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    # Verify the second batch receives only the remaining budget, independent
    # of host scheduling, while retaining real cancellation and durable writes.
    monkeypatch.setattr(
        _hybrid_index, "time", SimpleNamespace(monotonic=lambda: clock[0])
    )
    monkeypatch.setattr(
        _hybrid_index,
        "asyncio",
        SimpleNamespace(**{**vars(asyncio), "wait_for": bounded_batch}),
    )

    store = Store(tmp_path / "index.sqlite3")
    try:
        store.put(SCOPE, "source", source_text(45))
        status = await prepare(store, SCOPE, embedder, timeout=0.35)
        assert timeouts == [pytest.approx(0.35), pytest.approx(0.15)]
        assert status["seconds"] == pytest.approx(0.35)
        assert status["degraded"] and status["indexed"] == 16
        assert embedder.cancelled and len(saved(store)) == 16
    finally:
        store.close()


@pytest.mark.asyncio
async def test_query_model_change_cannot_mix_vector_spaces(tmp_path):
    class ChangingQuery(Embedding):
        async def embed(self, texts):
            vectors = await super().embed(texts)
            if texts == ["automobile"]:
                self.model = "different-space"
            return vectors

    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", ChangingQuery())
    try:
        spans = await retriever.rank(IDENTITY, "source", "car", "automobile")
        assert spans == [] and retriever.last_status == "embedding_fallback"
        assert len(saved(retriever._store)) == 1
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_history_above_default_512_allowance_eventually_uses_full_hybrid_index(
    tmp_path,
):
    body = source_text(650)
    embedder = Embedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "source", body, "automobile")
        total = len(retriever._store.chunks(SCOPE))
        # The fixed full history must advance within the same per-call
        # allowance even if a new chunk version produces more source spans.
        from veadk.context._hybrid_index import MAX_CHUNKS

        assert 512 < total <= MAX_CHUNKS
        assert spans == [] and retriever.last_status == "index_budget_fallback"
        assert len(saved(retriever._store)) == 512
        for call_index in range(1, (total + 511) // 512):
            previous = len(saved(retriever._store))
            spans = await retriever.rank(IDENTITY, "source", body, "automobile")
            committed = len(saved(retriever._store))
            assert committed == min(total, (call_index + 1) * 512)
            assert 0 < committed - previous <= 512
            if committed < total:
                assert spans == [] and retriever.last_status == "index_budget_fallback"
            else:
                assert spans and retriever.last_status == "hybrid"
        assert len(saved(retriever._store)) == total
        assert sum(map(len, embedder.requests)) == total + 1
        assert all(len(call) <= 16 for call in embedder.requests)
    finally:
        await retriever.close()
