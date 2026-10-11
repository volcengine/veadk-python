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

"""Conservative retrieval-only question focus; never rewrite model requests."""

from __future__ import annotations

import re


def _question_focus(query: str, *, keep_references: bool) -> str:
    """Keep complete standalone question lines, or retain the original query.

    No field names, task templates or dataset vocabulary are recognized.
    Labels and qualifications on a selected line remain verbatim. Ambiguous
    references keep the full query. The caller also ranks the full request,
    so other constraints are not silently discarded from lexical retrieval.
    """
    if not isinstance(query, str) or len(query.encode()) > 8192:
        raise ValueError("invalid_query")
    lines = query.splitlines()
    if len(lines) < 2 or "```" in query or "~~~" in query:
        return query
    nonempty = [line.strip() for line in lines if line.strip()]
    if any(line.startswith((">", '"', "'", "“", "‘")) for line in nonempty):
        return query
    questions = [line for line in nonempty if line.endswith(("?", "？"))]
    # An embedded/quoted question with a trailing qualification is ambiguous.
    if any(
        ("?" in line or "？" in line) and line not in questions for line in nonempty
    ):
        return query
    focused = "\n".join(questions)
    if not 1 <= len(questions) <= 4 or len(questions) == len(nonempty):
        return query
    if len(focused.encode()) > 2048:
        return query
    if keep_references and re.search(
        r"\b(it|its|they|them|their|he|him|his|she|her|these|those|this|that|"
        r"above|previous|former|latter|same)\b|它|他们|她们|上述|前述|前者|后者|该|其|这些|那些",
        focused,
        re.IGNORECASE,
    ):
        return query
    return focused


def focus_query(query: str) -> str:
    """Focus standalone questions; preserve ambiguous references verbatim."""
    return _question_focus(query, keep_references=True)


def supplemental_question(query: str) -> str | None:
    """Add a bounded question view without replacing its antecedent context.

    Only long requests dominated by surrounding text qualify. The original
    query remains a separate ranking component. Quoted/code questions and
    trailing qualifications keep the conservative single-query path.
    """
    focused = _question_focus(query, keep_references=False)
    if (
        len(query.encode()) < 512
        or focused == query
        or len(focused.encode()) * 4 > len(query.encode())
        or focus_query(query) != query
    ):
        return None
    return focused


def weighted_rrf(rankings, k=60):
    """Fuse ranked IDs; scores remain ranking signals, never answer content."""
    scores = {}
    for ranking, weight in rankings:
        for position, (index, _) in enumerate(ranking, 1):
            scores[index] = scores.get(index, 0.0) + weight / (k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
