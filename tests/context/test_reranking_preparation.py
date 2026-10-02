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

"""Native preparation must retain its own budget under built-in reranking."""

import asyncio
import copy
from types import SimpleNamespace

import pytest

from veadk.context import defaults
from veadk.context.index_preparation import prepare_request_index
from veadk.context.reranking import EvidenceRerankingRetriever
from test_default_index_preparation import install, policy_with_preparation
from test_default_retrieval import agent
from test_preview_admission import example


async def selector(*args, **kwargs):
    raise AssertionError("index preparation must not invoke answer/ranking models")


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [0, 1, 2])
async def test_native_preparation_regression(tmp_path, monkeypatch, depth):
    monkeypatch.chdir(tmp_path)
    embeddings = install(monkeypatch)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    original = copy.deepcopy(scope.session)
    original_request = request.model_dump()
    owner = defaults.DefaultContextRetriever(agent(), policy)
    for _ in range(depth):
        owner = EvidenceRerankingRetriever(owner, selector)
    scope.evidence_retriever = owner
    try:
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert scope.index_preparation_status == "complete", (
            "native preparation was bypassed by a built-in wrapper"
        )
        assert scope.index_preparation_results[0]["indexed"] > 0
        assert scope.index_preparation_results[0]["remaining"] == 0
        assert len(embeddings) == 2
        assert embeddings[0].calls == 0
        assert embeddings[1].calls > 0
        assert scope.session == original and request.model_dump() == original_request
    finally:
        await owner.close()
    assert all(e.closed for e in embeddings)


@pytest.mark.asyncio
async def test_custom_preparation_lifecycle_remains_caller_owned(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    embeddings = install(monkeypatch)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    calls = []

    class Custom:
        async def rank_with_deadline(self, *args, **kwargs):
            return []

        async def prepare_source(self, *args, **kwargs):
            calls.append(True)
            raise AssertionError("custom lifecycle must not be acquired implicitly")

        async def close(self):
            pass

    owner = EvidenceRerankingRetriever(Custom(), selector)
    scope.evidence_retriever = owner
    try:
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert calls == [] and embeddings == [] and scope.pending_state == {}
    finally:
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [1, 2])
@pytest.mark.parametrize(
    "case", ["disabled", "off", "lexical", "short", "protected", "expired"]
)
async def test_reranking_preparation_preserves_eligibility(
    tmp_path, monkeypatch, depth, case
):
    monkeypatch.chdir(tmp_path)
    embeddings = install(monkeypatch)
    _, request, scope, policy, _ = example(16000)
    updates = {
        "disabled": {"prepare_index": False},
        "off": {"mode": "off"},
        "lexical": {"retrieval": "lexical"},
        "short": {"input_limit": 200000},
        "protected": {"protected_context": ("Record 113:",)},
    }
    policy = policy_with_preparation(policy).model_copy(update=updates.get(case, {}))
    if case == "expired":
        scope.session.events.clear()
    owner = defaults.DefaultContextRetriever(agent(), policy)
    for _ in range(depth):
        owner = EvidenceRerankingRetriever(owner, selector)
    scope.evidence_retriever = owner
    try:
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert embeddings == [] and scope.pending_state == {}
    finally:
        await owner.close()


@pytest.mark.asyncio
async def test_reranking_preparation_without_embedding_stays_offline(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(defaults, "create_embedder", lambda *args: None)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    owner = EvidenceRerankingRetriever(
        defaults.DefaultContextRetriever(agent(), policy), selector
    )
    scope.evidence_retriever = owner
    try:
        await prepare_request_index(
            request, SimpleNamespace(model=request.model), policy, {}, scope
        )
        assert scope.index_preparation_status == "no_embedding"
        assert not (tmp_path / ".adk").exists()
    finally:
        await owner.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("depth", [1, 2])
async def test_reranking_preparation_cancellation_drains_native_work(
    tmp_path, monkeypatch, depth
):
    from veadk.context.attempts import AttemptLedger, current_attempts

    monkeypatch.chdir(tmp_path)
    _, request, scope, policy, _ = example(16000)
    policy = policy_with_preparation(policy)
    ledger = AttemptLedger(maximum=3, timeout=2)
    waiting = asyncio.Event()
    drained = []

    async def stall(self, *args, deadline):
        assert deadline <= ledger.started + 1.01
        waiting.set()
        try:
            await asyncio.Event().wait()
        finally:
            drained.append(True)

    monkeypatch.setattr(defaults.DefaultContextRetriever, "prepare_source", stall)
    owner = defaults.DefaultContextRetriever(agent(), policy)
    for _ in range(depth):
        owner = EvidenceRerankingRetriever(owner, selector)
    scope.evidence_retriever = owner
    token = current_attempts.set(ledger)
    task = None
    try:
        task = asyncio.create_task(
            prepare_request_index(
                request, SimpleNamespace(model=request.model), policy, {}, scope
            )
        )
        await asyncio.wait_for(waiting.wait(), 0.5)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert drained == [True] and task.done()
        assert ledger.used == 0
    finally:
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        current_attempts.reset(token)
        await owner.close()
