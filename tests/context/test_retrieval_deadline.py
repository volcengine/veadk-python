"""Optional embedding must not consume the time needed to return original evidence."""

import asyncio
import copy
import time

import pytest

from veadk.context import retrieval
from veadk.context.history import eligible_prefix_end
from veadk.context.history_retrieval import select_history
from veadk.context.hybrid_retriever import HybridContextRetriever
from veadk.context.budget import count_input, request_payload
from test_compression import content
from test_hybrid_history import scope_for
from test_hybrid_incremental import Embedding, StallAfterCompletedBatch, source_text
from test_long_history_evidence import FACT_A, PIN, original_history, policy, prepare


def selected_text(values, selected):
    return "\n".join(values[i].parts[p].text[a:b] for i, p, a, b in selected)


@pytest.mark.asyncio
async def test_cold_timeout_returns_original_lexical_evidence_and_resumes_index(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.4)
    path = tmp_path / "index.sqlite3"
    values = [content("user", source_text(35))]
    embedder = StallAfterCompletedBatch()
    retriever = HybridContextRetriever(path, embedder)
    scope = scope_for(values, retriever)
    before = copy.deepcopy(scope.session)
    try:
        selected = await select_history(scope, values, "car")
        assert selected and "car" in selected_text(values, selected)
        assert scope.session == before and embedder.cancelled
        assert scope.evidence_retrieval_status == "selected"
        assert (
            retriever._store.db.execute("SELECT count(*) FROM vectors").fetchone()[0]
            == 16
        )
        count = retriever._store.db.execute("SELECT count(*) FROM chunks").fetchone()[0]
        assert count > 16
    finally:
        await retriever.close()
    resumed = Embedding()
    retriever = HybridContextRetriever(path, resumed)
    try:
        scope = scope_for(values, retriever)
        selected = await select_history(scope, values, "car")
        assert selected and scope.session == before
        assert retriever.last_status == "hybrid"
        assert sum(map(len, resumed.requests)) == count - 16 + 1
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_warm_query_timeout_still_returns_lexical_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.3)
    values = [content("user", "Coverage CV-7284 expires in 2031.")]
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", Embedding())
    try:
        assert await select_history(scope_for(values, retriever), values, "coverage")

        class SlowQuery(Embedding):
            async def embed(self, texts):
                self.requests.append(texts)
                await asyncio.Event().wait()

        embedder = SlowQuery()
        retriever._embedder = embedder
        selected = await select_history(scope_for(values, retriever), values, "CV-7284")
        assert selected and "CV-7284" in selected_text(values, selected)
        assert embedder.requests == [["CV-7284"]]
        assert (
            retriever._store.db.execute("SELECT count(*) FROM vectors").fetchone()[0]
            == 1
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [12000, 20000])
async def test_real_history_manager_admits_evidence_when_cold_embedding_stalls(
    tmp_path, monkeypatch, budget
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.8)
    values = original_history()
    before = copy.deepcopy(values)
    embedder = StallAfterCompletedBatch()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        request, scope, client = await prepare(values, retriever, policy(budget))
        rendered = "\n".join(p.text or "" for c in request.contents for p in c.parts)
        assert FACT_A in rendered and PIN in rendered and embedder.cancelled
        assert not client.requests and scope.summary_calls == 0
        assert count_input(request_payload(request), policy(budget)) <= budget
        end = eligible_prefix_end(values, policy(budget).keep_recent_turns)
        assert request.contents[-len(values[end:]) :] == values[end:]
        assert [event.content for event in scope.session.events] == before == values
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_external_cancellation_is_not_converted_to_fallback(tmp_path):
    embedder = StallAfterCompletedBatch()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    values = [content("user", source_text(35))]
    task = asyncio.create_task(
        select_history(scope_for(values, retriever), values, "car")
    )
    try:
        await asyncio.wait_for(embedder.waiting.wait(), 2)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert embedder.cancelled and retriever.last_status == "cancelled"
        assert (
            retriever._store.db.execute("SELECT count(*) FROM vectors").fetchone()[0]
            == 16
        )
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("mutation", ["delete", "replace", "model"])
async def test_timeout_fallback_never_bypasses_source_or_model_revalidation(
    tmp_path, monkeypatch, mutation
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.25)
    values = [content("user", "Coverage CV-7284 expires in 2031.")]

    class Changing(Embedding):
        async def embed(self, texts):
            if mutation == "delete":
                scope.session.events.clear()
            elif mutation == "replace":
                scope.session.events[0].content.parts[0].text = "A different source."
            else:
                self.model = "different-model"
            await asyncio.Event().wait()

    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", Changing())
    scope = scope_for(values, retriever)
    try:
        assert await select_history(scope, values, "CV-7284") == []
        assert (
            retriever._store.db.execute("SELECT count(*) FROM vectors").fetchone()[0]
            == 0
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_no_lexical_match_does_not_return_partial_dense_results(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.3)
    values = [content("user", source_text(35))]
    embedder = StallAfterCompletedBatch()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        assert (
            await select_history(scope_for(values, retriever), values, "automobile")
            == []
        )
        assert embedder.cancelled
        assert ["automobile"] not in embedder.requests
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_contended_index_still_allows_authorized_keyword_evidence(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.3)
    values = [content("user", "Unicode 原文🙂 coverage identifier CV-7284.")]
    embedder = Embedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    await retriever._lock.acquire()
    scope = scope_for(values, retriever)
    before = copy.deepcopy(scope.session)
    try:
        selected = await select_history(scope, values, "CV-7284")
        assert selected and "原文🙂" in selected_text(values, selected)
        assert scope.session == before and embedder.requests == []
    finally:
        retriever._lock.release()
        await retriever.close()


@pytest.mark.asyncio
async def test_shared_remaining_deadline_bounds_optional_index_wait(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 10.0)
    values = [content("user", source_text(35))]
    embedder = StallAfterCompletedBatch()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    scope = scope_for(values, retriever)
    began = time.monotonic()
    scope.evidence_retrieval_deadline = began + 0.35
    try:
        selected = await select_history(scope, values, "car")
        assert selected and embedder.cancelled
        assert time.monotonic() - began < 0.65
        # Once the shared budget is exhausted another source cannot renew it.
        scope.evidence_retrieval_deadline = time.monotonic() - 0.01
        calls = len(embedder.requests)
        assert await select_history(scope, values, "background") == []
        assert len(embedder.requests) == calls
    finally:
        await retriever.close()
