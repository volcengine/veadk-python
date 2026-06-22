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
from veadk.extensions.harness.utils import redact_text, summarize_text

_UNPARSED = object()
_MAX_FACTS = 80
_MAX_SEQUENCE_ITEMS = 12
_MAX_DEPTH = 8
_MAX_SCALAR_CHARS = 64
_MAX_FACT_CHARS = 600


class BuiltinCompressionProvider:
    """Compress tool outputs by preserving structured facts."""

    name = "builtin"

    def compress(self, request: CompressionRequest) -> CompactionResult | None:
        """Compress eligible tool messages with bounded fact extraction."""

        compressed: list[ConversationMessage] = []
        changed = False
        for message in request.messages:
            if message.role not in {"tool", "tool_result", "function"}:
                compressed.append(message)
                continue
            facts = _extract_tool_facts(
                message.content,
                max_chars=max(512, request.max_context_chars - 160),
            )
            if facts and len(facts) < len(message.content):
                compressed.append(
                    message.model_copy(
                        update={
                            "content": (
                                "COMPRESSED_TOOL_OUTPUT\n"
                                "structured_facts:\n"
                                f"{facts}\n"
                                "compression_policy=preserve_bounded_structured_facts"
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


def _extract_tool_facts(text: str, *, max_chars: int) -> str:
    parsed = _parse_json_text(text)
    if parsed is _UNPARSED:
        return ""
    facts: list[str] = []
    _collect_structured_facts(
        value=parsed,
        path="$",
        facts=facts,
        depth=0,
    )
    return _join_limited_facts(facts, max_chars=max_chars)


def _collect_structured_facts(
    *,
    value: object,
    path: str,
    facts: list[str],
    depth: int,
) -> None:
    if len(facts) >= _MAX_FACTS or depth > _MAX_DEPTH:
        return
    if isinstance(value, Mapping):
        _collect_mapping_facts(value=value, path=path, facts=facts, depth=depth)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        _collect_sequence_facts(value=value, path=path, facts=facts, depth=depth)
        return
    if _is_scalar(value):
        _append_fact(facts, f"{path}={_format_scalar(value)}")


def _collect_mapping_facts(
    *,
    value: Mapping[object, object],
    path: str,
    facts: list[str],
    depth: int,
) -> None:
    scalar_parts: list[str] = []
    nested_items: list[tuple[str, object]] = []
    for key, item in value.items():
        child_path = _child_path(path, key)
        parsed = _parse_json_text(item) if isinstance(item, str) else _UNPARSED
        if parsed is not _UNPARSED:
            nested_items.append((child_path, parsed))
        elif _is_scalar(item):
            scalar_parts.append(f"{_key_text(key)}={_format_scalar(item)}")
        else:
            nested_items.append((child_path, item))
    if scalar_parts:
        _append_fact(facts, f"{path}: {' '.join(scalar_parts)}")
    for child_path, item in nested_items:
        _collect_structured_facts(
            value=item,
            path=child_path,
            facts=facts,
            depth=depth + 1,
        )
        if len(facts) >= _MAX_FACTS:
            return


def _collect_sequence_facts(
    *,
    value: Sequence[object],
    path: str,
    facts: list[str],
    depth: int,
) -> None:
    indexes = _representative_indexes(len(value))
    for index in indexes:
        _collect_structured_facts(
            value=value[index],
            path=f"{path}[{index}]",
            facts=facts,
            depth=depth + 1,
        )
        if len(facts) >= _MAX_FACTS:
            return
    omitted = len(value) - len(indexes)
    if omitted > 0:
        _append_fact(facts, f"{path}: omitted_items={omitted}")


def _representative_indexes(size: int) -> list[int]:
    if size <= _MAX_SEQUENCE_ITEMS:
        return list(range(size))
    head_count = max(1, _MAX_SEQUENCE_ITEMS - 2)
    tail_indexes = range(max(head_count, size - 2), size)
    return sorted({*range(head_count), *tail_indexes})


def _parse_json_text(value: str) -> object:
    stripped = value.strip()
    if not stripped or stripped[0] not in "[{":
        return _UNPARSED
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return _UNPARSED


def _is_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _child_path(parent: str, key: object) -> str:
    key_text = _key_text(key)
    if parent == "$":
        return f"$.{key_text}"
    return f"{parent}.{key_text}"


def _key_text(key: object) -> str:
    text = summarize_text(str(key), max_chars=80).replace("\n", " ").strip()
    return text or "<empty>"


def _format_scalar(value: object) -> str:
    if value is None or isinstance(value, (int, float, bool)):
        return json.dumps(value, ensure_ascii=False)
    text = redact_text(str(value))
    normalized = " ".join(text.split())
    if len(normalized) > _MAX_SCALAR_CHARS:
        return f"<text chars={len(normalized)}>"
    if not normalized:
        return '""'
    if any(char.isspace() for char in normalized) or "=" in normalized:
        return json.dumps(normalized, ensure_ascii=False)
    return normalized


def _append_fact(facts: list[str], fact: str) -> None:
    if len(facts) >= _MAX_FACTS:
        return
    normalized = summarize_text(redact_text(fact), max_chars=_MAX_FACT_CHARS)
    if normalized and normalized not in facts:
        facts.append(normalized)


def _join_limited_facts(facts: list[str], *, max_chars: int) -> str:
    lines: list[str] = []
    current_chars = 0
    for fact in facts:
        next_chars = len(fact) + (1 if lines else 0)
        if current_chars + next_chars > max_chars:
            omitted = len(facts) - len(lines)
            if omitted > 0:
                lines.append(f"... omitted_facts={omitted}")
            break
        lines.append(fact)
        current_chars += next_chars
    return "\n".join(lines)


def _extract_facts_from_value(value: object) -> str:
    """Backward-compatible private helper for older tests and callers."""

    facts: list[str] = []
    _collect_structured_facts(value=value, path="$", facts=facts, depth=0)
    return _join_limited_facts(facts, max_chars=24000)
