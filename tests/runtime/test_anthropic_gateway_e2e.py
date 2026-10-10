# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

import importlib.util
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest


PATH = (
    Path(__file__).parents[2] / "examples/16_self_host_sandbox/anthropic_gateway_e2e.py"
)
SPEC = importlib.util.spec_from_file_location("gateway_e2e_config_test", PATH)
e2e = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = e2e
SPEC.loader.exec_module(e2e)


@pytest.fixture
def config(monkeypatch):
    for key in ("MANAGED_AGENTS_GATEWAY", "MANAGED_AGENTS_GATEWAY_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://current.example")
    monkeypatch.setenv("ANTHROPIC_ENVIRONMENT_KEY", "test-current-key")
    monkeypatch.setenv("ANTHROPIC_ENVIRONMENT_ID", "env-test")
    monkeypatch.setenv("MANAGED_AGENTS_TEST_AGENT_ID", "agent-test")
    return monkeypatch


def test_uses_current_anthropic_configuration(config):
    args = e2e.parser().parse_args(["--mode", "conversation"])
    assert args.base_url == "https://current.example"
    assert args.auth_token == "test-current-key"


def test_explicit_and_legacy_overrides(config):
    config.setenv("MANAGED_AGENTS_GATEWAY", "https://override.example")
    config.setenv("MANAGED_AGENTS_GATEWAY_TOKEN", "test-override-key")
    args = e2e.parser().parse_args([])
    assert (args.base_url, args.auth_token) == (
        "https://override.example",
        "test-override-key",
    )
    args = e2e.parser().parse_args(
        ["--base-url", "https://cli.example", "--auth-token", "test-cli"]
    )
    assert (args.base_url, args.auth_token) == ("https://cli.example", "test-cli")


def test_missing_credentials_fail_before_network(config):
    config.delenv("ANTHROPIC_ENVIRONMENT_KEY")
    with pytest.raises(SystemExit):
        e2e.parser().parse_args([])


def test_failed_conversation_stops_and_archives_owned_session(config):
    sessions = SimpleNamespace(
        events=SimpleNamespace(send=AsyncMock()), archive=AsyncMock()
    )
    client = SimpleNamespace(beta=SimpleNamespace(sessions=sessions))
    context = AsyncMock()
    context.__aenter__.return_value = client
    config.setattr(e2e.anthropic, "AsyncAnthropic", lambda **kwargs: context)
    config.setattr(e2e, "create_session", AsyncMock(return_value="sesn-owned"))
    config.setattr(e2e, "run_turn", AsyncMock(side_effect=TimeoutError("turn timeout")))
    args = e2e.parser().parse_args(["--mode", "conversation"])
    with pytest.raises(TimeoutError, match="turn timeout"):
        asyncio.run(e2e.async_main(args))
    assert sessions.events.send.await_args_list[0].args == ("sesn-owned",)
    assert sessions.events.send.await_args_list[0].kwargs == {
        "events": [{"type": "user.interrupt"}]
    }
    assert sessions.events.send.await_args_list[1].kwargs == {
        "events": [{"type": "session.status_terminated"}]
    }
    sessions.archive.assert_awaited_once_with("sesn-owned")
