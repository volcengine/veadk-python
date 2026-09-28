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

"""SQLite hybrid retrieval primitives for request-scoped evidence selection.

SQLite sources are immutable. Indices are disposable, scoped derivatives.
No LLM-generated document context and no inference access to answer labels.
"""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
import re
import sqlite3
import struct
import time

from .score_fusion import distribution_fusion

CHUNK_VERSION = "paragraph-budgeted-char512-overlap80-v2"
MAX_SOURCE_BYTES = 2_000_000
MAX_CHUNKS = 4096
EMBEDDING_BATCH_SIZE = 16


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()


def canonical(values):
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


@dataclass(frozen=True)
class Scope:
    app: str
    user: str
    session: str
    agent: str
    branch: str = ""

    @property
    def key(self):
        values = [self.app, self.user, self.session, self.agent]
        if not all(isinstance(x, str) and 0 < len(x) <= 256 for x in values):
            raise ValueError("invalid_scope")
        if not isinstance(self.branch, str) or len(self.branch) > 256:
            raise ValueError("invalid_branch")
        return canonical(values + [self.branch])


@dataclass(frozen=True)
class Chunk:
    id: str
    source: str
    source_sha: str
    start: int
    end: int
    text: str
    title: str
    version: str

    @property
    def embedding_text(self):
        return (self.title + "\n" if self.title else "") + self.text


def ranges(text):
    """Exact Unicode character ranges, with bounded overlap and natural ends."""
    # Usually embed small spans; for very large sources, retain the original
    # full-source capacity without raising the maximum derived index size.
    # Every non-final step advances by at least ceil(length / MAX_CHUNKS).
    minimum = max(256, (len(text) + MAX_CHUNKS - 1) // MAX_CHUNKS + 80)
    maximum = max(512, minimum * 2)
    start = 0
    while start < len(text):
        end = min(len(text), start + maximum)
        if end < len(text):
            options = [
                m.end()
                for m in re.finditer(r"\n\s*\n|(?<=[.!?。！？])\s+", text[start:end])
                if m.end() >= minimum
            ]
            if options:
                end = start + options[-1]
        yield start, end
        if end == len(text):
            break
        start = end - 80


def tokens(text):
    words = re.findall(r"[a-z0-9_]+|[\u3400-\u9fff]+", text.casefold())
    return [
        token
        for word in words
        for token in (
            [word[i : i + 2] for i in range(len(word) - 1)]
            if len(word) > 1 and "\u3400" <= word[0] <= "\u9fff"
            else [word]
        )
    ]


def normalize(vector, dimension):
    if len(vector) != dimension or dimension <= 0:
        raise ValueError("invalid_dimension")
    values = [float(v) for v in vector]
    if not all(math.isfinite(v) for v in values):
        raise ValueError("nonfinite_vector")
    length = math.hypot(*values)
    if not math.isfinite(length) or length <= 0:
        raise ValueError("zero_or_invalid_vector")
    return [v / length for v in values]


class Store:
    def __init__(
        self,
        path,
        *,
        chunk_ranges: Callable[[str], Iterable[tuple[int, int]]] = ranges,
        chunk_version=CHUNK_VERSION,
    ):
        if (
            not callable(chunk_ranges)
            or not isinstance(chunk_version, str)
            or not 0 < len(chunk_version) <= 128
        ):
            raise ValueError("invalid_chunk_policy")
        self._chunk_ranges = chunk_ranges
        self._chunk_version = chunk_version
        self.path = Path(path)
        self.db = sqlite3.connect(path, timeout=0.05)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS sources (
            scope TEXT NOT NULL, source TEXT NOT NULL, sha TEXT NOT NULL,
            title TEXT NOT NULL, body TEXT NOT NULL,
            PRIMARY KEY(scope, source));
        CREATE TABLE IF NOT EXISTS chunks (
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, source TEXT NOT NULL,
            start INTEGER NOT NULL, end INTEGER NOT NULL, version TEXT NOT NULL,
            FOREIGN KEY(scope,source) REFERENCES sources(scope,source));
        CREATE INDEX IF NOT EXISTS chunk_scope ON chunks(scope,version);
        CREATE TABLE IF NOT EXISTS vectors (
            chunk TEXT NOT NULL, model TEXT NOT NULL, dimension INTEGER NOT NULL,
            value BLOB NOT NULL, checksum TEXT NOT NULL,
            PRIMARY KEY(chunk, model, dimension),
            FOREIGN KEY(chunk) REFERENCES chunks(id) ON DELETE CASCADE);
        """)

    def close(self):
        self.db.close()

    def put(self, scope, source, body, title=""):
        if not isinstance(source, str) or not source or len(source) > 512:
            raise ValueError("invalid_source")
        if len(body.encode()) > MAX_SOURCE_BYTES or len(title.encode()) > 1024:
            raise ValueError("source_too_large")
        sha = digest(body)
        row = self.db.execute(
            "SELECT sha,title,body FROM sources WHERE scope=? AND source=?",
            (scope.key, source),
        ).fetchone()
        if row and (row["sha"] != sha or row["body"] != body or row["title"] != title):
            raise ValueError("immutable_source_conflict")
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO sources VALUES (?,?,?,?,?)",
                (scope.key, source, sha, title, body),
            )
            # Version changes invalidate derived chunks, while preserving source.
            self.db.execute(
                "DELETE FROM chunks WHERE scope=? AND source=? AND version<>?",
                (scope.key, source, self._chunk_version),
            )
            for start, end in self._chunk_ranges(body):
                identifier = digest(
                    canonical(
                        [scope.key, source, sha, title, start, end, self._chunk_version]
                    )
                )
                self.db.execute(
                    "INSERT OR IGNORE INTO chunks VALUES (?,?,?,?,?,?)",
                    (identifier, scope.key, source, start, end, self._chunk_version),
                )
        return sha

    def chunks(self, scope, source=None):
        # A bounded parent shortlist is a complete second-stage search domain.
        if isinstance(source, tuple):
            if (
                not 1 <= len(source) <= 8
                or len(set(source)) != len(source)
                or not all(isinstance(s, str) and s for s in source)
            ):
                raise ValueError("invalid_source_shortlist")
            result = [
                chunk for selected in source for chunk in self.chunks(scope, selected)
            ]
            if len(result) > MAX_CHUNKS:
                raise ValueError("index_scope_limit")
            return result
        # Fetch source bodies once, not once per overlapping chunk. Scope is
        # enforced in both metadata and body queries, before either ranker.
        rows = self.db.execute(
            """SELECT c.*,s.sha,s.title FROM chunks c JOIN sources s
            ON c.scope=s.scope AND c.source=s.source WHERE c.scope=? AND c.version=? AND (? IS NULL OR c.source=?)
            ORDER BY c.source,c.start LIMIT ?""",
            (scope.key, self._chunk_version, source, source, MAX_CHUNKS + 1),
        ).fetchall()
        if len(rows) > MAX_CHUNKS:
            raise ValueError("index_scope_limit")
        bodies = {}
        output = []
        for row in rows:
            if row["source"] not in bodies:
                source = self.db.execute(
                    "SELECT body FROM sources WHERE scope=? AND source=?",
                    (scope.key, row["source"]),
                ).fetchone()
                if source is None or digest(source["body"]) != row["sha"]:
                    raise ValueError("source_integrity")
                bodies[row["source"]] = source["body"]
            body = bodies[row["source"]]
            if not 0 <= row["start"] < row["end"] <= len(body):
                raise ValueError("invalid_range")
            expected = digest(
                canonical(
                    [
                        scope.key,
                        row["source"],
                        row["sha"],
                        row["title"],
                        row["start"],
                        row["end"],
                        row["version"],
                    ]
                )
            )
            if expected != row["id"]:
                raise ValueError("chunk_integrity")
            output.append(
                Chunk(
                    row["id"],
                    row["source"],
                    row["sha"],
                    row["start"],
                    row["end"],
                    body[row["start"] : row["end"]],
                    row["title"],
                    row["version"],
                )
            )
        return output

    def read(self, scope, source, sha, start, end):
        row = self.db.execute(
            "SELECT body,sha FROM sources WHERE scope=? AND source=?",
            (scope.key, source),
        ).fetchone()
        if row is None:
            raise ValueError("source_not_available")
        if row["sha"] != sha or digest(row["body"]) != sha:
            raise ValueError("source_integrity")
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or not 0 <= start < end <= len(row["body"])
        ):
            raise ValueError("invalid_range")
        return row["body"][start:end]

    def vector(self, scope, chunk, model, dimension):
        row = self.db.execute(
            """SELECT v.value,v.checksum FROM vectors v JOIN chunks c ON c.id=v.chunk
            WHERE c.scope=? AND c.id=? AND c.version=? AND v.model=? AND v.dimension=?""",
            (scope.key, chunk.id, self._chunk_version, model, dimension),
        ).fetchone()
        if row is None:
            return None
        raw = row["value"]
        if (
            len(raw) != dimension * 4
            or hashlib.sha256(raw).hexdigest() != row["checksum"]
        ):
            raise ValueError("vector_integrity")
        return normalize(struct.unpack("<" + "f" * dimension, raw), dimension)

    def save_vectors(self, scope, pairs, model, dimension):
        with self.db:
            verified = {}
            for chunk, vector in pairs:
                # Embedding awaits external I/O. Revalidate original content,
                # title and offsets before committing its derived vector.
                if chunk.source not in verified:
                    verified[chunk.source] = {
                        c.id: c for c in self.chunks(scope, source=chunk.source)
                    }
                if verified[chunk.source].get(chunk.id) != chunk:
                    raise ValueError("chunk_not_available")
                row = self.db.execute(
                    "SELECT scope,version FROM chunks WHERE id=?", (chunk.id,)
                ).fetchone()
                if (
                    not row
                    or row["scope"] != scope.key
                    or row["version"] != self._chunk_version
                ):
                    raise ValueError("chunk_not_available")
                raw = struct.pack("<" + "f" * dimension, *normalize(vector, dimension))
                self.db.execute(
                    "INSERT OR REPLACE INTO vectors VALUES (?,?,?,?,?)",
                    (chunk.id, model, dimension, raw, hashlib.sha256(raw).hexdigest()),
                )


def bm25_rank(chunks, query, limit=40):
    terms = set(tokens(query))
    docs = [Counter(tokens(c.embedding_text)) for c in chunks]
    average = sum(sum(d.values()) for d in docs) / max(len(docs), 1)
    frequencies = Counter(term for doc in docs for term in doc)
    ranked = []
    for i, doc in enumerate(docs):
        length = sum(doc.values())
        score = 0.0
        for term in terms & doc.keys():
            # Positive Robertson/Lucene IDF remains meaningful in small scopes.
            idf = math.log1p(
                (len(docs) - frequencies[term] + 0.5) / (frequencies[term] + 0.5)
            )
            tf = doc[term]
            score += (
                idf * tf * 2.2 / (tf + 1.2 * (0.25 + 0.75 * length / max(average, 1)))
            )
        if score > 0:
            ranked.append((i, score))
    return sorted(ranked, key=lambda pair: (-pair[1], pair[0]))[:limit]


def rrf(rankings, k=60):
    scores: dict[int, float] = {}
    for ranking in rankings:
        seen = set()
        for rank, (index, _) in enumerate(ranking, 1):
            if index not in seen:
                scores[index] = scores.get(index, 0.0) + 1 / (k + rank)
            seen.add(index)
    return sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))


async def prepare(
    store, scope, embedder, timeout=120.0, *, source=None, max_new_chunks=None
):
    """Commit bounded valid batches, preserving progress across cancellation.

    One shared deadline covers all batches. An incomplete index remains a
    lexical fallback; committed vectors only become searchable once complete.
    """
    if max_new_chunks is not None and (
        type(max_new_chunks) is not int or not 1 <= max_new_chunks <= 512
    ):
        raise ValueError("invalid_chunk_limit")
    model, dimension = embedder.model, embedder.dimension
    chunks = store.chunks(scope, source)
    missing = [c for c in chunks if store.vector(scope, c, model, dimension) is None]
    started = time.monotonic()
    deadline = started + timeout
    indexed = 0

    def result(reason=None):
        remaining = len(missing) - indexed
        return {
            "indexed": indexed,
            "reused": len(chunks) - len(missing),
            "remaining": remaining,
            "degraded": reason is not None,
            "reason": reason,
            "seconds": time.monotonic() - started,
        }

    allowance = len(missing) if max_new_chunks is None else max_new_chunks
    try:
        for start in range(0, min(len(missing), allowance), EMBEDDING_BATCH_SIZE):
            batch = missing[start : min(start + EMBEDDING_BATCH_SIZE, allowance)]
            remaining_time = deadline - time.monotonic()
            if remaining_time <= 0:
                raise asyncio.TimeoutError
            if (embedder.model, embedder.dimension) != (model, dimension):
                raise ValueError("embedding_version_changed")
            vectors = await asyncio.wait_for(
                embedder.embed([c.embedding_text for c in batch]), remaining_time
            )
            if (embedder.model, embedder.dimension) != (model, dimension):
                raise ValueError("embedding_version_changed")
            if len(vectors) != len(batch):
                raise ValueError("embedding_count")
            store.save_vectors(scope, list(zip(batch, vectors)), model, dimension)
            indexed += len(batch)
        return result("index_budget" if indexed < len(missing) else None)
    except (asyncio.TimeoutError, ValueError, EmbeddingUnavailable) as exc:
        return result(type(exc).__name__)


async def search(
    store,
    scope,
    query,
    embedder=None,
    mode="hybrid",
    top=40,
    timeout=10.0,
    *,
    source=None,
    focus_questions=False,
):
    if mode not in {"bm25", "dense", "hybrid"} or not 1 <= top <= 100:
        raise ValueError("invalid_search")
    if not isinstance(query, str) or len(query.encode()) > 8192:
        raise ValueError("invalid_query")
    chunks = store.chunks(scope, source)
    lexical = bm25_rank(chunks, query, top)
    from .query_focus import focus_query, weighted_rrf

    focused = focus_query(query) if focus_questions else query
    focused_lexical = bm25_rank(chunks, focused, top) if focused != query else lexical
    lexical_fallback = (
        weighted_rrf([(focused_lexical, 1.0), (lexical, 0.25)])
        if focused != query
        else lexical
    )
    dense = []
    degraded = False
    reason = None
    if mode != "bm25" and chunks:
        try:
            if embedder is None:
                raise EmbeddingUnavailable("embedding_unconfigured")
            model, dimension = embedder.model, embedder.dimension
            vectors = [store.vector(scope, c, model, dimension) for c in chunks]
            # Partial indices must not silently bias ranking towards indexed chunks.
            if any(v is None for v in vectors):
                raise EmbeddingUnavailable("incomplete_index")
            query_vectors = await asyncio.wait_for(embedder.embed([focused]), timeout)
            if (embedder.model, embedder.dimension) != (model, dimension):
                raise ValueError("embedding_version_changed")
            if len(query_vectors) != 1:
                raise ValueError("embedding_count")
            q = normalize(query_vectors[0], dimension)
            dense = sorted(
                [(i, sum(a * b for a, b in zip(q, v))) for i, v in enumerate(vectors)],
                key=lambda pair: (-pair[1], pair[0]),
            )[:top]
        except (asyncio.TimeoutError, ValueError, EmbeddingUnavailable) as exc:
            degraded = True
            reason = type(exc).__name__
    ranked = (
        lexical_fallback
        if mode == "bm25" or degraded
        else dense
        if mode == "dense"
        else (
            distribution_fusion([(dense, 3.0), (focused_lexical, 1.0), (lexical, 0.25)])
            if focused != query
            else distribution_fusion([(lexical, 1.0), (dense, 1.0)])
        )
    )
    # No lexical overlap is an explicit empty result; do not claim relevance.
    return [chunks[i] for i, _ in ranked[:top]], {
        "degraded": degraded,
        "reason": reason,
        "candidate_count": len(chunks),
        "lexical_matches": len(lexical),
        "dense_matches": len(dense),
    }


def pack(store, scope, ranked, budget, count_tokens):
    """Budget includes reference framing. Every excerpt is read and revalidated."""
    if budget < 0:
        raise ValueError("invalid_budget")
    selected = {}

    def render(groups):
        output = []
        refs = []
        for (source, sha), spans in sorted(groups.items()):
            merged = []
            for start, end in sorted(spans):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
                else:
                    merged.append((start, end))
            for start, end in merged:
                text = store.read(scope, source, sha, start, end)
                ref = {"source": source, "sha256": sha, "start": start, "end": end}
                output.append("[Source " + canonical(ref) + "]\n" + text)
                refs.append(ref)
        return "\n\n".join(output), refs

    for chunk in ranked:
        # Never trust caller-supplied excerpt content; scope/hash/range is authoritative.
        trial = {key: list(value) for key, value in selected.items()}
        trial.setdefault((chunk.source, chunk.source_sha), []).append(
            (chunk.start, chunk.end)
        )
        text, refs = render(trial)
        if count_tokens(text) <= budget:
            selected = trial
    text, refs = render(selected)
    assert count_tokens(text) <= budget
    return {"text": text, "references": refs, "tokens": count_tokens(text)}


class EmbeddingUnavailable(Exception):
    pass
