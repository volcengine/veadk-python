"""Keep Managed Agents tests isolated from user credentials and other suites."""

import pytest


@pytest.fixture(autouse=True)
def isolated_managed_agent_environment(monkeypatch):
    from veadk.runtime.managed_agents.sandbox import get_default_agent

    for key, value in {
        "ANTHROPIC_BASE_URL": "https://sandbox.example.com",
        "ANTHROPIC_ENVIRONMENT_KEY": "test-token",
        "MODEL_AGENT_API_KEY": "test-model-api-key",
        "MODEL_AGENT_NAME": "test-model",
    }.items():
        monkeypatch.setenv(key, value)
    get_default_agent.cache_clear()
    yield
    get_default_agent.cache_clear()
