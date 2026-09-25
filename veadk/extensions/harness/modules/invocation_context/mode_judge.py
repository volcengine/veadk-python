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

"""Decision-model judgement for the Harness mode blocks.

The invocation context builder injects a precision block and an artifact block
when the user's wording suggests them. Keyword matching misses paraphrases and
fires on incidental words, so the ``decision`` strategy asks the configured
decision model whether the task really needs each block. The builder thresholds
the probabilities, so one request covers both blocks.

Judgements are optional: when no decision model is configured, the builder
keeps the keyword markers.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol

from veadk.extensions.decisions import (
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    UNTRUSTED_NOTICE,
    get_default_decision_extension,
    noul_question,
    untrusted,
)
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from veadk.extensions.harness.modules.invocation_context.builder import (
        HarnessInvocationContextConfig,
    )

logger = get_logger(__name__)

#: 两个模式块的名称，也是判定返回的键。
PRECISION_MODE = "precision"
ARTIFACT_MODE = "artifact"

PRECISION_QUESTION_ID = PRECISION_MODE
ARTIFACT_QUESTION_ID = ARTIFACT_MODE

_MAX_INPUT_CHARS = 4000

_PRECISION_INSTRUCTIONS = (
    "Does the user's request require exact handling of selectors, schemas, "
    "dates, counts, or numeric thresholds?"
)
_ARTIFACT_INSTRUCTIONS = (
    "Does the user's request require creating a file, chart, report, or other "
    "artifact as the deliverable?"
)


class ModeJudge(Protocol):
    """Judge which Harness mode blocks a user request needs."""

    async def aprobabilities(self, *, user_input: str) -> Mapping[str, float]:
        """Return ``{mode_name: probability that the mode applies}``."""
        ...


class DecisionModeJudge:
    """Ask a decision model which mode blocks a request needs."""

    def __init__(self, extension: DecisionExtension) -> None:
        self.extension = extension

    async def aprobabilities(self, *, user_input: str) -> Mapping[str, float]:
        """Return the probability of each mode block.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to fall back to their keyword markers.
        """
        result = await self.extension.aevaluate(
            state="\n".join(
                [
                    "[Mode Triage]",
                    UNTRUSTED_NOTICE,
                    "user_request: "
                    + untrusted(
                        "user_request",
                        summarize_text(user_input, max_chars=_MAX_INPUT_CHARS)
                        or "unspecified",
                    ),
                    "[/Mode Triage]",
                ]
            ),
            questions={
                PRECISION_QUESTION_ID: build_precision_question(),
                ARTIFACT_QUESTION_ID: build_artifact_question(),
            },
        )
        return {
            PRECISION_MODE: _probability(result.answers, PRECISION_QUESTION_ID),
            ARTIFACT_MODE: _probability(result.answers, ARTIFACT_QUESTION_ID),
        }


def build_precision_question() -> dict[str, Any]:
    """Build the precision-mode question."""
    return noul_question(
        _PRECISION_INSTRUCTIONS,
        yes="the answer must respect exact values, formats, or filters",
        no="approximate or qualitative handling is enough",
    )


def build_artifact_question() -> dict[str, Any]:
    """Build the artifact-mode question."""
    return noul_question(
        _ARTIFACT_INSTRUCTIONS,
        yes="a file, chart, or report has to be produced",
        no="an explanation in the reply is enough",
    )


def build_mode_judge(
    config: HarnessInvocationContextConfig,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionModeJudge | None:
    """Build the judge a configuration asks for.

    Args:
        config: Builder settings; only the ``decision`` strategy builds one.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge for the ``decision`` strategy, or ``None`` for the ``keywords``
        strategy or an unconfigured decision model.
    """
    if config.mode_strategy != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "mode strategy is 'decision' but no decision model is configured; "
            "keeping the keyword markers"
        )
        return None
    return DecisionModeJudge(extension)


def _probability(answers: Mapping[str, Any], question_id: str) -> float:
    """Return one probability, rejecting an unusable answer."""
    answer = answers.get(question_id)
    if not isinstance(answer, NoulAnswer):
        raise DecisionModelResponseError(
            f"mode judge returned no usable answer for {question_id!r}"
        )
    return answer.noul


__all__ = [
    "ARTIFACT_MODE",
    "DecisionModeJudge",
    "ModeJudge",
    "PRECISION_MODE",
    "build_artifact_question",
    "build_mode_judge",
    "build_precision_question",
]
