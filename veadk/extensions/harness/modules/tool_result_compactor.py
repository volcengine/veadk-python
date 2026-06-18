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

from veadk.extensions.harness.modules.builtin_provider import BuiltinCompressionProvider
from veadk.extensions.harness.modules.headroom_provider import (
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


class ToolResultCompactorConfig(HarnessBaseModel):
    """Settings for tool-result compaction."""

    provider: str = "builtin"
    max_context_chars: int = 24000
    max_tool_result_chars: int = 4000
    min_candidate_chars: int = 4000
    protect_recent_messages: int = 2
    summary_chars: int = 900


class ContextCompactionPolicy:
    """Select safe historical context for compaction."""

    def __init__(self, config: ToolResultCompactorConfig | None = None) -> None:
        self.config = config or ToolResultCompactorConfig()

    def plan(self, messages: list[ConversationMessage]) -> CompressionPlan:
        decisions = [
            self._classify(index=index, total=len(messages), message=message)
            for index, message in enumerate(messages)
        ]
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
        return CompressionPlan(
            decisions=decisions,
            candidate_indexes=candidate_indexes,
            summary=summary,
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

    def __init__(self, config: ToolResultCompactorConfig | None = None) -> None:
        self.config = config or ToolResultCompactorConfig()
        self.policy = ContextCompactionPolicy(self.config)
        self.builtin = BuiltinCompressionProvider()
        self._headroom: HeadroomCompressionProvider | None = None

    def compress_messages(self, request: CompressionRequest) -> CompactionResult:
        """Compact candidate messages while preserving control-plane messages."""

        original_chars = self._messages_char_count(request.messages)
        if original_chars <= request.max_context_chars:
            return CompactionResult(
                messages=list(request.messages),
                report=CompactionReport(
                    provider=self.config.provider,
                    original_chars=original_chars,
                    compressed_chars=original_chars,
                    changed=False,
                ),
            )

        plan = self.policy.plan(request.messages)
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
    "ContextCompactionPolicy",
    "ContextCompressionPolicy",
    "ToolResultCompactor",
    "ToolResultCompactorConfig",
    "ToolResultCompressor",
    "ToolResultCompressorConfig",
]
