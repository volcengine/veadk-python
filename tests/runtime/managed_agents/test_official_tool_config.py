"""Official SDK response parsing must preserve native tool discriminants."""

import anthropic
import httpx2
import pytest

from veadk.runtime.managed_agents import worker


def sdk_snapshot(configs, *, default_enabled=False):
    payload = {
        "type": "agent",
        "id": "fixture-agent",
        "name": "fixture-agent",
        "model": {"id": "fixture-model"},
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {
                    "enabled": default_enabled,
                    "permission_policy": {"type": "always_allow"},
                },
                "configs": configs,
            }
        ],
        "skills": [],
    }
    with anthropic.Anthropic(
        api_key="offline-fixture-key",
        base_url="http://sdk.invalid",
        http_client=httpx2.Client(
            transport=httpx2.MockTransport(lambda _: httpx2.Response(200, json=payload))
        ),
    ) as sdk:
        return sdk.beta.agents.retrieve("fixture-agent")


def test_official_sdk_type_only_configs_enable_all_six_native_tools():
    names = {"bash", "read", "write", "edit", "glob", "grep"}
    snapshot = sdk_snapshot(
        [
            {
                "type": name,
                "enabled": True,
                "permission_policy": {"type": "always_allow"},
            }
            for name in sorted(names)
        ]
    )
    assert isinstance(snapshot, anthropic.types.beta.BetaManagedAgentsAgent)
    # The server round-trips the official input schema without legacy `name`.
    assert all(
        not getattr(config, "name", None) for config in snapshot.tools[0].configs
    )
    config = worker.managed_agent_config(snapshot)
    assert {tool.__name__ for tool in config["tools"]} == names
    policies = worker._tool_permission_map(snapshot)
    assert all(policies[name] == "always_allow" for name in names)


def test_typed_disable_override_and_permission_share_the_same_discriminant():
    snapshot = sdk_snapshot(
        [
            {
                "type": "bash",
                "enabled": False,
                "permission_policy": {"type": "always_allow"},
            },
            {
                "type": "read",
                "enabled": True,
                "permission_policy": {"type": "always_ask"},
            },
        ],
        default_enabled=True,
    )
    config = worker.managed_agent_config(snapshot)
    names = {tool.__name__ for tool in config["tools"]}
    assert "bash" not in names
    assert "read" in names
    assert worker._tool_permission_map(snapshot)["read"] == "always_ask"


def test_official_type_takes_precedence_over_legacy_name():
    snapshot = {
        "model": "fixture-model",
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [
                    {
                        "type": "read",
                        "name": "bash",
                        "enabled": True,
                        "permission_policy": {"type": "always_ask"},
                    }
                ],
            }
        ],
    }
    assert [
        tool.__name__ for tool in worker.managed_agent_config(snapshot)["tools"]
    ] == ["read"]
    assert worker._tool_permission_map(snapshot)["read"] == "always_ask"
    assert "bash" not in worker._tool_permission_map(snapshot)


def test_unknown_official_type_cannot_be_hidden_by_a_legacy_name():
    snapshot = {
        "model": "fixture-model",
        "tools": [
            {
                "type": "agent_toolset_20260401",
                "default_config": {"enabled": False},
                "configs": [{"type": "unsupported", "name": "read", "enabled": True}],
            }
        ],
    }
    with pytest.raises(ValueError, match="unsupported"):
        worker.managed_agent_config(snapshot)


def test_mcp_configs_continue_to_use_names_not_native_type_discriminants():
    snapshot = {
        "tools": [
            {
                "type": "mcp_toolset",
                "mcp_server_name": "fixture-server",
                "configs": [
                    {
                        "name": "fixture-tool",
                        "type": "custom",
                        "permission_policy": {"type": "always_ask"},
                    }
                ],
            }
        ]
    }
    assert (
        worker._tool_permission_map(snapshot)["mcp__fixture-server__fixture-tool"]
        == "always_ask"
    )
