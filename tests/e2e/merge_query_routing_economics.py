"""Merge complete rerun pairs without duplicate weighting or hiding attempt costs."""

import hashlib
import json
from pathlib import Path

from query_routing_economics import summarize


def merge(original, recovery, output, *, require_complete_usage=True):
    original, recovery, output = map(Path, (original, recovery, output))
    base_bytes = (original / "experiment-manifest.json").read_bytes()
    base = json.loads(base_bytes)
    retry = json.loads((recovery / "experiment-manifest.json").read_text())
    basis = retry["rerun_basis"]
    if basis["original_manifest_sha256"] != hashlib.sha256(base_bytes).hexdigest():
        raise ValueError("rerun manifest does not identify this original experiment")
    operational_fields = {
        "cases",
        "concurrency",
        "selected_jobs",
        "rerun_basis",
        "preload_agents",
    }
    for key in (base.keys() | retry.keys()) - operational_fields:
        if base.get(key) != retry.get(key):
            raise ValueError(f"rerun changed the experiment configuration: {key}")
    base_cases = {c["id"]: c for c in base["cases"]}
    if any(base_cases.get(c["id"]) != c for c in retry["cases"]):
        raise ValueError("rerun changed a task or its initial state")

    def lines(folder, name):
        return [json.loads(line) for line in (folder / name).read_text().splitlines()]

    old_rows = lines(original, "paired-results.jsonl")
    new_rows = lines(recovery, "paired-results.jsonl")
    old_audit, new_audit = (
        lines(original, "audit.jsonl"),
        lines(recovery, "audit.jsonl"),
    )
    summarize(old_rows, old_audit)
    summarize(new_rows, new_audit)
    if require_complete_usage and any(
        row["unknown_usage_attempts"] for row in new_rows
    ):
        raise ValueError("rerun accounting is still incomplete")
    affected = {(r["cohort"], r["id"]) for r in new_rows}
    old_affected = [r for r in old_rows if (r["cohort"], r["id"]) in affected]
    if len(old_affected) != len(new_rows):
        raise ValueError("rerun must replace complete existing pairs")
    # Both arms are replaced, even when a rerun answer is worse. Answer quality
    # never determines which of the repeated observations enters the result.
    rows = [r for r in old_rows if (r["cohort"], r["id"]) not in affected] + new_rows
    audit = [
        a
        for a in old_audit
        if (a.get("cohort"), a.get("experiment_case_id")) not in affected
    ] + new_audit
    result = summarize(rows, audit)
    if base.get("public_benchmarks"):
        from query_routing_benchmark_report import build_benchmark_report

        result["public_benchmarks"] = build_benchmark_report(rows, audit, base)
    result["manifest_sha256"] = hashlib.sha256(base_bytes).hexdigest()
    prior_path = original / "economics-summary.json"
    prior = (
        json.loads(prior_path.read_text()).get("recovery", {})
        if prior_path.exists()
        else {}
    )
    old_cost = sum(r["cost_cny"] for r in old_rows)
    old_unknown = sum(r["unknown_usage_attempts"] for r in old_rows)
    result["recovery"] = {
        "reason": basis["reason"],
        "replaced_pairs": len(affected),
        "original_http_turns": len(old_rows),
        "rerun_http_turns": len(new_rows),
        "selected_http_turns": len(rows),
        "original_missing_usage_attempts": sum(
            r["unknown_usage_attempts"] for r in old_rows
        ),
        "discarded_observations": [
            {
                k: r[k]
                for k in (
                    "id",
                    "cohort",
                    "arm",
                    "success",
                    "cost_cny",
                    "unknown_usage_attempts",
                )
            }
            for r in old_affected
        ],
        "experiment_known_cost_cny": prior.get("experiment_known_cost_cny", old_cost)
        + sum(r["cost_cny"] for r in new_rows),
        "experiment_unknown_usage_attempts": prior.get(
            "experiment_unknown_usage_attempts", old_unknown
        )
        + sum(r["unknown_usage_attempts"] for r in new_rows),
        "experiment_http_turns": prior.get("experiment_http_turns", len(old_rows))
        + len(new_rows),
        "superseded_known_cost_cny": prior.get("superseded_known_cost_cny", 0)
        + sum(r["cost_cny"] for r in old_affected),
        "previous_recovery": prior or None,
        "require_complete_usage": require_complete_usage,
        "note": "Comparison uses complete replacement pairs once each. All original attempt costs remain in the separate experiment ledger; missing original usage is still unknown, not retroactively inferred from reruns.",
    }
    output.mkdir(parents=True, exist_ok=False)
    (output / "economics-summary.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2)
    )
    (output / "paired-results.jsonl").write_text(
        "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows)
    )
    (output / "audit.jsonl").write_text(
        "".join(json.dumps(a, ensure_ascii=False) + "\n" for a in audit)
    )
    (output / "experiment-manifest.json").write_bytes(base_bytes)
    return result


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("original")
    parser.add_argument("recovery")
    parser.add_argument("output")
    parser.add_argument(
        "--allow-unknown-usage",
        action="store_true",
        help="Keep unmeasured costs explicitly unknown when merging an implementation repair.",
    )
    args = parser.parse_args()
    result = merge(
        args.original,
        args.recovery,
        args.output,
        require_complete_usage=not args.allow_unknown_usage,
    )
    print(
        json.dumps(
            {"cohorts": result["cohorts"], "recovery": result["recovery"]},
            ensure_ascii=False,
            indent=2,
        )
    )
