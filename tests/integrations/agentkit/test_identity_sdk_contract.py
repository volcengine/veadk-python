"""Real AgentKit SDK contract required by VeADK Runtime identity mode."""

from __future__ import annotations

import inspect

from agentkit.apps import AgentkitAgentServerApp


def test_installed_agentkit_exposes_runtime_identity_contract() -> None:
    parameters = inspect.signature(AgentkitAgentServerApp).parameters
    assert "identity" in parameters
    assert "identity_health_routes" in parameters
