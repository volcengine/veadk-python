"""Bounded search evidence from matching source headings and ranked windows.

Ordinary previews and exact reads are unchanged. Every returned character
range belongs to the original source, including serialized history.
"""

import re
from bisect import bisect_left, bisect_right

from . import evidence


def _heading_terms(text):
    result = set()
    for word in evidence._words(text):
        if len(word) >= 5 and word.isascii() and word.isalpha():
            if word.endswith("ies"):
                word = word[:-3] + "y"
            elif word.endswith(("ches", "shes", "xes", "zes")):
                word = word[:-2]
            elif word.endswith("s") and not word.endswith(("ss", "us", "is")):
                word = word[:-1]
        result.add(word)
    return result


def search_ranges(text, query, maximum):
    baseline = evidence.evidence_ranges(text, query, maximum, max_ranges=3)
    if len(text.encode()) > evidence.MAX_SOURCE_BYTES or len(query.encode()) > 8192:
        return baseline
    terms = _heading_terms(query)
    if not terms or len(terms) > 8 or maximum < 768:
        return baseline
    candidates = []
    # Literal backslash-newline is only a retrieval boundary hint. It can occur
    # in serialized history; no source content is decoded or treated as trusted.
    for boundary in re.finditer(r"\A|\r?\n|\\n", text):
        start = boundary.end()
        line = re.split(r"\r?\n|\\n", text[start : start + 160], maxsplit=1)[0]
        line = re.sub(r"^(?:#{1,6}\s+|\d+(?:\.\d+)*[.)]?\s+)", "", line)
        heading = re.split(r"[.:。：!?！？](?:\s|$)", line, maxsplit=1)[0].strip()
        if not 1 <= len(heading) <= 120:
            continue
        present = _heading_terms(heading)
        if terms <= present:
            candidates.append((len(present - terms), start))
        if len(candidates) > 256:
            return baseline
    if not candidates:
        return baseline
    bounds = sorted(
        {
            0,
            len(text),
            *(
                m.end()
                for m in re.finditer(
                    r"[。！？]+[ \t]*|(?<=[.!?])[ \t]+|\r?\n+|\\n", text
                )
            ),
        }
    )
    width = min(1600, max(192, maximum // 5))
    preferred = []
    for _, anchor in sorted(candidates):
        start = bounds[max(0, bisect_right(bounds, max(0, anchor - 160)) - 1)]
        end = bounds[
            min(
                len(bounds) - 1,
                bisect_left(bounds, min(len(text), anchor + width + 160)),
            )
        ]
        # Do not extend through an unbounded paragraph before the heading.
        # Prefer sentence boundaries only while the whole unit fits the page.
        if len(text[start:end].encode()) > min(maximum, width + 640):
            start, end = max(0, anchor - 160), min(len(text), anchor + width + 160)
        if any(
            max(0, min(end, b) - max(start, a)) > 0.25 * (end - start)
            for a, b in preferred
        ):
            continue
        preferred.append((start, end))
        if len(preferred) == 2:
            break
    selected, remaining = [], maximum
    for start, end in preferred + [(m["offset"], m["end"]) for m in baseline]:
        if len(selected) >= 3 or remaining < 128:
            break
        if any(
            max(0, min(end, b) - max(start, a)) > 0.25 * (end - start)
            for a, b in selected
        ):
            continue
        excerpt = text[start:end].encode()[:remaining].decode(errors="ignore")
        if excerpt:
            selected.append((start, start + len(excerpt)))
            remaining -= len(excerpt.encode()) + 80
    return [dict(offset=a, end=b, text=text[a:b]) for a, b in sorted(selected)]
