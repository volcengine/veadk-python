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

"""Decision-model judgement for the memories a search hands to the agent.

``search_memory`` returns whatever the backend ranked highest for a query.
Similarity alone cannot tell "a memory the answer has to respect" from "a
memory about the same topic the request does not need", and the backend score
is not comparable across backends, so the ``decision`` strategy rates each
candidate for the query and drops what does not clear the threshold.

Judgements are optional: when no decision model is configured, the caller
keeps every match.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from veadk.config import getenv
from veadk.extensions.decisions import (
    DEFAULT_JUDGEMENT_THRESHOLD,
    DecisionAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    ScoreAnswer,
    get_default_decision_extension,
    probability_threshold,
    score_question,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 每个候选记忆对应的问题 id，形如 ``memory_2``。
QUESTION_ID_PREFIX = "memory"

#: 召回判定策略：``decision`` 才会构建判定器，其它值都按关闭处理。
MEMORY_RECALL_STRATEGY = getenv("MEMORY_RECALL_STRATEGY", "off")

#: 相关度阈值：判定低于该值的记忆视为不相关并被丢弃。
MEMORY_RECALL_RELEVANCE_THRESHOLD = probability_threshold(
    getenv(
        "MEMORY_RECALL_RELEVANCE_THRESHOLD",
        DEFAULT_JUDGEMENT_THRESHOLD,
        allow_false_values=True,
    ),
    name="MEMORY_RECALL_RELEVANCE_THRESHOLD",
)

#: 一次判定最多覆盖的记忆条数；超出的按后端顺序原样保留。
MAX_JUDGED_MEMORIES = 20

_DEFAULT_STATE_CHARS = 12000
_DEFAULT_ITEM_CHARS = 600
_MIN_ITEM_CHARS = 120
#: 请求文本在判定状态里的字符上限。
_MAX_REQUEST_CHARS = 600

_RELEVANCE_INSTRUCTIONS = (
    "Rate how much each memory matters for answering the user's request. "
    "Judge only the request, not how interesting the memory is on its own."
)

#: 有序的相关度等级，从最低到最高。等级描述会同时用于提问与 legend。
_RELEVANCE_LEVELS = (
    "irrelevant: it says nothing the request needs",
    "related: the same topic, but it adds nothing the request needs",
    "useful: background the request can build on",
    "required: the request has to respect it to be answered correctly",
)


class RecallJudge(Protocol):
    """Judge how much each recalled memory matters to one query."""

    async def arelevance(
        self, *, query: str, memories: Sequence[str]
    ) -> Mapping[int, float]:
        """Return ``{memory_index: relevance in 0..1}``."""
        ...


class DecisionRecallJudge:
    """Ask a decision model how relevant each recalled memory is.

    One request carries every candidate, so a search costs one decision-model
    call no matter how many memories the backend returned.
    """

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_item_chars: int = _DEFAULT_ITEM_CHARS,
    ) -> None:
        if max_item_chars < 1:
            raise ValueError("max_item_chars must be positive")
        self.extension = extension
        self.max_item_chars = max_item_chars

    async def arelevance(
        self, *, query: str, memories: Sequence[str]
    ) -> Mapping[int, float]:
        """Return the relevance of every memory, keyed by its index.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to keep every match in that case.
        """
        if not memories:
            return {}
        questions = {
            f"{QUESTION_ID_PREFIX}_{index}": _relevance_question(index)
            for index in range(len(memories))
        }
        result = await self.extension.aevaluate(
            state=self._state(query, memories),
            questions=questions,
        )
        return _relevance_scores(result.answers, len(memories))

    def _state(self, query: str, memories: Sequence[str]) -> str:
        """Render the shared state: the query plus a numbered memory list.

        The per-item budget comes from the memory count, so every memory a
        question refers to stays present even when the list is long.
        """
        per_item = max(
            _MIN_ITEM_CHARS,
            min(self.max_item_chars, _DEFAULT_STATE_CHARS // len(memories)),
        )
        lines = [
            "[Memory Recall]",
            f"request: {_truncate(query, _MAX_REQUEST_CHARS)}",
            "memories:",
        ]
        for index, memory in enumerate(memories):
            lines.append(f"- memory {index}: {_truncate(memory, per_item)}")
        lines.append("[/Memory Recall]")
        return "\n".join(lines)


def _relevance_question(index: int) -> dict[str, Any]:
    """Build the relevance question for one recalled memory."""
    return score_question(
        f"{_RELEVANCE_INSTRUCTIONS} memory {index} is:",
        _RELEVANCE_LEVELS,
    )


def _relevance_scores(
    answers: Mapping[str, DecisionAnswer], count: int
) -> dict[int, float]:
    """Map the answers back to memory indexes.

    Raises:
        DecisionModelResponseError: If one memory has no usable answer.
            Callers then keep every match instead of acting on a partial
            judgement.
    """
    scores: dict[int, float] = {}
    for index in range(count):
        answer = answers.get(f"{QUESTION_ID_PREFIX}_{index}")
        if not isinstance(answer, ScoreAnswer):
            raise DecisionModelResponseError(
                f"recall judge returned no usable answer for memory {index}"
            )
        scores[index] = answer.score
    return scores


def build_recall_judge(
    strategy: str,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionRecallJudge | None:
    """Build the judge a strategy asks for.

    Args:
        strategy: ``decision`` builds a judge; anything else returns ``None``.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge, or ``None`` when the strategy is not ``decision`` or no
        decision model is configured. ``None`` keeps every recall match.
    """
    if (strategy or "").strip().lower() != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "recall strategy is 'decision' but no decision model is "
            "configured; keeping every recalled memory"
        )
        return None
    return DecisionRecallJudge(extension)


def _truncate(text: str, max_chars: int) -> str:
    """Keep a judgement state within budget."""
    normalized = " ".join(str(text).split())
    if len(normalized) <= max_chars:
        return normalized
    omitted = len(normalized) - max_chars
    return f"{normalized[:max_chars]} ... [truncated {omitted} chars]"


__all__ = [
    "DecisionRecallJudge",
    "MAX_JUDGED_MEMORIES",
    "MEMORY_RECALL_RELEVANCE_THRESHOLD",
    "MEMORY_RECALL_STRATEGY",
    "RecallJudge",
    "build_recall_judge",
]
