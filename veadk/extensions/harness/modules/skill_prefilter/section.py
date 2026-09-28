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

"""Reading and rewriting the skill list an agent advertises to its model.

The skills callback describes every loaded skill in the agent instruction, so a
large library spends prompt budget on skills the current request will never use.
This module owns the only part of that text a prefilter may change: the
advertised entries themselves. The header, the checklist note, the tool hint and
any block appended later are preserved exactly as they were.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass

#: 技能列表的标题行，与 skills 回调写出的格式一致。
SKILL_SECTION_HEADER = "You have the following skills:"

_NAME_PREFIX = "- name: "
_DESCRIPTION_PREFIX = "- description: "


@dataclass(frozen=True)
class AdvertisedSkill:
    """One ``- name:`` / ``- description:`` entry of the advertised list."""

    name: str
    description: str
    #: 该条目的原文，重写时按原样放回。
    block: str


@dataclass(frozen=True)
class AdvertisedSkills:
    """The advertised skill list found in one system instruction.

    ``prefix`` ends right before the first entry and ``suffix`` starts right
    after the last one, so ``prefix + blocks + suffix`` reproduces the original
    text when no entry is dropped.
    """

    entries: tuple[AdvertisedSkill, ...]
    prefix: str
    suffix: str

    @property
    def names(self) -> tuple[str, ...]:
        """Advertised skill names, in the order the model reads them."""
        return tuple(entry.name for entry in self.entries)

    @property
    def descriptions(self) -> dict[str, str]:
        """Advertised skill descriptions, keyed by name."""
        return {entry.name: entry.description for entry in self.entries}

    def render(self) -> str:
        """Return the instruction text this list was parsed from."""
        return (
            self.prefix + "".join(entry.block for entry in self.entries) + self.suffix
        )


def parse_advertised_skills(text: str) -> AdvertisedSkills | None:
    """Return the advertised skill list of ``text``, or ``None``.

    ``None`` means the text does not carry a list in the documented shape, and
    callers must then leave the instruction alone instead of guessing.
    """
    body_start = _body_start(text)
    if body_start is None:
        return None
    entries: list[AdvertisedSkill] = []
    cursor = body_start
    while True:
        spans, paragraph_end = _paragraph_spans(text, cursor)
        entry = _read_entry(text, cursor, paragraph_end, spans)
        if entry is None:
            break
        entries.append(entry)
        cursor = paragraph_end
    if not entries:
        return None
    return AdvertisedSkills(
        entries=tuple(entries),
        prefix=text[:body_start],
        suffix=text[cursor:],
    )


def apply_skill_selection(
    advertised: AdvertisedSkills, keep: Collection[str]
) -> tuple[str, tuple[str, ...]]:
    """Advertise only ``keep`` and report which skills were dropped.

    Returns the original text and an empty tuple when there is nothing to drop
    or when the selection would drop every skill: a request that hides the whole
    library is indistinguishable from having no skills at all, so an empty
    selection keeps the list and lets the model decide.
    """
    kept = [entry for entry in advertised.entries if entry.name in keep]
    dropped = tuple(
        entry.name for entry in advertised.entries if entry.name not in keep
    )
    if not dropped or not kept:
        return advertised.render(), ()
    note = (
        f"- note: {len(dropped)} of {len(advertised.entries)} skills are not "
        "listed for this request; ask for the full list if the task changes.\n"
    )
    body = "".join(entry.block for entry in kept)
    return advertised.prefix + body + note + advertised.suffix, dropped


def _body_start(text: str) -> int | None:
    """Return the offset right after the skill-list header line."""
    header_at = text.find(SKILL_SECTION_HEADER)
    if header_at < 0:
        return None
    line_end = text.find("\n", header_at)
    return len(text) if line_end < 0 else line_end + 1


def _read_entry(
    text: str, start: int, end: int, spans: list[tuple[str, int]]
) -> AdvertisedSkill | None:
    """Read the entry at ``start``, or ``None`` when none begins there."""
    if len(spans) < 2:
        return None
    name_line, description_line = spans[0][0], spans[1][0]
    if not name_line.startswith(_NAME_PREFIX):
        return None
    if not description_line.startswith(_DESCRIPTION_PREFIX):
        return None
    name = name_line[len(_NAME_PREFIX) :].strip()
    if not name:
        return None
    description = "\n".join(
        [description_line[len(_DESCRIPTION_PREFIX) :].strip()]
        + [line.strip() for line, _ in spans[2:]]
    ).strip()
    return AdvertisedSkill(
        name=name,
        description=description,
        block=text[start:end],
    )


def _paragraph_spans(text: str, start: int) -> tuple[list[tuple[str, int]], int]:
    """Return the lines of the paragraph at ``start`` and the offset after it.

    The returned offset includes the blank line that ends the paragraph, so the
    caller walks paragraphs without losing the separators between them. A
    description containing a blank line therefore ends its own paragraph, and the
    entries after it stay untouched rather than being cut at the wrong place.
    """
    spans: list[tuple[str, int]] = []
    cursor = start
    while cursor < len(text):
        line_end = text.find("\n", cursor)
        line_end = len(text) if line_end < 0 else line_end
        line = text[cursor:line_end].rstrip("\r")
        if not line.strip():
            break
        spans.append((line, min(line_end + 1, len(text))))
        cursor = line_end + 1
    while cursor < len(text) and text[cursor] == "\n":
        cursor += 1
    return spans, cursor


__all__ = [
    "AdvertisedSkill",
    "AdvertisedSkills",
    "SKILL_SECTION_HEADER",
    "apply_skill_selection",
    "parse_advertised_skills",
]
