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

"""Semantic matches must enter the SDK's small, byte-bounded source preview.

Synthetic vectors isolate retrieval/admission from model quality. The fixture
uses paraphrases with no query keyword overlap and two distant required facts.
"""

from dataclasses import replace

import pytest

from veadk.context._hybrid_index import Scope, digest
from veadk.context.hybrid_retriever import HybridContextRetriever
from veadk.context.retrieval import _matches, _preview


IDENTITY = ("app", "user", "session", "agent", "")
QUERY = "Where are car and doctor?"
FACTS = ("The automobile is at East Garage.", "The physician is at West Clinic.")


@pytest.mark.parametrize("unit", ["abcde", "x" * 300 + "\n\n"])
def test_maximum_supported_source_retains_full_coverage_within_index_cap(unit):
    from veadk.context._hybrid_index import MAX_CHUNKS, MAX_SOURCE_BYTES, ranges

    source = (unit * (MAX_SOURCE_BYTES // len(unit) + 1))[:MAX_SOURCE_BYTES]
    spans = list(ranges(source))
    assert 0 < len(spans) <= MAX_CHUNKS
    assert spans[0][0] == 0 and spans[-1][1] == len(source)
    assert all(0 <= start < end <= len(source) for start, end in spans)
    assert all(
        spans[i][0] < spans[i + 1][0] <= spans[i][1] for i in range(len(spans) - 1)
    )


class SemanticBoundary:
    model = "offline-preview-admission-v1"
    dimension = 3

    def __init__(self):
        self.documents = 0

    async def embed(self, texts):
        self.documents += sum(text != QUERY for text in texts)
        return [
            [1.0, 0.0, 0.0]
            if text == QUERY or any(fact in text for fact in FACTS)
            else [0.0, 1.0, 0.0]
            for text in texts
        ]


@pytest.mark.asyncio
@pytest.mark.parametrize("padding,budget", [("z", 1300), ("补", 3400), ("🙂", 4500)])
async def test_two_distant_semantic_facts_enter_budgeted_sdk_preview(
    tmp_path, padding, budget
):
    source = padding * 1800 + FACTS[0] + padding * 2600 + FACTS[1] + padding * 2000
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", SemanticBoundary())
    scope = Scope(*IDENTITY)
    try:
        ranked = await retriever.rank(IDENTITY, "record", source, QUERY)
        assert retriever.last_status == "hybrid"
        selected = _matches(source, ranked, budget, preview=True)
        rendered = _preview(selected)
        assert len(rendered.encode()) <= budget
        assert all(fact in rendered for fact in FACTS)
        for match in selected:
            assert match["text"] == source[match["offset"] : match["end"]]
        assert (
            retriever._store.read(scope, "record", digest(source), 0, len(source))
            == source
        )
        with pytest.raises(ValueError):
            retriever._store.read(
                replace(scope, user="different"),
                "record",
                digest(source),
                0,
                len(source),
            )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_reopened_small_preview_reuses_vectors_and_keeps_semantic_fact(tmp_path):
    source = "z" * 1800 + FACTS[0] + "z" * 4200
    embedder = SemanticBoundary()
    path = tmp_path / "index.sqlite3"
    retriever = HybridContextRetriever(path, embedder)
    try:
        await retriever.rank(IDENTITY, "record", source, QUERY)
        prepared = embedder.documents
    finally:
        await retriever.close()
    retriever = HybridContextRetriever(path, embedder)
    try:
        ranked = await retriever.rank(IDENTITY, "record", source, QUERY)
        assert embedder.documents == prepared
        selected = _matches(source, ranked, 700, preview=True)
        rendered = _preview(selected)
        assert len(rendered.encode()) <= 700 and FACTS[0] in rendered
        assert (
            retriever._store.read(
                Scope(*IDENTITY), "record", digest(source), 0, len(source)
            )
            == source
        )
    finally:
        await retriever.close()


@pytest.mark.asyncio
async def test_preview_too_small_does_not_truncate_or_fabricate_evidence(tmp_path):
    source = "z" * 1800 + FACTS[0] + "z" * 4200
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", SemanticBoundary())
    try:
        ranked = await retriever.rank(IDENTITY, "record", source, QUERY)
        assert _matches(source, ranked, 1, preview=True) == []
        assert (
            retriever._store.read(
                Scope(*IDENTITY), "record", digest(source), 0, len(source)
            )
            == source
        )
    finally:
        await retriever.close()
