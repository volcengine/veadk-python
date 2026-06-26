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

"""Invocation context preparation module."""

from __future__ import annotations

from pydantic import Field

from veadk.extensions.harness.schemas import (
    ToolReceipt,
    InvocationContextBlock,
    ConversationMessage,
    HarnessBaseModel,
    HarnessInvocationRef,
)
from veadk.extensions.harness.utils import summarize_text


class HarnessInvocationContextConfig(HarnessBaseModel):
    """Settings for invocation context generation."""

    max_history_messages: int = 12
    max_context_chars: int = 24000
    max_receipts: int = 8
    history_message_chars: int = 500
    receipt_summary_chars: int = 500
    include_history: bool = True
    include_receipts: bool = True
    precision_markers: list[str] = Field(
        default_factory=lambda: [
            ".csv",
            "ranking",
            "top ",
            "filter",
            "outlier",
            "percentage",
            "selector",
            "sort",
            "threshold",
            "日志",
            "排序",
            "筛选",
        ]
    )
    artifact_markers: list[str] = Field(
        default_factory=lambda: [
            "file",
            "artifact",
            "chart",
            "plot",
            "graph",
            "dashboard",
            "report",
            "图表",
            "文件",
            "报告",
        ]
    )


class HarnessInvocationContextBuilder:
    """Build compact invocation context for an Agent turn."""

    def __init__(self, config: HarnessInvocationContextConfig | None = None) -> None:
        self.config = config or HarnessInvocationContextConfig()

    def prepare_context(
        self,
        context: HarnessInvocationRef,
        *,
        user_input: str = "",
        history: list[ConversationMessage] | None = None,
        receipts: list[ToolReceipt] | None = None,
        has_tools: bool = False,
    ) -> InvocationContextBlock:
        """Create an invocation context block for a model call."""

        history = history or []
        receipts = receipts or []
        header = self.build_context_header(
            context=context,
            user_input=user_input,
            history=history,
            receipts=receipts,
            has_tools=has_tools,
        )
        original_chars = sum(len(message.content) for message in history)
        if len(header) > self.config.max_context_chars:
            header = summarize_text(header, max_chars=self.config.max_context_chars)
        return InvocationContextBlock(
            header=header,
            messages=history[-self.config.max_history_messages :],
            original_chars=original_chars,
            context_chars=len(header),
            injected=bool(header.strip()),
        )

    def build_context_header(
        self,
        *,
        context: HarnessInvocationRef,
        user_input: str = "",
        history: list[ConversationMessage] | None = None,
        receipts: list[ToolReceipt] | None = None,
        has_tools: bool = False,
    ) -> str:
        """Build the plain-text Harness Context block."""

        task_goal = context.task.goal if context.task else user_input
        acceptance = context.task.acceptance_criteria if context.task else []
        lines = [
            "[Harness Context]",
            f"profile: {context.profile}",
            f"session_id: {context.session_id}",
            f"task_goal: {task_goal or user_input}",
            "acceptance:",
        ]
        if acceptance:
            lines.extend(f"- {item}" for item in acceptance)
        else:
            lines.extend(
                [
                    "- Stay anchored to the current user goal.",
                    "- Preserve exact filenames, schemas, numbers, and dates.",
                    "- Verify tool-backed claims before presenting completion.",
                ]
            )

        recent = (history or [])[-self.config.max_history_messages :]
        if self.config.include_history and recent:
            lines.append("recent_history:")
            for message in recent:
                text = summarize_text(
                    message.content, max_chars=self.config.history_message_chars
                )
                lines.append(f"- {message.role}: {text}")

        if self.config.include_receipts and receipts:
            lines.append("capability_receipts:")
            for receipt in receipts[-self.config.max_receipts :]:
                summary = summarize_text(
                    receipt.summary, max_chars=self.config.receipt_summary_chars
                )
                lines.append(f"- {receipt.name} [{receipt.status}]: {summary}")

        mode_header = self._build_mode_header(
            user_input=user_input, has_tools=has_tools
        )
        if mode_header:
            lines.extend(["", mode_header])
        lines.append("[/Harness Context]")
        return "\n".join(lines)

    def enhance_messages(
        self,
        messages: list[ConversationMessage],
        context: HarnessInvocationRef,
        *,
        user_input: str = "",
        receipts: list[ToolReceipt] | None = None,
        has_tools: bool = False,
    ) -> tuple[list[ConversationMessage], InvocationContextBlock]:
        """Return messages with a Harness context message inserted."""

        bundle = self.prepare_context(
            context,
            user_input=user_input,
            history=messages,
            receipts=receipts,
            has_tools=has_tools,
        )
        if not bundle.header:
            return messages, bundle

        insert_at = 0
        for index, message in enumerate(messages):
            if message.role in {"system", "developer"}:
                insert_at = index + 1
        injected = ConversationMessage(
            role="system",
            name="veadk_harness_context",
            content=bundle.header,
        )
        return messages[:insert_at] + [injected] + messages[insert_at:], bundle

    def _build_mode_header(self, *, user_input: str, has_tools: bool) -> str:
        lowered = user_input.lower()
        blocks = []
        if any(marker in lowered for marker in self.config.precision_markers):
            blocks.append(
                "\n".join(
                    [
                        "[Harness Precision Mode]",
                        "- Treat selectors, schemas, dates, counts, and numeric thresholds as exact requirements.",
                        "- Prefer deterministic parsing or tool checks over unsupported estimates.",
                        "[/Harness Precision Mode]",
                    ]
                )
            )
        if any(marker in lowered for marker in self.config.artifact_markers):
            blocks.append(
                "\n".join(
                    [
                        "[Harness Artifact Mode]",
                        "- Create the requested artifact before claiming completion.",
                        "- Verify the artifact exists and is non-empty when tools are available.",
                        "[/Harness Artifact Mode]",
                    ]
                )
            )
        if has_tools:
            blocks.append(
                "\n".join(
                    [
                        "[Harness Tool Protocol]",
                        "- Emit tool calls with complete, valid JSON object arguments as required by the runtime.",
                        "- Do not truncate code, paths, strings, or JSON values inside tool arguments.",
                        "- If a tool fails, use the failure as evidence and choose a different path when possible.",
                        "[/Harness Tool Protocol]",
                    ]
                )
            )
        return "\n\n".join(blocks)


ContextEngineConfig = HarnessInvocationContextConfig
ContextEngine = HarnessInvocationContextBuilder

__all__ = [
    "ContextEngine",
    "ContextEngineConfig",
    "HarnessInvocationContextBuilder",
    "HarnessInvocationContextConfig",
]
