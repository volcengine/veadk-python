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

"""Experimental complete-parent retrieval followed by bounded child retrieval.

Both levels store derived data only. Returned offsets always address the original
authorized source, and the SDK must revalidate that source before displaying it.
"""

from __future__ import annotations

import asyncio
from itertools import zip_longest
import math
import re
import time

from ._hybrid_index import (
    MAX_CHUNKS,
    MAX_SOURCE_BYTES,
    Chunk,
    Scope,
    Store,
    bm25_rank,
    canonical,
    digest,
    prepare,
    ranges,
    search,
)
from .hybrid_retriever import HybridContextRetriever
from .query_focus import focus_query, weighted_rrf


PARENT_VERSION = "hierarchical-parent-char1400-overlap120-v1"
CHILD_PREFIX = "hierarchical-child-v1:"
PARENT_SHORTLIST = 4


def supplement_spans(semantic, lexical):
    """Interleave exact spans; discard only evidence already fully covered.

    A semantic parent shortlist can exclude an exact fact elsewhere in the
    source. Give the independent whole-source lexical route early positions,
    while preserving the leading semantic evidence and the downstream budget.
    """
    selected = []
    covered = []
    for pair in zip_longest(semantic, lexical):
        for span in pair:
            if span is None:
                continue
            start, end = span
            if any(left <= start and end <= right for left, right in covered):
                continue
            selected.append(span)
            merged = []
            for left, right in sorted([*covered, span]):
                if merged and left <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(right, merged[-1][1]))
                else:
                    merged.append((left, right))
            covered = merged
            if len(selected) == 40:
                return selected
    return selected


def parent_ranges(text):
    minimum = max(700, (len(text) + MAX_CHUNKS - 1) // MAX_CHUNKS + 120)
    maximum = max(1400, minimum * 2)
    start = 0
    while start < len(text):
        end = min(len(text), start + maximum)
        if end < len(text):
            boundaries = [
                m.end()
                for m in re.finditer(r"\n\s*\n|(?<=[.!?。！？])\s+", text[start:end])
                if m.end() >= minimum
            ]
            if boundaries:
                end = start + boundaries[-1]
        yield start, end
        if end == len(text):
            break
        start = end - 120


class _QueryReuse:
    """One invocation, one exact query, one model revision and dimension."""

    def __init__(self, embedder, query):
        self.inner = embedder
        self.query = query
        self.cached = None

    @property
    def model(self):
        return self.inner.model

    @property
    def dimension(self):
        return self.inner.dimension

    async def embed(self, texts):
        identity = (self.model, self.dimension)
        if texts == [self.query] and self.cached and self.cached[0] == identity:
            return [list(self.cached[1])]
        vectors = await self.inner.embed(texts)
        if (
            texts == [self.query]
            and len(vectors) == 1
            and (self.model, self.dimension) == identity
        ):
            self.cached = (identity, list(vectors[0]))
        return vectors


class HierarchicalContextRetriever(HybridContextRetriever):
    """Opt-in cascade; the existing fine-span retriever remains available."""

    def __init__(self, index_path, embedder, *, max_new_chunks=512):
        super().__init__(index_path, embedder, max_new_chunks=max_new_chunks)
        try:
            # Separate source keys and chunk versions share the chosen database.
            # Neither connection creates another storage location or holds keys.
            self._parents = Store(
                index_path, chunk_ranges=parent_ranges, chunk_version=PARENT_VERSION
            )
        except BaseException:
            self._store.close()
            raise

    def _validate(self, identity, reference, text, query, deadline):
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("invalid_deadline")
        scope = Scope(*identity)
        scope.key
        if (
            not isinstance(reference, str)
            or not 0 < len(reference) <= 512
            or reference.startswith(CHILD_PREFIX)
        ):
            raise ValueError("invalid_source")
        if len(text.encode()) > MAX_SOURCE_BYTES or len(query.encode()) > 8192:
            raise ValueError("input_limit")
        if self._closed:
            raise ValueError("index_closed")
        if (self._embedder.model, self._embedder.dimension) != (
            self._model,
            self._dimension,
        ):
            raise ValueError("embedding_version_changed")
        return scope

    def _lexical(self, text, query, parents=None):
        """Use exact fine spans and, when available, a complete parent ranking."""
        parts = parents if parents is not None else [(0, len(text))]
        chunks = []
        seen = set()
        buckets = []
        for left, right in parts:
            bucket = []
            for start, end in ranges(text[left:right]):
                span = (left + start, left + end)
                if span in seen:
                    continue
                seen.add(span)
                bucket.append(len(chunks))
                chunks.append(
                    Chunk(
                        str(len(chunks)),
                        "",
                        "",
                        *span,
                        text[span[0] : span[1]],
                        "",
                        "fallback",
                    )
                )
            buckets.append(bucket)
        if len(chunks) > MAX_CHUNKS:
            raise ValueError("index_scope_limit")
        lexical = bm25_rank(chunks, query)
        focused = focus_query(query)
        if focused != query:
            lexical = weighted_rrf([(bm25_rank(chunks, focused), 1.0), (lexical, 0.25)])
        if parents is not None:
            # Round-robin keeps several complete semantic parents represented.
            # No partially prepared child vector participates in this fallback.
            parent_order = [
                (bucket[round_], 1.0)
                for round_ in range(max(map(len, buckets), default=0))
                for bucket in buckets
                if round_ < len(bucket)
            ]
            lexical = weighted_rrf([(lexical, 1.0), (parent_order, 1.0)])
        return [(chunks[i].start, chunks[i].end) for i, _ in lexical[:40]]

    async def rank(self, identity, reference, text, query):
        return await self.rank_with_deadline(
            identity, reference, text, query, deadline=time.monotonic() + 120.0
        )

    async def prepare_source(self, identity, reference, text, *, deadline):
        """Build a bounded, query-independent parent index before querying.

        Call only with an authorized immutable Session original and its exact
        retrieval identity/reference. This is awaited ingestion work: it does
        not launch a background task, read a question, or extend query timeouts.
        Report this work's latency and embedding usage separately from query
        work. Completed batches persist; a later call resumes missing batches.
        ``complete`` means the full parent source is indexed, not the children.
        """
        scope = self._validate(identity, reference, text, "", deadline)
        started = time.monotonic()
        # Keep preparation bounded even when an accidental distant deadline is
        # supplied. The constructor's document allowance still applies.
        end = min(deadline, started + 120.0)
        result = {
            "complete": False,
            "indexed": 0,
            "reused": 0,
            "remaining": None,
            "reason": "timeout",
        }

        async def build():
            async with self._lock:
                self._validate(identity, reference, text, "", end)
                sha = self._parents.put(scope, reference, text)
                status = await prepare(
                    self._parents,
                    scope,
                    self._embedder,
                    timeout=max(0.0, end - time.monotonic()),
                    source=reference,
                    max_new_chunks=self._max_new_chunks,
                )
                self._validate(identity, reference, text, "", end)
                # Validate even when no new batch was required or embedding
                # failed. Source integrity is never a degraded success.
                if (
                    text
                    and self._parents.read(scope, reference, sha, 0, len(text)) != text
                ):
                    raise ValueError("source_integrity")
                result.update(
                    {
                        key: status[key]
                        for key in ("indexed", "reused", "remaining", "reason")
                    }
                )
                result["complete"] = not status["degraded"] and status["remaining"] == 0

        if end > started:
            try:
                await asyncio.wait_for(build(), max(0.0, end - time.monotonic()))
            except asyncio.TimeoutError:
                # Cancellation joins external work. Partial saved batches are
                # safe to reuse but never counted as a complete semantic index.
                self._validate(identity, reference, text, "", end)
        result["seconds"] = time.monotonic() - started
        return result

    async def rank_with_deadline(self, identity, reference, text, query, *, deadline):
        scope = self._validate(identity, reference, text, query, deadline)
        if deadline <= time.monotonic():
            self.last_status = "timeout_bm25_fallback"
            return self._lexical(text, query)
        try:
            return await asyncio.wait_for(
                self._rank(scope, reference, text, query, deadline),
                max(0.0, deadline - time.monotonic()),
            )
        except asyncio.TimeoutError:
            self._validate(identity, reference, text, query, deadline)
            self.last_status = "timeout_bm25_fallback"
            return self._lexical(text, query)

    async def _rank(self, scope, reference, text, query, deadline):
        async with self._lock:
            self._validate(
                (scope.app, scope.user, scope.session, scope.agent, scope.branch),
                reference,
                text,
                query,
                deadline,
            )
            sha = self._parents.put(scope, reference, text)
            wrapped = _QueryReuse(self._embedder, focus_query(query))
            self.last_status = "indexing"

            async def select_parents():
                status = await prepare(
                    self._parents,
                    scope,
                    wrapped,
                    source=reference,
                    max_new_chunks=self._max_new_chunks,
                )
                if status["degraded"]:
                    return [], status
                found, ranking = await search(
                    self._parents,
                    scope,
                    query,
                    wrapped,
                    source=reference,
                    focus_questions=True,
                )
                if ranking["degraded"]:
                    return [], {**status, "degraded": True}
                return found[:PARENT_SHORTLIST], status

            try:
                parents, preparation = await asyncio.wait_for(
                    select_parents(), max(0.0, deadline - time.monotonic()) * 0.75
                )
            except asyncio.TimeoutError:
                self.last_status = "timeout_bm25_fallback"
                return self._lexical(text, query)
            if preparation["degraded"]:
                self.last_status = (
                    "index_budget_fallback"
                    if preparation.get("reason") == "index_budget"
                    else "embedding_fallback"
                )
                return self._lexical(text, query)
            if not parents:
                self.last_status = "hybrid"
                return []
            parent_spans = [(c.start, c.end) for c in parents]
            sources = {}
            for parent in parents:
                source = CHILD_PREFIX + digest(
                    canonical(
                        [reference, sha, parent.start, parent.end, PARENT_VERSION]
                    )
                )
                # Child text must still be the exact original parent excerpt.
                body = self._parents.read(
                    scope, reference, sha, parent.start, parent.end
                )
                self._store.put(scope, source, body)
                sources[source] = parent.start
            domain = tuple(sources)
            allowance = self._max_new_chunks - preparation["indexed"]

            async def select_children():
                if allowance <= 0:
                    return None
                status = await prepare(
                    self._store, scope, wrapped, source=domain, max_new_chunks=allowance
                )
                if status["degraded"]:
                    return None
                children, ranking = await search(
                    self._store,
                    scope,
                    query,
                    wrapped,
                    source=domain,
                    focus_questions=True,
                )
                if ranking["degraded"]:
                    return None
                spans = []
                for child in children:
                    start, end = (
                        sources[child.source] + child.start,
                        sources[child.source] + child.end,
                    )
                    if text[start:end] != child.text:
                        raise ValueError("child_source_integrity")
                    if (start, end) not in spans:
                        spans.append((start, end))
                return spans

            try:
                spans = await asyncio.wait_for(
                    select_children(), max(0.0, deadline - time.monotonic()) * 0.9
                )
            except asyncio.TimeoutError:
                spans = None
            if self._parents.read(scope, reference, sha, 0, len(text)) != text:
                raise ValueError("source_integrity")
            if (self._embedder.model, self._embedder.dimension) != (
                self._model,
                self._dimension,
            ):
                raise ValueError("embedding_version_changed")
            if spans is None:
                self.last_status = "parent_semantic_child_lexical"
                spans = self._lexical(text, query, parent_spans)
                return supplement_spans(spans, self._lexical(text, query))
            self.last_status = "hybrid"
            return supplement_spans(spans, self._lexical(text, query))

    async def close(self):
        async with self._lock:
            if not self._closed:
                self._parents.close()
                self._store.close()
                self._closed = True
