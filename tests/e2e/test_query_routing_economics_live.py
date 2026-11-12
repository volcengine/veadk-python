"""Paired real HTTP experiment; run only with live opt-in and a frozen manifest."""

import asyncio
import hashlib
import json
import os
import random
import time
from pathlib import Path

import httpx
import pytest
from query_routing_economics import answer_ok, summarize
from test_query_routing_http_live import AgentResponseError, server, turn  # noqa: F401

pytestmark = [
    pytest.mark.query_routing_live,
    pytest.mark.skipif(
        os.getenv("VEADK_QUERY_ROUTING_LIVE") != "1"
        or not os.getenv("VEADK_ROUTING_EXPERIMENT_MANIFEST")
        or not os.getenv("MODEL_AGENT_API_KEY"),
        reason="requires explicit live opt-in, credentials and a frozen manifest",
    ),
]


@pytest.mark.asyncio
async def test_paired_quality_and_cost(server):  # noqa: F811 - imported pytest fixture
    manifest_path = Path(os.environ["VEADK_ROUTING_EXPERIMENT_MANIFEST"])
    raw = manifest_path.read_bytes()
    assert (
        hashlib.sha256(raw).hexdigest()
        == manifest_path.with_suffix(".sha256").read_text().strip()
    )
    manifest = json.loads(raw)
    root = server["root"]
    (root / "experiment-manifest.json").write_bytes(raw)
    rows = []
    randomizer = random.Random(731912)
    jobs = [
        (case, cohort)
        for case in manifest["cases"]
        for cohort in manifest.get("cohorts", ["pro"])
    ]
    if manifest.get("selected_jobs"):
        selected_jobs = {tuple(job) for job in manifest["selected_jobs"]}
        jobs = [
            (case, cohort)
            for case, cohort in jobs
            if (cohort, case["id"]) in selected_jobs
        ]
    randomizer.shuffle(jobs)
    gate = asyncio.Semaphore(manifest.get("concurrency", 4))

    async def pair(case, cohort):
        async with gate:
            protocol = "_chat" if case["protocol"] == "chat" else ""
            suffix = (f"_{cohort}" if cohort != "deepseek" else "") + (
                "_nested" if case.get("nested") else ""
            )
            apps = {
                "strong": f"baseline_economy{suffix}{protocol}",
                "routed": f"economy{suffix}{protocol}",
            }
            if manifest.get("public_benchmarks"):
                from query_routing_public_benchmarks import benchmark_app

                apps = {
                    arm: benchmark_app(case, cohort, arm)
                    for arm in manifest.get("arms", ["strong", "routed"])
                }
            order = list(manifest.get("arms", ["strong", "routed"]))
            random.Random(case["id"] + cohort).shuffle(order)
            async with httpx.AsyncClient(
                base_url=server["url"],
                timeout=manifest.get("http_timeout", 180),
                trust_env=False,
            ) as client:
                identities = {}
                for arm in order:
                    app = apps[arm]
                    response = await client.post(
                        f"/apps/{app}/users/paired/sessions",
                        json={"state": case.get("state", {})},
                    )
                    response.raise_for_status()
                    identities[arm] = {
                        "appName": app,
                        "userId": "paired",
                        "sessionId": response.json()["id"],
                    }
                for index, item in enumerate(case.get("turns", [case])):
                    case_id = f"{case['id']}:{index}"
                    for arm in order:
                        started = time.monotonic()
                        try:
                            result = await turn(
                                client,
                                identities[arm],
                                item["prompt"],
                                stream=case["protocol"] == "responses",
                                parts=item.get("parts"),
                                metadata={
                                    "experiment_case_id": case_id,
                                    "arm": arm,
                                    "cohort": cohort,
                                },
                            )
                        except AgentResponseError as exc:
                            result = exc.result
                        except (httpx.HTTPError, AssertionError) as exc:
                            result = {
                                "events": [],
                                "answer": "",
                                "routes": [],
                                "elapsed_ms": round(
                                    (time.monotonic() - started) * 1000, 2
                                ),
                                "errors": [{"type": type(exc).__name__}],
                            }
                        routes = result.get("routes", [])
                        success = (
                            answer_ok(item, result)
                            if item.get("oracle") != "upstream"
                            else None
                        )
                        if case.get("nested"):
                            audit = [
                                json.loads(line)
                                for line in (root / "audit.jsonl")
                                .read_text()
                                .splitlines()
                            ]
                            success = success and any(
                                r.get("kind") == "workflow_completed"
                                and r.get("experiment_case_id") == case_id
                                and r.get("arm") == arm
                                and r.get("cohort") == cohort
                                for r in audit
                            )
                        row = {
                            "id": case_id,
                            "cluster": case["id"],
                            "category": case["category"],
                            "source": case["source"],
                            "cohort": cohort,
                            "arm": arm,
                            "protocol": case["protocol"],
                            "expected": item.get("expected"),
                            "high_risk": item.get("high_risk", False),
                            "route": routes[0]["route"] if routes else None,
                            "success": success,
                            **result,
                        }
                        rows.append(row)
                        with (root / "paired-results.jsonl").open("a") as output:
                            output.write(json.dumps(row, ensure_ascii=False) + "\n")
            print(
                f"completed {cohort}/{case['id']} ({len(rows)} HTTP turns)", flush=True
            )

    await asyncio.gather(*(pair(case, cohort) for case, cohort in jobs))
    if manifest.get("public_benchmarks"):
        from query_routing_benchmark_scoring import score_public_rows

        score_public_rows(manifest, rows, root)
    attempts = [
        json.loads(line) for line in (root / "audit.jsonl").read_text().splitlines()
    ]
    if manifest.get("matched_execution"):
        from query_routing_calibration import summarize_comparisons

        report = summarize_comparisons(rows, attempts)
    else:
        report = summarize(rows, attempts)
    if manifest.get("public_benchmarks") and not manifest.get("matched_execution"):
        from query_routing_benchmark_report import build_benchmark_report

        report["public_benchmarks"] = build_benchmark_report(rows, attempts, manifest)
    (root / "accounted-results.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    )
    report["manifest_sha256"] = hashlib.sha256(raw).hexdigest()
    report["server_command"] = server["command"]
    (root / "economics-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)
    )
    print(
        json.dumps(
            {"artifacts": str(root), "cohorts": report["cohorts"]},
            ensure_ascii=False,
            indent=2,
        )
    )
    # Engineering invariants are separate from benchmark answer accuracy and
    # financial acceptance. Failed tasks remain in every denominator.
    assert all(len(r["execution_models"]) <= 1 for r in rows)
    assert all(r["decision_calls"] <= 1 for r in rows)
    assert not any(
        r["decision_calls"] for r in rows if r["arm"] in {"strong", "candidate"}
    )
    # Quality/cost thresholds are reporting references, not a binary benchmark
    # exam. Preserve the measurements and intervals even when a reference
    # check is false; only violated execution contracts fail this test.
