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

"""No-model defaults must retrieve real evidence without inference dependencies."""

import asyncio
import copy
from pathlib import Path
import re
import time
from types import SimpleNamespace

import pytest

from veadk.context import defaults
from veadk.context.config import ContextCompressionConfig


@pytest.mark.parametrize("mode", ["auto", "lexical"])
@pytest.mark.parametrize("online", [True, False])
def test_explicit_online_and_lexical_selection(mode, online, monkeypatch):
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    if online:
        monkeypatch.setenv("MODEL_EMBEDDING_API_KEY", "offline-explicit")
    result = defaults.create_embedder(
        SimpleNamespace(), ContextCompressionConfig(retrieval=mode)
    )
    if online and mode == "auto":
        assert isinstance(result, defaults.ArkContextEmbedding)
    else:
        assert result is None


def test_unconfigured_default_has_no_embedding(monkeypatch):
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("MODEL_EMBEDDING_NAME", "studio-placeholder")
    owner = SimpleNamespace(model_api_key="offline-agent-only")
    assert defaults.create_embedder(owner, ContextCompressionConfig()) is None


def test_no_bundled_inference_dependencies():
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib

    root = Path(__file__).resolve().parents[2]
    config = tomllib.loads((root / "pyproject.toml").read_text())
    names = {
        re.split(r"[<>=!~;\[ ]", item, maxsplit=1)[0].lower()
        for item in config["project"]["dependencies"]
    }
    assert not names & {"onnxruntime", "tokenizers", "numpy"}
    assert not (root / "veadk/context/_offline_worker.py").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query,answer",
    [
        ("退款到账时间", "退款到账需要七个工作日"),
        ("invoice INV-418", "INV-418 = 187.25"),
    ],
)
async def test_model_free_ranker_finds_tail_and_keeps_exact_ranges(
    query, answer, tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    text = "Warehouse operations are unchanged.\n\n" * 300 + answer
    async with defaults.invocation_retriever(
        SimpleNamespace(), ContextCompressionConfig()
    ) as retriever:
        spans = await retriever.rank_with_deadline(
            ("app", "user", "session", "agent", ""),
            "source",
            text,
            query,
            deadline=time.monotonic() + 5,
        )
        assert spans and retriever.last_status == "bm25"
        assert answer in text[spans[0][0] : spans[0][1]]
        assert all(0 <= a < b <= len(text) for a, b in spans)
        assert retriever._embedder is None
    assert not (tmp_path / ".adk").exists()


@pytest.mark.asyncio
async def test_model_free_query_miss_and_deadline(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    async with defaults.invocation_retriever(
        SimpleNamespace(), ContextCompressionConfig()
    ) as retriever:
        args = (("app", "u", "s", "a", ""), "ref", "Invoice INV-418.", "missing987")
        assert (
            await retriever.rank_with_deadline(*args, deadline=time.monotonic() + 5)
            == []
        )
        with pytest.raises(asyncio.TimeoutError):
            await retriever.rank_with_deadline(*args, deadline=time.monotonic() - 1)


@pytest.mark.asyncio
async def test_model_free_bounds_and_cancellation():
    from veadk.context.lexical_retriever import rank_lexical

    args = (("app", "u", "s", "a", ""), "ref")
    with pytest.raises(ValueError, match="lexical_input_limit"):
        await rank_lexical(*args, "x" * 2_000_001, "x", deadline=time.monotonic() + 5)
    work = asyncio.create_task(
        rank_lexical(
            *args,
            "inventory unchanged. " * 10000,
            "inventory",
            deadline=time.monotonic() + 5,
        )
    )
    await asyncio.sleep(0)
    assert not work.done()
    work.cancel()
    with pytest.raises(asyncio.CancelledError):
        await work


@pytest.mark.asyncio
async def test_model_free_default_compression_and_source_recovery(
    tmp_path, monkeypatch
):
    from veadk import Agent
    from veadk.context.budget import count_input, request_payload
    from veadk.context.manager import prepare_context
    from veadk.context.runtime import current_scope
    from test_preview_admission import example
    from test_recoverable_context import read

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    owner = Agent(name="model_free_agent", model_api_key="offline-test")
    for _ in range(2):
        text, request, scope, policy, before = example(16000)
        original = copy.deepcopy(scope.session.events)
        async with defaults.invocation_retriever(owner, policy) as retriever:
            scope.evidence_retriever = retriever
            token = current_scope.set(scope)
            try:
                await prepare_context(
                    request, SimpleNamespace(model=request.model), policy, {}
                )
            finally:
                current_scope.reset(token)
            after = count_input(request_payload(request), policy)
            assert after < before
            assert after <= policy.input_limit - min(1024, policy.input_limit // 20)
            assert retriever.last_status == "bm25" and retriever._embedder is None
            rendered = "".join(c.model_dump_json() for c in request.contents)
            ref = re.search(r"ctx_[a-f0-9]{24}", rendered)[0]
            result = await read(request, scope, ref, query="Record 113:")
            assert result["text"] == text[result["offset"] : result["end"]]
            assert "audited balance 2599 units" in result["text"]
            assert scope.session.events == original
    assert not (tmp_path / ".adk/context-index.sqlite3").exists()
