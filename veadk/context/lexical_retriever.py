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

"""Stateless BM25 evidence selection with no model, downloads or vector index."""

import asyncio
import math
import time

from ._hybrid_index import MAX_CHUNKS, MAX_SOURCE_BYTES, Chunk, Scope, bm25_rank, ranges
from .query_focus import focus_query, weighted_rrf


async def rank_lexical(identity, reference, text, query, *, deadline):
    Scope(*identity).key
    if (
        not isinstance(reference, str)
        or not 0 < len(reference) <= 512
        or not isinstance(text, str)
        or not isinstance(query, str)
        or len(text.encode()) > MAX_SOURCE_BYTES
        or len(query.encode()) > 8192
    ):
        raise ValueError("lexical_input_limit")
    if type(deadline) not in (int, float) or not math.isfinite(deadline):
        raise ValueError("invalid_deadline")

    def check_deadline():
        if time.monotonic() >= deadline:
            raise asyncio.TimeoutError

    check_deadline()
    chunks = []
    for i, (start, end) in enumerate(ranges(text)):
        if i >= MAX_CHUNKS:
            raise ValueError("lexical_chunk_limit")
        if i % 32 == 0:
            check_deadline()
            await asyncio.sleep(0)
        chunks.append(
            Chunk(str(i), reference, "", start, end, text[start:end], "", "lexical")
        )
    check_deadline()
    ranked = bm25_rank(chunks, query, deadline=deadline)
    focused = focus_query(query)
    if focused != query:
        ranked = weighted_rrf(
            [(bm25_rank(chunks, focused, deadline=deadline), 1.0), (ranked, 0.25)]
        )
    check_deadline()
    return [(chunks[i].start, chunks[i].end) for i, _ in ranked[:40]]
