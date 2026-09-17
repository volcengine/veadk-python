#!/usr/bin/env python3
"""Build a deterministic report from an MPA P0 benchmark sample set."""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path
from typing import Any


def _percentile(values: list[float], quantile: float) -> float:
    position = (len(values) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return values[lower]
    fraction = position - lower
    return values[lower] + (values[upper] - values[lower]) * fraction


def _build_report(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise ValueError
    revision = payload.get("revision")
    endpoint = payload.get("endpoint")
    warmup = payload.get("warmupMilliseconds")
    requests = payload.get("requests")
    if (
        not isinstance(revision, str)
        or re.fullmatch(r"[0-9a-f]{40}", revision) is None
        or not isinstance(endpoint, str)
        or not endpoint
        or not isinstance(warmup, list)
        or len(warmup) != 5
        or not isinstance(requests, list)
        or len(requests) != 100
    ):
        raise ValueError
    latencies: list[float] = []
    errors = 0
    indexes: list[int] = []
    for request in requests:
        if not isinstance(request, dict):
            raise ValueError
        index = request.get("index")
        latency = request.get("milliseconds")
        status = request.get("status")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or isinstance(latency, bool)
            or not isinstance(latency, (int, float))
            or latency < 0
            or isinstance(status, bool)
            or not isinstance(status, int)
        ):
            raise ValueError
        indexes.append(index)
        latencies.append(float(latency))
        errors += int(status < 200 or status >= 400)
    if len(set(indexes)) != 100:
        raise ValueError
    latencies.sort()
    return {
        "schemaVersion": 1,
        "revision": revision,
        "endpoint": endpoint,
        "warmupCount": 5,
        "requestCount": 100,
        "concurrency": 10,
        "p50Milliseconds": round(_percentile(latencies, 0.5), 3),
        "p95Milliseconds": round(_percentile(latencies, 0.95), 3),
        "maxMilliseconds": max(latencies),
        "errorRate": round(errors / len(latencies), 6),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        payload = json.loads(args.samples.read_text(encoding="utf-8"))
        report = _build_report(payload)
    except (OSError, ValueError, json.JSONDecodeError):
        print(
            json.dumps(
                {
                    "status": "invalid_samples",
                    "errorCode": "invalid_benchmark_samples",
                },
                separators=(",", ":"),
            )
        )
        return 2
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
