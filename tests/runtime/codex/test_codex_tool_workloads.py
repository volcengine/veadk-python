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

"""Batch contract checks and real Codex multi-turn tool workloads."""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.benchmark_codex_tools import bounded_batch_lookup


@pytest.mark.asyncio
async def test_batch_limits_admission_before_any_lookup():
    called = []

    async def lookup(key):
        called.append(key)
        return {"key": key}

    with pytest.raises(ValueError):
        await bounded_batch_lookup(["a", "b"], lookup, max_size=1)
    assert called == []


@pytest.mark.asyncio
async def test_batch_preserves_each_failure_and_timeout():
    async def lookup(key):
        if key == "error":
            raise ValueError("synthetic failure")
        if key == "slow":
            await asyncio.sleep(1)
        return {"key": key}

    result = await bounded_batch_lookup(
        ["ok", "error", "slow"], lookup, item_timeout=0.02
    )
    assert result["status"] == "partial_failure"
    assert [r["status"] for r in result["results"]] == ["completed", "error", "error"]
    assert result["results"][1]["error_type"] == "ValueError"
    assert result["results"][2]["error_type"] in {
        "TimeoutError",
        "TimeoutErrorException",
    }


@pytest.mark.asyncio
async def test_batch_cancellation_reaches_all_inflight_lookups():
    both_started = asyncio.Event()
    started, cancelled = set(), set()

    async def lookup(key: str) -> dict[str, str]:
        started.add(key)
        if len(started) == 2:
            both_started.set()
        try:
            await asyncio.sleep(60)
        finally:
            cancelled.add(key)
        return {"key": key}

    task = asyncio.create_task(bounded_batch_lookup(["a", "b"], lookup))
    await both_started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled == {"a", "b"}


@pytest.mark.codex_smoke
@pytest.mark.parametrize("scenario", ["single", "parallel", "serial", "batch"])
@pytest.mark.parametrize("pool_size", [0, 20])
def test_real_multi_turn_tool_workload(scenario, pool_size, tmp_path):
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip(
            "set CODEX_RUN_SMOKE=1; real Codex, loopback model, no provider tokens"
        )
    pytest.importorskip("openai_codex")
    root = Path(__file__).resolve().parents[3]
    output = tmp_path / "result.json"
    # A fresh process isolates the real SDK and all runtime state from the
    # differential SDK doubles imported by other tests during collection.
    proc = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/benchmark_codex_tools.py"),
            "--scenario",
            scenario,
            "--turns",
            "3",
            "--pool-size",
            str(pool_size),
            "--output",
            str(output),
        ],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(output.read_text())
    rows = report["rows"]
    assert len(rows) == 3 and all(r["correct"] for r in rows)
    assert [r["reuse_outcome"] for r in rows] == ["new_thread"] + (
        ["warm"] * 2 if pool_size else ["resumed"] * 2
    )
    if pool_size:
        assert all(r["developer_messages"] == 1 for r in rows)
    assert all(r["reset_warnings"] == 0 for r in rows)
    requests = 3 if scenario == "serial" else 2
    assert all(r["model_requests"] == requests for r in rows)
    assert all(
        r["tool_calls"] == (2 if scenario in {"parallel", "serial"} else 1)
        for r in rows
    )
    assert report["peak_concurrency"] == (2 if scenario in {"parallel", "batch"} else 1)
    assert report["cleanup"] == {"pool_idle": 0, "bridge_processes": 0}
