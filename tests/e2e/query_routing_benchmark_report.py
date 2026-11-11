"""Task-weighted benchmark statistics; multi-turn tasks receive one vote."""

import random
from collections import Counter, defaultdict


def aggregate_tasks(rows, attempts, manifest):
    cases = {c["id"]: c for c in manifest["cases"]}
    logical = Counter()
    for attempt in attempts:
        if attempt["kind"] == "model" and attempt.get("experiment_case_id"):
            logical[
                (attempt["cohort"], attempt["arm"], attempt["experiment_case_id"])
            ] += 1
    groups = defaultdict(list)
    for row in rows:
        groups[(row["cohort"], row["arm"], row["cluster"])].append(row)
    tasks = []
    for (cohort, arm, identifier), group in groups.items():
        group.sort(key=lambda r: int(r["id"].rsplit(":", 1)[1]))
        case = cases[identifier]
        tasks.append(
            {
                "id": identifier,
                "cluster": case.get("task_group", identifier),
                "cohort": cohort,
                "arm": arm,
                "source": case["source"],
                "category": case["category"],
                "condition": case.get("condition", "standard"),
                "protocol": case["protocol"],
                "success": all(bool(r["success"]) for r in group),
                "http_turns": len(group),
                "cost_cny": sum(r["cost_cny"] for r in group),
                "decision_cost_cny": sum(r["decision_cost_cny"] for r in group),
                "unknown_usage_attempts": sum(
                    r["unknown_usage_attempts"] for r in group
                ),
                "model_attempts": sum(r["model_calls"] for r in group),
                "llm_calls": sum(logical[(cohort, arm, r["id"])] for r in group),
                "decision_calls": sum(r["decision_calls"] for r in group),
                "elapsed_ms": sum(r["elapsed_ms"] for r in group),
                "routes": Counter(r.get("route") or "none" for r in group),
                "route_reasons": Counter(
                    route["reason"]
                    for r in group
                    for route in r.get("routes", [])
                    if "reason" in route
                ),
                "execution_models": sorted(
                    {m for r in group for m in r["execution_models"]}
                ),
                "attack_success": any(
                    r.get("native_score", {}).get("attack_success", False)
                    for r in group
                ),
                "native_scores": [r.get("native_score") for r in group],
                "answers": [r["answer"] for r in group],
                "errors": [e for r in group for e in r.get("errors", [])],
                "context_chars": case.get("context_chars"),
                "budget_band": case.get("budget_band"),
            }
        )
    return tasks


def paired_statistics(tasks, *, resamples=2000):
    pairs = defaultdict(dict)
    for row in tasks:
        if row["arm"] in pairs[row["id"]]:
            raise ValueError("duplicate task observation")
        pairs[row["id"]][row["arm"]] = row
    if not pairs or any(set(p) != {"strong", "routed"} for p in pairs.values()):
        raise ValueError("task comparisons require complete pairs")
    values = list(pairs.values())
    arms = {}
    for arm in ("strong", "routed"):
        selected = [pair[arm] for pair in values]
        successes = sum(r["success"] for r in selected)
        cost = sum(r["cost_cny"] for r in selected)
        arms[arm] = {
            "tasks": len(selected),
            "successes": successes,
            "success_rate": successes / len(selected),
            "cost_cny": cost,
            "cost_per_task": cost / len(selected),
            "cost_per_success": cost / successes if successes else None,
            **{
                key: sum(r[key] for r in selected)
                for key in (
                    "http_turns",
                    "unknown_usage_attempts",
                    "model_attempts",
                    "llm_calls",
                    "decision_calls",
                    "decision_cost_cny",
                    "attack_success",
                )
            },
        }
    wins = sum(p["routed"]["success"] and not p["strong"]["success"] for p in values)
    losses = sum(p["strong"]["success"] and not p["routed"]["success"] for p in values)
    buckets = defaultdict(lambda: defaultdict(list))
    for pair in values:
        r = pair["strong"]
        buckets[(r["source"], r["category"])][r["cluster"]].append(pair)
    pooled = {source for (source, _), groups in buckets.items() if len(groups) < 2}
    # One task per category (for example MMMU disciplines) cannot estimate
    # within-category sampling variance. Pool that family's observed mixture.
    sampling_buckets = defaultdict(lambda: defaultdict(list))
    for pair in values:
        r = pair["strong"]
        category = "all" if r["source"] in pooled else r["category"]
        sampling_buckets[(r["source"], category)][r["cluster"]].append(pair)
    strata = [list(groups.values()) for groups in sampling_buckets.values()]
    rng = random.Random(731915)
    deltas = []
    savings = []
    for _ in range(resamples):
        sample = [
            pair
            for groups in strata
            for cluster in rng.choices(groups, k=len(groups))
            for pair in cluster
        ]
        deltas.append(
            100
            * sum(p["routed"]["success"] - p["strong"]["success"] for p in sample)
            / len(sample)
        )
        baseline = sum(p["strong"]["cost_cny"] for p in sample)
        if baseline:
            savings.append(
                100 * (1 - sum(p["routed"]["cost_cny"] for p in sample) / baseline)
            )

    def interval(data):
        data = sorted(data)
        return (
            [
                data[int(len(data) * 0.025)],
                data[min(len(data) - 1, int(len(data) * 0.975))],
            ]
            if data
            else None
        )

    complete = [
        p
        for p in values
        if not p["strong"]["unknown_usage_attempts"]
        and not p["routed"]["unknown_usage_attempts"]
    ]
    baseline = sum(p["strong"]["cost_cny"] for p in complete)
    return {
        "arms": arms,
        "pairs": len(values),
        "paired_wins": wins,
        "paired_losses": losses,
        "quality_delta_pp": 100 * (wins - losses) / len(values),
        "quality_delta_95ci_pp": interval(deltas),
        "known_cost_saving_percent": 100
        * (1 - arms["routed"]["cost_cny"] / arms["strong"]["cost_cny"])
        if arms["strong"]["cost_cny"]
        else None,
        "known_cost_saving_95ci_percent": interval(savings),
        "complete_cost_pairs": len(complete),
        "complete_pair_saving_percent": 100
        * (1 - sum(p["routed"]["cost_cny"] for p in complete) / baseline)
        if baseline
        else None,
        "pooled_category_families": sorted(pooled),
        "interval_note": "Paired cluster bootstrap within benchmark/category; families with singleton categories use the observed family mixture instead. Small samples and zero observed discordance do not establish equivalence.",
    }


def build_benchmark_report(rows, attempts, manifest):
    tasks = aggregate_tasks(rows, attempts, manifest)
    cells = []
    for cohort in manifest["cohorts"]:
        selected = [r for r in tasks if r["cohort"] == cohort]
        for source in ["all", *sorted({r["source"] for r in selected})]:
            for condition in ["clean", "attack"] if source == "AgentDojo" else ["all"]:
                group = [
                    r
                    for r in selected
                    if (source == "all" or r["source"] == source)
                    and (condition == "all" or r["condition"] == condition)
                ]
                if not group:
                    continue
                cells.append(
                    {
                        "cohort": cohort,
                        "source": source,
                        "condition": condition,
                        **paired_statistics(group),
                    }
                )
    return {
        "tasks": tasks,
        "cells": cells,
        "counting_unit": "One vote per complete task; all actual HTTP turns and model attempts are charged. AgentDojo clean/attack are separate conditions, correlated by task group.",
    }
