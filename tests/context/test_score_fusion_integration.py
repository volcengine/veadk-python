"""Score-gap regressions at shared search and both native retrieval routes."""

import math
import time

import pytest

from veadk.context import _hybrid_index as index
from veadk.context.adaptive_retriever import AdaptiveContextRetriever
from veadk.context.score_fusion import distribution_fusion

IDENTITY = ("app", "user", "session", "agent", "")


class QueryEmbedding:
    model = "offline-score-gap-v1"
    dimension = 2

    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[1.0, 0.0] for _ in texts]


@pytest.mark.asyncio
@pytest.mark.parametrize("focused", [False, True])
async def test_search_preserves_score_gap_not_just_rank(tmp_path, monkeypatch, focused):
    store = index.Store(tmp_path / "index.sqlite3")
    scope = index.Scope(*IDENTITY)
    embedder = QueryEmbedding()
    try:
        for name in ("a", "b", "c"):
            store.put(scope, name, "Immutable evidence " + name)
        chunks = store.chunks(scope)
        assert len(chunks) == 3
        if focused:
            # Rank-only 3:1:.25 fusion favors b despite near-tied semantic
            # support and much stronger exact evidence for a.
            similarities = [0.89, 0.9, -0.9]
            lexical = [(0, 100.0), (1, 2.0), (2, 1.0)]
            question = "Follow the report.\nWhich evidence is relevant?\nReturn prose."
            expected = chunks[0].source
        else:
            # Opposed rankings tie under RRF, which chooses a by ID.
            # b retains middle lexical support and almost the strongest
            # semantic support; preserving the gap makes b the winner.
            similarities = [-0.9, 0.89, 0.9]
            lexical = [(0, 3.0), (1, 2.0), (2, 1.0)]
            question = "Find relevant evidence"
            expected = chunks[1].source
        store.save_vectors(
            scope,
            [(c, [v, math.sqrt(1 - v * v)]) for c, v in zip(chunks, similarities)],
            embedder.model,
            2,
        )
        monkeypatch.setattr(index, "bm25_rank", lambda *a, **k: list(lexical))
        found, status = await index.search(
            store, scope, question, embedder, focus_questions=True
        )
        assert not status["degraded"]
        assert found[0].source == expected
        for chunk in found:
            assert (
                store.read(
                    scope, chunk.source, chunk.source_sha, chunk.start, chunk.end
                )
                == chunk.text
            )
    finally:
        store.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("long_source", [False, True])
async def test_native_routes_share_fusion_and_reopen_original(
    tmp_path, monkeypatch, long_source
):
    fact = "The automobile is at East Garage."
    text = "z" * (240000 if long_source else 10000) + fact + "z" * 10000
    query = "car"

    class Semantic(QueryEmbedding):
        async def embed(self, texts):
            self.calls.append(list(texts))
            return [
                [1.0, 0.0] if t == query or fact in t else [0.0, 1.0] for t in texts
            ]

    calls = []

    def observe(rankings):
        calls.append(len(rankings))
        return distribution_fusion(rankings)

    # Setting an absent symbol is intentional for the old-search comparison:
    # the regression then fails on routing, never an import/attribute error.
    monkeypatch.setattr(index, "distribution_fusion", observe, raising=False)
    path = tmp_path / "index.sqlite3"
    embedder = Semantic()
    retriever = AdaptiveContextRetriever(path, embedder)
    try:
        prepared = await retriever.prepare_source(
            IDENTITY, "record", text, deadline=time.monotonic() + 5
        )
        assert prepared["complete"]
        assert prepared["granularity"] == (
            "hierarchical_parent" if long_source else "full_source_fine"
        )
        spans = await retriever.rank(IDENTITY, "record", text, query)
        assert retriever.last_status == "hybrid"
        assert len(calls) == (2 if long_source else 1)
        assert any(fact in text[a:b] for a, b in spans)
        assert all(0 <= a < b <= len(text) for a, b in spans)
    finally:
        await retriever.close()
    fresh = AdaptiveContextRetriever(path, embedder)
    try:
        prepared = await fresh.prepare_source(
            IDENTITY, "record", text, deadline=time.monotonic() + 5
        )
        assert prepared["indexed"] == 0
        assert await fresh.rank(IDENTITY, "record", text, query) == spans
        delegate = fresh._last
        store = delegate._parents if long_source else delegate._store
        assert (
            store.read(
                index.Scope(*IDENTITY), "record", index.digest(text), 0, len(text)
            )
            == text
        )
        with pytest.raises(ValueError):
            store.read(
                index.Scope("app", "other-user", "session", "agent", ""),
                "record",
                index.digest(text),
                0,
                len(text),
            )
    finally:
        await fresh.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["hybrid", "bm25", "dense"])
async def test_partial_index_uses_lexical_without_score_fusion(
    tmp_path, monkeypatch, mode
):
    store = index.Store(tmp_path / "index.sqlite3")
    scope = index.Scope(*IDENTITY)
    embedder = QueryEmbedding()
    try:
        store.put(scope, "a", "first unrelated material")
        store.put(scope, "b", "exact invoice code QX42")
        first = store.chunks(scope)[0]
        store.save_vectors(scope, [(first, [1.0, 0.0])], embedder.model, 2)

        def forbidden(*args):
            raise AssertionError("partial_index_must_not_enter_fusion")

        monkeypatch.setattr(index, "distribution_fusion", forbidden, raising=False)
        found, status = await index.search(store, scope, "QX42", embedder, mode=mode)
        assert [c.source for c in found] == ["b"]
        assert status["degraded"] == (mode != "bm25")
        assert not embedder.calls
    finally:
        store.close()
