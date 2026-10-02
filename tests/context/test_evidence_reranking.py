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

"""Exercise the actual SDK rank, projection, reader and cancellation boundaries."""

import asyncio
import copy
from dataclasses import FrozenInstanceError
import time
from types import SimpleNamespace

import pytest

from veadk.context import retrieval
from veadk.context.budget import count_input, request_payload
from veadk.context.manager import prepare_context
from veadk.context.reranking import (
    EvidenceOrder,
    EvidenceRerankingRetriever,
    evidence_order,
)
from veadk.context.runtime import current_scope
from test_hybrid_integration import reader_case
from test_preview_admission import example
from test_recoverable_context import read


WHO = ("app", "user", "session", "agent", "")


class Base:
    def __init__(self, fixed=None):
        self.fixed = fixed
        self.calls = []
        self.closed = False

    async def rank_with_deadline(self, identity, reference, text, query, *, deadline):
        self.calls.append(deadline)
        if self.fixed is not None:
            return self.fixed
        start = text.index("汽车") if "汽车" in text else text.index("Record 113:")
        return [(0, 32), (start, min(start + 100, len(text)))]

    async def close(self):
        self.closed = True


async def choose_last(query, passages, *, deadline):
    assert isinstance(passages, tuple) and all(isinstance(p, str) for p in passages)
    return [len(passages) - 1]


@pytest.mark.asyncio
async def test_manager_preserves_validated_order_and_original_session():
    retriever = EvidenceRerankingRetriever(Base(), choose_last)
    with retrieval.use_context_retriever(retriever):
        text, request, scope, policy, before = example(16000)
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    assert scope.evidence_rankings
    assert all(
        isinstance(value, EvidenceOrder) for value in scope.evidence_rankings.values()
    )
    preview = (
        request.contents[1].parts[0].function_response.response["content"][0]["text"]
    )
    assert "audited balance 2599 units" in preview
    assert scope.session.events == original and scope.summary_calls == 0
    assert count_input(request_payload(request), policy) < before
    assert count_input(request_payload(request), policy) <= policy.input_limit - min(
        1024, policy.input_limit // 20
    )
    await retriever.close()


@pytest.mark.parametrize("maximum", [100, 180, 300, 650, 1000, 1600, 2400])
@pytest.mark.parametrize("preview", [False, True])
def test_actual_renderer_never_grows_baseline_budget(maximum, preview):
    pieces = ["🙂中文证据。" * 14, "a" * 175, "Other evidence. " * 21, "é" * 95]
    text = "\n\n".join(pieces)
    spans = []
    start = 0
    for piece in pieces:
        spans.append((start, start + len(piece)))
        start += len(piece) + 2
    order = evidence_order(text, spans, [2, 0])
    before = retrieval._matches(text, spans, maximum, preview=preview)
    after = retrieval._matches(text, order, maximum, preview=preview)

    def size(matches):
        return (
            len(retrieval._preview(matches).encode())
            if preview
            else sum(len(m["text"].encode()) for m in matches)
        )

    # Empty preview metadata can exceed a tiny allowance but is never admitted.
    assert size(after) <= size(before)
    assert not after or size(after) <= maximum
    assert all(m["text"] == text[m["offset"] : m["end"]] for m in after)


def test_renderer_rejects_order_from_changed_source():
    order = evidence_order("first source", [(0, 5), (6, 12)], [1])
    with pytest.raises(ValueError):
        retrieval._matches("other source", order, 1000, preview=True)


def test_order_immutable_and_not_a_route_to_new_source_spans():
    order = evidence_order("abcdefghijkl", [(0, 3), (4, 7)], [1])
    with pytest.raises(FrozenInstanceError):
        order.ranked = ((8, 12),)
    invalid = EvidenceOrder(order.source_sha256, order.baseline, ((8, 12), (0, 3)))
    with pytest.raises(ValueError):
        invalid.validate("abcdefghijkl")


@pytest.mark.parametrize("ids", [[True], [1.0], [-1], [2], [0, 0], ["0"], {"ids": [0]}])
@pytest.mark.asyncio
async def test_invalid_selector_output_returns_exact_base_ranking(ids):
    base = Base([(0, 3), (4, 7)])

    async def select(*args, **kwargs):
        return ids

    wrapper = EvidenceRerankingRetriever(base, select)
    result = await wrapper.rank_with_deadline(
        WHO, "source", "abcdefgh", "query", deadline=time.monotonic() + 1
    )
    assert result is base.fixed
    await wrapper.close()


@pytest.mark.asyncio
async def test_empty_and_provider_error_preserve_exact_ranking():
    for failure in (False, True):
        base = Base([(0, 3), (4, 7)])

        async def select(*args, **kwargs):
            if failure:
                raise RuntimeError("provider-error-must-not-escape")
            return []

        wrapper = EvidenceRerankingRetriever(base, select)
        assert await wrapper.rank(WHO, "source", "abcdefgh", "query") is base.fixed
        await wrapper.close()


@pytest.mark.asyncio
async def test_expired_delegate_budget_never_calls_selector():
    base = Base([(0, 3)])

    async def select(*args, **kwargs):
        raise AssertionError("must_not_call")

    wrapper = EvidenceRerankingRetriever(base, select)
    deadline = time.monotonic() - 1
    assert (
        await wrapper.rank_with_deadline(
            WHO, "source", "abc", "query", deadline=deadline
        )
        is base.fixed
    )
    assert base.calls == [deadline]
    await wrapper.close()


@pytest.mark.asyncio
async def test_timeout_cancels_owned_selector_and_returns_baseline():
    base = Base([(0, 3)])
    cancelled = []

    async def select(*args, **kwargs):
        try:
            await asyncio.sleep(10)
        finally:
            cancelled.append(True)

    wrapper = EvidenceRerankingRetriever(base, select)
    result = await wrapper.rank_with_deadline(
        WHO, "source", "abc", "query", deadline=time.monotonic() + 0.15
    )
    assert result is base.fixed and cancelled and not wrapper._pending
    await wrapper.close()


@pytest.mark.asyncio
async def test_external_cancel_and_close_leave_no_selector_tasks():
    for mode in ("cancel", "close"):
        base = Base([(0, 3)])
        entered = asyncio.Event()
        cancelled = []

        async def select(*args, **kwargs):
            entered.set()
            try:
                await asyncio.sleep(10)
            finally:
                cancelled.append(True)

        wrapper = EvidenceRerankingRetriever(base, select)
        task = asyncio.create_task(wrapper.rank(WHO, "source", "abc", "query"))
        await entered.wait()
        if mode == "cancel":
            task.cancel()
        else:
            await wrapper.close()
        with pytest.raises(asyncio.CancelledError):
            await task
        await wrapper.close()
        assert cancelled and base.closed and not wrapper._pending


@pytest.mark.asyncio
async def test_close_cancellation_still_drains_base():
    entered = asyncio.Event()
    finished = []

    class SlowClose(Base):
        async def close(self):
            entered.set()
            await asyncio.sleep(0.02)
            finished.append(True)

    wrapper = EvidenceRerankingRetriever(SlowClose(), choose_last)
    task = asyncio.create_task(wrapper.close())
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert finished
    with pytest.raises(ValueError):
        await wrapper.rank(WHO, "source", "abc", "query")


@pytest.mark.asyncio
async def test_source_deleted_during_selector_cannot_be_recovered():
    async def select(*args, **kwargs):
        scope.session.events.clear()
        return [1]

    wrapper = EvidenceRerankingRetriever(Base(), select)
    _, request, scope, reference = reader_case(wrapper)
    from veadk.context.references import saved_references

    source = saved_references(scope)[reference]
    text = retrieval.resolve(scope, source)
    result = await retrieval._rank(scope, source, text, "vehicle warranty")
    assert result is None and scope.evidence_retrieval_status == "source_expired"
    await wrapper.close()


@pytest.mark.parametrize("field", ["app_name", "user_id", "id", "agent_name", "branch"])
@pytest.mark.asyncio
async def test_foreign_scope_cannot_invoke_selector(field):
    called = []

    async def select(*args, **kwargs):
        called.append(True)
        return [1]

    wrapper = EvidenceRerankingRetriever(Base(), select)
    _, request, scope, reference = reader_case(wrapper)
    foreign = copy.copy(scope)
    foreign.session = scope.session.model_copy(deep=True)
    setattr(
        foreign if field in {"agent_name", "branch"} else foreign.session,
        field,
        "foreign",
    )
    result = await read(
        request, foreign, reference, operation="search", query="warranty"
    )
    assert result["error"] == "context_reference_not_available" and not called
    await wrapper.close()


@pytest.mark.asyncio
async def test_explicit_lookup_delegates_without_selector_or_semantic_fallback():
    called = []

    class LexicalBase(Base):
        async def rank_search_with_deadline(self, *args, deadline):
            called.append((args, deadline))
            return []

    async def select(*args, **kwargs):
        raise AssertionError("explicit_lookup_must_not_rerank")

    base = LexicalBase()
    wrapper = EvidenceRerankingRetriever(base, select)
    deadline = time.monotonic() + 1
    assert (
        await wrapper.rank_search_with_deadline(
            WHO, "source", "original", "query", deadline=deadline
        )
        == []
    )
    assert len(called) == 1 and called[0][1] == deadline and not base.calls
    await wrapper.close()


@pytest.mark.parametrize("unit", ["delivery", "运输记录", '\\"'])
@pytest.mark.asyncio
async def test_expansion_retains_reranked_evidence_with_original_json_budget(unit):
    from test_preview_budget import fixture
    from veadk.context import tool_results

    request, scope, policy = fixture(unit)
    base = scope.evidence_retriever

    class Delegate:
        async def rank_with_deadline(self, *args, deadline):
            return await base.rank(*args)

        async def close(self):
            pass

    wrapper = EvidenceRerankingRetriever(Delegate(), choose_last)
    scope.evidence_retriever = wrapper
    events = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    preview = (
        request.contents[1].parts[0].function_response.response["content"][0]["text"]
    )
    assert "Backup delivery location: South warehouse." in preview
    assert (
        count_input(request_payload(request), policy)
        <= policy.input_limit * policy.target_ratio
    )
    assert scope.session.events == events and base.calls == 1
    assert tool_results.READ_CONTEXT_TOOL in request.tools_dict
    await wrapper.close()


@pytest.mark.parametrize("maximum", [500, 900, 1500])
def test_expanded_order_retains_every_prior_span(maximum):
    text = (
        "First evidence. " * 15
        + "\n\n"
        + "Second evidence. " * 15
        + "\n\n"
        + "Third evidence. " * 20
    )
    spans = [(0, 220), (242, 460), (499, len(text))]
    order = evidence_order(text, spans, [1, 2])
    prior = retrieval._matches(text, order, 500, preview=True)
    after = retrieval._matches(
        text,
        order,
        maximum,
        preview=True,
        retained=[(m["offset"], m["end"]) for m in prior],
    )
    rendered = retrieval._preview(after)
    assert len(rendered.encode()) <= maximum
    assert all(m["text"] in rendered for m in prior)
