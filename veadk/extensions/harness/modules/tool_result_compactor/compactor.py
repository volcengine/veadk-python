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

"""Tool-result compaction module."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import Field

from veadk.extensions.decisions import DecisionModelError
from veadk.extensions.harness.modules.tool_result_compactor.builtin_provider import (
    BuiltinCompressionProvider,
)
from veadk.extensions.harness.modules.tool_result_compactor.decision_judge import (
    CompactionJudge,
    build_compaction_judge,
)
from veadk.extensions.harness.modules.tool_result_compactor.headroom_provider import (
    HeadroomCompressionProvider,
)
from veadk.extensions.harness.schemas import (
    CompressionDecision,
    CompressionPlan,
    CompactionReport,
    CompressionRequest,
    CompactionResult,
    ConversationMessage,
    HarnessBaseModel,
    JsonObject,
)
from veadk.extensions.harness.utils import (
    coerce_json_object,
    redact_text,
    stringify_json_value,
    summarize_text,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

#: 判定为"必须原样保留"时的决策原因，便于调用方和报表区分来源。
DECISION_KEEP_REASON = "decision_model_keep_verbatim"
#: 判定为"可以摘要"时的决策原因。
DECISION_SUMMARIZE_REASON = "decision_model_summarizable"


class ToolResultCompactorConfig(HarnessBaseModel):
    """Settings for tool-result compaction."""

    provider: str = "builtin"
    # ``decision`` replaces the role based candidate rules with a content
    # pre-filter plus a decision-model judgement; ``builtin`` keeps them
    # untouched. Role labels cannot separate a tool result from the user's own
    # text on real ADK traffic, which is why the content filter exists.
    strategy: Literal["builtin", "decision"] = "builtin"
    max_context_chars: int = 24000
    max_tool_result_chars: int = 4000
    min_candidate_chars: int = 4000
    protect_recent_messages: int = 2
    #: 判定策略下始终原样保留的开头消息数，用于护住最初的任务描述。
    protect_leading_messages: int = Field(default=1, ge=0)
    summary_chars: int = 900
    decision_keep_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    decision_evidence_chars: int = Field(default=600, ge=1)


class ContextCompactionPolicy:
    """Select safe historical context for compaction.

    The builtin rules only read message roles and sizes. A ``judge`` adds a
    content judgement for every candidate the rules selected, so evidence a
    run still needs can be protected from summarization.
    """

    def __init__(
        self,
        config: ToolResultCompactorConfig | None = None,
        *,
        judge: CompactionJudge | None = None,
    ) -> None:
        self.config = config or ToolResultCompactorConfig()
        self.judge = judge

    def plan(self, messages: list[ConversationMessage]) -> CompressionPlan:
        """Plan from the builtin rules alone."""
        return self._build_plan(self._classify_all(messages))

    async def aplan(
        self, messages: list[ConversationMessage], *, goal: str = ""
    ) -> CompressionPlan:
        """Plan with the configured judge, degrading to the builtin rules.

        Under the decision strategy the candidates come from a content
        pre-filter instead of the role based rules, because role labels cannot
        tell a tool result from the user's own text on real ADK traffic. Every
        candidate is then judged on content: the ones the judge keeps stay
        verbatim, the rest may be summarized.

        Args:
            messages: Messages to classify.
            goal: The task the run is working on, used as judgement context.
        """
        decisions = self._classify_all(messages)
        if self.judge is None:
            return self._build_plan(decisions)
        evidence = {
            index: messages[index].content
            for index in self._judgeable_indexes(messages)
        }
        if not evidence:
            return self._build_plan(decisions)
        try:
            keep_probabilities = await self.judge.aprotect(goal=goal, evidence=evidence)
        except DecisionModelError as exc:
            logger.warning(
                "decision model could not judge compaction candidates, keeping "
                "the builtin rules: %s",
                exc,
            )
            return self._build_plan(decisions)
        judged = [
            self._apply_judgement(decision, keep_probabilities.get(decision.index))
            for decision in decisions
        ]
        return self._build_plan(
            judged,
            summary_extra={
                "judged_by": "decision_model",
                "judged_candidates": len(evidence),
                "kept_verbatim": sum(
                    1
                    for index in evidence
                    if keep_probabilities[index] >= self.config.decision_keep_threshold
                ),
            },
        )

    def _judgeable_indexes(self, messages: list[ConversationMessage]) -> list[int]:
        """Indexes the decision strategy may summarize.

        Only large, non-leading, non-recent messages qualify; instructions are
        never summarized. The leading window is always protected so the
        original task statement survives a wrong judgement.
        """
        total = len(messages)
        return [
            index
            for index, message in enumerate(messages)
            if index >= self.config.protect_leading_messages
            and message.role not in {"system", "developer"}
            and total - index > self.config.protect_recent_messages
            and len(message.content) >= self.config.min_candidate_chars
        ]

    def _classify_all(
        self, messages: list[ConversationMessage]
    ) -> list[CompressionDecision]:
        return [
            self._classify(index=index, total=len(messages), message=message)
            for index, message in enumerate(messages)
        ]

    def _build_plan(
        self,
        decisions: list[CompressionDecision],
        summary_extra: JsonObject | None = None,
    ) -> CompressionPlan:
        candidate_indexes = [
            decision.index for decision in decisions if decision.action == "compress"
        ]
        by_action: dict[str, int] = {}
        by_reason: dict[str, int] = {}
        for decision in decisions:
            by_action[decision.action] = by_action.get(decision.action, 0) + 1
            key = f"{decision.action}:{decision.reason}"
            by_reason[key] = by_reason.get(key, 0) + 1
        summary: JsonObject = {
            "mode": "role_and_recency_aware",
            "message_count": len(decisions),
            "candidate_count": len(candidate_indexes),
            "candidate_indexes": list(candidate_indexes),
            "by_action": by_action,
            "by_reason": by_reason,
        }
        if summary_extra:
            summary.update(summary_extra)
        return CompressionPlan(
            decisions=decisions,
            candidate_indexes=candidate_indexes,
            summary=summary,
        )

    def _apply_judgement(
        self, decision: CompressionDecision, keep_probability: float | None
    ) -> CompressionDecision:
        """Apply the judgement of one candidate.

        Args:
            decision: The builtin decision, kept when the message was not
                handed to the judge.
            keep_probability: Probability that the message must stay verbatim,
                or ``None`` when it was not a candidate.
        """
        if keep_probability is None:
            return decision
        if keep_probability >= self.config.decision_keep_threshold:
            return decision.model_copy(
                update={"action": "protect", "reason": DECISION_KEEP_REASON}
            )
        return decision.model_copy(
            update={"action": "compress", "reason": DECISION_SUMMARIZE_REASON}
        )

    def _classify(
        self,
        *,
        index: int,
        total: int,
        message: ConversationMessage,
    ) -> CompressionDecision:
        role = message.role
        chars = len(message.content)
        messages_from_end = total - index
        if role in {"system", "developer"}:
            return self._decision(index, "protect", "instructions", role, chars)
        if role == "user":
            return self._decision(index, "protect", "user_intent", role, chars)
        if role == "assistant":
            return self._decision(index, "protect", "assistant_state", role, chars)
        if messages_from_end <= self.config.protect_recent_messages:
            return self._decision(index, "protect", "recent_feedback", role, chars)
        if chars < self.config.min_candidate_chars:
            return self._decision(index, "skip", "small_output", role, chars)
        if role in {"tool", "tool_result", "function"}:
            reason = (
                "old_large_error_or_recovery_evidence"
                if self._looks_like_recovery_evidence(message.content)
                else "old_large_tool_output"
            )
            return self._decision(index, "compress", reason, role, chars)
        return self._decision(index, "compress", "old_large_unknown_role", role, chars)

    def _decision(
        self,
        index: int,
        action: Literal["protect", "skip", "compress"],
        reason: str,
        role: str,
        chars: int,
    ) -> CompressionDecision:
        return CompressionDecision(
            index=index,
            action=action,
            reason=reason,
            role=role,
            chars=chars,
        )

    def _looks_like_recovery_evidence(self, text: str) -> bool:
        lowered = text.lower()
        signals = (
            "traceback",
            "exception",
            "error:",
            "failed",
            "permission denied",
            "no such file",
            "syntaxerror",
            "typeerror",
            "diff --git",
        )
        return any(signal in lowered for signal in signals)


class ToolResultCompactor:
    """Dependency-free compactor for large historical tool results."""

    def __init__(
        self,
        config: ToolResultCompactorConfig | None = None,
        *,
        compaction_judge: CompactionJudge | None = None,
    ) -> None:
        self.config = config or ToolResultCompactorConfig()
        # ``None`` keeps the builtin rules; the config decides which strategy
        # is asked for and an unconfigured decision model degrades back to them.
        self.policy = ContextCompactionPolicy(
            self.config,
            judge=compaction_judge or build_compaction_judge(self.config),
        )
        self.builtin = BuiltinCompressionProvider()
        self._headroom: HeadroomCompressionProvider | None = None

    @property
    def uses_judgement(self) -> bool:
        """Whether a decision model judges the compaction candidates."""
        return self.policy.judge is not None

    def compress_messages(self, request: CompressionRequest) -> CompactionResult:
        """Compact candidate messages while preserving control-plane messages."""

        if self._fits(request):
            return self._unchanged_result(request)
        return self._compress_messages(request, self.policy.plan(request.messages))

    async def acompress_messages(
        self, request: CompressionRequest, *, goal: str = ""
    ) -> CompactionResult:
        """Asynchronous counterpart of :meth:`compress_messages`.

        Args:
            request: Messages and limits to compact.
            goal: The task the run is working on, used as judgement context.
        """
        if self._fits(request):
            return self._unchanged_result(request)
        plan = await self.policy.aplan(request.messages, goal=goal)
        return self._compress_messages(request, plan)

    def _fits(self, request: CompressionRequest) -> bool:
        """Whether the request already fits its context budget."""
        return self._messages_char_count(request.messages) <= request.max_context_chars

    def _unchanged_result(self, request: CompressionRequest) -> CompactionResult:
        """Return the messages of a request that already fits."""
        original_chars = self._messages_char_count(request.messages)
        return CompactionResult(
            messages=list(request.messages),
            report=CompactionReport(
                provider=self.config.provider,
                original_chars=original_chars,
                compressed_chars=original_chars,
                changed=False,
            ),
        )

    def _compress_messages(
        self, request: CompressionRequest, plan: CompressionPlan
    ) -> CompactionResult:
        """Compact the candidates of ``plan`` to fit the context budget."""

        original_chars = self._messages_char_count(request.messages)
        warnings: list[str] = []
        if self._uses_headroom():
            result = self._compress_messages_with_headroom(request, plan)
            if result is not None:
                return result
            warnings.append("headroom provider unavailable; used builtin fallback")

        if self._uses_headroom() or self._uses_builtin_or_default():
            result = self._compress_messages_with_builtin(request, plan, warnings)
            if result is not None:
                return result

        compressed = list(request.messages)
        for index in plan.candidate_indexes:
            message = compressed[index]
            compressed[index] = message.model_copy(
                update={"content": self._summary(message.content, index=index)}
            )
            if self._messages_char_count(compressed) <= request.max_context_chars:
                break

        omitted = 0
        while (
            self._messages_char_count(compressed) > request.max_context_chars
            and len(compressed) > request.protected_message_count
        ):
            removable = self._oldest_removable_index(compressed)
            if removable is None:
                break
            compressed.pop(removable)
            omitted += 1

        compressed_chars = self._messages_char_count(compressed)
        if self._uses_headroom() and plan.candidate_indexes:
            warnings[-1:] = [
                "headroom and builtin providers unavailable; used heuristic fallback"
            ]
        if compressed_chars > request.max_context_chars:
            warnings.append("context still exceeds max_context_chars")
        return CompactionResult(
            messages=compressed,
            report=CompactionReport(
                provider=self._fallback_provider(),
                original_chars=original_chars,
                compressed_chars=compressed_chars,
                changed=compressed != request.messages,
                omitted_messages=omitted,
                protected_messages=len(
                    [item for item in plan.decisions if item.action == "protect"]
                ),
                compression_ratio=(
                    compressed_chars / original_chars if original_chars else 1.0
                ),
                transforms_applied=["heuristic_summary"]
                if compressed != request.messages
                else [],
                policy=plan.summary,
                warnings=warnings,
            ),
        )

    def compress_tool_result(self, result: object) -> tuple[object, CompactionReport]:
        """Compact a single tool result mapping if it exceeds the configured size."""

        original_text = self._raw_payload_text(result)
        original_chars = len(original_text)
        if original_chars <= self.config.max_tool_result_chars:
            return result, CompactionReport(
                provider=self.config.provider,
                original_chars=original_chars,
                compressed_chars=original_chars,
                changed=False,
            )

        warnings: list[str] = []
        if self._uses_headroom():
            headroom = self._compress_tool_result_with_headroom(
                result=result,
                original_text=original_text,
                original_chars=original_chars,
            )
            if headroom is not None:
                return headroom
            warnings.append("headroom provider unavailable; used builtin fallback")

        builtin = self._compress_tool_result_with_builtin(
            result=result,
            original_text=original_text,
            original_chars=original_chars,
            warnings=warnings,
        )
        if builtin is not None:
            return builtin

        summary = self._summary(original_text, index=0)
        compressed: dict[str, object] = {
            "harness_compressed": True,
            "summary": summary,
            "original_chars": original_chars,
        }
        if isinstance(result, dict) and "error" in result:
            compressed["error"] = result["error"]
        if isinstance(result, dict) and "status" in result:
            compressed["status"] = result["status"]
        report = CompactionReport(
            provider=self._fallback_provider(),
            original_chars=original_chars,
            compressed_chars=len(self._raw_payload_text(compressed)),
            changed=True,
            transforms_applied=["tool_result_summary"],
            policy={"mode": "single_tool_result"},
            warnings=warnings
            + (
                ["builtin provider unavailable; used heuristic fallback"]
                if self._uses_headroom()
                else []
            ),
        )
        return compressed, report

    def receipt_summary(self, tool_name: str, result: dict[str, object]) -> str:
        """Build a concise receipt summary for a tool result."""

        status = result.get("status") or ("error" if "error" in result else "success")
        body = stringify_json_value(result, max_chars=1200)
        return f"{tool_name} status={status}; {body}"

    def _summary(self, text: str, *, index: int) -> str:
        return "\n".join(
            [
                "[Compressed tool context]",
                f"message_index: {index}",
                f"summary: {summarize_text(text, max_chars=self.config.summary_chars)}",
            ]
        )

    def _oldest_removable_index(
        self, messages: list[ConversationMessage]
    ) -> int | None:
        for index, message in enumerate(messages):
            if message.role not in {"system", "developer", "user", "assistant"}:
                return index
        return None

    def _compress_messages_with_headroom(
        self, request: CompressionRequest, plan: CompressionPlan
    ) -> CompactionResult | None:
        if not plan.candidate_indexes:
            return None
        candidates = [request.messages[index] for index in plan.candidate_indexes]
        metadata = self._headroom_metadata(
            request.metadata,
            mode="model_context",
            token_budget=max(1, request.max_context_chars // 4),
        )
        result = self._headroom_provider().compress(
            CompressionRequest(
                messages=candidates,
                max_context_chars=request.max_context_chars,
                protected_message_count=0,
                metadata=metadata,
            )
        )
        if result is None or len(result.messages) != len(candidates):
            return None

        compressed = list(request.messages)
        for index, message in zip(plan.candidate_indexes, result.messages):
            compressed[index] = message

        omitted = 0
        while (
            self._messages_char_count(compressed) > request.max_context_chars
            and len(compressed) > request.protected_message_count
        ):
            removable = self._oldest_removable_index(compressed)
            if removable is None:
                break
            compressed.pop(removable)
            omitted += 1

        original_chars = self._messages_char_count(request.messages)
        compressed_chars = self._messages_char_count(compressed)
        warnings = list(result.report.warnings)
        if compressed_chars > request.max_context_chars:
            warnings.append("context still exceeds max_context_chars")
        transforms = list(result.report.transforms_applied)
        if "headroom_candidate_compression" not in transforms:
            transforms.append("headroom_candidate_compression")
        return CompactionResult(
            messages=compressed,
            report=result.report.model_copy(
                update={
                    "original_chars": original_chars,
                    "compressed_chars": compressed_chars,
                    "changed": compressed != request.messages,
                    "omitted_messages": omitted,
                    "protected_messages": len(
                        [item for item in plan.decisions if item.action == "protect"]
                    ),
                    "compression_ratio": (
                        compressed_chars / original_chars if original_chars else 1.0
                    ),
                    "transforms_applied": transforms,
                    "policy": plan.summary,
                    "warnings": warnings,
                }
            ),
        )

    def _compress_messages_with_builtin(
        self,
        request: CompressionRequest,
        plan: CompressionPlan,
        warnings: list[str],
    ) -> CompactionResult | None:
        if not plan.candidate_indexes:
            return None
        candidates = [request.messages[index] for index in plan.candidate_indexes]
        result = self.builtin.compress(
            CompressionRequest(
                messages=candidates,
                max_context_chars=request.max_context_chars,
                protected_message_count=0,
                metadata=request.metadata,
            )
        )
        if result is None or len(result.messages) != len(candidates):
            return None
        compressed = list(request.messages)
        for index, message in zip(plan.candidate_indexes, result.messages):
            compressed[index] = message
        original_chars = self._messages_char_count(request.messages)
        compressed_chars = self._messages_char_count(compressed)
        return CompactionResult(
            messages=compressed,
            report=result.report.model_copy(
                update={
                    "original_chars": original_chars,
                    "compressed_chars": compressed_chars,
                    "changed": compressed != request.messages,
                    "protected_messages": len(
                        [item for item in plan.decisions if item.action == "protect"]
                    ),
                    "compression_ratio": (
                        compressed_chars / original_chars if original_chars else 1.0
                    ),
                    "policy": plan.summary,
                    "warnings": list(warnings),
                }
            ),
        )

    def _compress_tool_result_with_headroom(
        self,
        *,
        result: object,
        original_text: str,
        original_chars: int,
    ) -> tuple[dict[str, object], CompactionReport] | None:
        metadata = self._headroom_metadata(
            {},
            mode="single_tool_result",
            token_budget=max(1, self.config.max_tool_result_chars // 4),
        )
        headroom_result = self._headroom_provider().compress(
            CompressionRequest(
                messages=[
                    ConversationMessage(
                        role="tool",
                        content=original_text,
                        metadata=coerce_json_object(result),
                    )
                ],
                max_context_chars=self.config.max_tool_result_chars,
                protected_message_count=0,
                metadata=metadata,
            )
        )
        if headroom_result is None or not headroom_result.messages:
            return None
        summary = headroom_result.messages[0].content
        if not summary or len(summary) >= original_chars:
            return None
        compressed: dict[str, object] = {
            "harness_compressed": True,
            "provider": "headroom",
            "summary": summary,
            "original_chars": original_chars,
        }
        if isinstance(result, dict) and "error" in result:
            compressed["error"] = result["error"]
        if isinstance(result, dict) and "status" in result:
            compressed["status"] = result["status"]
        compressed_chars = len(self._raw_payload_text(compressed))
        transforms = list(headroom_result.report.transforms_applied)
        if "headroom_tool_result_compression" not in transforms:
            transforms.append("headroom_tool_result_compression")
        report = headroom_result.report.model_copy(
            update={
                "original_chars": original_chars,
                "compressed_chars": compressed_chars,
                "changed": True,
                "compression_ratio": compressed_chars / original_chars,
                "transforms_applied": transforms,
                "policy": {"mode": "single_tool_result", "provider": "headroom"},
            }
        )
        return compressed, report

    def _compress_tool_result_with_builtin(
        self,
        *,
        result: object,
        original_text: str,
        original_chars: int,
        warnings: list[str],
    ) -> tuple[dict[str, object], CompactionReport] | None:
        builtin_result = self.builtin.compress(
            CompressionRequest(
                messages=[
                    ConversationMessage(
                        role="tool",
                        content=original_text,
                        metadata=coerce_json_object(result),
                    )
                ],
                max_context_chars=self.config.max_tool_result_chars,
                protected_message_count=0,
                metadata={},
            )
        )
        if builtin_result is None or not builtin_result.messages:
            return None
        summary = builtin_result.messages[0].content
        compressed: dict[str, object] = {
            "harness_compressed": True,
            "provider": "builtin",
            "summary": summary,
            "original_chars": original_chars,
        }
        if isinstance(result, dict) and "error" in result:
            compressed["error"] = result["error"]
        if isinstance(result, dict) and "status" in result:
            compressed["status"] = result["status"]
        compressed_chars = len(self._raw_payload_text(compressed))
        report = builtin_result.report.model_copy(
            update={
                "original_chars": original_chars,
                "compressed_chars": compressed_chars,
                "changed": True,
                "compression_ratio": compressed_chars / original_chars,
                "policy": {"mode": "single_tool_result", "provider": "builtin"},
                "warnings": list(warnings),
            }
        )
        return compressed, report

    def _messages_char_count(self, messages: list[ConversationMessage]) -> int:
        return sum(len(message.content) for message in messages)

    def _uses_headroom(self) -> bool:
        return self._provider_name() in {
            "headroom",
            "managed_compressor",
            "context_compressor",
        }

    def _uses_builtin_or_default(self) -> bool:
        return self._provider_name() in {"", "auto", "builtin", "built_in", "managed"}

    def _fallback_provider(self) -> str:
        return "heuristic"

    def _provider_name(self) -> str:
        return self.config.provider.strip().lower()

    def _headroom_provider(self) -> HeadroomCompressionProvider:
        if self._headroom is None:
            self._headroom = HeadroomCompressionProvider()
        return self._headroom

    def _headroom_metadata(
        self,
        metadata: JsonObject,
        *,
        mode: str,
        token_budget: int,
    ) -> JsonObject:
        merged = dict(metadata)
        merged.setdefault("compression_config", {"mode": mode})
        merged.setdefault("token_budget", token_budget)
        return merged

    def dict_to_message(
        self, role: str, payload: dict[str, object]
    ) -> ConversationMessage:
        """Convert a mapping into a message projection."""

        return ConversationMessage(
            role=role,
            content=stringify_json_value(payload),
            metadata=coerce_json_object(payload),
        )

    def _raw_payload_text(self, payload: object) -> str:
        try:
            return redact_text(json.dumps(payload, ensure_ascii=False, default=str))
        except TypeError:
            return redact_text(str(payload))


ToolResultCompressorConfig = ToolResultCompactorConfig
ContextCompressionPolicy = ContextCompactionPolicy
ToolResultCompressor = ToolResultCompactor

__all__ = [
    "DECISION_KEEP_REASON",
    "DECISION_SUMMARIZE_REASON",
    "ContextCompactionPolicy",
    "ContextCompressionPolicy",
    "ToolResultCompactor",
    "ToolResultCompactorConfig",
    "ToolResultCompressor",
    "ToolResultCompressorConfig",
]
