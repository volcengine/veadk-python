"""Exercise actual retriever input selection, source integrity and fallback."""

import asyncio
import copy
import time
from types import SimpleNamespace

import pytest

from veadk.context.hybrid_retriever import HybridContextRetriever
from veadk.context._hybrid_index import Scope, digest


IDENTITY = ("app", "user", "session", "agent", "")


class RecordingEmbedding:
    model = "offline-focus-v1"
    dimension = 3

    def __init__(self):
        self.requests = []

    async def embed(self, texts):
        self.requests.append(list(texts))
        # A synthetic semantic boundary, not a simulated quality score.
        return [
            [0.0, 1.0, 0.0] if "FORMATTING_DISTRACTION" in t else [1.0, 0.0, 0.0]
            for t in texts
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question",
    [
        "Which warehouse stores replacement pumps?",
        "For batch Q7 in 2024 only: Which warehouse stores replacement pumps?",
        "只考虑2024年Q7批次：备件泵存放在哪个仓库？",
        "Where are pumps stored? Which batch is covered?",
    ],
)
async def test_focus_keeps_complete_question_line_and_scoped_original(
    tmp_path, question
):
    embedder = RecordingEmbedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    query = (
        "FORMATTING_DISTRACTION: produce concise prose.\n\n"
        + question
        + "\n\nReturn plain text."
    )
    original = "Replacement pumps for batch Q7 are stored at East warehouse."
    try:
        selected = await retriever.rank(IDENTITY, "record", original, query)
        assert embedder.requests[-1] == [question]
        assert len(embedder.requests) == 2  # one source batch, one query
        assert selected and original[selected[0][0] : selected[0][1]] == original
        assert (
            retriever._store.read(
                Scope(*IDENTITY), "record", digest(original), 0, len(original)
            )
            == original
        )
        assert query.startswith("FORMATTING_DISTRACTION")
    finally:
        await retriever.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "Locate the warehouse for replacement pumps.\nRespond concisely.",
        "The selected supplier is Acme.\nWhere is its warehouse?",
        "供应商是甲公司。\n它的仓库在哪里？",
        '```python\nprint("Where is the warehouse?")\n```\nExplain the code.',
        "> Where is the warehouse?\nAnalyze the quotation.",
        "Which warehouse?\nWhich batch?",
        'Look up the question "Which warehouse?" in the notes.\nList matches.',
        "Which warehouse?",
    ],
)
async def test_ambiguous_or_declarative_query_is_not_rewritten(tmp_path, query):
    embedder = RecordingEmbedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        await retriever.rank(IDENTITY, "record", "East warehouse stores pumps.", query)
        assert embedder.requests[-1] == [query]
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_separate_constraints_still_participate_in_lexical_rank(
    tmp_path, monkeypatch
):
    from veadk.context import _hybrid_index as index

    calls = []
    baseline = index.bm25_rank

    def record(chunks, query, *args, **kwargs):
        calls.append(query)
        return baseline(chunks, query, *args, **kwargs)

    monkeypatch.setattr(index, "bm25_rank", record)
    full = "Only the 2024 Q7 batch is authorized.\nWhich warehouse stores pumps?\nReturn plain text."
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", RecordingEmbedding())
    try:
        await retriever.rank(
            IDENTITY, "record", "Q7 2024 pumps are in East warehouse.", full
        )
        assert full in calls and "Which warehouse stores pumps?" in calls
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_multiple_question_lines_preserved_together(tmp_path):
    embedder = RecordingEmbedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    query = "Use the report.\nWhich warehouse stores pumps?\nWhen does the lease expire?\nReturn prose."
    try:
        await retriever.rank(
            IDENTITY, "record", "East warehouse lease expires in 2031.", query
        )
        assert embedder.requests[-1] == [
            "Which warehouse stores pumps?\nWhen does the lease expire?"
        ]
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_timeout_fallback_prioritizes_question_but_retains_original(tmp_path):
    class Slow(RecordingEmbedding):
        async def embed(self, texts):
            await asyncio.Event().wait()

    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", Slow())
    query = "FORMATTING_DISTRACTION: produce prose.\nWhich warehouse stores pumps?\nReturn plain text."
    source = "FORMATTING_DISTRACTION " * 90 + "\n\n" + "Warehouse stores pumps. " * 70
    try:
        selected = await retriever.rank_with_deadline(
            IDENTITY, "record", source, query, deadline=time.monotonic() + 0.05
        )
        assert (
            selected
            and "Warehouse stores pumps." in source[selected[0][0] : selected[0][1]]
        )
        assert retriever.last_status == "timeout_bm25_fallback"
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_framing_no_longer_selects_irrelevant_source_first(tmp_path):
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", RecordingEmbedding())
    query = "FORMATTING_DISTRACTION: produce concise prose.\nWhich warehouse stores pumps?\nReturn plain text."
    irrelevant = "FORMATTING_DISTRACTION produce concise prose return plain text. "
    evidence = "East warehouse stores replacement pumps for batch Q7. "
    source = irrelevant * 80 + "\n\n" + evidence * 90
    try:
        selected = await retriever.rank(IDENTITY, "record", source, query)
        assert selected
        first = source[selected[0][0] : selected[0][1]]
        assert "East warehouse stores replacement pumps" in first
        assert "FORMATTING_DISTRACTION" not in first
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_actual_manager_preserves_user_request_and_original_events(tmp_path):
    from veadk.context.manager import prepare_context
    from veadk.context.runtime import current_scope
    from veadk.context.budget import count_input, request_payload
    from test_preview_admission import example

    original, request, scope, policy, before = example(16000)
    request.contents[-1].parts[
        0
    ].text = "Return only the requested fact.\nWhat is the audited balance for record 113?\nUse units."
    user = copy.deepcopy(request.contents[-1])
    events = copy.deepcopy(scope.session.events)
    embedder = RecordingEmbedding()
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    scope.evidence_retriever = retriever
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
        assert request.contents[-1] == user and scope.session.events == events
        assert count_input(request_payload(request), policy) < before
        assert count_input(request_payload(request), policy) <= policy.input_limit
        assert embedder.requests[-1] == ["What is the audited balance for record 113?"]
        assert scope.evidence_retrieval_status == "selected"
    finally:
        current_scope.reset(token)
        await retriever.close()
