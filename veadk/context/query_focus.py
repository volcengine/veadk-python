"""Conservative retrieval-only question focus; never rewrite model requests."""

from __future__ import annotations

import re


def focus_query(query: str) -> str:
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
    if re.search(
        r"\b(it|its|they|them|their|he|him|his|she|her|these|those|this|that|"
        r"above|previous|former|latter|same)\b|它|他们|她们|上述|前述|前者|后者|该|其|这些|那些",
        focused,
        re.IGNORECASE,
    ):
        return query
    return focused


def weighted_rrf(rankings, k=60):
    """Fuse ranked IDs; scores remain ranking signals, never answer content."""
    scores = {}
    for ranking, weight in rankings:
        for position, (index, _) in enumerate(ranking, 1):
            scores[index] = scores.get(index, 0.0) + weight / (k + position)
    return sorted(scores.items(), key=lambda item: (-item[1], item[0]))
