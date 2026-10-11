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

"""Ordinary Agents must prepare cold indexes without borrowing query budgets."""

import copy
import asyncio
import time
from types import SimpleNamespace

import pytest

from veadk.context import defaults
from veadk.context.config import ContextCompressionConfig
from veadk.context.manager import prepare_context
from veadk.context.runtime import current_scope
from test_default_retrieval import agent
from test_hybrid_incremental import source_text
from test_hybrid_index import FakeEmbedding
from test_preview_admission import example


def policy_with_preparation(policy=None):
    # model_copy lets the regression reach the old manager before fields exist.
    return (policy or ContextCompressionConfig()).model_copy(
        update={
            "prepare_index": True,
            "index_preparation_max_calls": 512,
            "index_preparation_timeout_seconds": 60.0,
        }
    )


class BudgetEmbedding(FakeEmbedding):
    def __init__(self, limit):
        super().__init__()
        self.limit = limit
        self.closed = False

    async def embed(self, texts):
        if self.calls + len(texts) > self.limit:
            raise ValueError("embedding_call_budget_exhausted")
        return await super().embed(texts)

    async def close(self):
        self.closed = True


def install(monkeypatch):
    embeddings = []

    def create(_agent, config):
        value = BudgetEmbedding(config.embedding_max_calls)
        embeddings.append(value)
        return value

    monkeypatch.setattr(defaults, "create_embedder", create)
    return embeddings


def test_preparation_defaults_on_and_is_bounded():
    policy = ContextCompressionConfig()
    assert policy.prepare_index is True
    assert ContextCompressionConfig(prepare_index=False).prepare_index is False
    assert policy.embedding_max_calls == 64
    for update in [
        {"index_preparation_max_calls": 513},
        {"index_preparation_timeout_seconds": 121},
    ]:
        with pytest.raises(ValueError):
            ContextCompressionConfig(**update)


@pytest.mark.asyncio
async def test_cold_preparation_reserves_query_calls_and_reuses_after_restart(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    embeddings = install(monkeypatch)
    policy = policy_with_preparation()
    text = source_text(80)
    who = ("app", "user", "session", "agent", "")
    for turn in range(2):
        async with defaults.invocation_retriever(agent(), policy) as owner:
            result = await owner.prepare_source(
                who, "source", text, deadline=time.monotonic() + 30
            )
            assert result["complete"]
            assert result["indexed"] > 64 if turn == 0 else result["indexed"] == 0
            assert await owner.rank_with_deadline(
                who, "source", text, "car", deadline=time.monotonic() + 5
            )
            assert owner.last_status == "hybrid"
            assert embeddings[-2].calls == 1  # only query, separate 64-call pool
        assert all(e.closed for e in embeddings)


@pytest.mark.asyncio
async def test_manager_prepares_authorized_source_before_query_clock(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    install(monkeypatch)
    text, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    original = copy.deepcopy(scope.session)
    seen = []
    original_rank = defaults.DefaultContextRetriever.rank_with_deadline

    async def rank(self, *args, deadline):
        seen.append(scope.index_preparation_status)
        assert scope.index_preparation_results[0]["complete"]
        assert deadline > time.monotonic()
        return await original_rank(self, *args, deadline=deadline)

    monkeypatch.setattr(defaults.DefaultContextRetriever, "rank_with_deadline", rank)
    async with defaults.invocation_retriever(agent(), policy) as owner:
        scope.evidence_retriever = owner
        token = current_scope.set(scope)
        try:
            await prepare_context(
                request, SimpleNamespace(model=request.model), policy, {}
            )
        finally:
            current_scope.reset(token)
        assert seen == ["complete"]
        assert scope.session == original
        assert scope.evidence_retrieval_deadline is None
        assert scope.index_preparation_results[0]["indexed"] > 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", ["off", "lexical", "short", "protected", "expired", "custom"]
)
async def test_ineligible_requests_never_initialize_preparation(
    tmp_path, monkeypatch, case
):
    from veadk.context.index_preparation import prepare_request_index

    monkeypatch.chdir(tmp_path)
    embeddings = install(monkeypatch)
    _, request, scope, policy, _ = example(16000)
    updates = {
        "off": {"mode": "off"},
        "lexical": {"retrieval": "lexical"},
        "short": {"input_limit": 200000},
        "protected": {"protected_context": ("Record 113:",)},
    }
    policy = policy_with_preparation(policy).model_copy(update=updates.get(case, {}))
    if case == "expired":
        scope.session.events.clear()
    async with defaults.invocation_retriever(agent(), policy) as owner:
        scope.evidence_retriever = object() if case == "custom" else owner
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert embeddings == []
        assert scope.pending_state == {}


@pytest.mark.asyncio
async def test_no_embedding_does_not_create_index_or_preparation_client(
    tmp_path, monkeypatch
):
    from veadk.context.index_preparation import prepare_request_index

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    async with defaults.invocation_retriever(agent(), policy) as owner:
        scope.evidence_retriever = owner
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert scope.index_preparation_status == "no_embedding"
        assert owner._preparation_owner is None
        assert not (tmp_path / ".adk").exists()


@pytest.mark.asyncio
async def test_preparation_timeout_is_cumulative_and_joins_work(tmp_path, monkeypatch):
    from veadk.context.index_preparation import prepare_request_index
    from veadk.context.attempts import AttemptLedger, current_attempts

    monkeypatch.chdir(tmp_path)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy).model_copy(
        update={"index_preparation_timeout_seconds": 0.05}
    )
    calls = []
    cancelled = []

    async def stall(self, *args, deadline):
        calls.append(deadline)
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    monkeypatch.setattr(defaults.DefaultContextRetriever, "prepare_source", stall)
    ledger = AttemptLedger(maximum=3, timeout=10)
    token = current_attempts.set(ledger)
    try:
        async with defaults.invocation_retriever(agent(), policy) as owner:
            scope.evidence_retriever = owner
            for _ in range(2):
                await prepare_request_index(
                    request, SimpleNamespace(model=request.model), policy, {}, scope
                )
            assert len(calls) == len(cancelled) == 1
            assert scope.index_preparation_status == "budget_exhausted"
            assert scope.index_preparation_remaining == 0
            assert ledger.used == 0 and 0 < ledger.remaining() < 10
    finally:
        current_attempts.reset(token)


@pytest.mark.asyncio
async def test_preparation_preserves_parent_deadline_and_external_cancellation(
    tmp_path, monkeypatch
):
    from veadk.context.index_preparation import prepare_request_index
    from veadk.context.attempts import AttemptLedger, current_attempts

    monkeypatch.chdir(tmp_path)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    waiting = asyncio.Event()
    closed = []
    ledger = AttemptLedger(maximum=3, timeout=2)

    async def stall(self, *args, deadline):
        assert deadline <= ledger.started + 1.01
        waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            closed.append(True)

    monkeypatch.setattr(defaults.DefaultContextRetriever, "prepare_source", stall)
    token = current_attempts.set(ledger)
    try:
        async with defaults.invocation_retriever(agent(), policy) as owner:
            scope.evidence_retriever = owner
            task = asyncio.create_task(
                prepare_request_index(
                    request, SimpleNamespace(model=request.model), policy, {}, scope
                )
            )
            await asyncio.wait_for(waiting.wait(), 2)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert closed == [True]
    finally:
        current_attempts.reset(token)


@pytest.mark.asyncio
async def test_history_prepares_only_actual_eligible_prefix(tmp_path, monkeypatch):
    from google.adk.models.llm_request import LlmRequest
    from veadk.context.index_preparation import prepare_request_index
    from veadk.context.history import eligible_prefix_end
    from veadk.context.references import archive_history, resolve
    from test_hybrid_history import scope_for
    from test_long_history_evidence import original_history

    monkeypatch.chdir(tmp_path)
    values = original_history()
    policy = policy_with_preparation(ContextCompressionConfig(input_limit=20000))
    scope = scope_for(values, None)
    request = LlmRequest(
        model="deepseek-v4-1-flash-260910", contents=copy.deepcopy(values)
    )
    refs = {}
    reference = archive_history(scope, values[: eligible_prefix_end(values, 2)], refs)
    expected = resolve(scope, refs[reference])
    before = copy.deepcopy(scope.session)
    seen = []

    async def prepare(self, who, ref, text, *, deadline):
        assert ref == reference and text == expected
        seen.append(ref)
        return {
            "complete": True,
            "indexed": 1,
            "reused": 0,
            "remaining": 0,
            "reason": "complete",
        }

    monkeypatch.setattr(defaults.DefaultContextRetriever, "prepare_source", prepare)
    async with defaults.invocation_retriever(agent(), policy) as owner:
        scope.evidence_retriever = owner
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert seen == [reference]
        assert scope.session == before and scope.pending_state == {}


@pytest.mark.asyncio
async def test_source_changed_during_preparation_is_not_marked_complete(
    tmp_path, monkeypatch
):
    from veadk.context.index_preparation import prepare_request_index

    monkeypatch.chdir(tmp_path)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)

    async def mutate(self, *args, deadline):
        scope.session.events.clear()
        return {"complete": True}

    monkeypatch.setattr(defaults.DefaultContextRetriever, "prepare_source", mutate)
    async with defaults.invocation_retriever(agent(), policy) as owner:
        scope.evidence_retriever = owner
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert scope.index_preparation_status == "source_expired"
        assert scope.index_preparation_results == []
