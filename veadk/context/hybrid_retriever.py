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

"""Experimental opt-in BM25/embedding ranker with a disposable SQLite index."""

from __future__ import annotations

import asyncio
import math
import os
from pathlib import Path
import time

from ._hybrid_index import (
    CHUNK_VERSION,
    MAX_CHUNKS,
    MAX_SOURCE_BYTES,
    Chunk,
    Scope,
    Store,
    bm25_rank,
    digest,
    prepare,
    ranges,
    search,
)
from .query_focus import focus_query, weighted_rrf


class HybridContextRetriever:
    """Use a caller-owned async embedder exposing model, dimension and embed().

    The embedder's model identifier must include its revision. This object owns
    only the local index and must be closed after use. Session originals remain
    authoritative; index bodies must never be used directly by the reader.
    No model service or model weights are configured or downloaded implicitly.
    """

    def __init__(self, index_path, embedder, *, max_new_chunks=512):
        if type(max_new_chunks) is not int or not 1 <= max_new_chunks <= 512:
            raise ValueError("invalid_chunk_limit")
        if not isinstance(embedder.model, str) or not 0 < len(embedder.model) <= 256:
            raise ValueError("invalid_embedding_model")
        if type(embedder.dimension) is not int or not 1 <= embedder.dimension <= 8192:
            raise ValueError("invalid_embedding_dimension")
        path = Path(index_path)
        if path.is_symlink():
            raise ValueError("index_symlink_not_allowed")
        # The developer chooses the directory; no fallback to global/home state.
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)
        self._store = Store(path)
        self._embedder = embedder
        self._model = embedder.model
        self._dimension = embedder.dimension
        self._max_new_chunks = max_new_chunks
        self._lock = asyncio.Lock()
        self._closed = False
        self.last_status = "not_requested"

    async def prepare_source(self, identity, reference, text, *, deadline):
        """Explicitly index every fine source chunk before query-only work.

        The caller supplies an authorized immutable Session original. No query,
        synthetic context or answer is used. Ingestion latency and embedding
        usage must be reported separately; this never extends query deadlines.
        A bounded unfinished index may be resumed, but is never semantic-ready.
        """
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("invalid_deadline")
        scope = Scope(*identity)
        scope.key
        if not isinstance(reference, str) or not 0 < len(reference) <= 512:
            raise ValueError("invalid_source")
        if not isinstance(text, str) or len(text.encode()) > MAX_SOURCE_BYTES:
            raise ValueError("input_limit")

        def validate():
            if self._closed:
                raise ValueError("index_closed")
            if (self._embedder.model, self._embedder.dimension) != (
                self._model,
                self._dimension,
            ):
                raise ValueError("embedding_version_changed")

        validate()
        started = time.monotonic()
        end = min(deadline, started + 120.0)
        result = {
            "complete": False,
            "indexed": 0,
            "reused": 0,
            "remaining": None,
            "reason": "timeout",
            "granularity": "full_source_fine",
        }

        async def build():
            async with self._lock:
                validate()
                source_sha = self._store.put(scope, reference, text)
                status = await prepare(
                    self._store,
                    scope,
                    self._embedder,
                    timeout=max(0.0, end - time.monotonic()),
                    source=reference,
                    max_new_chunks=self._max_new_chunks,
                )
                validate()
                if (
                    text
                    and self._store.read(scope, reference, source_sha, 0, len(text))
                    != text
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
                # wait_for joins canceled I/O; only committed batches survive.
                validate()
        result["seconds"] = time.monotonic() - started
        return result

    async def rank_with_deadline(self, identity, reference, text, query, *, deadline):
        """Bound optional indexing/query I/O, retaining a lexical source view.

        Only our own timeout selects this fallback. Explicit caller cancellation
        propagates, including cancellation while waiting for the index lock.
        The SDK still authorizes and revalidates the supplied original source.
        """
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("invalid_deadline")
        # Validate before optional work or fallback, even when the index is busy.
        Scope(*identity).key
        if not isinstance(reference, str) or not 0 < len(reference) <= 512:
            raise ValueError("invalid_source")
        if len(text.encode()) > MAX_SOURCE_BYTES or len(query.encode()) > 8192:
            raise ValueError("input_limit")
        remaining = deadline - time.monotonic()
        if remaining > 0:
            try:
                return await asyncio.wait_for(
                    self.rank(identity, reference, text, query), timeout=remaining
                )
            except asyncio.TimeoutError:
                # wait_for has cancelled and joined rank: committed index
                # batches survive, and no embedding task is left in flight.
                pass
        if self._closed:
            raise ValueError("index_closed")
        if (self._embedder.model, self._embedder.dimension) != (
            self._model,
            self._dimension,
        ):
            raise ValueError("embedding_version_changed")
        # No SQLite lock or vector is needed here. These temporary candidates
        # use the caller's original text, never an index body or cached answer.
        source_sha = digest(text)
        chunks = []
        for start, end in ranges(text):
            if len(chunks) >= MAX_CHUNKS:
                raise ValueError("index_scope_limit")
            chunks.append(
                Chunk(
                    str(len(chunks)),
                    reference,
                    source_sha,
                    start,
                    end,
                    text[start:end],
                    "",
                    CHUNK_VERSION,
                )
            )
        ranked = bm25_rank(chunks, query)
        focused = focus_query(query)
        if focused != query:
            ranked = weighted_rrf([(bm25_rank(chunks, focused), 1.0), (ranked, 0.25)])
        self.last_status = "timeout_bm25_fallback"
        return [(chunks[i].start, chunks[i].end) for i, _ in ranked]

    async def rank(self, identity, reference, text, query):
        if self._closed:
            raise ValueError("index_closed")
        scope = Scope(*identity)
        async with self._lock:
            if self._closed:
                raise ValueError("index_closed")
            if (self._embedder.model, self._embedder.dimension) != (
                self._model,
                self._dimension,
            ):
                raise ValueError("embedding_version_changed")
            self._store.put(scope, reference, text)
            mode = "hybrid"
            self.last_status = "indexing"
            try:
                status = await prepare(
                    self._store,
                    scope,
                    self._embedder,
                    source=reference,
                    max_new_chunks=self._max_new_chunks,
                )
            except asyncio.CancelledError:
                self.last_status = "cancelled"
                raise
            if status["degraded"]:
                mode = "bm25"
                self.last_status = (
                    "index_budget_fallback"
                    if status["reason"] == "index_budget"
                    else "embedding_fallback"
                )
            ranked, status = await search(
                self._store,
                scope,
                query,
                self._embedder,
                mode=mode,
                source=reference,
                focus_questions=True,
            )
            if mode == "hybrid":
                self.last_status = (
                    "embedding_fallback" if status["degraded"] else "hybrid"
                )
            return [(chunk.start, chunk.end) for chunk in ranked]

    async def close(self):
        async with self._lock:
            if not self._closed:
                self._store.close()
                self._closed = True
