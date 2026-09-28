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

"""Actual projection/reader contracts, using deterministic offline rankers."""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from veadk.context import retrieval
from veadk.context.budget import count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.hybrid_retriever import HybridContextRetriever
from veadk.context.manager import prepare_context
from veadk.context.retrieval import prepare_previews, use_context_retriever
from veadk.context.runtime import current_scope
from veadk.context.tool_results import compact_tool_results
from test_hybrid_index import FakeEmbedding
from test_preview_admission import example
from test_recoverable_context import mcp_source, read


class FixedRanker:
    def __init__(self, needle="Record 113:"):
        self.calls = []
        self.needle = needle

    async def rank(self, identity, reference, text, query):
        self.calls.append((identity, reference, query))
        start = text.index(self.needle)
        return [(start, min(len(text), start + 100))]


@pytest.mark.asyncio
async def test_async_manager_uses_prepared_evidence_and_preserves_payload_budget():
    ranker = FixedRanker()
    with use_context_retriever(ranker):
        text, request, scope, policy, before = example(16000)
    assert scope.evidence_retriever is ranker
    original = copy.deepcopy(scope.session.events)
    token = current_scope.set(scope)
    try:
        await prepare_context(request, SimpleNamespace(model=request.model), policy, {})
    finally:
        current_scope.reset(token)
    assert len(ranker.calls) == 1
    assert scope.evidence_rankings and scope.summary_calls == 0
    preview = (
        request.contents[1].parts[0].function_response.response["content"][0]["text"]
    )
    assert "audited balance 2599 units" in preview and "Original characters" in preview
    after = count_input(request_payload(request), policy)
    assert after < before
    assert after <= policy.input_limit - min(1024, policy.input_limit // 20)
    assert scope.session.events == original
    assert not example(16000)[2].evidence_retriever


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["protected", "unregistered", "sufficient_budget"])
async def test_no_embedding_for_ineligible_or_unpressured_input(kind):
    ranker = FixedRanker()
    text, request, scope, policy, _ = example(16000)
    scope.evidence_retriever = ranker
    scope.projection_bytes = 4000
    if kind == "protected":
        policy = policy.model_copy(update={"protected_context": ("Record 113:",)})
    elif kind == "unregistered":
        scope.session.events.clear()
    else:
        policy = policy.model_copy(update={"input_limit": 200000})
    if kind == "sufficient_budget":
        token = current_scope.set(scope)
        try:
            await prepare_context(
                request, SimpleNamespace(model=request.model), policy, {}
            )
        finally:
            current_scope.reset(token)
    else:
        await prepare_previews(request, scope, policy)
    assert not ranker.calls and not scope.evidence_rankings


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "exception", "invalid_range"])
async def test_failure_falls_back_without_changing_original_or_leaking_exception(
    failure, monkeypatch
):
    cancelled = []

    class FailedRanker:
        calls = 0

        async def rank(self, *args):
            self.calls += 1
            if failure == "timeout":
                try:
                    await asyncio.sleep(10)
                finally:
                    cancelled.append(True)
            if failure == "exception":
                raise RuntimeError("synthetic-provider-error-must-not-be-stored")
            return [(True, 99)]

    # Give source eligibility/integrity checks time to finish, so this tests
    # cancellation of an in-flight provider rather than preflight expiry.
    monkeypatch.setattr(retrieval, "RETRIEVAL_TIMEOUT", 0.2)
    text, request, scope, policy, _ = example(16000)
    scope.evidence_retriever = FailedRanker()
    scope.projection_bytes = 4000
    original = copy.deepcopy(scope.session.events)
    baseline = copy.deepcopy(request)
    bare_scope = copy.copy(scope)
    bare_scope.evidence_rankings = {}
    compact_tool_results(baseline, bare_scope, policy)
    await prepare_previews(request, scope, policy)
    assert scope.evidence_retriever.calls == 1
    compact_tool_results(request, scope, policy)
    assert request.contents == baseline.contents
    assert scope.session.events == original and not scope.evidence_rankings
    assert "synthetic-provider-error" not in repr(scope.pending_state)
    if failure == "timeout":
        assert cancelled


def reader_case(ranker):
    text = "a" * 18000 + "汽车保修有效至 2030 年。🙂" + "z" * 18000
    request, scope = mcp_source(text)
    scope.evidence_retriever = ranker
    policy = ContextCompressionConfig(max_retrieval_calls=2)
    refs = compact_tool_results(request, scope, policy)
    return text, request, scope, next(iter(refs))


@pytest.mark.asyncio
async def test_async_search_returns_exact_unicode_ranges_and_keeps_exact_read_separate():
    ranker = FixedRanker("汽车")
    text, request, scope, ref = reader_case(ranker)
    result = await read(
        request, scope, ref, operation="search", query="vehicle warranty"
    )
    assert len(ranker.calls) == 1 and result["found"]
    for match in result["matches"]:
        assert match["text"] == text[match["offset"] : match["end"]]
    assert "2030" in result["matches"][0]["text"]
    exact = await read(request, scope, ref, operation="read", query="汽车")
    assert exact["text"] == text[exact["offset"] : exact["end"]]
    assert len(ranker.calls) == 1
    assert (await read(request, scope, ref, operation="search", query="warranty"))[
        "error"
    ] == "context_retrieval_budget_exhausted"


@pytest.mark.asyncio
async def test_overlapping_chunks_retain_the_fact_continuation_without_duplicate_text():
    class OverlappingRanker:
        async def rank(self, identity, reference, text, query):
            start = text.index("汽车")
            return [(start, start + 9), (start + 7, start + 18)]

    text, request, scope, ref = reader_case(OverlappingRanker())
    result = await read(request, scope, ref, operation="search", query="warranty")
    assert len(result["matches"]) == 1
    match = result["matches"][0]
    assert match == {"offset": 18000, "end": 18018, "text": text[18000:18018]}
    assert "2030 年" in match["text"]


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["app_name", "user_id", "id", "agent_name", "branch"])
async def test_authorization_precedes_embedding(field):
    ranker = FixedRanker("汽车")
    _, request, scope, ref = reader_case(ranker)
    foreign = copy.copy(scope)
    foreign.session = scope.session.model_copy(deep=True)
    setattr(
        foreign if field in {"agent_name", "branch"} else foreign.session,
        field,
        "foreign",
    )
    result = await read(request, foreign, ref, operation="search", query="warranty")
    assert result["error"] == "context_reference_not_available" and not ranker.calls


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["deleted_before", "deleted_during", "changed_during"]
)
async def test_source_expiry_cannot_be_resurrected_by_async_index(mutation):
    class MutatingRanker(FixedRanker):
        async def rank(self, *args):
            spans = await super().rank(*args)
            if mutation == "deleted_during":
                scope.session.events.clear()
            elif mutation == "changed_during":
                scope.session.events[0].content.parts[0].function_response.response[
                    "content"
                ][0]["text"] = "changed"
            return spans

    ranker = MutatingRanker("汽车")
    _, request, scope, ref = reader_case(ranker)
    if mutation == "deleted_before":
        scope.session.events.clear()
    result = await read(request, scope, ref, operation="search", query="warranty")
    assert result == {"error": "context_reference_expired"}
    if mutation == "deleted_before":
        assert not ranker.calls


@pytest.mark.asyncio
async def test_parallel_async_searches_share_remaining_input_and_call_budget():
    class YieldingRanker(FixedRanker):
        async def rank(self, *args):
            await asyncio.sleep(0)
            return await super().rank(*args)

    ranker = YieldingRanker("汽车")
    text, request, scope, ref = reader_case(ranker)
    scope.retrieval_headroom = 1500
    results = await asyncio.gather(
        *[
            read(request, scope, ref, operation="search", query=query)
            for query in ("warranty", "vehicle", "coverage")
        ]
    )
    assert 0 <= scope.retrieval_headroom < 1500 and scope.retrieval_calls == 2
    assert len(ranker.calls) == 2
    assert results[2]["error"] == "context_retrieval_budget_exhausted"
    for result in results:
        for match in result.get("matches", []):
            assert match["text"] == text[match["offset"] : match["end"]]


@pytest.mark.asyncio
async def test_hybrid_index_restart_reuses_vectors_and_filters_current_source(tmp_path):
    path = tmp_path / "derived.sqlite3"
    embedder = FakeEmbedding()
    who = ("app", "user", "session", "agent", "branch")
    retriever = HybridContextRetriever(path, embedder)
    await retriever.rank(who, "old-source", "car automobile", "car")
    text = "An automobile is parked outside."
    spans = await retriever.rank(who, "current-source", text, "car")
    assert spans == [(0, len(text))] and retriever.last_status == "hybrid"
    before = embedder.calls
    await retriever.close()
    restarted = HybridContextRetriever(path, embedder)
    try:
        assert await restarted.rank(who, "current-source", text, "car") == spans
        assert embedder.calls == before + 1  # Query only; no source reembedding.
        assert path.stat().st_mode & 0o777 == 0o600
    finally:
        await restarted.close()


@pytest.mark.asyncio
async def test_native_runner_binding_and_sqlite_restart_preserve_business_tool_once(
    tmp_path, monkeypatch
):
    from test_default_sqlite_session import (
        test_default_runner_preserves_original_and_reference_after_recreation,
    )

    ranker = FixedRanker("prefix ")
    with use_context_retriever(ranker):
        await test_default_runner_preserves_original_and_reference_after_recreation(
            tmp_path, monkeypatch, False
        )
    assert ranker.calls
    assert all(call[0][:3] == ("project", "owner", "session") for call in ranker.calls)
