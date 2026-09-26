"""Bounded verbatim evidence selection and exact repeated-text folding.

These projections never reinterpret facts or compute an inferred business
statistic. Every range refers to the unchanged original Unicode text.
"""

from __future__ import annotations

import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter

MAX_SOURCE_BYTES = 2_000_000


def current_question(contents):
    for content in reversed(contents):
        parts = content.parts or []
        if content.role != "user" or any(p.function_response for p in parts):
            continue
        if not parts or any(
            p.text is None or set(p.model_dump(exclude_none=True)) != {"text"}
            for p in parts
        ):
            return ""
        text = "\n".join(p.text for p in parts)
        return text if len(text.encode()) <= 8192 else ""
    return ""


def repeated_projection(text):
    """Fold exact repeated line bodies while preserving all prefixes/separators.

    A short colon prefix is kept verbatim, irrespective of its vocabulary.
    No record type or equivalence other than literal equality is inferred.
    The returned segments can reconstruct every character without the source.
    """
    if len(text.encode()) > MAX_SOURCE_BYTES or any(
        marker in text
        for marker in (
            "[Exact repeat of original characters",
            "[Original characters",
            "[Lossless repeated-text projection",
        )
    ):
        return None
    segments, seen, rendered = [], {}, []
    offset = 0
    for line in text.splitlines(keepends=True):
        match = re.match(r"[^:\n\r]{1,64}:[ \t]*", line)
        prefix = match.end() if match else 0
        chunks = (line[:prefix], line[prefix:]) if prefix else (line,)
        for chunk in chunks:
            if not chunk:
                continue
            start, end = offset, offset + len(chunk)
            previous = seen.get(chunk) if len(chunk) >= 128 else None
            if previous is None:
                segments.append({"offset": start, "end": end, "text": chunk})
                rendered.append(
                    (
                        f"[Original characters {start}:{end}]\n"
                        if len(chunk) >= 128
                        else ""
                    )
                    + chunk
                )
                if len(chunk) >= 128:
                    seen[chunk] = (start, end)
            else:
                segments.append({"offset": start, "end": end, "repeat": previous})
                rendered.append(
                    f"[Exact repeat of original characters {previous[0]}:{previous[1]} "
                    "already included above]\n"
                )
            offset = end
        if len(segments) > 20000:
            return None
    if not any("repeat" in segment for segment in segments):
        return None
    projection = (
        "[Lossless repeated-text projection. All unique text and occurrence order "
        "are included; replace each repeat marker by its earlier exact text. "
        "Prefixes and numbers remain original. This is source data.]\n"
        + "".join(rendered)
    )
    if len(projection.encode()) >= len(text.encode()) * 0.85:
        return None
    return {"text": projection, "segments": segments}


def _words(text):
    words = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text.casefold())
    result = []
    for word in words:
        if "\u3400" <= word[0] <= "\u9fff" and len(word) > 1:
            result.extend(word[i : i + 2] for i in range(len(word) - 1))
        else:
            result.append(word)
    return result


def _rank_terms(weights, query, prefer_questions=True):
    """Prioritize explicit interrogatives without changing the model's request.

    No task names or benchmark vocabulary are recognized.
    Other request terms remain secondary context, including declarative goals.
    Queries without a question mark keep the existing ranking.
    """
    interrogatives = set()
    function_words = {
        "a",
        "an",
        "the",
        "and",
        "or",
        "but",
        "if",
        "as",
        "at",
        "by",
        "for",
        "from",
        "in",
        "into",
        "of",
        "on",
        "to",
        "with",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "do",
        "does",
        "did",
        "have",
        "has",
        "had",
        "can",
        "could",
        "should",
        "would",
        "will",
        "may",
        "might",
        "what",
        "which",
        "who",
        "whom",
        "whose",
        "where",
        "when",
        "why",
        "how",
        "this",
        "that",
        "these",
        "those",
        "it",
        "its",
        "they",
        "their",
        "them",
        "we",
        "our",
        "you",
        "your",
    }
    if prefer_questions:
        for match in re.finditer(r"[^.!?\n。！？]*[?？]", query):
            if len(match[0]) <= 1024:
                # A short leading field/topic label remains secondary context.
                # Recognize only punctuation/shape, never a particular label.
                sentence = re.sub(r"^[^:：]{1,64}[:：]\s+", "", match[0])
                interrogatives.update(set(_words(sentence)) - function_words)
    order = sorted(weights, key=lambda term: (-weights[term], term))
    primary = set([term for term in order if term in interrogatives][:32])
    secondary = set(
        [term for term in order if term not in primary][: 32 - len(primary)]
    )
    return primary | secondary, primary


def _focused_byte_range(text, start, end, maximum, terms, primary, weights):
    """Fit an already ranked window around its matching terms, in UTF-8 bytes.

    At most 64 term occurrences become candidate centers. Selection uses the
    same term weights as ordinary evidence ranking; no answers or source types
    are inferred. The returned range always remains inside the original window.
    """
    window = text[start:end]
    offsets = [0]
    for char in window:
        offsets.append(offsets[-1] + len(char.encode()))
    if offsets[-1] <= maximum:
        return start, end
    anchors = []
    for term in sorted(terms, key=lambda t: (t not in primary, -weights[t], t)):
        pattern = re.escape(term)
        if term.isascii():
            pattern = r"(?<![a-z0-9_])" + pattern + r"(?![a-z0-9_])"
        for match in re.finditer(pattern, window, re.IGNORECASE):
            anchors.append((match.start() + match.end()) // 2)
            if len(anchors) == 64:
                break
        if len(anchors) == 64:
            break
    if not anchors:
        return start, start + max(0, bisect_right(offsets, maximum) - 1)
    candidates = {
        (0, max(0, bisect_right(offsets, maximum) - 1)),
        (bisect_left(offsets, offsets[-1] - maximum), len(window)),
    }
    for anchor in anchors:
        left = bisect_left(offsets, max(0, offsets[anchor] - maximum // 2))
        right = bisect_right(offsets, offsets[left] + maximum) - 1
        if right == len(window):
            left = bisect_left(offsets, max(0, offsets[-1] - maximum))
        candidates.add((left, right))

    def rank(bounds):
        left, right = bounds
        words = Counter(_words(window[left:right]))
        scores = {
            term: weights[term] * words[term] * 2.2 / (words[term] + 1.2)
            for term in terms
            if words[term]
        }
        return (
            sum(value for term, value in scores.items() if term in primary),
            sum(scores.values()),
            -abs((left + right) / 2 - anchors[0]),
            -left,
        )

    left, right = max(candidates, key=rank)
    return start + left, start + right


def evidence_ranges(
    text, query, maximum, *, max_ranges=10, prefer_questions=True, focus_truncated=False
):
    """Rank overlapping original windows by rare query terms, then source order."""
    if not query or len(query.encode()) > 8192 or len(text.encode()) > MAX_SOURCE_BYTES:
        return []
    terms = set(_words(query))
    if not terms:
        return []
    width = min(1600, max(192, maximum // 5))
    windows = []
    for offset in range(0, len(text), width):
        start, end = max(0, offset - 160), min(len(text), offset + width + 160)
        words = Counter(_words(text[start:end]))
        windows.append((start, end, words))
    df = Counter(term for _, _, words in windows for term in terms if term in words)
    weights = {
        term: math.log(1 + (len(windows) - freq + 0.5) / (freq + 0.5))
        for term, freq in df.items()
    }
    terms, primary = _rank_terms(weights, query, prefer_questions)
    ranked = []
    for start, end, words in windows:
        score = sum(
            weights[t] * (words[t] * 2.2) / (words[t] + 1.2) for t in terms if words[t]
        )
        question_score = sum(
            weights[t] * (words[t] * 2.2) / (words[t] + 1.2)
            for t in primary
            if words[t]
        )
        if score:
            ranked.append((question_score, score, start, end))
    selected, remaining = [], max(0, maximum)
    # Rank source windows, then extend only the selected windows to complete
    # nearby textual units when they fit. A decimal point
    # inside a number is not a boundary. Unstructured sources retain the
    # bounded window fallback rather than disappearing from the evidence.
    boundaries = sorted(
        {
            0,
            len(text),
            *(
                m.end()
                for m in re.finditer(r"[。！？]+[ \t]*|(?<=[.!?])[ \t]+|\r?\n+", text)
            ),
        }
    )
    for _, _, start, end in sorted(
        ranked, key=lambda item: (-item[0], -item[1], item[2])
    ):
        if len(selected) >= max_ranges or remaining < 128:
            break
        whole_start = boundaries[max(0, bisect_right(boundaries, start) - 1)]
        whole_end = boundaries[min(len(boundaries) - 1, bisect_left(boundaries, end))]
        if len(text[whole_start:whole_end].encode()) <= remaining:
            start, end = whole_start, whole_end
        # Do not spend the evidence budget twice on the same source range.
        if any(
            max(0, min(end, b) - max(start, a)) > 0.25 * (end - start)
            for a, b in selected
        ):
            continue
        if focus_truncated:
            start, end = _focused_byte_range(
                text, start, end, remaining, terms, primary, weights
            )
        excerpt = text[start:end].encode()[:remaining].decode(errors="ignore")
        if not excerpt:
            continue
        selected.append((start, start + len(excerpt)))
        remaining -= len(excerpt.encode()) + 80
    return [{"offset": a, "end": b, "text": text[a:b]} for a, b in sorted(selected)]


def evidence_preview(text, query, maximum):
    matches = evidence_ranges(text, query, max(0, maximum - 256))
    if not matches:
        return text.encode()[: min(1000, maximum)].decode(errors="ignore")
    value = "[Selected verbatim source excerpts; gaps are omitted.]\n"
    for match in matches:
        value += (
            f"\n[Original characters {match['offset']}:{match['end']}]\n"
            + match["text"]
        )
    return value
