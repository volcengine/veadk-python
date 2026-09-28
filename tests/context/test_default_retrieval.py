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

"""Default binding must activate real retrieval, preserve overrides and close I/O."""

import asyncio
import copy
import stat
import time
from types import SimpleNamespace

import pytest

from veadk.context.config import ContextCompressionConfig
from veadk.context import defaults
from veadk.context.manager import prepare_context
from veadk.context.runtime import ContextScope, current_scope
from veadk.context.retrieval import use_context_retriever
from test_hybrid_index import FakeEmbedding
from test_preview_admission import example


def agent(**updates):
    return SimpleNamespace(
        model_provider="openai",
        model_api_key="offline-test",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
        **updates,
    )


@pytest.mark.asyncio
async def test_default_prepares_full_source_and_reuses_index_after_close(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    embedders = []

    class Embedding(FakeEmbedding):
        closed = False

        async def close(self):
            self.closed = True

    def create(_agent, _config):
        embedding = Embedding()
        embedders.append(embedding)
        return embedding

    monkeypatch.setattr(defaults, "create_embedder", create)
    policy = ContextCompressionConfig()
    who = ("app", "user", "session", "agent", "")
    text = "The vehicle warranty is valid until 2030. " * 60
    reference = "authorized-test-source"
    for turn in range(2):
        async with defaults.invocation_retriever(agent(), policy) as retriever:
            assert not embedders or turn == 1
            spans = await retriever.rank_with_deadline(
                who, reference, text, "vehicle warranty", deadline=time.monotonic() + 5
            )
            assert spans and retriever.last_status == "hybrid"
            assert all(0 <= a < b <= len(text) for a, b in spans)
        assert embedders[-1].closed
    # A reopened index requires only the query embedding, no source embeddings.
    assert embedders[0].calls > embedders[1].calls
    assert (tmp_path / ".adk/context-index.sqlite3").is_file()


@pytest.mark.asyncio
async def test_default_manager_selects_evidence_without_manual_binding(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    embedding = FakeEmbedding()
    monkeypatch.setattr(defaults, "create_embedder", lambda *_: embedding)
    text, request, scope, policy, before = example(16000)
    original = copy.deepcopy(scope.session.events)
    async with defaults.invocation_retriever(agent(), policy) as retriever:
        scope.evidence_retriever = retriever
        token = current_scope.set(scope)
        try:
            await prepare_context(
                request, SimpleNamespace(model=request.model), policy, {}
            )
        finally:
            current_scope.reset(token)
        assert scope.evidence_rankings
        assert embedding.calls
        assert scope.session.events == original


@pytest.mark.asyncio
async def test_explicit_override_is_borrowed_and_not_closed():
    custom = SimpleNamespace()
    with use_context_retriever(custom):
        async with defaults.invocation_retriever(
            agent(), ContextCompressionConfig()
        ) as retriever:
            assert retriever is custom
        assert ContextScope(None, "agent", "").evidence_retriever is custom


@pytest.mark.asyncio
async def test_off_and_unpressured_requests_do_not_open_clients_or_storage(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)

    def unexpected(*_):
        pytest.fail("No embedding client should be opened")

    monkeypatch.setattr(defaults, "create_embedder", unexpected)
    async with defaults.invocation_retriever(
        agent(), ContextCompressionConfig(mode="off")
    ) as value:
        assert value is None
    async with defaults.invocation_retriever(
        agent(), ContextCompressionConfig()
    ) as value:
        assert value is not None
    assert not (tmp_path / ".adk").exists()


@pytest.mark.asyncio
async def test_cancellation_drains_embedding_and_closes_index(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    started, cancelled, closed = asyncio.Event(), asyncio.Event(), asyncio.Event()

    class SlowEmbedding(FakeEmbedding):
        async def embed(self, texts):
            started.set()
            try:
                await asyncio.sleep(60)
            finally:
                cancelled.set()

        async def close(self):
            closed.set()

    monkeypatch.setattr(defaults, "create_embedder", lambda *_: SlowEmbedding())

    async def run():
        async with defaults.invocation_retriever(
            agent(), ContextCompressionConfig()
        ) as retriever:
            await retriever.rank_with_deadline(
                ("app", "u", "s", "a", ""),
                "ref",
                "source " * 200,
                "question",
                deadline=time.monotonic() + 30,
            )

    task = asyncio.create_task(run())
    await asyncio.wait_for(started.wait(), 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and closed.is_set()


@pytest.mark.parametrize(
    "provider,base",
    [
        ("openai", "https://api.openai.com/v1"),
        ("volcengine", "https://custom-proxy.invalid/api/v3"),
    ],
)
def test_no_implicit_transfer_of_another_provider_key(provider, base, monkeypatch):
    for name in ("MODEL_EMBEDDING_API_KEY", "MODEL_EMBEDDING_API_BASE"):
        monkeypatch.delenv(name, raising=False)
    owner = SimpleNamespace(
        model_provider=provider, model_api_key="offline-other-key", model_api_base=base
    )
    assert defaults.create_embedder(owner, ContextCompressionConfig()) is None


def test_standard_ark_compatible_agent_configures_default_embedding(monkeypatch):
    from veadk import Agent

    for name in ("MODEL_EMBEDDING_API_KEY", "MODEL_EMBEDDING_API_BASE"):
        monkeypatch.delenv(name, raising=False)
    owner = Agent(name="ordinary_agent", model_api_key="offline-test")
    embedding = defaults.create_embedder(owner, owner.context_compression)
    assert isinstance(embedding, defaults.ArkContextEmbedding)
    assert embedding._client is None  # Construction must not open network clients.


@pytest.mark.asyncio
async def test_default_embedding_failure_drains_siblings_and_obeys_concurrency(
    monkeypatch,
):
    import volcenginesdkarkruntime

    active = peak = started = 0
    entered = asyncio.Event()
    closed = []

    async def create(**kwargs):
        nonlocal active, peak, started
        active += 1
        started += 1
        peak = max(peak, active)
        if active == 4:
            entered.set()
        try:
            await entered.wait()
            if kwargs["input"][0]["text"] == "0":
                raise RuntimeError("synthetic provider failure")
            await asyncio.sleep(60)
        finally:
            active -= 1

    async def close():
        closed.append(True)

    monkeypatch.setattr(
        volcenginesdkarkruntime,
        "AsyncArk",
        lambda **_: SimpleNamespace(
            multimodal_embeddings=SimpleNamespace(create=create), close=close
        ),
    )
    embedding = defaults.ArkContextEmbedding(
        model="offline",
        dimension=3,
        api_key="offline-test",
        api_base="https://invalid.invalid",
        max_calls=16,
    )
    with pytest.raises(RuntimeError, match="synthetic"):
        await embedding.embed([str(i) for i in range(8)])
    assert active == 0 and peak == 4
    assert started <= 8
    await embedding.close()
    assert closed


@pytest.mark.asyncio
async def test_embedding_call_budget_applies_across_batches(monkeypatch):
    import volcenginesdkarkruntime

    calls = []

    async def create(**kwargs):
        calls.append(kwargs["input"])
        return SimpleNamespace(data=SimpleNamespace(embedding=[1.0, 0.0, 0.0]))

    async def close():
        pass

    monkeypatch.setattr(
        volcenginesdkarkruntime,
        "AsyncArk",
        lambda **_: SimpleNamespace(
            multimodal_embeddings=SimpleNamespace(create=create), close=close
        ),
    )
    embedding = defaults.ArkContextEmbedding(
        model="offline",
        dimension=3,
        api_key="offline-test",
        api_base="https://invalid.invalid",
        max_calls=3,
    )
    await embedding.embed(["a", "b"])
    with pytest.raises(ValueError, match="budget"):
        await embedding.embed(["c", "d"])
    assert len(calls) == 2
    await embedding.close()


def test_embedding_endpoint_changes_invalidate_cached_vector_identity():
    kwargs = dict(model="same-label", dimension=3, api_key="offline-test", max_calls=3)
    first = defaults.ArkContextEmbedding(
        api_base="https://first.invalid/api/v3/", **kwargs
    )
    second = defaults.ArkContextEmbedding(
        api_base="https://second.invalid/api/v3/", **kwargs
    )
    assert first.model != second.model
    assert "https://" not in first.model
    assert "offline-test" not in first.model


@pytest.mark.asyncio
async def test_new_default_index_is_private_in_an_existing_project_directory(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".adk").mkdir(mode=0o755)
    monkeypatch.setattr(defaults, "create_embedder", lambda *_: FakeEmbedding())
    async with defaults.invocation_retriever(
        agent(), ContextCompressionConfig()
    ) as retriever:
        await retriever.rank_with_deadline(
            ("app", "u", "s", "a", ""),
            "ref",
            "source text " * 20,
            "question",
            deadline=time.monotonic() + 5,
        )
    assert (
        stat.S_IMODE((tmp_path / ".adk/context-index.sqlite3").stat().st_mode) == 0o600
    )


@pytest.mark.parametrize("model_type", ["chat", "responses"])
@pytest.mark.parametrize("base", [None, "https://another-provider.invalid/v1"])
def test_explicit_transport_overrides_default_agent_endpoint(
    model_type, base, monkeypatch
):
    from veadk import Agent
    from veadk.models.ark_llm import ArkLlm
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_EMBEDDING_API_BASE", raising=False)
    cls = ArkLlm if model_type == "responses" else RetryingLiteLlm
    model = cls(model="openai/offline", api_key="offline-transport", api_base=base)
    owner = Agent(name="explicit_transport", model=model, model_api_key="offline-outer")
    assert owner.model_api_base.startswith("https://ark.")
    assert defaults.create_embedder(owner, owner.context_compression) is None


@pytest.mark.parametrize("model_type", ["chat", "responses"])
def test_official_transport_uses_its_own_key(model_type, monkeypatch):
    from veadk import Agent
    from veadk.models.ark_llm import ArkLlm
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("MODEL_EMBEDDING_API_BASE", raising=False)
    cls = ArkLlm if model_type == "responses" else RetryingLiteLlm
    model = cls(
        model="openai/offline",
        api_key="offline-transport",
        api_base="https://ark.cn-beijing.volces.com/api/v3/",
    )
    owner = Agent(name="explicit_transport", model=model, model_api_key="offline-outer")
    embedding = defaults.create_embedder(owner, owner.context_compression)
    assert embedding is not None and embedding._api_key == "offline-transport"


def test_explicit_embedding_key_configures_other_provider(monkeypatch):
    monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "offline-explicit")
    owner = agent()
    owner.model_api_base = "https://another-provider.invalid/v1"
    embedding = defaults.create_embedder(owner, ContextCompressionConfig())
    assert embedding is not None and embedding._api_key == "offline-explicit"


@pytest.mark.asyncio
@pytest.mark.parametrize("business_fails", [False, True])
async def test_optional_cleanup_preserves_business_result_and_error(
    business_fails, monkeypatch
):
    class BusinessError(Exception):
        pass

    async def close(self):
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(defaults.DefaultContextRetriever, "close", close)

    async def business():
        async with defaults.invocation_retriever(agent(), ContextCompressionConfig()):
            if business_fails:
                raise BusinessError("original failure")
            return "business result"

    if business_fails:
        with pytest.raises(BusinessError, match="original failure"):
            await business()
    else:
        assert await business() == "business result"
