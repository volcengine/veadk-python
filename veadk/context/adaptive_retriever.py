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

"""Choose source granularity from a bounded, query-independent chunk count."""

from __future__ import annotations

import asyncio
import math
import time

from ._hybrid_index import MAX_SOURCE_BYTES, Scope, ranges
from .hierarchical_retriever import CHILD_PREFIX, HierarchicalContextRetriever
from .hybrid_retriever import HybridContextRetriever


class AdaptiveContextRetriever:
    """Compose existing rankers without increasing their work or time limits.

    Both rankers use the caller's SQLite index. An immutable source always
    selects the same granularity for this configuration, including after restart.
    Model services, original Session storage and access control remain owned by
    the caller. A complete parent index does not mean all children are indexed.
    """

    def __init__(self, index_path, embedder, *, max_new_chunks=512):
        self._fine = HybridContextRetriever(
            index_path, embedder, max_new_chunks=max_new_chunks
        )
        try:
            self._parent = HierarchicalContextRetriever(
                index_path, embedder, max_new_chunks=max_new_chunks
            )
        except BaseException:
            self._fine._store.close()
            raise
        self._embedder = embedder
        self._model = embedder.model
        self._dimension = embedder.dimension
        self._limit = max_new_chunks
        self._closing = False
        self._last = None
        self.last_granularity = "not_requested"

    @property
    def last_status(self):
        return self._last.last_status if self._last is not None else "not_requested"

    def _select(self, identity, reference, text, query, deadline):
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("invalid_deadline")
        Scope(*identity).key
        if (
            not isinstance(reference, str)
            or not 0 < len(reference) <= 512
            or reference.startswith(CHILD_PREFIX)
        ):
            raise ValueError("invalid_source")
        if (
            not isinstance(text, str)
            or not isinstance(query, str)
            or len(text.encode()) > MAX_SOURCE_BYTES
            or len(query.encode()) > 8192
        ):
            raise ValueError("input_limit")
        if self._closing:
            raise ValueError("index_closed")
        if (self._embedder.model, self._embedder.dimension) != (
            self._model,
            self._dimension,
        ):
            raise ValueError("embedding_version_changed")
        selected, granularity = self._fine, "full_source_fine"
        for count, _ in enumerate(ranges(text), 1):
            if count > self._limit:
                selected, granularity = self._parent, "hierarchical_parent"
                break
        self._last = selected
        self.last_granularity = granularity
        return selected, granularity

    async def prepare_source(self, identity, reference, text, *, deadline):
        selected, granularity = self._select(identity, reference, text, "", deadline)
        result = await selected.prepare_source(
            identity, reference, text, deadline=deadline
        )
        return {**result, "granularity": granularity}

    async def rank_with_deadline(self, identity, reference, text, query, *, deadline):
        selected, _ = self._select(identity, reference, text, query, deadline)
        return await selected.rank_with_deadline(
            identity, reference, text, query, deadline=deadline
        )

    async def rank(self, identity, reference, text, query):
        return await self.rank_with_deadline(
            identity, reference, text, query, deadline=time.monotonic() + 120.0
        )

    async def close(self):
        self._closing = True
        # Drain both delegates even when the caller cancels close. No background
        # work or half-closed connection survives a completed close invocation.
        pending = asyncio.gather(self._fine.close(), self._parent.close())
        try:
            await asyncio.shield(pending)
        except asyncio.CancelledError:
            await pending
            raise
