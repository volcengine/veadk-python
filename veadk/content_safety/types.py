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
"""Value objects shared by the content-safety pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class Provider(str, Enum):
    """Content-safety backend selection."""

    NONE = "none"
    DECISION = "decision"
    LLM_SHIELD = "llm_shield"


class Checkpoint(str, Enum):
    """A point in the agent lifecycle where content is audited."""

    BEFORE_MODEL = "before_model"
    AFTER_MODEL = "after_model"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"


class AuditStatus(str, Enum):
    """Outcome of one audit call."""

    PASSED = "passed"
    RISK_HIT = "risk_hit"
    ERROR = "error"
    DISABLED = "disabled"
    SKIPPED = "skipped"


class AuditAction(str, Enum):
    """What the caller must do with the audited content."""

    ALLOW = "allow"
    BLOCK = "block"


@dataclass(frozen=True)
class QuestionResult:
    """Per-question verdict."""

    question: str
    threshold: float
    probability: float | None = None
    valid: bool = False
    hit: bool = False
    error_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "question": self.question,
            "threshold": self.threshold,
            "probability": self.probability,
            "valid": self.valid,
            "hit": self.hit,
            "error_type": self.error_type,
        }


@dataclass(frozen=True)
class AuditResult:
    """Verdict for one invocation at one checkpoint.

    ``risk_hit`` is terminal and always blocks. ``error`` follows the
    configured ``on_error`` policy and is always marked ``degraded``.
    """

    provider: Provider
    checkpoint: Checkpoint
    status: AuditStatus
    action: AuditAction
    degraded: bool = False
    matched_questions: tuple[str, ...] = ()
    question_results: tuple[QuestionResult, ...] = ()
    error_type: str | None = None
    reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider.value,
            "checkpoint": self.checkpoint.value,
            "status": self.status.value,
            "action": self.action.value,
            "degraded": self.degraded,
            "matched_questions": list(self.matched_questions),
            "question_results": [item.to_dict() for item in self.question_results],
            "error_type": self.error_type,
            "reason": self.reason,
        }

    @classmethod
    def allow(
        cls,
        *,
        provider: Provider,
        checkpoint: Checkpoint,
        question_results: tuple[QuestionResult, ...] = (),
        reason: str | None = None,
    ) -> "AuditResult":
        return cls(
            provider=provider,
            checkpoint=checkpoint,
            status=AuditStatus.PASSED,
            action=AuditAction.ALLOW,
            question_results=question_results,
            reason=reason,
        )

    @classmethod
    def block(
        cls,
        *,
        provider: Provider,
        checkpoint: Checkpoint,
        matched_questions: tuple[str, ...],
        question_results: tuple[QuestionResult, ...] = (),
        reason: str | None = None,
    ) -> "AuditResult":
        return cls(
            provider=provider,
            checkpoint=checkpoint,
            status=AuditStatus.RISK_HIT,
            action=AuditAction.BLOCK,
            matched_questions=matched_questions,
            question_results=question_results,
            reason=reason,
        )

    @classmethod
    def error(
        cls,
        *,
        provider: Provider,
        checkpoint: Checkpoint,
        on_error: str,
        error_type: str,
        reason: str | None = None,
        question_results: tuple[QuestionResult, ...] = (),
    ) -> "AuditResult":
        return cls(
            provider=provider,
            checkpoint=checkpoint,
            status=AuditStatus.ERROR,
            action=AuditAction.BLOCK if on_error == "block" else AuditAction.ALLOW,
            degraded=True,
            question_results=question_results,
            error_type=error_type,
            reason=reason,
        )

    @classmethod
    def skipped(
        cls, *, provider: Provider, checkpoint: Checkpoint, reason: str
    ) -> "AuditResult":
        return cls(
            provider=provider,
            checkpoint=checkpoint,
            status=AuditStatus.SKIPPED,
            action=AuditAction.ALLOW,
            reason=reason,
        )

    @classmethod
    def disabled(
        cls, *, provider: Provider, checkpoint: Checkpoint, reason: str
    ) -> "AuditResult":
        return cls(
            provider=provider,
            checkpoint=checkpoint,
            status=AuditStatus.DISABLED,
            action=AuditAction.ALLOW,
            reason=reason,
        )
