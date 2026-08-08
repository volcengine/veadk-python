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

"""User-selectable generation styles kept separate from Session orchestration."""

from __future__ import annotations

from typing import Final

STYLE_PRESETS: Final[dict[str, str]] = {
    "concise": "Keep the Skill concise and practical. Prefer short, directly actionable instructions.",
    "strict": "Prioritize robust constraints, explicit validation, safe failure modes, and edge cases.",
    "tutorial": "Make the Skill tutorial-friendly with clear sequencing and small concrete examples.",
    "automation": "Optimize for repeatable automation, deterministic steps, and minimal manual intervention.",
}


def style_instruction(style: str | None) -> str:
    value = (style or "").strip()
    if not value:
        return STYLE_PRESETS["concise"]
    return STYLE_PRESETS.get(value, value[:2_000])


def decorate_intent(intent: str, *, style: str | None, name: str | None) -> str:
    sections = [intent.strip()]
    normalized_name = (name or "").strip()
    if normalized_name:
        sections.append(
            f"Use `{normalized_name}` as the Skill name unless it violates the Skill format."
        )
    sections.append(f"Writing style: {style_instruction(style)}")
    return "\n\n".join(sections)


__all__ = ["STYLE_PRESETS", "decorate_intent", "style_instruction"]
