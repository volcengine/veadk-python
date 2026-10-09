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

"""Bounded ingestion and query isolation for input-driven granularity.

The frozen baseline uses its existing fine retriever so the long-source failure
is an actual incomplete index, not a missing-module failure.
"""

import asyncio
import time
from types import SimpleNamespace

import pytest

from veadk.context._hybrid_index import Scope, digest, ranges

try:
    from veadk.context.adaptive_retriever import AdaptiveContextRetriever as Retriever
except ModuleNotFoundError as exc:
    if exc.name != "veadk.context.adaptive_retriever":
        raise
    from veadk.context.hybrid_retriever import HybridContextRetriever as Retriever

IDENTITY = ("app", "user", "session", "agent", "")
FACT = "The automobile is stored at East Garage."
QUERY = "car"
SHORT = "z" * 31000 + FACT + "z" * 31000
LONG = "z" * 240000 + FACT + "z" * 240000
# Functional completeness/reuse checks are not five-second CPU/SQLite benchmarks.
# Keep a watchdog; short deadline and cancellation contracts are tested separately.
FUNCTIONAL_TIMEOUT = 30.0


class Embedding:
    model = "offline-adaptive-v1"
    dimension = 2

    def __init__(self):
        self.documents = 0
        self.queries = 0
        self.active = 0
        self.stall = False
        self.entered = asyncio.Event()

    async def embed(self, texts):
        self.active += 1
        try:
            if self.stall:
                self.entered.set()
                await asyncio.Event().wait()
            if texts == [QUERY]:
                self.queries += 1
            else:
                self.documents += len(texts)
            return [
                [1.0, 0.0] if text == QUERY or FACT in text else [0.0, 1.0]
                for text in texts
            ]
        finally:
            self.active -= 1


async def prepare(
    r, text, *, ref="source", identity=IDENTITY, seconds=FUNCTIONAL_TIMEOUT
):
    return await r.prepare_source(
        identity, ref, text, deadline=time.monotonic() + seconds
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [False, True])
async def test_long_source_completes_one_bounded_ingestion_then_recovers_semantic_fact(
    tmp_path, restart
):
    e = Embedding()
    path = tmp_path / "index.sqlite3"
    r = Retriever(path, e)
    try:
        assert sum(1 for _ in ranges(LONG)) > 512
        ready = await prepare(r, LONG)
        assert ready["complete"] and ready["remaining"] == 0
        assert 0 < ready["indexed"] <= 512 and e.queries == 0
        assert ready["granularity"] == "hierarchical_parent"
        if restart:
            await r.close()
            r = Retriever(path, e)
        again = await prepare(r, LONG)
        assert again["complete"] and again["indexed"] == 0
        spans = await r.rank_with_deadline(
            IDENTITY,
            "source",
            LONG,
            QUERY,
            deadline=time.monotonic() + FUNCTIONAL_TIMEOUT,
        )
        assert r.last_status == "hybrid"
        assert any(FACT in LONG[a:b] for a, b in spans)
        assert all(0 <= a < b <= len(LONG) for a, b in spans)
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_short_source_keeps_fine_semantics_and_query_does_no_document_work(
    tmp_path,
):
    e = Embedding()
    r = Retriever(tmp_path / "index.sqlite3", e)
    try:
        ready = await prepare(r, SHORT)
        assert ready["complete"] and ready["granularity"] == "full_source_fine"
        before = e.documents
        spans = await r.rank_with_deadline(
            IDENTITY,
            "source",
            SHORT,
            QUERY,
            deadline=time.monotonic() + FUNCTIONAL_TIMEOUT,
        )
        assert e.documents == before and e.queries == 1
        assert any(FACT in SHORT[a:b] for a, b in spans)
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_shared_database_concurrent_routes_reuse_and_preserve_originals(tmp_path):
    e = Embedding()
    r = Retriever(tmp_path / "index.sqlite3", e)
    try:
        ready = await asyncio.gather(
            prepare(r, SHORT, ref="short"), prepare(r, LONG, ref="long")
        )
        assert all(item["complete"] for item in ready)
        again = await asyncio.gather(
            prepare(r, SHORT, ref="short"), prepare(r, LONG, ref="long")
        )
        assert all(item["complete"] and item["indexed"] == 0 for item in again)
        for delegate, ref, text in (
            (r._fine, "short", SHORT),
            (r._parent, "long", LONG),
        ):
            store = delegate._parents if ref == "long" else delegate._store
            assert store.read(Scope(*IDENTITY), ref, digest(text), 0, len(text)) == text
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_cross_route_same_reference_rejects_mutated_source(tmp_path):
    r = Retriever(tmp_path / "index.sqlite3", Embedding())
    try:
        await prepare(r, SHORT)
        with pytest.raises(ValueError, match="immutable_source_conflict"):
            await prepare(r, LONG)
        assert (await prepare(r, SHORT))["indexed"] == 0
    finally:
        await r.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", range(5))
async def test_foreign_identity_never_reuses_vectors(tmp_path, field):
    r = Retriever(tmp_path / "index.sqlite3", Embedding())
    try:
        first = await prepare(r, LONG)
        other = list(IDENTITY)
        other[field] = "foreign"
        foreign = await prepare(r, LONG, identity=tuple(other))
        assert first["complete"] and foreign["complete"]
        assert foreign["reused"] == 0 and foreign["indexed"] == first["indexed"]
    finally:
        await r.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [SHORT, LONG], ids=["fine", "parent"])
async def test_cancellation_joins_embedding_without_switching_routes(tmp_path, text):
    e = Embedding()
    e.stall = True
    r = Retriever(tmp_path / "index.sqlite3", e)
    task = asyncio.create_task(prepare(r, text))
    try:
        await asyncio.wait_for(e.entered.wait(), 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert e.active == e.documents == e.queries == 0
        e.stall = False
        assert (await prepare(r, text))["complete"]
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await r.close()


@pytest.mark.asyncio
async def test_parent_capacity_exceeded_is_still_incomplete_not_success(tmp_path):
    r = Retriever(tmp_path / "index.sqlite3", Embedding(), max_new_chunks=7)
    try:
        result = await prepare(r, LONG)
        assert not result["complete"] and result["reason"] == "index_budget"
        assert result["indexed"] == 7 and result["remaining"] > 0
    finally:
        await r.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [SHORT, LONG], ids=["fine", "parent"])
async def test_preparation_budget_includes_source_storage_before_embedding(
    tmp_path, text, monkeypatch
):
    from veadk.context import _hybrid_index, hierarchical_retriever, hybrid_retriever

    clock = [100.0]
    timer = SimpleNamespace(monotonic=lambda: clock[0])
    for module in (_hybrid_index, hierarchical_retriever, hybrid_retriever):
        monkeypatch.setattr(module, "time", timer)
    original_put = _hybrid_index.Store.put
    delayed = [False]

    def slow_store(store, *args, **kwargs):
        result = original_put(store, *args, **kwargs)
        if not delayed[0]:
            delayed[0] = True
            clock[0] += 6.0
        return result

    monkeypatch.setattr(_hybrid_index.Store, "put", slow_store)
    e = Embedding()
    r = Retriever(tmp_path / "index.sqlite3", e)
    try:
        result = await r.prepare_source(IDENTITY, "source", text, deadline=105.0)
        assert not result["complete"] and result["reason"] == "TimeoutError"
        assert result["indexed"] == 0 and result["remaining"] > 0
        assert result["seconds"] == pytest.approx(6.0)
        assert e.documents == e.queries == e.active == 0
        store = r._fine._store if text == SHORT else r._parent._parents
        assert (
            store.read(Scope(*IDENTITY), "source", digest(text), 0, len(text)) == text
        )
        resumed = await r.prepare_source(IDENTITY, "source", text, deadline=111.0)
        assert resumed["complete"] and resumed["remaining"] == 0
        assert resumed["indexed"] > 0 and resumed["reused"] == 0
    finally:
        await r.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [SHORT, LONG], ids=["fine", "parent"])
async def test_deadline_includes_delegate_lock_wait_and_no_embedding(tmp_path, text):
    e = Embedding()
    r = Retriever(tmp_path / "index.sqlite3", e)
    try:
        delegate = r._fine if text == SHORT else r._parent
        async with delegate._lock:
            result = await prepare(r, text, seconds=0.03)
            assert not result["complete"] and result["reason"] == "timeout"
            spans = await r.rank_with_deadline(
                IDENTITY,
                "source",
                text,
                "East Garage",
                deadline=time.monotonic() + 0.03,
            )
            assert r.last_status == "timeout_bm25_fallback"
            assert any("East Garage" in text[a:b] for a, b in spans)
        assert e.documents == e.queries == 0
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_reserved_reference_and_changed_model_rejected_before_work(tmp_path):
    e = Embedding()
    r = Retriever(tmp_path / "index.sqlite3", e)
    try:
        with pytest.raises(ValueError, match="invalid_source"):
            await prepare(r, SHORT, ref="hierarchical-child-v1:external")
        for field, value in (("model", "changed"), ("dimension", 3)):
            old = getattr(e, field)
            setattr(e, field, value)
            with pytest.raises(ValueError, match="embedding_version_changed"):
                await prepare(r, LONG)
            setattr(e, field, old)
        assert e.documents == e.queries == 0
    finally:
        await r.close()


@pytest.mark.asyncio
async def test_cancelled_close_drains_both_connections_and_rejects_new_work(tmp_path):
    r = Retriever(tmp_path / "index.sqlite3", Embedding())
    await r._parent._lock.acquire()
    closing = asyncio.create_task(r.close())
    try:
        await asyncio.sleep(0)
        with pytest.raises(ValueError, match="index_closed"):
            await prepare(r, SHORT)
        closing.cancel()
        await asyncio.sleep(0)
        assert not closing.done()
    finally:
        r._parent._lock.release()
        with pytest.raises(asyncio.CancelledError):
            await closing
        await r.close()
    assert r._fine._closed and r._parent._closed


@pytest.mark.asyncio
async def test_actual_history_selector_accepts_adaptive_offsets_and_keeps_original_session(
    tmp_path,
):
    from google.genai import types
    from veadk.context.history_retrieval import select_history
    from test_hybrid_history import scope_for

    r = Retriever(tmp_path / "index.sqlite3", Embedding())
    contents = [types.Content(role="user", parts=[types.Part(text=SHORT)])]
    scope = scope_for(contents, r)
    before = scope.session.model_dump()
    try:
        selected = await select_history(scope, contents, QUERY)
        assert any(FACT in contents[i].parts[p].text[a:b] for i, p, a, b in selected)
        assert scope.session.model_dump() == before
    finally:
        await r.close()
