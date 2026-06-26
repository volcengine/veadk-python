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

"""Small text helpers used by Harness modules."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from veadk.extensions.harness.schemas import JsonObject, JsonValue

_SECRET_PATTERNS = (
    re.compile(r"(?i)(authorization\s*[:=]\s*bearer\s+)[^\s,;]+"),
    re.compile(r"(?i)((?:api[_-]?key|secret|token|password)\s*[:=]\s*)[^\s,;]+"),
    re.compile(r"(?i)((?:access[_-]?key|secret[_-]?key)\s*[:=]\s*)[^\s,;]+"),
)


def summarize_text(text: str, *, max_chars: int = 900) -> str:
    """Return a compact single-string summary without model calls."""

    normalized = " ".join(text.split())
    if len(normalized) <= max_chars:
        return normalized
    head = normalized[: max_chars // 2].rstrip()
    tail = normalized[-max_chars // 3 :].lstrip()
    omitted = len(normalized) - len(head) - len(tail)
    return f"{head} ... [omitted {omitted} chars] ... {tail}"


def redact_text(text: str) -> str:
    """Mask common credential shapes in traces and receipts."""

    redacted = text
    for pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(r"\1[REDACTED]", redacted)
    return redacted


def stringify_json_value(value: object, *, max_chars: int = 4000) -> str:
    """Render dynamic values for receipts without leaking huge payloads."""

    if isinstance(value, str):
        return summarize_text(redact_text(value), max_chars=max_chars)
    if isinstance(value, Mapping):
        parts = []
        for key, item in value.items():
            parts.append(f"{key}: {stringify_json_value(item, max_chars=400)}")
        return summarize_text(redact_text("; ".join(parts)), max_chars=max_chars)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        parts = [stringify_json_value(item, max_chars=300) for item in value[:20]]
        return summarize_text(redact_text("; ".join(parts)), max_chars=max_chars)
    return summarize_text(redact_text(str(value)), max_chars=max_chars)


def coerce_json_value(value: object) -> JsonValue:
    """Convert a Python object into the SDK's JSON-safe value type."""

    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [coerce_json_value(item) for item in value]
    return str(value)


def coerce_json_object(value: object) -> JsonObject:
    """Convert a mapping-like object into a JSON object."""

    if not isinstance(value, Mapping):
        return {}
    return {str(key): coerce_json_value(item) for key, item in value.items()}
