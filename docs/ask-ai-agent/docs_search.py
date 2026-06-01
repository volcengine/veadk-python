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

"""Dependency-free keyword search over the docs index.

Tokenizes both Latin words and CJK character bigrams, then scores pages with a
BM25-style ranking (title + headings weighted higher than body). No embeddings,
no external services — just the prebuilt `docs_index.json`.
"""

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path

_INDEX_PATH = Path(__file__).resolve().parent / "docs_index.json"

_LATIN = re.compile(r"[a-zA-Z0-9_]+")
_CJK = re.compile(r"[一-鿿]")


def _tokenize(text: str) -> list[str]:
    text = text.lower()
    tokens = _LATIN.findall(text)
    cjk = _CJK.findall(text)
    # CJK character bigrams (plus singletons for short queries)
    tokens += ["".join(pair) for pair in zip(cjk, cjk[1:])]
    tokens += cjk
    return tokens


@lru_cache(maxsize=1)
def _load() -> tuple[list[dict], list[dict], dict[str, int], float]:
    pages = json.loads(_INDEX_PATH.read_text(encoding="utf-8"))
    postings: list[dict[str, int]] = []
    df: dict[str, int] = {}
    total_len = 0
    for page in pages:
        blob = " ".join(
            [page.get("title", "")] * 3
            + page.get("headings", []) * 2
            + [page.get("text", "")]
        )
        toks = _tokenize(blob)
        total_len += len(toks)
        tf: dict[str, int] = {}
        for t in toks:
            tf[t] = tf.get(t, 0) + 1
        postings.append(tf)
        for t in tf:
            df[t] = df.get(t, 0) + 1
    avg_len = (total_len / len(pages)) if pages else 1.0
    return pages, postings, df, avg_len


def search(query: str, top_k: int = 5, lang: str | None = None) -> list[dict]:
    """Return the top-k most relevant doc pages for a query."""
    pages, postings, df, avg_len = _load()
    n = len(pages)
    q_terms = set(_tokenize(query))
    if not q_terms:
        return []

    k1, b = 1.5, 0.75
    scored: list[tuple[float, int]] = []
    for i, tf in enumerate(postings):
        if lang and pages[i].get("lang") != lang:
            continue
        doc_len = sum(tf.values()) or 1
        score = 0.0
        for term in q_terms:
            f = tf.get(term, 0)
            if not f:
                continue
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            score += idf * (f * (k1 + 1)) / (f + k1 * (1 - b + b * doc_len / avg_len))
        if score > 0:
            scored.append((score, i))

    scored.sort(reverse=True)
    results = []
    for score, i in scored[:top_k]:
        page = pages[i]
        results.append(
            {
                "title": page["title"],
                "url": page["url"],
                "lang": page["lang"],
                "excerpt": _excerpt(page["text"], q_terms),
                "score": round(score, 3),
            }
        )
    return results


def _excerpt(text: str, q_terms: set[str], width: int = 600) -> str:
    """A snippet centered on the first query-term hit."""
    low = text.lower()
    pos = -1
    for term in q_terms:
        p = low.find(term)
        if p != -1 and (pos == -1 or p < pos):
            pos = p
    if pos == -1:
        return text[:width].strip()
    start = max(0, pos - width // 3)
    return text[start : start + width].strip()
