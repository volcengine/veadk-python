"""Offline contract tests for cost measurement; never contact a provider."""

import gzip
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import pytest
from query_routing_economics import answer_ok, price, summarize
from query_routing_usage import install_usage_audit


@pytest.mark.parametrize("budget", [None, "32000", "100000"])
def test_experiment_context_budget_controls_both_gates_in_isolated_process(budget):
    # The live-agent module installs process-wide observers; isolate this test
    # from the parent suite and never call a real provider.
    env = {
        **os.environ,
        "MODEL_AGENT_API_KEY": "test-placeholder",
        "MODEL_AGENT_API_BASE": "https://ark.cn-beijing.volces.com/api/v3",
        "PYTHONPATH": os.pathsep.join([str(Path(__file__).parent), str(Path.cwd())]),
    }
    env.pop("VEADK_ROUTING_EXPERIMENT_CONTEXT_CHARS", None)
    if budget is not None:
        env["VEADK_ROUTING_EXPERIMENT_CONTEXT_CHARS"] = budget
    script = """
import socket
def deny_network(*args, **kwargs):
    raise AssertionError('offline budget test attempted a network connection')
socket.socket.connect = deny_network
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from query_routing_http_agent import build_agent
from veadk.routing.state import IncompleteRoutingState
from veadk.routing.llm import RoutingLlm
import os

budget = int(os.getenv('VEADK_ROUTING_EXPERIMENT_CONTEXT_CHARS', '32000'))
agent = build_agent('economy_pro_chat')
router = agent.model.classifier
text = 'BEGIN ' + 'x' * 70000 + ' END'
request = LlmRequest(contents=[types.Content(role='user', parts=[types.Part(text=text)])])
assert router.registry.runtimes[0].config.max_context_chars == budget
if budget == 32000:
    assert router.registry.first_available(request) is None
    try:
        router._state_builder.build_for_routing(request)
    except IncompleteRoutingState:
        pass
    else:
        raise AssertionError('decision input gate must retain its default')
else:
    assert router.registry.first_available(request) is not None
    state = router._state_builder.build_for_routing(request)
    assert text in '\\n'.join(part.get('text', '') for part in state)
assert not isinstance(build_agent('baseline_economy_pro_chat').model, RoutingLlm)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        env=env,
        text=True,
        capture_output=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def usage_record(**overrides):
    return {
        "kind": "transport_end",
        "endpoint": "/api/v3/responses",
        "model": "deepseek-v4-1-flash-261017",
        "completed_at": datetime(
            2026, 11, 11, 20, tzinfo=ZoneInfo("Asia/Shanghai")
        ).timestamp(),
        "usage": {
            "input_tokens": 1000,
            "output_tokens": 100,
            "input_tokens_details": {"cached_tokens": 200},
        },
        **overrides,
    }


def test_price_uses_completion_window_cache_and_reasoning_without_double_counting():
    record = usage_record()
    assert price(record) == pytest.approx(0.001204)
    record["completed_at"] = datetime(
        2026, 11, 11, 10, tzinfo=ZoneInfo("Asia/Shanghai")
    ).timestamp()
    assert price(record) == pytest.approx(0.002408)
    record["usage"]["output_tokens_details"] = {"reasoning_tokens": 90}
    assert price(record) == pytest.approx(0.002408)
    record["model"] = "doubao-seed-2-1-pro-260915"
    # Console screenshot input/output prices; public cache price is separate.
    assert price(record) == pytest.approx(0.0072678)
    record["model"] = "doubao-seed-2-1-lite-260915"
    assert price(record) == pytest.approx(0.000942)
    record["model"] = "kimi-k3-1-pro-261024"
    assert price(record) == pytest.approx(0.01746)
    record["endpoint"] = "/api/v1/systemone"
    assert price(record) == pytest.approx(0.013)


@pytest.mark.parametrize(
    "model,expected",
    [
        ("doubao-seed-2-1-lite-260915", 0.0008),
        ("doubao-seed-2-1-pro-260915", 0.005406),
        ("kimi-k3-1-pro-261024", 0.013),
        ("unknown-decision-model", None),
    ],
)
def test_systemone_uses_its_actual_model_input_rate_and_free_output(model, expected):
    record = usage_record(
        model=model, endpoint="/api/v1/systemone", usage={"input_tokens": 1000}
    )
    measured = price(record)
    assert measured is None if expected is None else measured == pytest.approx(expected)


@pytest.mark.parametrize(
    "usage",
    [
        None,
        {},
        {"input_tokens": True, "output_tokens": 1},
        {"input_tokens": -1, "output_tokens": 0},
        {
            "input_tokens": 1,
            "output_tokens": 0,
            "input_tokens_details": {"cached_tokens": 2},
        },
    ],
)
def test_missing_or_invalid_usage_is_not_free(usage):
    assert price(usage_record(usage=usage)) is None


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [False, True])
@pytest.mark.parametrize("compressed", [False, True])
async def test_transport_audit_reads_fragmented_and_compressed_usage_without_changing_response(
    monkeypatch, streaming, compressed
):
    records = []
    original = httpx.AsyncClient.send
    # Register the original before installing the observer, so fixture teardown
    # restores httpx instead of leaving a wrapper in later tests.
    monkeypatch.setattr(httpx.AsyncClient, "send", original)
    install_usage_audit(lambda **r: records.append(r))
    usage = {"input_tokens": 123, "output_tokens": 4}
    item = {"response": {"usage": usage}} if streaming else {"usage": usage}
    data = (
        ("data: " + json.dumps(item) + "\n\ndata: [DONE]\n\n").encode()
        if streaming
        else json.dumps(item).encode()
    )
    raw = gzip.compress(data) if compressed else data

    class Stream(httpx.AsyncByteStream):
        async def __aiter__(self):
            for i in range(0, len(raw), 3):
                yield raw[i : i + 3]

    async def handler(request):
        headers = {
            "content-type": "text/event-stream" if streaming else "application/json"
        }
        if compressed:
            headers["content-encoding"] = "gzip"
        return httpx.Response(200, stream=Stream(), headers=headers)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        response = await client.post(
            "https://example.test/responses",
            json={"model": "model", "messages": ["private-value"]},
        )
        assert response.content == data
    assert len(records) == 2
    assert records[1]["usage"] == usage
    assert records[0]["attempt_id"] == records[1]["attempt_id"]
    assert "private-value" not in str(records)


def test_incomplete_pairs_are_rejected_and_missing_measurements_fail_gate():
    assert httpx.AsyncClient.send.__module__ == "httpx._client"
    row = {
        "cohort": "test",
        "arm": "strong",
        "id": "1",
        "cluster": "1",
        "category": "test",
        "success": True,
        "elapsed_ms": 1,
        "high_risk": True,
        "route": "strong",
    }
    with pytest.raises(ValueError, match="incomplete pairs"):
        summarize([dict(row)], [])
    report = summarize([dict(row), {**row, "arm": "routed"}], [])
    assert report["cohorts"]["test"]["gates"]["cost"] is False
    assert report["cohorts"]["test"]["gates"]["quality"] is False


def test_workflow_oracle_requires_executed_tool_result():
    case = {"oracle": "workflow", "expected": "DONE-X", "workflows": ["X"]}
    result = {"answer": "DONE-X", "events": []}
    assert answer_ok(case, result) is False
    result["events"] = [
        {
            "content": {
                "parts": [
                    {
                        "functionResponse": {
                            "response": {"done": True, "result": "DONE-X"}
                        }
                    }
                ]
            }
        }
    ]
    assert answer_ok(case, result) is True


@pytest.fixture
def recovery_runs(tmp_path):
    manifest = {
        "temperature": 0.6,
        "max_output_tokens": 4096,
        "thinking": "disabled",
        "cohorts": ["test"],
        "capability_description": "fixed description",
        "cases": [{"id": "1"}],
    }
    raw = json.dumps(manifest).encode()
    folders = [tmp_path / name for name in ("original", "recovery")]
    for index, folder in enumerate(folders):
        folder.mkdir()
        data = dict(manifest)
        if index:
            data["rerun_basis"] = {
                "original_manifest_sha256": hashlib.sha256(raw).hexdigest(),
                "reason": "missing usage",
            }
        (folder / "experiment-manifest.json").write_text(json.dumps(data))
        rows = [
            {
                "cohort": "test",
                "arm": arm,
                "id": "1:0",
                "cluster": "1",
                "category": "test",
                "success": not index,
                "elapsed_ms": 1,
                "high_risk": False,
                "route": "strong",
            }
            for arm in ("strong", "routed")
        ]
        audit = [
            usage_record(
                cohort="test",
                arm=arm,
                experiment_case_id="1:0",
                attempt_id=f"{index}-{arm}",
            )
            for arm in ("strong", "routed")
        ]
        (folder / "paired-results.jsonl").write_text("\n".join(map(json.dumps, rows)))
        (folder / "audit.jsonl").write_text("\n".join(map(json.dumps, audit)))
    return *folders, tmp_path / "merged"


def test_recovery_keeps_worse_complete_answers_and_all_consumed_costs(recovery_runs):
    from merge_query_routing_economics import merge

    result = merge(*recovery_runs)
    assert result["cohorts"]["test"]["pairs"] == 1
    assert not any(r["success"] for r in result["rows"])
    assert result["recovery"]["experiment_known_cost_cny"] == pytest.approx(
        4 * 0.001204
    )
    assert result["recovery"]["superseded_known_cost_cny"] == pytest.approx(
        2 * 0.001204
    )


def test_recovery_rejects_changed_candidate_description(recovery_runs):
    from merge_query_routing_economics import merge

    path = recovery_runs[1] / "experiment-manifest.json"
    manifest = json.loads(path.read_text())
    manifest["capability_description"] = "different routing policy"
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="configuration"):
        merge(*recovery_runs)


def test_repeated_recovery_accumulates_every_attempt_cost(recovery_runs):
    from merge_query_routing_economics import merge

    original, recovery, first = recovery_runs
    merge(original, recovery, first)
    result = merge(first, recovery, first.with_name("second"))
    assert result["recovery"]["experiment_known_cost_cny"] == pytest.approx(
        6 * 0.001204
    )
    assert result["recovery"]["superseded_known_cost_cny"] == pytest.approx(
        4 * 0.001204
    )
    assert result["recovery"]["experiment_http_turns"] == 6


def test_explicit_repair_merge_keeps_unknown_cost_unknown(recovery_runs):
    from merge_query_routing_economics import merge

    path = recovery_runs[1] / "audit.jsonl"
    records = [json.loads(line) for line in path.read_text().splitlines()]
    records[0]["usage"] = None
    path.write_text("\n".join(map(json.dumps, records)))
    with pytest.raises(ValueError, match="accounting"):
        merge(*recovery_runs)
    result = merge(*recovery_runs, require_complete_usage=False)
    assert result["cohorts"]["test"]["arms"]["strong"]["unknown_usage_attempts"] == 1
    assert result["recovery"]["experiment_unknown_usage_attempts"] == 1
    assert result["recovery"]["experiment_known_cost_cny"] == pytest.approx(
        3 * 0.001204
    )


@pytest.mark.parametrize("family", ["BFCL", "AgentDojo"])
def test_recovery_rebuilds_public_task_statistics(recovery_runs, family):
    from merge_query_routing_economics import merge

    for folder in recovery_runs[:2]:
        path = folder / "experiment-manifest.json"
        manifest = json.loads(path.read_text())
        manifest["public_benchmarks"] = True
        manifest["cohorts"].append("unused")
        manifest["cases"][0].update(
            source=family, category="tools", protocol="responses", condition="clean"
        )
        if folder == recovery_runs[1]:
            manifest["rerun_basis"]["original_manifest_sha256"] = hashlib.sha256(
                (recovery_runs[0] / "experiment-manifest.json").read_bytes()
            ).hexdigest()
        path.write_text(json.dumps(manifest))
        path = folder / "paired-results.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        for row in rows:
            row.update(answer="", source=family, protocol="responses")
        path.write_text("\n".join(map(json.dumps, rows)))
    result = merge(*recovery_runs)
    public = result["public_benchmarks"]
    assert len(public["tasks"]) == 2
    assert len(public["cells"]) == 2
    assert public["cells"][0]["pairs"] == 1
    assert public["cells"][0]["arms"]["routed"]["successes"] == 0


@pytest.mark.parametrize(
    "hour,expected",
    [(8, 0.0009632), (9, 0.0019264), (12, 0.0009632), (14, 0.0019264), (18, 0.0009632)],
)
def test_economy_prices_apply_peak_boundaries(hour, expected):
    record = usage_record(
        model="deepseek-v4-1-flash-economy-261017",
        completed_at=datetime(
            2026, 11, 11, hour, tzinfo=ZoneInfo("Asia/Shanghai")
        ).timestamp(),
    )
    assert price(record) == pytest.approx(expected)
