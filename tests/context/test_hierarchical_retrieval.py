"""Cold indexing must admit exact evidence without indexing every fine span.

The synthetic embedder limits work deterministically rather than relying on
machine speed. Semantic fixtures prove routing and budgets, not answer quality.
The same tests run against the frozen fine-span baseline without this module.
"""

import asyncio
from dataclasses import replace
import time

import pytest

from veadk.context._hybrid_index import (
    EmbeddingUnavailable,
    Scope,
    digest,
    ranges,
)
from veadk.context.retrieval import _matches, _preview

try:
    from veadk.context.hierarchical_retriever import (
        HierarchicalContextRetriever as Retriever,
    )
except ModuleNotFoundError as exc:
    if exc.name != "veadk.context.hierarchical_retriever":
        raise
    from veadk.context.hybrid_retriever import HybridContextRetriever as Retriever


IDENTITY = ("app", "user", "session", "agent", "branch")
SCOPE = Scope(*IDENTITY)
QUERY = "Where are car and doctor?"
FACTS = ("The automobile is at East Garage.", "The physician is at West Clinic.")


def source(padding="z"):
    return padding * 14000 + FACTS[0] + padding * 14000 + FACTS[1] + padding * 14000


class Semantic:
    model = "offline-hierarchical-routing-v1"
    dimension = 3

    def __init__(self, limit=None):
        self.limit = limit
        self.documents = 0
        self.queries = 0
        self.requests = []

    async def embed(self, texts):
        self.requests.append(list(texts))
        self.queries += sum(text == QUERY for text in texts)
        requested = sum(text != QUERY for text in texts)
        if self.limit is not None and self.documents + requested > self.limit:
            raise EmbeddingUnavailable("synthetic_work_limit")
        self.documents += requested
        return [
            [1.0, 0.0, 0.0]
            if text == QUERY or any(fact in text for fact in FACTS)
            else [0.0, 1.0, 0.0]
            for text in texts
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("padding,budget", [("z", 1300), ("补", 3400), ("🙂", 4500)])
async def test_cold_budget_admits_two_distant_semantic_facts_with_less_index_work(
    tmp_path, padding, budget
):
    text = source(padding)
    embedder = Semantic(limit=64)
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "record", text, QUERY)
        assert retriever.last_status == "hybrid"
        matches = _matches(text, spans, budget, preview=True)
        preview = _preview(matches)
        assert all(fact in preview for fact in FACTS)
        assert len(preview.encode()) <= budget
        assert embedder.documents < len(list(ranges(text))) * 0.75
        assert embedder.queries == 1
        assert all(
            match["text"] == text[match["offset"] : match["end"]] for match in matches
        )
        assert (
            retriever._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_restart_reuses_both_levels_and_reads_original_not_child_archive(
    tmp_path,
):
    text = source()
    path = tmp_path / "index.sqlite3"
    embedder = Semantic(limit=64)
    retriever = Retriever(path, embedder)
    try:
        first = await retriever.rank(IDENTITY, "record", text, QUERY)
        assert retriever.last_status == "hybrid"
        before = embedder.documents
    finally:
        await retriever.close()
    retriever = Retriever(path, embedder)
    try:
        second = await retriever.rank(IDENTITY, "record", text, QUERY)
        assert first == second and second
        assert embedder.documents == before and embedder.queries == 2
        assert path.stat().st_mode & 0o777 == 0o600
        assert (
            retriever._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
        )
        for field in ("app", "user", "session", "agent", "branch"):
            with pytest.raises(ValueError):
                retriever._store.read(
                    replace(SCOPE, **{field: "other"}),
                    "record",
                    digest(text),
                    0,
                    len(text),
                )
    finally:
        await retriever.close()


class StallChildren(Semantic):
    def __init__(self):
        super().__init__()
        self.waiting = asyncio.Event()
        self.cancelled = False

    async def embed(self, texts):
        if self.queries and texts != [QUERY]:
            self.waiting.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True
        return await super().embed(texts)


@pytest.mark.asyncio
async def test_child_timeout_uses_complete_parents_without_partial_child_ranking(
    tmp_path,
):
    embedder = StallChildren()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    text = source()
    try:
        spans = await retriever.rank_with_deadline(
            IDENTITY, "record", text, QUERY, deadline=time.monotonic() + 0.25
        )
        assert embedder.waiting.is_set() and embedder.cancelled
        assert retriever.last_status == "parent_semantic_child_lexical"
        assert spans and all(0 <= a < b <= len(text) for a, b in spans)
        children = retriever._store.chunks(SCOPE)
        assert children and all(
            retriever._store.vector(SCOPE, c, embedder.model, 3) is None
            for c in children
        )
        assert (
            retriever._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_external_cancel_propagates_joins_child_work_and_restart_keeps_parents(
    tmp_path,
):
    path = tmp_path / "index.sqlite3"
    embedder = StallChildren()
    retriever = Retriever(path, embedder)
    text = source()
    task = asyncio.create_task(retriever.rank(IDENTITY, "record", text, QUERY))
    try:
        await asyncio.wait_for(embedder.waiting.wait(), 1.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert embedder.cancelled
        prepared = embedder.documents
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await retriever.close()
    resumed = Semantic()
    retriever = Retriever(path, resumed)
    try:
        spans = await retriever.rank(IDENTITY, "record", text, QUERY)
        assert spans and retriever.last_status == "hybrid"
        assert 0 < resumed.documents < prepared
        assert resumed.queries == 1
        assert (
            retriever._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_new_document_allowance_is_shared_by_parent_and_child_stages(tmp_path):
    text = source()
    embedder = Semantic()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder, max_new_chunks=7)
    try:
        for _ in range(12):
            before = embedder.documents
            spans = await retriever.rank(IDENTITY, "record", text, QUERY)
            assert embedder.documents - before <= 7
            if retriever.last_status == "hybrid":
                assert spans
                break
        else:
            pytest.fail(
                "bounded indexing did not reach complete parent and child retrieval"
            )
        assert embedder.documents < len(list(ranges(text))) * 0.75
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_incomplete_parent_index_never_enters_semantic_search(tmp_path):
    embedder = Semantic()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder, max_new_chunks=3)
    try:
        spans = await retriever.rank(IDENTITY, "record", source(), QUERY)
        assert spans == [] and retriever.last_status == "index_budget_fallback"
        assert embedder.documents == 3 and embedder.queries == 0
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("invalid", ["dimension", "zero", "nan"])
async def test_invalid_child_batch_keeps_valid_parent_fallback(tmp_path, invalid):
    class InvalidChildren(Semantic):
        async def embed(self, texts):
            child = self.queries and texts != [QUERY]
            vectors = await super().embed(texts)
            if child:
                vectors[-1] = {
                    "dimension": [1.0],
                    "zero": [0.0, 0.0, 0.0],
                    "nan": [float("nan"), 0.0, 0.0],
                }[invalid]
            return vectors

    embedder = InvalidChildren()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "record", source(), QUERY)
        assert spans and retriever.last_status == "parent_semantic_child_lexical"
        assert all(
            retriever._store.vector(SCOPE, c, embedder.model, 3) is None
            for c in retriever._store.chunks(SCOPE)
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_expired_deadline_uses_exact_lexical_spans_without_embedding(tmp_path):
    embedder = Semantic()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    text = "z" * 1800 + " car record is retained. " + "z" * 1800
    try:
        spans = await retriever.rank_with_deadline(
            IDENTITY, "record", text, "car", deadline=time.monotonic() - 1.0
        )
        assert spans and embedder.requests == []
        assert retriever.last_status == "timeout_bm25_fallback"
        assert all(0 <= a < b <= len(text) for a, b in spans)
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_child_model_change_rejects_mixed_vector_space(tmp_path):
    class Changed(Semantic):
        async def embed(self, texts):
            child = self.queries and texts != [QUERY]
            vectors = await super().embed(texts)
            if child:
                self.model = "different-space"
            return vectors

    retriever = Retriever(tmp_path / "index.sqlite3", Changed())
    try:
        with pytest.raises(ValueError, match="embedding_version_changed"):
            await retriever.rank(IDENTITY, "record", source(), QUERY)
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_tiny_preview_never_fabricates_or_truncates_selected_evidence(tmp_path):
    retriever = Retriever(tmp_path / "index.sqlite3", Semantic())
    text = source()
    try:
        spans = await retriever.rank(IDENTITY, "record", text, QUERY)
        assert _matches(text, spans, 1, preview=True) == []
        assert (
            retriever._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_closed_or_foreign_source_cannot_reuse_cached_children(tmp_path):
    retriever = Retriever(tmp_path / "index.sqlite3", Semantic())
    text = source()
    try:
        await retriever.rank(IDENTITY, "record", text, QUERY)
        with pytest.raises(ValueError, match="immutable_source_conflict"):
            await retriever.rank(IDENTITY, "record", text + "changed", QUERY)
        with pytest.raises(ValueError):
            retriever._store.read(
                replace(SCOPE, user="other"), "record", digest(text), 0, len(text)
            )
    finally:
        await retriever.close()
    with pytest.raises(ValueError, match="index_closed"):
        await retriever.rank(IDENTITY, "record", text, QUERY)


@pytest.mark.asyncio
async def test_original_changed_during_child_embedding_cannot_return_stale_evidence(
    tmp_path,
):
    class Mutating(Semantic):
        async def embed(self, texts):
            child = self.queries and texts != [QUERY]
            vectors = await super().embed(texts)
            if child:
                retriever._store.db.execute(
                    "UPDATE sources SET body='changed' WHERE source='record'"
                )
                retriever._store.db.commit()
            return vectors

    retriever = Retriever(tmp_path / "index.sqlite3", Mutating())
    try:
        with pytest.raises(ValueError, match="source_integrity"):
            await retriever.rank(IDENTITY, "record", source(), QUERY)
    finally:
        await retriever.close()


@pytest.mark.parametrize("unit", ["abcde", "x" * 750 + "\n\n"])
def test_parent_partition_preserves_maximum_source_without_increasing_capacity(unit):
    from veadk.context._hybrid_index import MAX_CHUNKS, MAX_SOURCE_BYTES

    try:
        from veadk.context.hierarchical_retriever import parent_ranges
    except ModuleNotFoundError:
        parent_ranges = ranges
    text = (unit * (MAX_SOURCE_BYTES // len(unit) + 1))[:MAX_SOURCE_BYTES]
    spans = list(parent_ranges(text))
    assert 0 < len(spans) <= MAX_CHUNKS
    assert spans[0][0] == 0 and spans[-1][1] == len(text)
    assert all(0 <= a < b <= len(text) for a, b in spans)
    assert all(
        spans[i][0] < spans[i + 1][0] <= spans[i][1] for i in range(len(spans) - 1)
    )
