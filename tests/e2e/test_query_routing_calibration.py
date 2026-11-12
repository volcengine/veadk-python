"""Contract tests for matched controls; all network access is forbidden."""

import copy
from types import SimpleNamespace

import pytest
from query_routing_calibration import install_fixed_control, summarize_comparisons


@pytest.mark.asyncio
@pytest.mark.parametrize("route,model", [("strong", None), ("simple", "candidate")])
async def test_fixed_control_uses_same_adapter_without_judging(route, model):
    class Classifier:
        registry = SimpleNamespace(
            runtimes=[SimpleNamespace(config=SimpleNamespace(name="candidate"))]
        )

        async def classify(self, *args, **kwargs):
            raise AssertionError("fixed control must not infer a decision")

    adapter = SimpleNamespace(classifier=Classifier())
    agent = SimpleNamespace(model=adapter)
    install_fixed_control(agent, route)
    result = await adapter.classifier.classify(
        object(), invocation_id="root", session_id="session"
    )
    assert agent.model is adapter
    assert result.route == route
    assert result.model_name == model
    assert result.invocation_id == "root"
    assert result.reason == "fixed_model_control"


def test_invalid_fixed_control_is_rejected():
    with pytest.raises(ValueError):
        install_fixed_control(None, "other")


def test_comparison_accounting_keeps_controls_separate():
    rows = [
        dict(
            id="task:0",
            cluster="task",
            category="category",
            source="engineering",
            cohort="pro",
            arm=arm,
            success=arm != "candidate",
            elapsed_ms=10,
            route="strong",
        )
        for arm in ("strong", "candidate", "routed")
    ]
    attempts = [
        dict(
            kind="transport_end",
            attempt_id=arm,
            cohort="pro",
            arm=arm,
            experiment_case_id="task:0",
            endpoint="https://ark.example/api/v3/responses",
            model="doubao-seed-2-1-lite-260915",
            usage={"input_tokens": 100, "output_tokens": 10},
            timestamp="2026-11-12T00:00:00+00:00",
        )
        for arm in ("strong", "candidate", "routed")
    ]
    original = copy.deepcopy(attempts)
    report = summarize_comparisons(rows, attempts)
    assert attempts == original
    assert {r["arm"] for r in rows} == {"strong", "candidate", "routed"}
    assert all(r["model_calls"] == 1 for r in rows)
    assert report["cohorts"]["candidate"]["pro"]["arms"]["routed"]["successes"] == 0
    assert report["cohorts"]["routed"]["pro"]["arms"]["routed"]["successes"] == 1
