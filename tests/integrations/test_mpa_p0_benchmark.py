from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "scripts" / "benchmark-mpa-p0.py"


def test_benchmark_deterministically_reports_warmup_percentiles_and_errors(
    tmp_path: Path,
) -> None:
    samples = tmp_path / "samples.json"
    samples.write_text(
        json.dumps(
            {
                "revision": "a" * 40,
                "endpoint": "agent-list",
                "warmupMilliseconds": [100, 90, 80, 70, 60],
                "requests": [
                    {"index": index, "milliseconds": index, "status": 200}
                    for index in range(1, 101)
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    result = subprocess.run(
        [str(RUNNER), "--samples", str(samples), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report == {
        "schemaVersion": 1,
        "revision": "a" * 40,
        "endpoint": "agent-list",
        "warmupCount": 5,
        "requestCount": 100,
        "concurrency": 10,
        "p50Milliseconds": 50.5,
        "p95Milliseconds": 95.05,
        "maxMilliseconds": 100.0,
        "errorRate": 0.0,
    }


def test_benchmark_rejects_wrong_sample_count_without_partial_report(
    tmp_path: Path,
) -> None:
    samples = tmp_path / "samples.json"
    samples.write_text(
        json.dumps(
            {
                "revision": "b" * 40,
                "endpoint": "run-acceptance",
                "warmupMilliseconds": [1] * 5,
                "requests": [
                    {"index": index, "milliseconds": 1, "status": 200}
                    for index in range(99)
                ],
            }
        ),
        encoding="utf-8",
    )
    output = tmp_path / "report.json"

    result = subprocess.run(
        [str(RUNNER), "--samples", str(samples), "--output", str(output)],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert output.exists() is False
    assert json.loads(result.stdout)["errorCode"] == "invalid_benchmark_samples"
