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

"""Decision-model judgement for the skills one request needs.

A skill library is advertised as one list, so the model re-reads every
description on every call. Whether a request needs a skill is a yes/no question
per skill, so the ``decision`` strategy asks one ``noul`` question per candidate
in a single request and lets the caller keep the ones above its threshold.

The candidates are judged independently, and one request often needs two
skills, which is why this is not a single ``choice`` over the list: a choice
names one winner, while the prefilter needs a probability per candidate.
Sibling questions cannot see each other, so one skill's description cannot
decide another skill's answer.

Judgements are optional: when no decision model is configured, callers keep
advertising every skill.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import Field

from veadk.extensions.decisions import (
    DecisionAnswer,
    DecisionExtension,
    DecisionModelResponseError,
    NoulAnswer,
    UNTRUSTED_NOTICE,
    get_default_decision_extension,
    noul_question,
    untrusted,
)
from veadk.extensions.harness.schemas import HarnessBaseModel
from veadk.extensions.harness.utils import summarize_text
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定返回的问题 id 前缀，按候选顺序编号。
QUESTION_ID_PREFIX = "skill"

#: 一次判定最多覆盖的候选技能数；超过则不做判定，保留完整列表。
DEFAULT_MAX_CANDIDATES = 40

_DEFAULT_STATE_CHARS = 4000
_NO_DESCRIPTION = "this skill has no description"

_INSTRUCTIONS = "Does the user's request need this skill?"


class HarnessSkillPrefilterConfig(HarnessBaseModel):
    """Settings for the skills an agent advertises per request."""

    # ``decision`` asks the configured decision model which skills the request
    # needs; ``all`` keeps advertising every loaded skill.
    strategy: Literal["all", "decision"] = "all"
    decision_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    max_candidates: int = Field(default=DEFAULT_MAX_CANDIDATES, ge=1, le=255)


class SkillJudge(Protocol):
    """Judge which advertised skills one request needs."""

    async def aprobabilities(
        self, *, user_input: str, skills: Mapping[str, str]
    ) -> Mapping[str, float]:
        """Return ``{skill_name: probability that the request needs it}``."""
        ...


class DecisionSkillJudge:
    """Ask a decision model which advertised skills a request needs."""

    def __init__(
        self,
        extension: DecisionExtension,
        *,
        max_state_chars: int = _DEFAULT_STATE_CHARS,
    ) -> None:
        if max_state_chars < 1:
            raise ValueError("max_state_chars must be positive")
        self.extension = extension
        self.max_state_chars = max_state_chars

    async def aprobabilities(
        self, *, user_input: str, skills: Mapping[str, str]
    ) -> Mapping[str, float]:
        """Return the probability that the request needs each skill.

        Raises:
            DecisionModelError: If the decision model cannot answer. Callers
                are expected to keep the full list instead of acting on a
                partial judgement.
        """
        if not skills:
            return {}
        names = list(skills)
        result = await self.extension.aevaluate(
            state=self._state(user_input),
            questions={
                f"{QUESTION_ID_PREFIX}_{index}": build_skill_question(skills[name])
                for index, name in enumerate(names)
            },
        )
        return _probabilities(result.answers, names)

    def _state(self, user_input: str) -> str:
        """Render the state: only the request the questions ask about.

        The candidates travel in the questions, because a description that
        decides one answer must not be visible to the others.
        """
        request = summarize_text(user_input, max_chars=self.max_state_chars)
        return "\n".join(
            [
                "[Skill Triage]",
                UNTRUSTED_NOTICE,
                "user_request: " + untrusted("user_request", request or "unspecified"),
                "[/Skill Triage]",
            ]
        )


def build_skill_question(description: str) -> dict[str, Any]:
    """Build the question for one candidate skill."""
    return noul_question(
        f"{_INSTRUCTIONS} Skill description: {description or _NO_DESCRIPTION}",
        yes="the request matches what this skill does",
        no="the request is handled without this skill",
    )


def skill_selection(
    probabilities: Mapping[str, float],
    names: Sequence[str],
    *,
    threshold: float,
) -> frozenset[str]:
    """Return the skills to keep after one judgement.

    A skill the judgement did not answer for is kept: a missing probability is
    not evidence that the request does not need it, and dropping it would hide a
    skill from a model that never saw it questioned.
    """
    return frozenset(
        name for name in names if probabilities.get(name, 1.0) >= threshold
    )


def build_skill_judge(
    config: HarnessSkillPrefilterConfig,
    *,
    extension: DecisionExtension | None = None,
) -> DecisionSkillJudge | None:
    """Build the judge a configuration asks for.

    Args:
        config: Prefilter settings; only the ``decision`` strategy builds one.
        extension: Decision model to use instead of the process-wide one.

    Returns:
        A judge for the ``decision`` strategy, or ``None`` for the ``all``
        strategy or an unconfigured decision model. ``None`` keeps advertising
        every skill, which is the documented degradation path.
    """
    if config.strategy != "decision":
        return None
    extension = extension or get_default_decision_extension()
    if not extension.enabled:
        logger.warning(
            "skill strategy is 'decision' but no decision model is configured; "
            "advertising every skill"
        )
        return None
    return DecisionSkillJudge(extension)


def _probabilities(
    answers: Mapping[str, DecisionAnswer], names: Sequence[str]
) -> dict[str, float]:
    """Map the numbered answers back to skill names.

    Raises:
        DecisionModelResponseError: If one candidate has no usable answer.
            Callers then keep the full list instead of acting on a partial
            judgement.
    """
    probabilities: dict[str, float] = {}
    for index, name in enumerate(names):
        answer = answers.get(f"{QUESTION_ID_PREFIX}_{index}")
        if not isinstance(answer, NoulAnswer):
            raise DecisionModelResponseError(
                f"skill judge returned no usable answer for index {index}"
            )
        probabilities[name] = answer.noul
    return probabilities


__all__ = [
    "DEFAULT_MAX_CANDIDATES",
    "DecisionSkillJudge",
    "HarnessSkillPrefilterConfig",
    "QUESTION_ID_PREFIX",
    "SkillJudge",
    "build_skill_judge",
    "build_skill_question",
    "skill_selection",
]
