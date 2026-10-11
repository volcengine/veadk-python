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

"""Long formatting context must not hide a question with an unresolved pronoun."""

import pytest

from veadk.context._hybrid_index import Scope, digest
from veadk.context.hybrid_retriever import HybridContextRetriever

IDENTITY = ("app", "user", "session", "agent", "")


class QuestionEmbedding:
    model = "offline-query-supplement-v1"
    dimension = 2

    def __init__(self, question):
        self.question = question
        self.queries = []

    async def embed(self, texts):
        return [
            [1.0, 0.0] if "East warehouse" in text else [0.0, 1.0] for text in texts
        ]

    async def embed_query(self, texts):
        self.queries.append(list(texts))
        return [[1.0, 0.0] if text == self.question else [0.0, 1.0] for text in texts]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "question", ["Where do they store pumps?", "他们把泵存放在哪里？"]
)
async def test_long_framing_retains_full_query_and_recovers_question_evidence(
    tmp_path, question
):
    query = (
        "The maintenance team is Acme.\n"
        + "FORMATTING_DISTRACTION produce prose with formatting rules. " * 14
        + "\n"
        + question
        + "\nRespond concisely."
    )
    source = (
        "FORMATTING_DISTRACTION produce prose with formatting rules. " * 90
        + "\n\n"
        + "Acme store pumps in East warehouse. 他们把泵存放在东仓库。 " * 70
    )
    embedder = QuestionEmbedding(question)
    retriever = HybridContextRetriever(tmp_path / "index.sqlite3", embedder)
    try:
        spans = await retriever.rank(IDENTITY, "record", source, query)
        assert spans and "East warehouse" in source[slice(*spans[0])]
        assert embedder.queries == [[query, question]]
        assert (
            retriever._store.read(
                Scope(*IDENTITY), "record", digest(source), 0, len(source)
            )
            == source
        )
    finally:
        await retriever.close()


@pytest.mark.parametrize(
    "query",
    [
        "Acme is the selected supplier.\nWhere is its warehouse?",
        "Format carefully. " * 40 + "\n> Where is its warehouse?",
        "Format carefully. " * 40 + "\n```\nWhere is its warehouse?\n```",
        "Format carefully. " * 40 + "\nWhere is its warehouse? Use the old address.",
        "No question here. " * 40,
    ],
)
def test_supplement_does_not_strip_short_context_quotes_or_qualifications(query):
    from veadk.context.query_focus import supplemental_question

    assert supplemental_question(query) is None


@pytest.mark.asyncio
async def test_parent_child_reuse_keeps_two_exact_queries_and_model_identity():
    from veadk.context.hierarchical_retriever import _QueryReuse

    question = "Where is its warehouse?"
    query = "Formatting instructions. " * 40 + "\n" + question
    embedder = QuestionEmbedding(question)
    wrapper = _QueryReuse(embedder, query)
    first = await wrapper.embed_query([query, question])
    second = await wrapper.embed_query([query, question])
    assert len(embedder.queries) == 1
    first[0][0] = 99
    assert second == [[0.0, 1.0], [1.0, 0.0]]
    embedder.model = "offline-query-supplement-v2"
    await wrapper.embed_query([query, question])
    assert len(embedder.queries) == 2
    # Passage preprocessing never uses a query cache, even for equal text.
    assert await wrapper.embed([question]) == [[0.0, 1.0]]
