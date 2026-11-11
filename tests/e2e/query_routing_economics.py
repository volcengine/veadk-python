"""Measured usage pricing and paired quality/cost analysis for live experiments."""

import random
import re
import statistics
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from zoneinfo import ZoneInfo

PRICE_SOURCE = "https://docs.volcengine.com/docs/zh/ark/model-pricing.md"
DECISION_PRICE_SOURCE = "https://docs.volcengine.com/docs/zh/ark/decision-model.md"


def price(record):
    """CNY using console screenshots and separately verified public cache rates.

    Missing usage is unknown cost, never free. Reasoning tokens are already
    included in output_tokens/completion_tokens and must not be counted twice.
    """
    usage = record.get("usage")
    if not isinstance(usage, dict):
        return None
    decision = record["endpoint"].endswith("/systemone")
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens"))
    output_tokens = (
        0 if decision else usage.get("output_tokens", usage.get("completion_tokens"))
    )
    details = (
        usage.get("input_tokens_details", usage.get("prompt_tokens_details")) or {}
    )
    cached = 0 if decision else details.get("cached_tokens", 0)
    if (
        any(type(n) is not int or n < 0 for n in (input_tokens, output_tokens, cached))
        or cached > input_tokens
    ):
        return None
    if record["model"] == "doubao-seed-2-1-lite-260915":
        rates = (0.8, 0.16, 2.7)
    elif record["model"] == "doubao-seed-2-1-pro-260915":
        # User-provided console screenshot (2026-11-12). The screenshot omits
        # cache pricing: retain the verified public rate, never infer a discount.
        rates = (5.406, 1.2, 27.03)
    elif record["model"] == "kimi-k3-1-pro-261024":
        rates = (13, 1.3, 68)
    elif record["model"] in (
        "deepseek-v4-1-flash-261017",
        "deepseek-v4-1-flash-economy-261017",
    ):
        finished = datetime.fromtimestamp(
            record["completed_at"], ZoneInfo("Asia/Shanghai")
        )
        peak = finished.weekday() < 5 and (
            9 <= finished.hour < 12 or 14 <= finished.hour < 18
        )
        rates = (2, 0.04, 8) if peak else (1, 0.02, 4)
        if record["model"] == "deepseek-v4-1-flash-economy-261017":
            rates = tuple(rate * 0.8 for rate in rates)
    else:
        return None
    if decision:
        return input_tokens * rates[0] / 1_000_000
    return (
        (input_tokens - cached) * rates[0]
        + cached * rates[1]
        + output_tokens * rates[2]
    ) / 1_000_000


def answer_ok(case, result):
    if result.get("errors") or not result.get("answer"):
        return False
    value = result["answer"].strip()
    expected = str(case.get("expected", "")).strip()
    if case["oracle"] == "gsm8k":
        match = re.search(r"#### (\-?[0-9\.\,]+)", value)
        return bool(match) and match[1].strip().replace(",", "") == expected.replace(
            ",", ""
        )
    if case["oracle"] == "bbh":
        prefix = "so the answer is "
        if prefix in value.lower():
            value = value[value.lower().rfind(prefix) + len(prefix) :]
        return value.strip().rstrip(".").casefold() == expected.casefold()
    if case["oracle"] == "number":
        try:
            return Decimal(value.replace(",", "")) == Decimal(expected.replace(",", ""))
        except InvalidOperation:
            return False
    if case["oracle"] == "urgent_care":
        # A narrow synthetic emergency oracle; not a medical quality benchmark.
        return bool(
            re.search(r"emergency|ambulance|911|999|112|120", value, re.IGNORECASE)
        ) and not bool(
            re.search(
                r"(?:do not|don't|no need to)\s+(?:call|seek)", value, re.IGNORECASE
            )
        )
    if case["oracle"] == "nested_workflow":
        return value == expected
    if case["oracle"] == "workflow":
        responses = [
            p["functionResponse"]
            for event in result["events"]
            for p in (event.get("content") or {}).get("parts", [])
            if p.get("functionResponse")
        ]
        completed = {
            r["response"].get("result") for r in responses if r["response"].get("done")
        }
        return value == expected and all(
            f"DONE-{w}" in completed for w in case["workflows"]
        )
    return value == expected


def percentile(values, p):
    ordered = sorted(values)
    return (
        ordered[min(int((len(ordered) - 1) * p), len(ordered) - 1)] if ordered else None
    )


def summarize(rows, attempts):
    """Pair by case/turn; resample whole sessions within dataset strata."""
    by_turn = defaultdict(list)
    for attempt in attempts:
        if attempt["kind"] == "transport_end":
            by_turn[
                (
                    attempt.get("cohort"),
                    attempt.get("arm"),
                    attempt.get("experiment_case_id"),
                )
            ].append(attempt)
    for row in rows:
        calls = by_turn[(row["cohort"], row["arm"], row["id"])]
        costs = [price(call) for call in calls]
        row["attempts"] = len(calls)
        row["unknown_usage_attempts"] = sum(c is None for c in costs)
        row["cost_cny"] = sum(c for c in costs if c is not None)
        row["decision_cost_cny"] = sum(
            price(c) or 0 for c in calls if c["endpoint"].endswith("/systemone")
        )
        row["model_calls"] = sum(
            not c["endpoint"].endswith("/systemone") for c in calls
        )
        row["decision_calls"] = sum(c["endpoint"].endswith("/systemone") for c in calls)
        row["execution_models"] = sorted(
            {c["model"] for c in calls if not c["endpoint"].endswith("/systemone")}
        )

    cohorts = {}
    for cohort in sorted({r["cohort"] for r in rows}):
        selected = [r for r in rows if r["cohort"] == cohort]
        pair_arms = defaultdict(list)
        for row in selected:
            pair_arms[row["id"]].append(row["arm"])
        if any(sorted(arms) != ["routed", "strong"] for arms in pair_arms.values()):
            raise ValueError("experiment contains incomplete pairs")
        arms = {}
        for arm in ("strong", "routed"):
            group = [r for r in selected if r["arm"] == arm]
            success = sum(r["success"] for r in group)
            total = sum(r["cost_cny"] for r in group)
            arms[arm] = {
                "turns": len(group),
                "successes": success,
                "success_rate": success / len(group),
                "cost_cny": total,
                "cost_per_turn": total / len(group),
                "cost_per_success": total / success if success else None,
                "decision_cost_cny": sum(r["decision_cost_cny"] for r in group),
                "unknown_usage_attempts": sum(
                    r["unknown_usage_attempts"] for r in group
                ),
                "transport_attempts": sum(r["attempts"] for r in group),
                "model_calls": sum(r["model_calls"] for r in group),
                "latency_p50_ms": percentile([r["elapsed_ms"] for r in group], 0.5),
                "latency_p95_ms": percentile([r["elapsed_ms"] for r in group], 0.95),
            }
        pairs = defaultdict(dict)
        for row in selected:
            pairs[row["id"]][row["arm"]] = row
        if any(set(pair) != {"strong", "routed"} for pair in pairs.values()):
            raise ValueError("experiment contains incomplete pairs")
        losses = sum(
            p["strong"]["success"] and not p["routed"]["success"]
            for p in pairs.values()
        )
        wins = sum(
            p["routed"]["success"] and not p["strong"]["success"]
            for p in pairs.values()
        )
        cluster = defaultdict(list)
        for pair in pairs.values():
            cluster[(pair["strong"]["category"], pair["strong"]["cluster"])].append(
                pair
            )
        strata = defaultdict(list)
        for (category, _), pair_group in cluster.items():
            strata[category].append(pair_group)
        rng = random.Random(59182)
        differences, savings = [], []
        for _ in range(4000):
            sample = [
                pair
                for groups in strata.values()
                for group in rng.choices(groups, k=len(groups))
                for pair in group
            ]
            differences.append(
                statistics.mean(
                    int(p["routed"]["success"]) - int(p["strong"]["success"])
                    for p in sample
                )
            )
            strong_cost = sum(p["strong"]["cost_cny"] for p in sample)
            savings.append(
                1 - sum(p["routed"]["cost_cny"] for p in sample) / strong_cost
                if strong_cost
                else 0
            )
        # Zero discordance makes a naive bootstrap degenerate. A conservative
        # one-sided exact bound on loss-cluster probability prevents claiming
        # certainty from a finite all-agree sample. This is conditional on the
        # sampled benchmark strata, not a confidence claim for production.
        lower_quality = percentile(differences, 0.025)
        if losses == 0:
            lower_quality = min(lower_quality, -(1 - 0.025 ** (1 / len(cluster))))
        high_risk = [r for r in selected if r["arm"] == "routed" and r.get("high_risk")]
        downgrades = sum(r.get("route") != "strong" for r in high_risk)
        unknown = sum(a["unknown_usage_attempts"] for a in arms.values())
        start_ids = {
            a["attempt_id"]
            for a in attempts
            if a["kind"] == "transport_start" and a.get("cohort") == cohort
        }
        end_ids = {
            a["attempt_id"]
            for a in attempts
            if a["kind"] == "transport_end" and a.get("cohort") == cohort
        }
        missing = len(start_ids - end_ids)
        saving = (
            1 - arms["routed"]["cost_cny"] / arms["strong"]["cost_cny"]
            if arms["strong"]["cost_cny"]
            else 0
        )
        cohorts[cohort] = {
            "arms": arms,
            "pairs": len(pairs),
            "clusters": len(cluster),
            "paired_losses": losses,
            "paired_wins": wins,
            "quality_delta_pp": 100
            * (arms["routed"]["success_rate"] - arms["strong"]["success_rate"]),
            "quality_delta_95ci_pp": [
                100 * lower_quality,
                100 * percentile(differences, 0.975),
            ],
            "saving_percent": 100 * saving,
            "saving_95ci_percent": [
                100 * percentile(savings, 0.025),
                100 * percentile(savings, 0.975),
            ],
            "high_risk_turns": len(high_risk),
            "high_risk_downgrades": downgrades,
            "missing_transport_completions": missing,
            "gates": {
                "quality": lower_quality >= -0.01,
                "cost": unknown == 0
                and missing == 0
                and percentile(savings, 0.025) >= 0.20,
                "high_risk": len(high_risk) > 0 and downgrades == 0,
            },
        }
    return {
        "cohorts": cohorts,
        "price_source": PRICE_SOURCE,
        "decision_price_source": DECISION_PRICE_SOURCE,
        "price_basis": "Execution input/output: user-provided console screenshots dated 2026-11-12. Cache hits: separately verified public prices, no inferred discount. SystemOne: actual decision-request model input rate, free output. Not an account invoice.",
        "interval_method": "4000 paired stratified session-cluster bootstrap replicates; conservative exact loss-cluster bound with zero losses; 95% intervals conditional on this workload",
        "rows": rows,
    }
