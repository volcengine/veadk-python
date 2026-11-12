"""Adapter contracts; upstream tests opt in to a local, pinned source bundle."""

import ast
import copy
import inspect
import json
import os
import sys
from pathlib import Path

import pytest
from query_routing_benchmark_agent import BFCLBackend, json_schema
from query_routing_benchmark_scoring import isolated_lcb, score_bfcl, score_static
from query_routing_public_benchmarks import balanced_constraints, stable_sample


def test_task_weighting_keeps_multiturn_cost_without_duplicate_votes():
    from query_routing_benchmark_report import aggregate_tasks, paired_statistics

    cases = [
        {"id": name, "source": "BFCL", "category": "tools", "protocol": "chat"}
        for name in ("multi", "single")
    ]
    rows = []
    for arm in ("strong", "routed"):
        for name, count in (("multi", 3), ("single", 1)):
            for turn in range(count):
                rows.append(
                    {
                        "id": f"{name}:{turn}",
                        "cluster": name,
                        "cohort": "pro",
                        "arm": arm,
                        "success": name == "single",
                        "cost_cny": 1,
                        "decision_cost_cny": 0,
                        "unknown_usage_attempts": int(
                            arm == "routed" and name == "multi" and turn == 0
                        ),
                        "model_calls": 1,
                        "decision_calls": 0,
                        "elapsed_ms": 10,
                        "routes": [],
                        "execution_models": ["model"],
                        "answer": "",
                        "errors": [],
                    }
                )
    tasks = aggregate_tasks(rows, [], {"cases": cases})
    result = paired_statistics(tasks, resamples=20)
    assert result["pairs"] == 2
    assert result["arms"]["strong"]["success_rate"] == 0.5
    assert result["arms"]["strong"]["cost_cny"] == 4
    assert result["arms"]["strong"]["http_turns"] == 4
    assert result["complete_cost_pairs"] == 1
    assert result["arms"]["routed"]["unknown_usage_attempts"] == 1
    with pytest.raises(ValueError, match="duplicate"):
        paired_statistics([*tasks, tasks[0]], resamples=1)
    with pytest.raises(ValueError, match="complete pairs"):
        paired_statistics(tasks[1:], resamples=1)

    # A single sampled task per discipline has no within-discipline variance.
    # Resample the family instead of reporting a spurious point interval.
    for task in tasks:
        task["category"] = task["id"]
        if task["arm"] == "routed" and task["id"] == "multi":
            task["success"] = True
    result = paired_statistics(tasks, resamples=200)
    low, high = result["quality_delta_95ci_pp"]
    assert low < high
    assert result["pooled_category_families"] == ["BFCL"]


def test_route_reasons_exclude_model_event_metadata():
    from query_routing_benchmark_report import aggregate_tasks

    case = {"id": "a", "source": "BFCL", "category": "tools", "protocol": "chat"}
    row = {
        "id": "a:0",
        "cluster": "a",
        "cohort": "pro",
        "arm": "routed",
        "success": True,
        "cost_cny": 0,
        "decision_cost_cny": 0,
        "unknown_usage_attempts": 0,
        "model_calls": 2,
        "decision_calls": 1,
        "elapsed_ms": 1,
        "execution_models": ["model"],
        "answer": "",
        "routes": [{"reason": "all_thresholds_passed"}, {"target": "hash"}],
    }
    tasks = aggregate_tasks([row], [], {"cases": [case]})
    assert tasks[0]["route_reasons"] == {"all_thresholds_passed": 1}


def test_agentdojo_replay_preserves_order_except_native_calendar_participants():
    from query_routing_benchmark_scoring import agentdojo_results_equal

    event = {
        "id_": "1",
        "title": "Meeting",
        "start_time": "2026-01-01T10:00:00",
        "end_time": "2026-01-01T11:00:00",
        "participants": ["a@example.test", "b@example.test"],
    }
    reversed_event = copy.deepcopy(event)
    reversed_event["participants"].reverse()
    assert agentdojo_results_equal(event, reversed_event)
    changed = copy.deepcopy(event)
    changed["participants"] = ["a@example.test", "c@example.test"]
    assert not agentdojo_results_equal(event, changed)
    changed["participants"] = ["a@example.test", "b@example.test", "b@example.test"]
    assert not agentdojo_results_equal(event, changed)
    assert not agentdojo_results_equal({"values": [1, 2]}, {"values": [2, 1]})
    assert event["participants"] == ["a@example.test", "b@example.test"]


def test_native_score_metadata_preserves_values_in_json():
    from query_routing_benchmark_scoring import serializable_score

    result = serializable_score({"success": False, "missing": {"b", "a"}, "count": 2})
    assert result == {"success": False, "missing": ["a", "b"], "count": 2}
    with pytest.raises(TypeError):
        serializable_score({"unexpected": object()})


def test_sampling_is_reproducible_and_rejects_short_populations():
    population = list(range(100))
    assert stable_sample(population, 10, "family") == stable_sample(
        population, 10, "family"
    )
    assert stable_sample(population, 10, "family") != stable_sample(
        population, 10, "other"
    )
    with pytest.raises(ValueError, match="need 101"):
        stable_sample(population, 101, "family")


def test_constraint_sampler_covers_rare_constraints():
    rows = [{"key": i, "instruction_id_list": ["common"]} for i in range(100)]
    rows += [{"key": "rare", "instruction_id_list": ["rare"]}]
    selected = balanced_constraints(rows, 10)
    assert len(selected) == 10
    assert len({i["key"] for i in selected}) == 10
    assert any("rare" in i["instruction_id_list"] for i in selected)


def test_bfcl_schema_translation_preserves_required_and_input():
    source = {
        "type": "dict",
        "properties": {
            "items": {"type": "array", "items": {"type": "float"}},
            "x": {"type": "any"},
        },
        "required": ["items"],
    }
    original = copy.deepcopy(source)
    schema = json_schema(source)
    assert source == original
    assert schema["type"] == "object"
    assert schema["properties"]["items"]["items"]["type"] == "number"
    assert "type" not in schema["properties"]["x"]
    assert schema["required"] == ["items"]


@pytest.fixture(scope="module")
def bundle():
    root = os.getenv("VEADK_ROUTING_BENCHMARK_BUNDLE")
    if not root:
        pytest.skip("requires an explicitly prepared local upstream source bundle")
    root = Path(root)
    for folder in (
        "ifeval",
        "bfcl/berkeley-function-call-leaderboard",
        "livecodebench",
        "agentdojo/src",
    ):
        sys.path.insert(0, str(root / "sources" / folder))
    return root, json.loads((root / "manifest.json").read_text())


def row_with_calls(calls, answer=""):
    return {
        "answer": answer,
        "errors": [],
        "events": [{"content": {"parts": [{"functionCall": c} for c in calls]}}],
    }


def test_native_bfcl_checks_structured_calls_and_argument_values(bundle):
    root, manifest = bundle
    case = next(
        c
        for c in manifest["cases"]
        if c["source"] == "BFCL" and c["category"] == "simple_python"
    )
    truth = case["payload"]["answer"]["ground_truth"][0]
    name, args = next(iter(truth.items()))
    args = {k: values[0] for k, values in args.items() if values[0] != ""}
    call = {"name": name.replace(".", "_"), "args": args}
    assert score_bfcl(case, [row_with_calls([call])], root / "sources")["success"]
    assert not score_bfcl(
        case, [row_with_calls([], json.dumps(truth))], root / "sources"
    )["success"]
    bad = copy.deepcopy(call)
    bad["args"][next(iter(args))] = "WRONG_ARGUMENT"
    assert not score_bfcl(case, [row_with_calls([bad])], root / "sources")["success"]


def test_native_bfcl_non_json_results_follow_upstream_text_fallback(bundle):
    _, manifest = bundle
    case = next(c for c in manifest["cases"] if c["id"] == "BFCL-multi_turn_base_32")
    backend = BFCLBackend(case)
    args = {"value": 100, "base": 10, "precision": 40}
    native = backend.instances["MathAPI"].logarithm(**args)
    with pytest.raises(TypeError):
        json.dumps(native)
    result = backend.call("logarithm", args)
    assert result == str(native)
    assert json.loads(json.dumps(result)) == result
    assert backend.call("add", {"a": 2, "b": 3}) == {"result": 5}


def test_native_bfcl_multiturn_replays_ground_truth(bundle):
    root, manifest = bundle
    for case in [
        c
        for c in manifest["cases"]
        if c["source"] == "BFCL" and c["category"].startswith("multi_turn")
    ]:
        backend = BFCLBackend(case)
        rows = []
        for turn in case["payload"]["answer"]["ground_truth"]:
            calls = []
            for text in turn:
                expression = ast.parse(text, mode="eval").body
                name = expression.func.id
                target = next(
                    getattr(i, name)
                    for i in backend.instances.values()
                    if hasattr(i, name)
                )
                args = (
                    inspect.signature(target)
                    .bind(
                        *[ast.literal_eval(n) for n in expression.args],
                        **{
                            k.arg: ast.literal_eval(k.value)
                            for k in expression.keywords
                        },
                    )
                    .arguments
                )
                backend.call(name, args)
                calls.append({"name": name, "args": args})
            rows.append(row_with_calls(calls))
        assert score_bfcl(case, rows, root / "sources")["success"], case["id"]
        assert not score_bfcl(
            case, [row_with_calls([]) for _ in rows], root / "sources"
        )["success"]
        if case["id"] == "BFCL-multi_turn_base_32":
            bad = copy.deepcopy(rows)
            bad[-1]["events"][0]["content"]["parts"].append(
                {
                    "functionCall": {
                        "name": "touch",
                        "args": {"file_name": "unexpected.txt"},
                    }
                }
            )
            failure = score_bfcl(case, bad, root / "sources")
            assert not failure["success"]
            assert json.loads(json.dumps(failure))["success"] is False


def test_official_ifeval_rejects_bad_constraints(bundle):
    root, _ = bundle
    case = {
        "source": "IFEval",
        "payload": {
            "key": 1,
            "prompt": "Return valid JSON.",
            "instruction_id_list": ["detectable_format:json_format"],
            "kwargs": [{}],
        },
    }
    assert score_static(case, row_with_calls([], '{"answer": 42}'), root / "sources")[
        "success"
    ]
    assert not score_static(
        case, row_with_calls([], "This is not JSON."), root / "sources"
    )["success"]


def test_official_lcb_evaluator_isolates_files_environment_and_network(
    bundle, monkeypatch, tmp_path
):
    root, _ = bundle
    case = {"category": "test_output_easy", "payload": {"test": '[{"output": "42"}]'}}
    assert isolated_lcb(case, "assert f() == 42", root / "sources")["success"]
    assert not isolated_lcb(case, "assert f() == 43", root / "sources")["success"]
    monkeypatch.setenv("ROUTING_ISOLATION_SENTINEL", "test-only")
    private = tmp_path / "outside-sandbox.txt"
    private.write_text("42")
    expression = f"(__import__('os').getenv('ROUTING_ISOLATION_SENTINEL') is None and not __import__('os').path.exists({str(private)!r}) and not __import__('os').path.exists('/etc/passwd'))"
    case["payload"]["test"] = '[{"output": "true"}]'
    assert isolated_lcb(case, "assert f() == " + expression, root / "sources")[
        "success"
    ]
    assert not isolated_lcb(
        case,
        "assert f() == __import__('socket').create_connection(('1.1.1.1', 443), timeout=1)",
        root / "sources",
    )["success"]


def test_agentdojo_replay_preserves_recorded_email_time(bundle):
    import datetime

    from agentdojo.default_suites.v1.tools import email_client
    from query_routing_benchmark_agent import AgentDojoBackend
    from query_routing_benchmark_scoring import replay_agentdojo_call

    _, manifest = bundle
    case = next(
        c
        for c in manifest["cases"]
        if c["id"] == "AgentDojo-workspace-user_task_33-clean"
    )
    original_clock = datetime.datetime
    original = AgentDojoBackend(case)
    replay = AgentDojoBackend(case)
    args = {
        "recipients": ["colleague@example.com"],
        "subject": "Replay contract",
        "body": "Recorded tool output",
    }
    result = original.call("send_email", args)
    assert "timestamp" in result
    entry = {"name": "send_email", "arguments": args, "result": result}
    assert replay_agentdojo_call(replay, entry) == result
    assert (
        replay.environment.inbox.emails[result["id_"]].timestamp.isoformat()
        == result["timestamp"]
    )
    assert datetime.datetime is original_clock
    assert email_client.datetime is datetime


def test_agentdojo_replay_preserves_recorded_file_times(bundle, monkeypatch):
    import datetime
    from types import SimpleNamespace

    from agentdojo.default_suites.v1.tools import cloud_drive_client
    from query_routing_benchmark_agent import AgentDojoBackend
    from query_routing_benchmark_scoring import replay_agentdojo_call

    _, manifest = bundle
    case = next(
        c
        for c in manifest["cases"]
        if c["id"] == "AgentDojo-workspace-user_task_33-clean"
    )
    original = AgentDojoBackend(case)
    replay = AgentDojoBackend(case)
    recorded = datetime.datetime(2025, 1, 2, 3, 4, 5)

    class RecordedClock(datetime.datetime):
        @classmethod
        def now(cls, tz=None):
            return recorded if tz is None else recorded.astimezone(tz)

    clock = SimpleNamespace(datetime=RecordedClock)
    entries = []
    with monkeypatch.context() as patcher:
        patcher.setattr(cloud_drive_client, "datetime", clock)
        args = {"filename": "replay.txt", "content": "Before"}
        result = original.call("create_file", args)
        entries.append({"name": "create_file", "arguments": args, "result": result})
        recorded += datetime.timedelta(seconds=1)
        args = {"file_id": result["id_"], "content": "After"}
        result = original.call("append_to_file", args)
        entries.append({"name": "append_to_file", "arguments": args, "result": result})
    for entry in entries:
        assert replay_agentdojo_call(replay, entry) == entry["result"]
        assert cloud_drive_client.datetime is datetime
    assert replay.environment.cloud_drive == original.environment.cloud_drive
    assert replay.call("get_file_by_id", {"file_id": result["id_"]}) == result


def test_agentdojo_native_ground_truth_and_independent_environments(bundle):
    from agentdojo.agent_pipeline.ground_truth_pipeline import GroundTruthPipeline
    from agentdojo.task_suite.task_suite import (
        functions_stack_trace_from_messages,
        model_output_from_messages,
    )
    from agentdojo.types import get_text_content_as_str
    from query_routing_benchmark_agent import AgentDojoBackend

    _, manifest = bundle
    for case in [
        c
        for c in manifest["cases"]
        if c["source"] == "AgentDojo" and c["condition"] == "clean"
    ]:
        backend = AgentDojoBackend(case)
        other = AgentDojoBackend(case)
        before = other.environment.model_dump()
        _, _, backend.environment, messages, _ = GroundTruthPipeline(
            backend.task
        ).query(backend.task.PROMPT, backend.runtime, backend.environment)
        backend.calls = functions_stack_trace_from_messages(messages)
        answer = get_text_content_as_str(model_output_from_messages(messages) or [])
        assert backend.score(answer)["success"], case["id"]
        assert other.environment.model_dump() == before
