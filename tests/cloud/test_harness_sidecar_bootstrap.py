from __future__ import annotations

import runpy
from pathlib import Path

from veadk.cloud.harness_app import utils
from veadk.extensions.harness import HarnessExtension


def test_harness_app_starts_extension_before_building_agent(monkeypatch) -> None:
    events: list[str] = []
    extension = object()

    def from_env(_cls):
        events.append("extension")
        return extension

    def init_harness_agent():
        events.append("agent")
        return object(), object()

    monkeypatch.setattr(HarnessExtension, "from_env", classmethod(from_env))
    monkeypatch.setattr(utils, "init_harness_agent", init_harness_agent)
    agent_module = (
        Path(__file__).resolve().parents[2]
        / "veadk"
        / "cloud"
        / "harness_app"
        / "agent.py"
    )

    namespace = runpy.run_path(str(agent_module))

    assert events == ["extension", "agent"]
    assert namespace["harness_extension"] is extension
