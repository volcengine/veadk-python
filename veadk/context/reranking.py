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

"""Optional, source-bound evidence reordering with caller-owned model I/O."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import hashlib
import math
import time

from ._hybrid_index import Scope


def _hash(text):
    return hashlib.sha256(text.encode()).hexdigest()


def _ranges(value, length):
    if not isinstance(value, (tuple, list)) or not 1 <= len(value) <= 40:
        raise ValueError("reranking_range_count")
    checked = []
    for span in value:
        if not isinstance(span, (tuple, list)) or len(span) != 2:
            raise ValueError("reranking_range_shape")
        a, b = span
        if type(a) is not int or type(b) is not int or not 0 <= a < b <= length:
            raise ValueError("reranking_range_bounds")
        if (a, b) in checked:
            raise ValueError("reranking_duplicate_range")
        checked.append((a, b))
    return tuple(checked)


@dataclass(frozen=True)
class EvidenceOrder:
    """Ephemeral selection metadata; never an alternate source of evidence."""

    source_sha256: str
    baseline: tuple[tuple[int, int], ...]
    ranked: tuple[tuple[int, int], ...]

    def __iter__(self):
        return iter(self.ranked)

    def __len__(self):
        return len(self.ranked)

    def __getitem__(self, index):
        return self.ranked[index]

    def validate(self, text):
        baseline = _ranges(self.baseline, len(text))
        ranked = _ranges(self.ranked, len(text))
        if self.source_sha256 != _hash(text) or set(baseline) != set(ranked):
            raise ValueError("reranking_source_or_permutation")
        return EvidenceOrder(self.source_sha256, baseline, ranked)


def evidence_order(text, baseline, ids):
    original = _ranges(baseline, len(text))
    if (
        not isinstance(ids, (tuple, list))
        or not 1 <= len(ids) <= 12
        or any(type(i) is not int or not 0 <= i < len(original) for i in ids)
        or len(set(ids)) != len(ids)
    ):
        raise ValueError("reranking_invalid_ids")
    ranked = tuple(original[i] for i in ids) + tuple(
        r for i, r in enumerate(original) if i not in ids
    )
    return EvidenceOrder(_hash(text), original, ranked)


class EvidenceRerankingRetriever:
    """Decorate a retriever with a bounded async selector(query, passages, deadline=).

    The selector receives a tuple of original passage strings and returns at most
    twelve integer indices. The application owns its provider policy, accounting
    and close lifecycle. close() drains/closes only the wrapped retriever.
    """

    def __init__(self, retriever, selector):
        if not callable(getattr(retriever, "rank_with_deadline", None)) or not callable(
            selector
        ):
            raise ValueError("reranking_dependency")
        self._retriever = retriever
        self._selector = selector
        self._closing = False
        self._pending = set()
        self._close_task = None

    @property
    def last_status(self):
        return getattr(self._retriever, "last_status", "not_requested")

    @property
    def last_granularity(self):
        return getattr(self._retriever, "last_granularity", "not_requested")

    @property
    def uses_default_preparation(self):
        """Only a native delegate retains SDK-owned request index preparation.

        Wrapping a caller-owned retriever does not transfer its ingestion
        lifecycle to the SDK, even if it exposes a prepare_source method.
        """
        from .defaults import DefaultContextRetriever

        return isinstance(self._retriever, DefaultContextRetriever) or (
            isinstance(self._retriever, EvidenceRerankingRetriever)
            and self._retriever.uses_default_preparation
        )

    async def prepare_source(self, identity, reference, text, *, deadline):
        if self._closing:
            raise ValueError("reranking_closed")
        return await self._retriever.prepare_source(
            identity, reference, text, deadline=deadline
        )

    async def rank_with_deadline(self, identity, reference, text, query, *, deadline):
        if type(deadline) not in (int, float) or not math.isfinite(deadline):
            raise ValueError("reranking_deadline")
        Scope(*identity).key
        if (
            self._closing
            or not isinstance(reference, str)
            or not 0 < len(reference) <= 512
            or not isinstance(text, str)
            or len(text.encode()) > 2_000_000
            or not isinstance(query, str)
            or len(query.encode()) > 8192
        ):
            raise ValueError("reranking_input")
        original = await self._retriever.rank_with_deadline(
            identity, reference, text, query, deadline=deadline
        )
        if isinstance(original, EvidenceOrder):
            return original.validate(text)
        remaining = deadline - time.monotonic() - 0.05
        if remaining <= 0 or not original or self._closing:
            return original
        try:
            ranges = _ranges(original, len(text))
            passages = tuple(text[a:b] for a, b in ranges)
            if sum(len(p.encode()) for p in passages) + len(query.encode()) > 36000:
                return original
            task = asyncio.ensure_future(
                self._selector(query, passages, deadline=deadline - 0.05)
            )
            self._pending.add(task)
            try:
                ids = await asyncio.wait_for(task, timeout=remaining)
            finally:
                self._pending.discard(task)
            if not ids or self._closing or time.monotonic() >= deadline:
                return original
            return evidence_order(text, ranges, ids)
        except Exception:
            # Keep provider text out of SDK errors; caller cancellation propagates.
            return original

    async def rank_search_with_deadline(self, *args, deadline):
        """Keep the delegate's explicit lookup semantics; do not rerank searches."""
        if self._closing:
            raise ValueError("reranking_closed")
        search = getattr(self._retriever, "rank_search_with_deadline", None)
        if callable(search):
            return await search(*args, deadline=deadline)
        return await self._retriever.rank_with_deadline(*args, deadline=deadline)

    async def rank(self, identity, reference, text, query):
        return await self.rank_with_deadline(
            identity, reference, text, query, deadline=time.monotonic() + 5.0
        )

    async def close(self):
        self._closing = True
        if self._close_task is None:

            async def drain():
                pending = tuple(self._pending)
                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)
                await self._retriever.close()

            self._close_task = asyncio.create_task(drain())
        try:
            await asyncio.shield(self._close_task)
        except asyncio.CancelledError:
            await self._close_task
            raise
