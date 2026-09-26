"""History selection at actual projection, cache and persistent Runner boundaries."""

import asyncio
import copy
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.genai import types

from veadk.context import retrieval
from veadk.context.budget import count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.history_retrieval import _json, _parts, select_history
from veadk.context.manager import prepare_context
from veadk.context.references import saved_references
from veadk.context.retrieval import use_context_retriever
from veadk.context.runtime import ContextScope, current_scope
from test_compression import SummaryClient, content, history_request, model_for
from test_recoverable_context import read


class Ranker:
    def __init__(self, needle):
        self.needle = needle
        self.calls = []

    async def rank(self, identity, reference, text, query):
        self.calls.append((identity, reference, query))
        needle = self.needle(query) if callable(self.needle) else self.needle
        needle = _json(needle)[1:-1]
        start = text.index(needle)
        return [(start, start + len(needle))]


def scope_for(contents, ranker):
    session = Session(id="s", app_name="history", user_id="u")
    for i, item in enumerate(contents):
        session.events.append(
            Event(
                id=f"event-{i}",
                author="user" if item.role == "user" else "agent",
                content=copy.deepcopy(item),
                timestamp=1700000000 + i,
            )
        )
    return ContextScope(
        session=session, agent_name="agent", branch="", evidence_retriever=ranker
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "needle", ["中文🙂", 'quote "here"', "line\nnext", "back\\slash", "\t\x01"]
)
async def test_serialized_offsets_recover_exact_original_unicode_and_escapes(needle):
    text = 'prefix " \\ 🙂\n' + needle + "\n suffix"
    contents = [content("user", text), content("model", text)]
    scope = scope_for(contents, Ranker(needle))
    selected = await select_history(scope, contents, "query")
    assert len(selected) == 1
    i, p, a, b = selected[0]
    assert contents[i].parts[p].text[a:b] == needle
    serialized = _json([c.model_dump(mode="json", exclude_none=True) for c in contents])
    for (i, p), start, end, original in _parts(contents):
        assert serialized[start:end] == _json(original)[1:-1]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "unregistered",
        "foreign_author",
        "foreign_branch",
        "deleted_during",
        "changed_during",
    ],
)
async def test_history_authorization_and_expiry(mutation):
    contents = [content("user", "needle evidence"), content("model", "accepted")]

    class ChangingRanker(Ranker):
        async def rank(self, *args):
            result = await super().rank(*args)
            if mutation == "deleted_during":
                scope.session.events.clear()
            elif mutation == "changed_during":
                scope.session.events[0].content.parts[0].text = "replacement"
            return result

    ranker = ChangingRanker("needle")
    scope = scope_for(contents, ranker)
    if mutation == "unregistered":
        scope.session.events.clear()
    elif mutation == "foreign_author":
        scope.session.events[0].author = "other"
    elif mutation == "foreign_branch":
        scope.session.events[0].branch = "other"
    assert await select_history(scope, contents, "question") == []
    assert len(ranker.calls) == int(mutation.endswith("during"))


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "exception", "invalid"])
async def test_history_rank_failure_is_bounded_and_falls_back(failure, monkeypatch):
    called, cancelled = [], []

    class FailingRanker:
        async def rank(self, *args):
            called.append(True)
            if failure == "timeout":
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.append(True)
            if failure == "exception":
                raise RuntimeError("synthetic-private-error")
            return [(False, 5)]

    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.2)
    contents = [content("user", "source text")]
    scope = scope_for(contents, FailingRanker())
    before = copy.deepcopy(scope.session)
    assert await select_history(scope, contents, "query") == []
    assert called and scope.session == before
    assert "synthetic-private-error" not in repr(scope.pending_state)
    if failure == "timeout":
        assert cancelled


@pytest.mark.asyncio
async def test_large_history_manager_selects_semantic_evidence_and_keeps_protected_turns():
    fact = "The service guarantee expires in 2031."
    long = "Background facts unrelated to the question.\n" * 450
    contents = [
        content("user", "Do not submit payment."),
        content("model", "Approval remains pending."),
        content("user", long + fact + "\n" + long),
        content("model", "Material received."),
        content("user", "Use the stored material."),
        content("model", "Ready."),
        content("user", "When does vehicle coverage end?"),
    ]
    ranker = Ranker(fact)
    scope = scope_for(contents, ranker)
    request = LlmRequest(model="context-test", contents=copy.deepcopy(contents))
    config = ContextCompressionConfig(
        context_window=30000, input_limit=26000, output_reserve=1024
    )
    token = current_scope.set(scope)
    try:
        await prepare_context(
            request, SimpleNamespace(model="context-test"), config, {}
        )
    finally:
        current_scope.reset(token)
    assert len(ranker.calls) == 1 and scope.summary_calls == 0
    assert scope.evidence_retrieval_deadline is None
    assert fact in request.contents[2].parts[0].text
    for index in (0, 1, 3, 4, 5, 6):
        assert request.contents[index] == contents[index]
    assert count_input(request_payload(request), config) < 25000
    assert [event.content for event in scope.session.events] == contents
    refs = saved_references(scope)
    ref = next(r for r, source in refs.items() if source.get("kind") == "history")
    result = await read(request, scope, ref, operation="search", query="coverage")
    assert fact in " ".join(m["text"] for m in result["matches"])


@pytest.mark.asyncio
async def test_many_short_turns_get_evidence_and_cached_summary_refreshes_for_new_query():
    request = history_request()
    request.model = "openai/context-test"
    request.contents[1].parts[0].text += " Hidden warrant A: 2031."
    request.contents[3].parts[0].text += " Hidden warrant B: 2037."
    request.contents[-1] = content("user", "Find warrant A.")
    original = copy.deepcopy(request.contents)
    ranker = Ranker(
        lambda query: "Hidden warrant B: 2037."
        if "warrant B" in query
        else "Hidden warrant A: 2031."
    )
    scope = scope_for(original, ranker)
    client = SummaryClient()
    model = model_for(client)
    config = ContextCompressionConfig(
        context_window=20000,
        output_reserve=2000,
        safety_margin=256,
        trigger_ratio=0.4,
        summary_trigger_ratio=0.4,
        target_ratio=0.3,
    )
    token = current_scope.set(scope)
    try:
        await prepare_context(request, model, config, {})
        assert "Hidden warrant A: 2031." in request.contents[0].parts[0].text
        assert "Never submit payment" in request.contents[0].parts[0].text
        assert request.contents[-3:] == original[-3:]
        caches = [
            v for k, v in scope.pending_state.items() if k.startswith("veadk:context:")
        ]
        assert len(caches) == 1 and "Hidden warrant" not in caches[0]["summary"]
        summary_calls = len(client.requests)
        scope.session.state.update(scope.pending_state)
        scope.pending_state.clear()
        next_request = LlmRequest(
            model=request.model,
            contents=copy.deepcopy(original),
            config=copy.deepcopy(request.config),
        )
        next_request.contents[-1] = content("user", "Find warrant B.")
        await prepare_context(next_request, model, config, {})
        text = next_request.contents[0].parts[0].text
        assert (
            "Hidden warrant B: 2037." in text and "Hidden warrant A: 2031." not in text
        )
        assert len(client.requests) == summary_calls
        assert count_input(request_payload(next_request), config) < 17744
    finally:
        current_scope.reset(token)
    assert [event.content for event in scope.session.events] == original
    assert [call[-1] for call in ranker.calls] == ["Find warrant A.", "Find warrant B."]


@pytest.mark.asyncio
async def test_signed_or_tool_parts_never_become_plain_history_excerpts():
    contents = [
        types.Content(
            role="model", parts=[types.Part(text="signature needle", thought=True)]
        ),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="pay", id="c", args={"note": "needle"}
                    )
                )
            ],
        ),
    ]
    scope = scope_for(contents, Ranker("needle"))
    assert await select_history(scope, contents, "question") == []


@pytest.mark.asyncio
async def test_real_runner_sqlite_restart_and_original_recovery_with_hybrid_ranker(
    tmp_path,
):
    from test_history_evidence import (
        test_history_evidence_uses_one_prefill_and_originals_survive_restart,
    )

    ranker = Ranker(
        "The indigo shipment confirmation is CM-4729; preserve this exact code."
    )
    with use_context_retriever(ranker):
        await test_history_evidence_uses_one_prefill_and_originals_survive_restart(
            tmp_path
        )
    # The reused integration test checks actual provider input, a single answer
    # prefill, SQLite restart, immutable events, and exact original retrieval.
    assert ranker.calls


def test_shared_history_budget_prioritizes_retrieval_rank_over_document_order():
    from veadk.context.history_projection import _retrieved_projection, _text_cost

    first = "h" * 2000 + "A" * 2000 + "t" * 2000
    second = "h" * 2000 + "B" * 2000 + "t" * 2000
    baseline = ["x" * 1700, "x" * 1700]
    result = _retrieved_projection(
        [(0, 0, first), (2, 0, second)],
        [(2, 0, 2000, 4000), (0, 0, 2000, 4000)],
        baseline,
    )
    assert "B" * 2000 in result[1] and "A" not in result[0]
    assert _text_cost(result) <= _text_cost(baseline)


@pytest.mark.asyncio
async def test_history_preparation_uses_one_deadline_across_queries(monkeypatch):
    calls = []

    class SlowRanker:
        async def rank(self, *args):
            calls.append(True)
            await asyncio.sleep(10)

    contents = [content("user", "original text")]
    scope = scope_for(contents, SlowRanker())
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.2)
    retrieval.begin_retrieval(scope)
    assert await select_history(scope, contents, "first") == []
    assert await select_history(scope, contents, "second") == []
    assert len(calls) == 1 and scope.evidence_retrieval_status == "timeout"
