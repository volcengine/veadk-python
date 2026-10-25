from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from veadk import Agent


EXAMPLE_ROOT = Path(__file__).resolve().parents[2] / "examples"
sys.path.insert(0, str(EXAMPLE_ROOT))

from clickzetta_data_agent import tools  # noqa: E402


EXPECTED_TOOLS = {
    "get_clickzetta_status",
    "get_clickzetta_runtime_overview",
    "list_clickzetta_assets",
    "get_semantic_catalog",
    "ask_clickzetta_analytics",
    "run_readonly_sql",
}


def test_example_exports_a_real_veadk_root_agent() -> None:
    from clickzetta_data_agent.agent import root_agent

    assert isinstance(root_agent, Agent)
    assert root_agent.name == "clickzetta_readonly_data_agent"
    assert {tool.__name__ for tool in root_agent.tools} == EXPECTED_TOOLS


def test_every_cli_scenario_runs_through_the_veadk_runner() -> None:
    from clickzetta_data_agent.main import run_agent_prompt, scenario_prompt

    calls: list[dict[str, object]] = []

    class FakeRunner:
        def __init__(self, *, agent: Agent, app_name: str) -> None:
            calls.append({"agent": agent, "app_name": app_name})

        async def run(self, *, messages: str, session_id: str) -> str:
            calls.append({"messages": messages, "session_id": session_id})
            return "agent-result"

    for scenario in ("preflight", "demo", "guardrail"):
        answer = asyncio.run(
            run_agent_prompt(
                scenario_prompt(scenario),
                runner_factory=FakeRunner,
                session_id=f"test-{scenario}",
            )
        )
        assert answer == "agent-result"

    assert len([item for item in calls if "agent" in item]) == 3
    assert all(isinstance(item["agent"], Agent) for item in calls if "agent" in item)


def test_mutating_sql_is_rejected_before_reaching_clickzetta(monkeypatch) -> None:
    called = False

    def fake_run_cz(*args, **kwargs):
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr(tools, "_run_cz", fake_run_cz)

    result = tools.run_readonly_sql("DROP TABLE customer_data")

    assert result["allowed"] is False
    assert result["sent_to_clickzetta"] is False
    assert called is False


def test_readonly_sql_is_bounded_before_reaching_clickzetta(monkeypatch) -> None:
    received: list[list[str]] = []

    def fake_run_cz(args, timeout=120):
        received.append(args)
        return {"data": {"columns": ["value"], "rows": [[1]], "count": 1}}

    monkeypatch.setattr(tools, "_run_cz", fake_run_cz)

    result = tools.run_readonly_sql("SELECT 1", max_rows=500)

    assert result["allowed"] is True
    assert result["sent_to_clickzetta"] is True
    assert received == [["sql", "SELECT 1 LIMIT 100"]]
