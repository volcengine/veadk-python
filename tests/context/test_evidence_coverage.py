"""A parent shortlist must not eliminate the full-source lexical route.

Synthetic embeddings intentionally favor several incomplete semantic matches.
The uncommon exact fact is outside that shortlist. These test actual ranked
source spans and the SDK preview budget, not a mocked final answer.
"""

import asyncio
from dataclasses import replace
import time

import pytest

from veadk.context._hybrid_index import Scope, digest
from veadk.context.hierarchical_retriever import HierarchicalContextRetriever
from veadk.context.retrieval import _matches, _preview


IDENTITY = ("app", "user", "session", "agent", "branch")
QUESTION = "Where is the car parked and what is its renewal code?"
LOCATION = "The automobile stays at North Garage."
RENEWAL = "Its renewal code is R-4812."


def document(unit="z"):
    sections = []
    for number in range(8):
        sections.append(
            f"Car parked guidance section {number}. "
            + (LOCATION if number == 0 else "General parking discussion.")
            + "\n"
            + unit * 1300
            + ".\n\n"
        )
    return "".join(sections) + unit * 1800 + ".\n\n" + RENEWAL + "\n" + unit * 1000


class CoarsePreference:
    model = "offline-evidence-coverage-v1"
    dimension = 2

    def __init__(self):
        self.documents = 0
        self.queries = 0

    async def embed(self, texts):
        self.documents += sum(text != QUESTION for text in texts)
        self.queries += sum(text == QUESTION for text in texts)
        return [
            [1.0, 0.0]
            if text == QUESTION or "Car parked guidance" in text or LOCATION in text
            else [0.0, 1.0]
            for text in texts
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("unit,budget", [("z", 1800), ("补", 5000), ("🙂", 6500)])
async def test_outside_parent_fact_reaches_budgeted_preview_without_losing_semantic_fact(
    tmp_path, unit, budget
):
    text = document(unit)
    embedder = CoarsePreference()
    retriever = HierarchicalContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "record", text, QUESTION)
        assert retriever.last_status == "hybrid"
        matches = _matches(text, spans, budget, preview=True)
        preview = _preview(matches)
        assert LOCATION in preview
        assert RENEWAL in preview
        assert len(preview.encode()) <= budget
        assert all(m["text"] == text[m["offset"] : m["end"]] for m in matches)
        assert embedder.queries == 1
        assert embedder.documents <= 512
        assert (
            retriever._store.read(
                Scope(*IDENTITY), "record", digest(text), 0, len(text)
            )
            == text
        )
    finally:
        await retriever.close()


class WaitForChildren(CoarsePreference):
    def __init__(self):
        super().__init__()
        self.entered = asyncio.Event()
        self.cancelled = False

    async def embed(self, texts):
        if self.queries and texts != [QUESTION]:
            self.entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cancelled = True
        return await super().embed(texts)


@pytest.mark.asyncio
async def test_child_timeout_keeps_whole_source_lexical_route_and_joins_work(tmp_path):
    text = document()
    embedder = WaitForChildren()
    retriever = HierarchicalContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank_with_deadline(
            IDENTITY, "record", text, QUESTION, deadline=time.monotonic() + 0.5
        )
        assert embedder.entered.is_set() and embedder.cancelled
        assert retriever.last_status == "parent_semantic_child_lexical"
        preview = _preview(_matches(text, spans, 1800, preview=True))
        assert LOCATION in preview and RENEWAL in preview
        assert len(preview.encode()) <= 1800
        assert all(
            retriever._store.vector(Scope(*IDENTITY), chunk, embedder.model, 2) is None
            for chunk in retriever._store.chunks(Scope(*IDENTITY))
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_supplement_does_not_cross_scope_or_replace_original(tmp_path):
    text = document()
    retriever = HierarchicalContextRetriever(
        tmp_path / "index.sqlite3", CoarsePreference()
    )
    scope = Scope(*IDENTITY)
    try:
        await retriever.rank(IDENTITY, "record", text, QUESTION)
        for field in ("app", "user", "session", "agent", "branch"):
            with pytest.raises(ValueError):
                retriever._store.read(
                    replace(scope, **{field: "other"}),
                    "record",
                    digest(text),
                    0,
                    len(text),
                )
        with pytest.raises(ValueError, match="immutable_source_conflict"):
            await retriever.rank(IDENTITY, "record", text + " changed", QUESTION)
        assert (
            retriever._store.read(scope, "record", digest(text), 0, len(text)) == text
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_external_cancel_propagates_instead_of_starting_supplement(tmp_path):
    embedder = WaitForChildren()
    retriever = HierarchicalContextRetriever(tmp_path / "index.sqlite3", embedder)
    task = asyncio.create_task(retriever.rank(IDENTITY, "record", document(), QUESTION))
    try:
        await asyncio.wait_for(embedder.entered.wait(), 2.0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert embedder.cancelled
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        await retriever.close()


@pytest.mark.asyncio
async def test_reopen_reuses_vectors_and_tiny_budget_remains_empty(tmp_path):
    text = document()
    embedder = CoarsePreference()
    path = tmp_path / "index.sqlite3"
    first = HierarchicalContextRetriever(path, embedder)
    try:
        expected = await first.rank(IDENTITY, "record", text, QUESTION)
        documents = embedder.documents
    finally:
        await first.close()
    second = HierarchicalContextRetriever(path, embedder)
    try:
        actual = await second.rank(IDENTITY, "record", text, QUESTION)
        assert actual == expected
        assert embedder.documents == documents and embedder.queries == 2
        assert _matches(text, actual, 1, preview=True) == []
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        await second.close()
