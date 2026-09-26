"""Complete fine-grained indexing must finish before query-only work.

The work-budget embedder is deterministic; these are mechanism regressions,
not evidence that synthetic embeddings improve actual answer quality.
"""

import asyncio
from dataclasses import replace
import time

import pytest

from veadk.context._hybrid_index import EmbeddingUnavailable, Scope, digest
from veadk.context.hybrid_retriever import HybridContextRetriever as Retriever
from veadk.context.retrieval import _matches, _preview

IDENTITY = ("app", "user", "session", "agent", "branch")
SCOPE = Scope(*IDENTITY)
QUERY = "car"
FACT = "The automobile is stored at East Garage."
TEXT = "z" * 31000 + FACT + "z" * 31000


class BudgetedEmbedding:
    model = "offline-prepared-source-v1"
    dimension = 3

    def __init__(self):
        self.allow_documents = True
        self.documents = 0
        self.queries = 0
        self.active = 0
        self.stall_after = None
        self.waiting = asyncio.Event()

    async def embed(self, texts):
        self.active += 1
        try:
            if texts == [QUERY]:
                self.queries += 1
                return [[1.0, 0.0, 0.0]]
            if not self.allow_documents:
                raise EmbeddingUnavailable("query_document_work_budget")
            if self.stall_after is not None and self.documents >= self.stall_after:
                self.waiting.set()
                await asyncio.Event().wait()
            self.documents += len(texts)
            return [
                [1.0, 0.0, 0.0] if FACT in text else [0.0, 1.0, 0.0] for text in texts
            ]
        finally:
            self.active -= 1


async def prepare(retriever, *, deadline=None, identity=IDENTITY, text=TEXT):
    return await retriever.prepare_source(
        identity,
        "record",
        text,
        deadline=time.monotonic() + 5.0 if deadline is None else deadline,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("restart", [False, True])
async def test_complete_fine_index_survives_query_document_budget(tmp_path, restart):
    path = tmp_path / "index.sqlite3"
    embedder = BudgetedEmbedding()
    retriever = Retriever(path, embedder)
    try:
        # Same regression runs on the frozen baseline. Without a preparation
        # API, all cold document work competes with the query work budget.
        if hasattr(retriever, "prepare_source"):
            result = await prepare(retriever)
            assert result["complete"] and result["indexed"] > 16
            assert result["remaining"] == 0 and embedder.queries == 0
        if restart:
            await retriever.close()
            retriever = Retriever(path, embedder)
        embedder.allow_documents = False
        before = embedder.documents
        spans = await retriever.rank_with_deadline(
            IDENTITY, "record", TEXT, QUERY, deadline=time.monotonic() + 2.0
        )
        assert retriever.last_status == "hybrid"
        assert embedder.queries == 1 and embedder.documents == before
        assert FACT in _preview(_matches(TEXT, spans, 2200, preview=True))
        assert (
            retriever._store.read(SCOPE, "record", digest(TEXT), 0, len(TEXT)) == TEXT
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_cold_query_without_preparation_remains_explicit_lexical_fallback(
    tmp_path,
):
    embedder = BudgetedEmbedding()
    embedder.allow_documents = False
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "record", TEXT, QUERY)
        assert spans == [] and retriever.last_status == "embedding_fallback"
        assert embedder.queries == 0
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_preparation_is_query_independent_bounded_and_reuses_complete_source(
    tmp_path,
):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder, max_new_chunks=7)
    try:
        for _ in range(40):
            before = embedder.documents
            result = await prepare(retriever)
            assert 0 <= result["indexed"] <= 7
            assert embedder.documents - before == result["indexed"]
            assert embedder.queries == 0
            assert result["complete"] == (result["remaining"] == 0)
            if result["complete"]:
                break
            assert result["reason"] == "index_budget"
        else:
            pytest.fail("bounded preparation never completed")
        again = await prepare(retriever)
        assert again["complete"] and again["indexed"] == 0
        assert again["reused"] == embedder.documents
        assert retriever._store.chunks(SCOPE)
        assert all(
            retriever._store.vector(SCOPE, c, embedder.model, embedder.dimension)
            is not None
            for c in retriever._store.chunks(SCOPE)
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("external_cancel", [False, True])
async def test_interrupted_preparation_joins_io_keeps_batches_and_never_searches_partial(
    tmp_path, external_cancel
):
    path = tmp_path / "index.sqlite3"
    embedder = BudgetedEmbedding()
    embedder.stall_after = 16
    retriever = Retriever(path, embedder)
    task = asyncio.create_task(
        prepare(
            retriever, deadline=time.monotonic() + (5.0 if external_cancel else 0.2)
        )
    )
    try:
        await asyncio.wait_for(embedder.waiting.wait(), 1.0)
        if external_cancel:
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        else:
            result = await task
            assert not result["complete"]
        assert embedder.active == 0 and embedder.documents == 16
        embedder.allow_documents = False
        assert await retriever.rank(IDENTITY, "record", TEXT, QUERY) == []
        assert embedder.queries == 0 and retriever.last_status == "embedding_fallback"
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await retriever.close()
    resumed = BudgetedEmbedding()
    retriever = Retriever(path, resumed)
    try:
        result = await prepare(retriever)
        assert result["complete"] and result["reused"] == 16
        assert result["indexed"] == resumed.documents > 0 and resumed.queries == 0
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_preparation_deadline_covers_lock_wait_without_work(tmp_path):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        async with retriever._lock:
            result = await prepare(retriever, deadline=time.monotonic() + 0.05)
            assert not result["complete"] and result["reason"] == "timeout"
            assert result["remaining"] is None and embedder.documents == 0
        assert not retriever._store.chunks(SCOPE)
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["app", "user", "session", "agent", "branch"])
async def test_preparation_never_reuses_other_scope_vectors(tmp_path, field):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        first = await prepare(retriever)
        foreign = replace(SCOPE, **{field: "other"})
        foreign_identity = (
            foreign.app,
            foreign.user,
            foreign.session,
            foreign.agent,
            foreign.branch,
        )
        other = await prepare(retriever, identity=foreign_identity)
        assert first["complete"] and other["complete"]
        assert other["reused"] == 0 and other["indexed"] == first["indexed"]
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_preparation_rejects_source_conflict_model_change_and_closed_index(
    tmp_path,
):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        await prepare(retriever)
        with pytest.raises(ValueError, match="immutable_source_conflict"):
            await prepare(retriever, text=TEXT + "changed")
        embedder.model = "different-revision"
        with pytest.raises(ValueError, match="embedding_version_changed"):
            await prepare(retriever)
        embedder.model = "offline-prepared-source-v1"
    finally:
        await retriever.close()
    with pytest.raises(ValueError, match="index_closed"):
        await prepare(retriever)


@pytest.mark.asyncio
async def test_preparation_revalidates_source_after_embedding(tmp_path):
    class Mutating(BudgetedEmbedding):
        async def embed(self, texts):
            vectors = await super().embed(texts)
            retriever._store.db.execute(
                "UPDATE sources SET body='changed' WHERE source='record'"
            )
            retriever._store.db.commit()
            return vectors

    retriever = Retriever(tmp_path / "index.sqlite3", Mutating())
    try:
        with pytest.raises(ValueError, match="source_integrity"):
            await prepare(retriever)
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("deadline", [float("inf"), float("nan"), "later", True])
async def test_preparation_rejects_invalid_deadline_before_embedding(
    tmp_path, deadline
):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        with pytest.raises(ValueError, match="invalid_deadline"):
            await prepare(retriever, deadline=deadline)
        assert embedder.documents == 0
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_expired_preparation_does_not_claim_empty_index_complete(tmp_path):
    embedder = BudgetedEmbedding()
    retriever = Retriever(tmp_path / "index.sqlite3", embedder)
    try:
        result = await prepare(retriever, deadline=time.monotonic() - 1.0)
        assert not result["complete"] and result["remaining"] is None
        assert embedder.documents == embedder.queries == 0
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_full_fine_route_reaches_semantic_fact_outside_coarse_shortlist(tmp_path):
    from veadk.context.hierarchical_retriever import HierarchicalContextRetriever

    class DilutedEmbedding:
        model = "offline-coarse-dilution-v1"
        dimension = 2

        async def embed(self, texts):
            values = []
            for text in texts:
                if text == QUERY:
                    values.append([1.0, 0.0])
                elif len(text) > 600:
                    # Relevant sentence loses its signal inside a coarse chunk.
                    values.append(
                        [1.0, 0.0] if "Transportation overview" in text else [0.0, 1.0]
                    )
                else:
                    values.append([1.0, 0.0] if FACT in text else [0.3, 0.9])
            return values

    # No exact QUERY token: isolate semantic coarse-shortlist recall from the
    # separate RRF tradeoff where repeated exact keywords outrank one synonym.
    text = "".join(
        "Transportation overview.\n" + "z" * 1300 + ".\n\n" for _ in range(8)
    )
    text += "z" * 1800 + ".\n\n" + FACT + "\n" + "z" * 1000
    coarse = HierarchicalContextRetriever(
        tmp_path / "coarse.sqlite3", DilutedEmbedding()
    )
    fine = Retriever(tmp_path / "fine.sqlite3", DilutedEmbedding())
    try:
        if hasattr(fine, "prepare_source"):
            ready = await fine.prepare_source(
                IDENTITY, "record", text, deadline=time.monotonic() + 5.0
            )
            assert ready["complete"] and ready["granularity"] == "full_source_fine"
        coarse_spans = await coarse.rank(IDENTITY, "record", text, QUERY)
        fine_spans = await fine.rank(IDENTITY, "record", text, QUERY)
        assert not any(FACT in text[a:b] for a, b in coarse_spans)
        assert FACT in _preview(_matches(text, fine_spans, 2200, preview=True))
        assert all(0 <= a < b <= len(text) for a, b in fine_spans)
        assert fine._store.read(SCOPE, "record", digest(text), 0, len(text)) == text
    finally:
        await coarse.close()
        await fine.close()
