"""Extractive projection for large textual user history, without model calls.

Short conversational turns and every assistant message remain verbatim. Mixed
protocol/media inputs keep the existing semantic summary path. No projection is
written over the original Session records.
"""

from __future__ import annotations

import copy
import json
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter

from .evidence import (
    MAX_SOURCE_BYTES,
    _rank_terms,
    _words,
    current_question,
    evidence_ranges,
)


def _union(ranges):
    merged = []
    for start, finish in sorted(ranges):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(finish, merged[-1][1]))
        else:
            merged.append((start, finish))
    return merged


def _render(text, ranges, number):
    heading = (
        "[Earlier user excerpts. Each [start:end] indexes characters in that original "
        "message. Gaps are omitted; originals remain in Session.]\n"
        if number == 0
        else "[User excerpts]\n"
    )
    return heading + "\n".join(
        f"[{start}:{finish}]\n{text[start:finish]}" for start, finish in _union(ranges)
    )


def _text_cost(texts):
    # Include escaped quotes, newlines and control characters, not just source
    # lengths. The surrounding message structure is unchanged.
    return len(json.dumps(texts, ensure_ascii=False, separators=(",", ":")).encode())


def _shared_projection(candidates, question, baseline):
    """Spend the existing projection budget across independently indexed sources.

    The baseline caps serialized cost; no model/context limit is increased.
    Only the placement of verbatim evidence changes. Short/protected messages
    are outside this allocator and source intervals never span messages.
    """
    texts = [text for _, _, text in candidates]
    if len(texts) < 2 or sum(len(t.encode()) for t in texts) > MAX_SOURCE_BYTES:
        return baseline
    ranges = [
        [
            (0, len(t.encode()[:192].decode(errors="ignore"))),
            (len(t) - len(t.encode()[-192:].decode(errors="ignore")), len(t)),
        ]
        for t in texts
    ]
    rendered = [_render(t, r, i) for i, (t, r) in enumerate(zip(texts, ranges))]
    ceiling = _text_cost(baseline)
    remaining = ceiling - _text_cost(rendered)
    terms = set(_words(question))
    if remaining < 128 or not terms:
        return baseline
    width = min(1600, max(192, remaining // 4))
    windows = []
    for source, text in enumerate(texts):
        for offset in range(0, len(text), width):
            start, finish = max(0, offset - 160), min(len(text), offset + width + 160)
            windows.append((source, start, finish, Counter(_words(text[start:finish]))))
    df = Counter(term for *_, words in windows for term in terms if term in words)
    weights = {
        term: math.log(1 + (len(windows) - freq + 0.5) / (freq + 0.5))
        for term, freq in df.items()
    }
    terms, primary = _rank_terms(weights, question)
    ranked = []
    for source, start, finish, words in windows:
        score = sum(
            weights[t] * words[t] * 2.2 / (words[t] + 1.2) for t in terms if words[t]
        )
        question_score = sum(
            weights[t] * words[t] * 2.2 / (words[t] + 1.2) for t in primary if words[t]
        )
        if score:
            ranked.append((-question_score, -score, source, start, finish))
    boundaries = [
        sorted(
            {
                0,
                len(text),
                *(
                    m.end()
                    for m in re.finditer(
                        r"[。！？]+[ \t]*|(?<=[.!?])[ \t]+|\r?\n+", text
                    )
                ),
            }
        )
        for text in texts
    ]
    selected = 0
    for _, _, source, start, finish in sorted(ranked)[:128]:
        bounds = boundaries[source]
        whole_start = bounds[max(0, bisect_right(bounds, start) - 1)]
        whole_finish = bounds[min(len(bounds) - 1, bisect_left(bounds, finish))]
        # Prefer complete textual units. Keep a bounded window fallback for
        # unstructured text, but never truncate an already selected interval.
        for begin, end in dict.fromkeys(((whole_start, whole_finish), (start, finish))):
            merged = _union([*ranges[source], (begin, end)])
            if merged == _union(ranges[source]):
                continue
            candidate = list(rendered)
            candidate[source] = _render(texts[source], merged, source)
            if _text_cost(candidate) <= ceiling:
                rendered, ranges[source] = candidate, merged
                selected += 1
                break
    return rendered if selected else baseline


def _retrieved_projection(candidates, rankings, baseline):
    """Use retrieved original ranges within the existing serialized byte ceiling."""
    ranges = [
        [
            (0, len(text.encode()[:192].decode(errors="ignore"))),
            (len(text) - len(text.encode()[-192:].decode(errors="ignore")), len(text)),
        ]
        for _, _, text in candidates
    ]
    rendered = [
        _render(text, spans, i)
        for i, ((_, _, text), spans) in enumerate(zip(candidates, ranges))
    ]
    ceiling = _text_cost(baseline)
    selected = False
    locations = {
        (index, part): (i, text) for i, (index, part, text) in enumerate(candidates)
    }
    # Spend shared space in retrieval order, not the original document order.
    for index, part, start, end in rankings:
        candidate = locations.get((index, part))
        if candidate is None:
            continue
        i, text = candidate
        if not (
            type(start) is int and type(end) is int and 0 <= start < end <= len(text)
        ):
            continue
        trial_ranges = _union([*ranges[i], (start, end)])
        trial = list(rendered)
        trial[i] = _render(text, trial_ranges, i)
        if _text_cost(trial) <= ceiling:
            ranges[i], rendered, selected = trial_ranges, trial, True
    return rendered if selected else None


def project_history(contents, end, config, available, *, rankings=None):
    question = current_question(contents)
    if not question:
        return None
    candidates = []
    for index, content in enumerate(contents[:end]):
        if not content.parts or any(
            part.text is None or set(part.model_dump(exclude_none=True)) != {"text"}
            for part in content.parts
        ):
            return None
        if content.role != "user":
            continue
        for part_index, part in enumerate(content.parts):
            if len(part.text.encode()) > 2048 and not any(
                required in part.text for required in config.protected_context
            ):
                candidates.append((index, part_index, part.text))
    if not candidates or sum(len(text.encode()) for _, _, text in candidates) < 16000:
        return None
    per_part = min(8000, int(available * 0.4) // len(candidates))
    if per_part < 768:
        return None
    projected = copy.deepcopy(contents)
    for number, (index, part_index, text) in enumerate(candidates):
        # Establish the existing per-message projection and its byte ceiling.
        # The shared allocator may choose other evidence within this ceiling;
        # all original events and each source's head/tail remain available.
        matches = evidence_ranges(
            text, question, max(0, per_part - 512 - 256), prefer_questions=False
        )
        if matches:
            ranges = [(m["offset"], m["end"]) for m in matches]
        else:
            length = len(
                text.encode()[: min(1000, per_part - 512)].decode(errors="ignore")
            )
            ranges = [(0, length)]
        ranges += [
            (0, len(text.encode()[:192].decode(errors="ignore"))),
            (len(text) - len(text.encode()[-192:].decode(errors="ignore")), len(text)),
        ]
        projected[index].parts[part_index].text = _render(text, ranges, number)
    baseline = [projected[i].parts[p].text for i, p, _ in candidates]
    allocated = (
        _retrieved_projection(candidates, rankings, baseline) if rankings else None
    )
    if allocated is None:
        allocated = _shared_projection(candidates, question, baseline)
    for (index, part_index, _), text in zip(candidates, allocated):
        projected[index].parts[part_index].text = text
    return projected, candidates[0][:2]
