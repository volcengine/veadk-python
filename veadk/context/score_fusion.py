"""Bounded distribution normalization for shared context evidence retrieval."""

import math


def distribution_fusion(rankings):
    """Normalize each finite score list by sample mean ±3 sigma, then weight.

    Constant lists contribute 0.5 per present ID; absent IDs contribute zero.
    No clipping or query-specific tuning. Positive affine rescaling of any
    component preserves its contribution. Duplicate IDs fail closed.
    """
    totals = {}
    for ranking, weight in rankings:
        if (
            type(weight) not in (int, float)
            or not math.isfinite(weight)
            or not 0 < weight <= 10
        ):
            raise ValueError("invalid_weight")
        if len(ranking) > 100:
            raise ValueError("ranking_limit")
        seen = set()
        for index, score in ranking:
            if type(index) is not int or index < 0 or index in seen:
                raise ValueError("invalid_id")
            if type(score) not in (int, float) or not math.isfinite(score):
                raise ValueError("invalid_score")
            seen.add(index)
        if not ranking:
            continue
        scale = max(abs(score) for _, score in ranking) or 1.0
        values = [score / scale for _, score in ranking]
        mean = math.fsum(values) / len(values)
        sigma = (
            math.hypot(*(v - mean for v in values)) / math.sqrt(len(values) - 1)
            if len(values) > 1
            else 0.0
        )
        for (index, _), value in zip(ranking, values):
            normalized = 0.5 + (value - mean) / (6 * sigma) if sigma else 0.5
            totals[index] = totals.get(index, 0.0) + weight * normalized
    return sorted(totals.items(), key=lambda pair: (-pair[1], pair[0]))
