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

"""Bounded, redacted diagnostics safe for TOS persistence and the Studio UI."""

from __future__ import annotations

import re
from collections.abc import Iterable

_MAX_DIAGNOSTIC_CHARS = 4_000
_SECRET_NAMES = (
    r"authorization|api[_-]?key|access[_-]?key|secret(?:[_-]?key)?|"
    r"session[_-]?token|token|cookie"
)
_QUOTED_SECRET_ASSIGNMENT = re.compile(
    rf"(?i)([\"'](?:{_SECRET_NAMES})[\"']\s*:\s*)([\"'])(.*?)(\2)"
)
_SECRET_ASSIGNMENT = re.compile(rf"(?i)\b({_SECRET_NAMES})\b(\s*[:=]\s*)([^\s,;]+)")
_BEARER_TOKEN = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT_TOKEN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"
)


def sanitize_diagnostic(
    value: object,
    *,
    secrets: Iterable[str] = (),
    limit: int = _MAX_DIAGNOSTIC_CHARS,
) -> str:
    """Return one readable diagnostic without credentials or unbounded payloads."""
    text = str(value or "").replace("\x00", "").strip()
    for secret in secrets:
        if secret:
            text = text.replace(str(secret), "[REDACTED]")
    text = _BEARER_TOKEN.sub("Bearer [REDACTED]", text)
    text = _JWT_TOKEN.sub("[REDACTED]", text)
    text = _QUOTED_SECRET_ASSIGNMENT.sub(
        lambda match: (f"{match.group(1)}{match.group(2)}[REDACTED]{match.group(4)}"),
        text,
    )
    text = _SECRET_ASSIGNMENT.sub(
        lambda match: f"{match.group(1)}{match.group(2)}[REDACTED]",
        text,
    )
    if len(text) > limit:
        text = f"{text[:limit].rstrip()}\n[truncated]"
    return text


__all__ = ["sanitize_diagnostic"]
