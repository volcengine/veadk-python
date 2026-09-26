"""Failure-layer regressions for the independent retrieval component."""

import asyncio
from dataclasses import replace
import math
from pathlib import Path
import tempfile
import unittest

from veadk.context._hybrid_index import (
    Scope,
    Store,
    digest,
    bm25_rank,
    normalize,
    pack,
    prepare,
    ranges,
    rrf,
    search,
)


class FakeEmbedding:
    model = "offline-fixture-v1"
    dimension = 3

    def __init__(self):
        self.calls = 0

    async def embed(self, texts):
        self.calls += len(texts)
        # Fixture tests whether semantic results enter ranking, not model quality.
        return [
            [1.0, 0.0, 0.0]
            if any(t in text for t in ("car", "automobile", "汽车"))
            else [0.0, 1.0, 0.0]
            for text in texts
        ]


class TimeoutEmbedding(FakeEmbedding):
    async def embed(self, texts):
        await asyncio.sleep(10)


class Tests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "index.sqlite3"
        self.store = Store(self.path)
        self.scope = Scope("app", "user", "session", "agent")
        self.other = Scope("app", "other-user", "session", "agent")
        self.embedding = FakeEmbedding()

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_exact_unicode_and_bounded_chunk_coverage(self):
        text = "甲乙🙂 café e\u0301。\n\nContradiction is not removal. " * 150
        spans = list(ranges(text))
        self.assertEqual(spans[0][0], 0)
        self.assertEqual(spans[-1][1], len(text))
        for i, (a, b) in enumerate(spans):
            self.assertTrue(0 < b - a <= 1400)
            if i:
                self.assertLessEqual(a, spans[i - 1][1])
        self.store.put(self.scope, "event", text)
        for c in self.store.chunks(self.scope):
            self.assertEqual(c.text, text[c.start : c.end])

    async def test_semantic_route_can_return_zero_keyword_overlap(self):
        self.store.put(self.scope, "event-a", "An automobile is parked outside.")
        self.store.put(self.scope, "event-b", "A bicycle leans against the wall.")
        chunks = self.store.chunks(self.scope)
        self.assertEqual(bm25_rank(chunks, "car"), [])
        await prepare(self.store, self.scope, self.embedding)
        found, status = await search(self.store, self.scope, "car", self.embedding)
        self.assertEqual(found[0].source, "event-a")
        self.assertFalse(status["degraded"])

    async def test_scope_filter_applies_before_both_rankers(self):
        self.store.put(self.other, "foreign", "car automobile 汽车")
        self.store.put(self.scope, "own", "bicycle")
        await prepare(self.store, self.scope, self.embedding)
        await prepare(self.store, self.other, self.embedding)
        found, status = await search(self.store, self.scope, "car", self.embedding)
        self.assertEqual(status["candidate_count"], 1)
        self.assertEqual([c.source for c in found], ["own"])
        with self.assertRaises(ValueError):
            self.store.read(self.scope, "foreign", digest("car automobile 汽车"), 0, 3)

    async def test_all_four_identity_fields_isolate(self):
        self.store.put(self.scope, "event", "car")
        await prepare(self.store, self.scope, self.embedding)
        chunk = self.store.chunks(self.scope)[0]
        for field in ("app", "user", "session", "agent"):
            wrong = replace(self.scope, **{field: "different"})
            self.assertEqual(self.store.chunks(wrong), [])
            self.assertIsNone(self.store.vector(wrong, chunk, self.embedding.model, 3))
            with self.assertRaises(ValueError):
                self.store.save_vectors(
                    wrong, [(chunk, [1, 0, 0])], self.embedding.model, 3
                )

    async def test_restart_reuses_vectors_and_restores_full_original(self):
        text = "car details " + ("discardable filler " * 180)
        sha = self.store.put(self.scope, "event", text)
        await prepare(self.store, self.scope, self.embedding)
        calls = self.embedding.calls
        self.store.close()
        self.store = Store(self.path)
        result = await prepare(self.store, self.scope, self.embedding)
        self.assertEqual(result["indexed"], 0)
        self.assertEqual(self.embedding.calls, calls)
        self.assertEqual(self.store.read(self.scope, "event", sha, 0, len(text)), text)

    def test_mutable_event_key_rejected_original_retained(self):
        self.store.put(self.scope, "event", "old")
        with self.assertRaises(ValueError):
            self.store.put(self.scope, "event", "new")
        self.assertEqual(
            self.store.read(self.scope, "event", digest("old"), 0, 3), "old"
        )

    async def test_embedding_model_and_dimension_mismatch_not_reused(self):
        self.store.put(self.scope, "event", "car")
        await prepare(self.store, self.scope, self.embedding)
        c = self.store.chunks(self.scope)[0]
        self.assertIsNone(self.store.vector(self.scope, c, "other-model", 3))
        self.assertIsNone(self.store.vector(self.scope, c, self.embedding.model, 2))

    async def test_chunk_version_change_invalidates_only_derived_data(self):
        self.store.put(self.scope, "event", "car")
        await prepare(self.store, self.scope, self.embedding)
        self.store.db.execute("UPDATE chunks SET version='old-version'")
        self.store.db.commit()
        self.assertEqual(self.store.chunks(self.scope), [])
        self.store.put(self.scope, "event", "car")
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 0
        )
        self.assertEqual(
            self.store.read(self.scope, "event", digest("car"), 0, 3), "car"
        )

    def test_tampered_original_rejected_before_search_or_read(self):
        self.store.put(self.scope, "event", "old")
        self.store.db.execute("UPDATE sources SET body='new'")
        self.store.db.commit()
        with self.assertRaises(ValueError):
            self.store.chunks(self.scope)
        with self.assertRaises(ValueError):
            self.store.read(self.scope, "event", digest("old"), 0, 3)

    def test_tampered_title_or_range_rejected(self):
        self.store.put(self.scope, "event", "car outside", "title")
        self.store.db.execute("UPDATE sources SET title='other'")
        self.store.db.commit()
        with self.assertRaises(ValueError):
            self.store.chunks(self.scope)
        self.store.db.execute("UPDATE sources SET title='title'")
        self.store.db.execute("UPDATE chunks SET end=2")
        self.store.db.commit()
        with self.assertRaises(ValueError):
            self.store.chunks(self.scope)

    async def test_vector_blob_corruption_cannot_enter_similarity(self):
        self.store.put(self.scope, "event", "car")
        await prepare(self.store, self.scope, self.embedding)
        self.store.db.execute("UPDATE vectors SET value=x'00000000'")
        self.store.db.commit()
        found, status = await search(self.store, self.scope, "car", self.embedding)
        self.assertTrue(status["degraded"])
        self.assertEqual(found[0].text, "car")

    async def test_query_timeout_falls_back_without_forcing_reader(self):
        self.store.put(self.scope, "event", "car is here")
        await prepare(self.store, self.scope, self.embedding)
        found, status = await search(
            self.store, self.scope, "car", TimeoutEmbedding(), timeout=0.01
        )
        self.assertTrue(status["degraded"])
        self.assertEqual(found[0].source, "event")

    async def test_index_timeout_commits_no_partial_vectors(self):
        self.store.put(self.scope, "event", "car")
        result = await prepare(self.store, self.scope, TimeoutEmbedding(), timeout=0.01)
        self.assertTrue(result["degraded"])
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 0
        )
        found, status = await search(self.store, self.scope, "car", self.embedding)
        self.assertTrue(status["degraded"])
        self.assertEqual(found[0].text, "car")

    async def test_incomplete_index_is_explicit_lexical_fallback(self):
        self.store.put(self.scope, "a", "automobile")
        self.store.put(self.scope, "b", "car")
        first = self.store.chunks(self.scope)[0]
        self.store.save_vectors(
            self.scope, [(first, [1, 0, 0])], self.embedding.model, 3
        )
        found, status = await search(self.store, self.scope, "car", self.embedding)
        self.assertTrue(status["degraded"])
        self.assertEqual(found[0].source, "b")
        self.assertEqual(self.embedding.calls, 0)

    async def test_invalid_batch_rolls_back_all_vector_writes(self):
        self.store.put(self.scope, "a", "car")
        self.store.put(self.scope, "b", "bicycle")
        a, b = self.store.chunks(self.scope)
        with self.assertRaises(ValueError):
            self.store.save_vectors(
                self.scope,
                [(a, [1, 0, 0]), (b, [math.nan, 0, 0])],
                self.embedding.model,
                3,
            )
        self.assertEqual(
            self.store.db.execute("SELECT COUNT(*) FROM vectors").fetchone()[0], 0
        )

    def test_rrf_uses_rank_not_incompatible_raw_scores(self):
        left = [(0, 0.001), (1, 0.0005)]
        right = [(1, 10**9), (2, 10**8)]
        ranking = rrf([left, right])
        self.assertEqual(ranking[0][0], 1)
        self.assertEqual(ranking, rrf([[(i, s * 1000) for i, s in left], right]))

    def test_zero_nonfinite_and_dimension_invalid_vectors_rejected(self):
        for vector, dim in [
            ([0.0, 0.0], 2),
            ([float("inf"), 1.0], 2),
            ([float("nan"), 0.0], 2),
            ([1.0], 2),
        ]:
            with self.assertRaises(ValueError):
                normalize(vector, dim)

    def test_budget_includes_reference_and_unicode_text(self):
        text = "汽车的维修并未取消。\n" * 250
        self.store.put(self.scope, "event", text)
        chunks = self.store.chunks(self.scope)
        result = pack(self.store, self.scope, chunks, 5000, lambda t: len(t.encode()))
        self.assertLessEqual(len(result["text"].encode()), 5000)
        self.assertTrue(result["references"])
        for ref in result["references"]:
            self.assertIn(text[ref["start"] : ref["end"]], result["text"])
        self.assertEqual(pack(self.store, self.scope, chunks, 1, len)["references"], [])

    def test_pack_revalidates_scope_and_uses_original_not_supplied_text(self):
        self.store.put(self.scope, "event", "source truth")
        c = self.store.chunks(self.scope)[0]
        result = pack(
            self.store, self.scope, [replace(c, text="forged answer")], 1000, len
        )
        self.assertIn("source truth", result["text"])
        self.assertNotIn("forged answer", result["text"])
        with self.assertRaises(ValueError):
            pack(self.store, self.other, [c], 1000, len)

    def test_adjacent_overlap_is_merged_without_losing_corrections(self):
        text = "Prior: Monday.\nCorrection: not Monday; now Tuesday.\n" * 80
        self.store.put(self.scope, "event", text)
        result = pack(self.store, self.scope, self.store.chunks(self.scope), 10000, len)
        self.assertEqual(len(result["references"]), 1)
        self.assertEqual(result["references"][0]["end"], len(text))
        self.assertTrue(result["text"].endswith(text))

    async def test_empty_and_chinese_queries(self):
        self.store.put(self.scope, "event", "汽车故障代码 E1234，未修复。")
        found, _ = await search(self.store, self.scope, "汽车故障", mode="bm25")
        self.assertEqual(found[0].source, "event")
        found, _ = await search(self.store, self.scope, "", mode="bm25")
        self.assertEqual(found, [])
        found, _ = await search(self.store, self.scope, "E1234", mode="bm25")
        self.assertEqual(found[0].source, "event")

    def test_long_source_memory_does_not_scale_as_full_body_per_chunk(self):
        import tracemalloc

        source = "A generic source paragraph with precise facts. " * 2200
        self.store.put(self.scope, "event", source)
        tracemalloc.start()
        try:
            chunks = self.store.chunks(self.scope)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertTrue(all(c.text == source[c.start : c.end] for c in chunks))
        self.assertLess(peak, len(source.encode()) * 10)

    async def test_branch_isolation_matches_sdk_reference_identity(self):
        left = replace(self.scope, branch="branch-a")
        right = replace(self.scope, branch="branch-b")
        self.store.put(left, "same-event", "car for branch a")
        self.store.put(right, "same-event", "bicycle for branch b")
        await prepare(self.store, left, self.embedding)
        await prepare(self.store, right, self.embedding)
        found, status = await search(self.store, left, "bicycle", self.embedding)
        self.assertEqual(status["candidate_count"], 1)
        self.assertTrue(all(c.text == "car for branch a" for c in found))
        with self.assertRaises(ValueError):
            self.store.read(left, "same-event", digest("bicycle for branch b"), 0, 7)


if __name__ == "__main__":
    unittest.main()
