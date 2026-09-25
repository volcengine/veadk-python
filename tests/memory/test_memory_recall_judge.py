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

"""Recall filtering: judged relevance, opt-in, fail-safe."""

from __future__ import annotations

import asyncio
import importlib
from collections.abc import Sequence
from typing import Any

import pytest
from pydantic import Field

from veadk.extensions.decisions import (
    DecisionModelConfig,
    DecisionModelDisabledError,
    DecisionExtension,
    DecisionModelResponseError,
    DecisionResult,
    ScoreAnswer,
)
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.memory.recall_judge import (
    MAX_JUDGED_MEMORIES,
    DecisionRecallJudge,
    build_recall_judge,
)


class _StubExtension:
    """Answer with fixed payloads, without a decision model behind them."""

    def __init__(
        self,
        answers: dict[str, Any] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.answers = answers or {}
        self.error = error
        self.questions: dict[str, Any] = {}
        self.state: str = ""

    async def aevaluate(self, state: Any, questions: dict[str, Any]) -> DecisionResult:
        self.state = state
        self.questions = questions
        if self.error is not None:
            raise self.error
        return DecisionResult(answers=self.answers)


class _FakeJudge:
    """Record the memories it judged and return fixed relevance scores."""

    def __init__(
        self,
        scores: dict[int, float] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.scores = scores or {}
        self.error = error
        self.calls: list[dict[str, Any]] = []

    async def arelevance(
        self, *, query: str, memories: Sequence[str]
    ) -> dict[int, float]:
        self.calls.append({"query": query, "memories": list(memories)})
        if self.error is not None:
            raise self.error
        return self.scores


class _RecordingBackend(BaseLongTermMemoryBackend):
    chunks: list[str] = Field(default_factory=list)

    def precheck_index_naming(self) -> None:
        pass

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        return True

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        return list(self.chunks)


def _memory_with(judge: _FakeJudge | None, chunks: list[str], **kwargs: Any):
    backend = _RecordingBackend(index="support_app", chunks=chunks)
    memory = LongTermMemory(backend=backend, app_name="support_app", **kwargs)
    # 判定器由策略构建，这里直接注入替身以验证过滤本身。
    memory._recall_judge = judge
    return memory


def _search(memory: LongTermMemory) -> list[str]:
    response = asyncio.run(
        memory.search_memory(app_name="support_app", user_id="alice", query="pricing?")
    )
    return [
        part.text
        for entry in response.memories
        for part in (entry.content.parts or [])
        if part.text
    ]


def test_recall_strategy_is_opt_in() -> None:
    disabled = DecisionExtension(DecisionModelConfig.disabled())

    assert build_recall_judge("off", extension=disabled) is None
    assert build_recall_judge("", extension=disabled) is None
    assert build_recall_judge("decision", extension=disabled) is None
    assert (
        build_recall_judge(
            "decision",
            extension=DecisionExtension(DecisionModelConfig(enabled=True, api_key="k")),
        )
        is not None
    )


def test_the_judge_asks_one_score_question_per_memory() -> None:
    extension = _StubExtension(
        {
            "memory_0": ScoreAnswer(score=0.1),
            "memory_1": ScoreAnswer(score=0.9),
        }
    )
    judge = DecisionRecallJudge(extension)  # type: ignore[arg-type]

    scores = asyncio.run(
        judge.arelevance(query="pricing?", memories=["a greeting", "a stated limit"])
    )

    assert scores == {0: 0.1, 1: 0.9}
    assert set(extension.questions) == {"memory_0", "memory_1"}
    assert {question["type"] for question in extension.questions.values()} == {"score"}


def test_a_memory_without_an_answer_is_rejected() -> None:
    extension = _StubExtension({"memory_0": ScoreAnswer(score=0.9)})
    judge = DecisionRecallJudge(extension)  # type: ignore[arg-type]

    with pytest.raises(DecisionModelResponseError):
        asyncio.run(judge.arelevance(query="q", memories=["a", "b"]))


def test_the_state_names_every_memory_within_budget() -> None:
    extension = _StubExtension(
        {f"memory_{index}": ScoreAnswer(score=0.9) for index in range(3)}
    )
    judge = DecisionRecallJudge(extension)  # type: ignore[arg-type]

    asyncio.run(
        judge.arelevance(
            query="pricing?",
            memories=["x" * 5000 for _ in range(3)],
        )
    )

    for index in range(3):
        assert f"- memory {index}:" in extension.state
    assert len(extension.state) < 3000


def test_irrelevant_memories_are_dropped_and_order_is_kept() -> None:
    judge = _FakeJudge({0: 0.9, 1: 0.1, 2: 0.6})
    memory = _memory_with(judge, ["limit is 10 rps", "likes tea", "uses python 3.11"])

    assert _search(memory) == ["limit is 10 rps", "uses python 3.11"]
    assert judge.calls[0]["query"] == "pricing?"
    assert judge.calls[0]["memories"] == [
        "limit is 10 rps",
        "likes tea",
        "uses python 3.11",
    ]


def test_a_memory_at_the_threshold_is_kept() -> None:
    judge = _FakeJudge({0: 0.5, 1: 0.499})
    memory = _memory_with(judge, ["a", "b"])

    assert _search(memory) == ["a"]


def test_the_threshold_can_be_raised_from_the_instance() -> None:
    judge = _FakeJudge({0: 0.6, 1: 0.7})
    memory = _memory_with(judge, ["a", "b"], recall_relevance_threshold=0.65)

    assert _search(memory) == ["b"]


def test_a_failing_judge_keeps_every_memory() -> None:
    judge = _FakeJudge(error=DecisionModelDisabledError("not configured"))
    memory = _memory_with(judge, ["a", "b"])

    assert _search(memory) == ["a", "b"]


def test_a_memory_the_judge_did_not_rate_is_kept() -> None:
    judge = _FakeJudge({1: 0.0})
    memory = _memory_with(judge, ["unrated", "irrelevant"])

    assert _search(memory) == ["unrated"]


def test_memories_beyond_the_judged_budget_are_kept() -> None:
    judge = _FakeJudge({index: 1.0 for index in range(MAX_JUDGED_MEMORIES)})
    chunks = [f"memory {index}" for index in range(MAX_JUDGED_MEMORIES + 3)]
    memory = _memory_with(judge, chunks)

    kept = _search(memory)

    assert len(judge.calls[0]["memories"]) == MAX_JUDGED_MEMORIES
    assert kept[-3:] == ["memory 20", "memory 21", "memory 22"]


def test_no_judge_returns_every_match() -> None:
    memory = _memory_with(None, ["a", "b"])

    assert _search(memory) == ["a", "b"]


def test_an_unusable_relevance_threshold_is_sanitized_at_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """越界的阈值会被夹紧，NaN 回落到默认值，而不是让过滤静默失效。"""
    from veadk.memory import recall_judge

    monkeypatch.setenv("MEMORY_RECALL_RELEVANCE_THRESHOLD", "1.5")
    assert importlib.reload(recall_judge).MEMORY_RECALL_RELEVANCE_THRESHOLD == 1.0

    monkeypatch.setenv("MEMORY_RECALL_RELEVANCE_THRESHOLD", "nan")
    assert importlib.reload(recall_judge).MEMORY_RECALL_RELEVANCE_THRESHOLD == 0.5

    monkeypatch.delenv("MEMORY_RECALL_RELEVANCE_THRESHOLD")
    importlib.reload(recall_judge)
