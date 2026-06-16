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

"""Minimal ContextEngine example.

The implementation keeps only the primitives that matter for developer-facing
usage: a pinned task contract, a filtered history projection, an evidence-first
context header, and a small budget report.
"""

from __future__ import annotations

import hashlib
import re
from typing import Protocol

from .core import (
    AcceptanceCriterion,
    CapabilityReceipt,
    HarnessBudgetReport,
    HarnessContext,
    HarnessEvent,
    JSONDict,
    TaskContract,
    summarize_text,
)


class ContextEngineStoreProtocol(Protocol):
    def load_messages(
        self, session_id: str, *, limit: int | None = None
    ) -> list[JSONDict]: ...

    def load_receipts(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> list[CapabilityReceipt]: ...

    def append_event(self, event: HarnessEvent) -> None: ...


CONTROL_MARKERS = (
    "[progress]",
    "[debug]",
    "[trace]",
    "progress:",
    "debug:",
    "trace:",
)

FOLLOW_UP_MARKERS = (
    "继续",
    "刚才",
    "上面",
    "前面",
    "这个",
    "那个",
    "它",
    "按刚才",
    "same format",
    "continue",
    "that",
    "it",
    "previous",
)

CLARIFICATION_MARKERS = (
    "是",
    "不是",
    "可以",
    "不可以",
    "确认",
    "选",
    "yes",
    "no",
    "ok",
)

META_MARKERS = (
    "你是谁",
    "你能做什么",
    "帮助",
    "help",
    "who are you",
)

EXTERNAL_FACT_MARKERS = (
    "最新",
    "最近",
    "当前",
    "今天",
    "今年",
    "价格",
    "政策",
    "来源",
    "出处",
    "引用",
    "数据",
    "统计",
    "发布",
    "current",
    "latest",
    "recent",
    "today",
    "price",
    "policy",
    "source",
    "citation",
    "data",
    "release",
)

OUTPUT_FORMAT_MARKERS = (
    "表格",
    "json",
    "markdown",
    "清单",
    "列表",
    "要点",
    "table",
    "list",
    "bullet",
)


def estimate_tokens(text: str) -> int:
    """Rough CJK-aware token estimator for budget reporting."""

    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    non_cjk = re.sub(r"[\u4e00-\u9fff]", " ", text)
    wordish = len(re.findall(r"[A-Za-z0-9_./:-]+", non_cjk))
    punctuation = max(
        0, len(non_cjk) - sum(len(m) for m in re.findall(r"[A-Za-z0-9_./:-]+", non_cjk))
    )
    return max(1, int(cjk * 0.8 + wordish * 1.3 + punctuation * 0.15))


def has_external_fact_markers(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in EXTERNAL_FACT_MARKERS)


def has_output_format_markers(text: str) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in OUTPUT_FORMAT_MARKERS)


class ContextEngine:
    """Small context engineering module for veADK examples."""

    def __init__(
        self,
        *,
        store: ContextEngineStoreProtocol | None = None,
        max_history_messages: int = 6,
        max_context_chars: int = 6000,
        evidence_first: bool = True,
    ) -> None:
        self.store = store
        self.max_history_messages = max_history_messages
        self.max_context_chars = max_context_chars
        self.evidence_first = evidence_first

    def wrap_instruction(self, base_instruction: str) -> str:
        """Add a stable protocol so the model knows how to use context headers."""

        return (
            f"{base_instruction.rstrip()}\n\n"
            "Harness context protocol:\n"
            "- Treat the [Harness Context] block in the user message as pinned runtime context.\n"
            "- Preserve the task anchor and acceptance criteria across follow-up turns.\n"
            "- Prefer cited tool evidence over memory or unsupported assumptions.\n"
            "- If evidence is missing for an external factual claim, say what is missing instead of inventing a source."
        )

    def classify_turn(self, prompt: str, history: list[JSONDict] | None = None) -> str:
        lowered = prompt.strip().lower()
        history = history or []
        if any(marker in lowered for marker in META_MARKERS):
            return "conversation_meta"
        if (
            history
            and len(lowered) <= 12
            and any(lowered.startswith(marker) for marker in CLARIFICATION_MARKERS)
        ):
            return "clarification_answer"
        if history and any(marker in lowered for marker in FOLLOW_UP_MARKERS):
            return "follow_up"
        return "new_task"

    def build_acceptance(self, prompt: str) -> list[AcceptanceCriterion]:
        criteria = [
            AcceptanceCriterion(
                id="AC-final-answer",
                description="Return a non-empty final answer that addresses the user request.",
            )
        ]
        if has_external_fact_markers(prompt):
            criteria.append(
                AcceptanceCriterion(
                    id="AC-grounded-facts",
                    description="External or current factual claims must be grounded in tool evidence or cited sources.",
                )
            )
        if has_output_format_markers(prompt):
            criteria.append(
                AcceptanceCriterion(
                    id="AC-output-format",
                    description="Respect the requested output format.",
                )
            )
        return criteria

    def prepare_context(self, context: HarnessContext) -> HarnessContext:
        history = []
        receipts = []
        if self.store is not None:
            history = self.store.load_messages(context.session_id)
            receipts = self.store.load_receipts(session_id=context.session_id)

        turn_type = self.classify_turn(context.original_prompt, history)
        anchor_prompt = context.original_prompt
        if turn_type in {"follow_up", "clarification_answer"}:
            first_user_message = next(
                (
                    item
                    for item in history
                    if item.get("role") == "user"
                    and not self._is_control_message(
                        str(item.get("content", "")),
                        item.get("metadata")
                        if isinstance(item.get("metadata"), dict)
                        else {},
                    )
                ),
                None,
            )
            if first_user_message:
                anchor_prompt = str(first_user_message.get("content", ""))

        task_id = "task-" + hashlib.sha1(anchor_prompt.encode("utf-8")).hexdigest()[:12]
        acceptance_prompt = f"{anchor_prompt}\n{context.original_prompt}"
        context.turn_type = turn_type
        context.task_contract = TaskContract(
            task_id=task_id,
            original_prompt=anchor_prompt,
            turn_type=turn_type,
            acceptance=self.build_acceptance(acceptance_prompt),
            metadata={"current_prompt": context.original_prompt},
        )
        context.history_projection = self.project_history(history)
        context.receipts = receipts

        if self.store is not None:
            self.store.append_event(
                HarnessEvent(
                    event_type="context.prepared",
                    session_id=context.session_id,
                    run_id=context.run_id,
                    payload={
                        "turn_type": turn_type,
                        "task_id": task_id,
                        "history_count": len(context.history_projection),
                    },
                )
            )

        return context

    def project_history(self, history: list[JSONDict]) -> list[JSONDict]:
        projected: list[JSONDict] = []
        for item in history:
            role = item.get("role")
            content = str(item.get("content") or "")
            raw_metadata = item.get("metadata")
            metadata = raw_metadata if isinstance(raw_metadata, dict) else {}
            if role not in {"user", "assistant"}:
                continue
            if self._is_control_message(content, metadata):
                continue
            projected.append(
                {
                    "role": role,
                    "content": summarize_text(content, max_chars=700),
                    "run_id": item.get("run_id", ""),
                }
            )
        return projected[-self.max_history_messages :]

    def build_context_header(
        self,
        *,
        context: HarnessContext,
        receipts: list[CapabilityReceipt] | None = None,
    ) -> str:
        if context.task_contract is None:
            context = self.prepare_context(context)

        receipts = receipts if receipts is not None else context.receipts
        task = context.task_contract
        assert task is not None

        fixed_lines = [
            "[Harness Context]",
            "Task anchor:",
            f"- task_id: {task.task_id}",
            f"- session_id: {context.session_id}",
            f"- turn_type: {context.turn_type}",
            f"- original_task: {task.original_prompt}",
            "",
            "Acceptance criteria:",
        ]
        fixed_lines.extend(
            f"- {criterion.id}: {criterion.description}"
            for criterion in task.acceptance
        )

        evidence_lines = self._build_evidence_lines(receipts)
        history_lines = self._build_history_lines(context.history_projection)

        ordered_variable = (
            evidence_lines + history_lines
            if self.evidence_first
            else history_lines + evidence_lines
        )
        variable_lines = list(ordered_variable)
        omitted_count = 0
        truncated = False

        def render(lines: list[str]) -> str:
            text = "\n".join(fixed_lines + [""] + lines + ["[/Harness Context]"])
            return text.strip()

        header = render(variable_lines)
        while len(header) > self.max_context_chars and variable_lines:
            truncated = True
            omitted_count += 1
            self._drop_low_value_line(variable_lines)
            header = render(variable_lines)

        context.budget = HarnessBudgetReport(
            estimated_tokens=estimate_tokens(header),
            max_context_chars=self.max_context_chars,
            truncated=truncated,
            omitted_count=omitted_count,
            kept_history_count=sum(
                1 for line in variable_lines if line.startswith("- history")
            ),
        )

        if self.store is not None:
            self.store.append_event(
                HarnessEvent(
                    event_type="context.assembled",
                    session_id=context.session_id,
                    run_id=context.run_id,
                    payload={
                        "estimated_tokens": context.budget.estimated_tokens,
                        "truncated": context.budget.truncated,
                        "omitted_count": context.budget.omitted_count,
                    },
                )
            )

        return header

    def build_user_prompt(self, *, context: HarnessContext, user_prompt: str) -> str:
        header = self.build_context_header(context=context)
        return f"{header}\n\n[User Request]\n{user_prompt}"

    def _build_history_lines(self, history_projection: list[JSONDict]) -> list[str]:
        if not history_projection:
            return ["Recent session history:", "- history: <none>"]

        lines = ["Recent session history:"]
        for idx, item in enumerate(history_projection, start=1):
            role = item.get("role", "unknown")
            content = item.get("content", "")
            lines.append(f"- history[{idx}] {role}: {content}")
        return lines

    def _build_evidence_lines(self, receipts: list[CapabilityReceipt]) -> list[str]:
        if not receipts:
            return ["Evidence preview:", "- evidence: <none>"]

        lines = ["Evidence preview:"]
        for receipt in receipts[-4:]:
            refs = getattr(receipt, "evidence_refs", []) or []
            ref_ids = ", ".join(ref.ref_id for ref in refs) or "no-ref"
            tool_name = getattr(receipt, "tool_name", "tool")
            summary = getattr(receipt, "result_summary", "")
            lines.append(f"- evidence {tool_name} [{ref_ids}]: {summary}")
        return lines

    def _drop_low_value_line(self, lines: list[str]) -> None:
        for idx, line in enumerate(lines):
            if line.startswith("- history"):
                del lines[idx]
                return
        del lines[-1]

    def _is_control_message(self, content: str, metadata: JSONDict) -> bool:
        if metadata.get("control"):
            return True
        lowered = content.strip().lower()
        return lowered.startswith(CONTROL_MARKERS)
