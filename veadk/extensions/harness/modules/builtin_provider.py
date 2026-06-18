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

"""Built-in loss-aware compression provider."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from veadk.extensions.harness.schemas import (
    CompactionReport,
    CompressionRequest,
    CompactionResult,
    ConversationMessage,
)


class BuiltinCompressionProvider:
    """Compress tool outputs by preserving structured facts."""

    name = "builtin"

    def compress(self, request: CompressionRequest) -> CompactionResult | None:
        """Compress eligible tool messages with built-in fact extraction."""

        compressed: list[ConversationMessage] = []
        changed = False
        for message in request.messages:
            if message.role not in {"tool", "tool_result", "function"}:
                compressed.append(message)
                continue
            facts = _extract_tool_facts(message.content)
            if facts and len(facts) < len(message.content):
                compressed.append(
                    message.model_copy(
                        update={
                            "content": (
                                "COMPRESSED_TOOL_OUTPUT\n"
                                "lossless_facts:\n"
                                f"{facts}\n"
                                "compression_policy=preserve_metric_rows_and_tool_identity"
                            )
                        }
                    )
                )
                changed = True
            else:
                compressed.append(message)
        if not changed:
            return None
        original_chars = _messages_char_count(request.messages)
        compressed_chars = _messages_char_count(compressed)
        return CompactionResult(
            messages=compressed,
            report=CompactionReport(
                provider=self.name,
                original_chars=original_chars,
                compressed_chars=compressed_chars,
                changed=True,
                tokens_before=max(1, original_chars // 4),
                tokens_after=max(1, compressed_chars // 4),
                tokens_saved=max(0, original_chars // 4 - compressed_chars // 4),
                compression_ratio=compressed_chars / max(1, original_chars),
                transforms_applied=["builtin_tool_fact_compaction"],
            ),
        )


def _messages_char_count(messages: list[ConversationMessage]) -> int:
    return sum(len(message.content) for message in messages)


def _extract_tool_facts(text: str) -> str:
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return ""
    return _extract_facts_from_value(parsed)


def _extract_facts_from_value(value: object) -> str:
    facts: list[str] = []
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for item in value:
            if isinstance(item, Mapping):
                row = _extract_metric_row(item)
                if row:
                    facts.append(row)
    elif isinstance(value, Mapping):
        row = _extract_metric_row(value)
        if row:
            facts.append(row)
        facts.extend(_extract_nested_output_facts(value))
        for nested_key in (
            "metric_rows",
            "metrics",
            "rows",
            "data",
            "result",
            "stdout",
            "output",
        ):
            nested = value.get(nested_key)
            if nested is value:
                continue
            nested_facts = _extract_facts_from_value(nested)
            if nested_facts:
                facts.append(nested_facts)
    elif isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return ""
        if parsed is value:
            return ""
        return _extract_facts_from_value(parsed)
    return "\n".join(dict.fromkeys(facts))


def _extract_nested_output_facts(item: Mapping[object, object]) -> list[str]:
    facts: list[str] = []
    output_candidates: list[object] = []
    data = item.get("data")
    if isinstance(data, Mapping):
        outputs = data.get("outputs")
        if isinstance(outputs, Sequence) and not isinstance(
            outputs, (str, bytes, bytearray)
        ):
            output_candidates.extend(outputs)
    outputs = item.get("outputs")
    if isinstance(outputs, Sequence) and not isinstance(
        outputs, (str, bytes, bytearray)
    ):
        output_candidates.extend(outputs)
    for key in ("stdout", "output", "text", "result"):
        value = item.get(key)
        if isinstance(value, str):
            output_candidates.append({"text": value})
    for output in output_candidates:
        text = _output_text(output)
        if not text:
            continue
        try:
            nested = json.loads(text)
        except json.JSONDecodeError:
            continue
        nested_facts = _extract_facts_from_value(nested)
        if nested_facts:
            facts.append(nested_facts)
    return facts


def _output_text(output: object) -> str:
    if isinstance(output, Mapping):
        for key in ("text", "data", "output"):
            value = output.get(key)
            if isinstance(value, str):
                return value
        return ""
    return output if isinstance(output, str) else ""


def _extract_metric_row(item: Mapping[object, object]) -> str:
    kind = item.get("kind")
    if isinstance(kind, str) and kind.lower() != "metric":
        return ""
    keys = {str(key).lower() for key in item}
    if not ({"model", "accuracy"} <= keys or {"name", "score"} <= keys):
        return ""
    ordered_keys = (
        "model",
        "name",
        "accuracy",
        "score",
        "ner_f1",
        "latency_ms",
        "latency",
        "rank",
    )
    parts: list[str] = []
    seen: set[str] = set()
    normalized = {str(key): value for key, value in item.items()}
    for key in ordered_keys:
        if key in normalized:
            parts.append(f"{key}={normalized[key]}")
            seen.add(key)
    for key in sorted(normalized):
        if key in seen or key == "kind":
            continue
        value = normalized[key]
        if value is None or isinstance(value, (str, int, float, bool)):
            parts.append(f"{key}={value}")
    return " ".join(parts)
