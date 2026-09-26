import math
import unittest
from veadk.context.score_fusion import distribution_fusion as fuse


class FusionTests(unittest.TestCase):
    def test_sample_standard_deviation(self):
        values = dict(fuse([([(0, 0.0), (1, 2.0)], 1)]))
        self.assertAlmostEqual(values[0], 0.5 - 1 / (6 * math.sqrt(2)))
        self.assertAlmostEqual(values[1], 0.5 + 1 / (6 * math.sqrt(2)))

    def test_flat_singleton_and_missing_ids(self):
        self.assertEqual(fuse([([], 1)]), [])
        self.assertEqual(
            fuse([([(2, 5), (1, 5)], 1), ([(3, -9)], 2)]),
            [(3, 1.0), (1, 0.5), (2, 0.5)],
        )

    def test_preserves_magnitude_information(self):
        # RRF is identical for these lists. Strong support in the first
        # retriever should differ from a near tie when the other is reversed.
        a = fuse(
            [([(0, 3.0), (1, 2.0), (2, 1.0)], 1), ([(2, 3.0), (1, 2.0), (0, 1.0)], 1)]
        )
        b = fuse(
            [([(0, 100.0), (1, 2.0), (2, 1.0)], 1), ([(2, 3.0), (1, 2.0), (0, 1.0)], 1)]
        )
        self.assertAlmostEqual(dict(a)[0], dict(a)[2])
        self.assertGreater(dict(b)[0], dict(a)[0])

    def test_no_clipping_outlier(self):
        values = dict(fuse([([(i, 100 if i == 0 else 0) for i in range(40)], 1)]))
        self.assertGreater(values[0], 1.0)

    def test_affine_scale_and_input_order(self):
        data = [[(0, -2), (1, 4), (2, 9)], [(1, 0.1), (0, 0.7)]]
        first = dict(fuse([(data[0], 3), (data[1], 0.25)]))
        second = dict(
            fuse(
                [
                    (list(reversed([(i, s * 1000 + 23) for i, s in data[0]])), 3),
                    (data[1], 0.25),
                ]
            )
        )
        for key in first:
            self.assertAlmostEqual(first[key], second[key])

    def test_extreme_finite_scores(self):
        values = fuse([([(0, -1e308), (1, 1e308)], 1)])
        self.assertTrue(all(math.isfinite(v) for _, v in values))
        self.assertEqual(values[0][0], 1)

    def test_invalid_inputs(self):
        for ranking, weight in [
            ([(0, 1), (0, 2)], 1),
            ([(0, float("nan"))], 1),
            ([(True, 2)], 1),
            ([(0, 2)], float("inf")),
            ([(0, 2)], 0),
            ([(i, 1) for i in range(101)], 1),
        ]:
            with self.subTest(
                ranking_length=len(ranking), weight_type=type(weight).__name__
            ):
                with self.assertRaises(ValueError):
                    fuse([(ranking, weight)])
