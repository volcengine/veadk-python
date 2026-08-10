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

from __future__ import annotations

import json
from secrets import token_urlsafe

import pytest

from veadk.extensions.harness.sidecar_runtime.deploy import to_runtime_env
from veadk.extensions.harness.sidecar_runtime.runtime_components import (
    RUNTIME_COMPONENT_DEPENDENCIES,
    RUNTIME_COMPONENT_ORDER,
)
from veadk.extensions.harness.sidecar_runtime.sidecar_config import (
    HarnessSidecarConfig,
    resolve_sidecar_config,
    sidecar_config_to_env,
)


def test_internal_runtime_inventory_matches_single_wheel_contract() -> None:
    assert RUNTIME_COMPONENT_ORDER == (
        "harness_core",
        "ops",
        "goal_runtime",
        "model_proxy",
        "mcp_gateway",
        "browser_runtime",
        "eval_runtime",
        "shadow_runtime",
    )


def test_vertical_runtime_components_depend_only_on_harness_core() -> None:
    assert RUNTIME_COMPONENT_DEPENDENCIES["harness_core"] == ()
    assert {
        component: dependencies
        for component, dependencies in RUNTIME_COMPONENT_DEPENDENCIES.items()
        if component != "harness_core"
    } == {
        component: ("harness_core",)
        for component in RUNTIME_COMPONENT_ORDER
        if component != "harness_core"
    }


def test_ops_profile_expands_product_defaults() -> None:
    config = HarnessSidecarConfig(profile="ops")

    assert config.model_proxy.enabled is True
    assert config.mcp_gateway.enabled is True
    assert config.mcp_gateway.presets == ["sql_readonly"]
    assert config.mcp_gateway.readonly_segments == ["*"]
    assert config.mcp_gateway.policy["result_quality"]["empty_is_unhealthy"] is True
    assert config.mcp_gateway.policy["budget"]["max_calls_per_session"] == 70
    assert config.runtime_flavor == "harness-sidecar"
    assert config.required_runtime_components == [
        "harness_core",
        "ops",
        "goal_runtime",
        "model_proxy",
        "mcp_gateway",
    ]


def test_explicit_values_override_profile_defaults() -> None:
    config = resolve_sidecar_config(
        {
            "profile": "ops",
            "model_proxy": {"enabled": False},
            "mcp_gateway": {"policy": {"large_result": {"max_bytes": 65_536}}},
        }
    )

    assert config.model_proxy.enabled is False
    assert config.mcp_gateway.policy["large_result"]["max_bytes"] == 65_536
    assert config.mcp_gateway.policy["budget"]["max_calls_per_session"] == 70


def test_unknown_profile_fails_fast() -> None:
    with pytest.raises(ValueError, match="Unknown Harness Sidecar profile"):
        HarnessSidecarConfig(profile="unknown")


def test_runtime_payload_excludes_public_launcher_details() -> None:
    config = HarnessSidecarConfig(
        profile="ops", runtime_command=["python", "fake-runtime.py"]
    )

    payload = config.runtime_payload()

    assert "runtime_command" not in payload
    assert "startup_timeout_seconds" not in payload
    assert payload["profile"] == "ops"
    assert payload["runtime_components"] == config.required_runtime_components


def test_apig_runtime_port_env_round_trip_and_runtime_payload() -> None:
    env = sidecar_config_to_env(
        {
            "profile": "ops",
            "fail_open": False,
            "transport": "apig_runtime_port",
            "model_proxy": {
                "host": "0.0.0.0",
                "port": 18787,
                "prefer_configured_upstream_api_key": True,
            },
            "mcp_gateway": {
                "enabled": True,
                "host": "0.0.0.0",
                "port": 18788,
                "upstreams_env": "TOOL_MCP_ROUTER_URL",
                "upstream_api_key_env": "TOOL_MCP_ROUTER_API_KEY",
                "prefer_configured_upstream_api_key": True,
                "fail_open": False,
            },
        }
    )
    env["TOOL_MCP_ROUTER_URL"] = "https://toolset.example/mcp"
    env["TOOL_MCP_ROUTER_API_KEY"] = token_urlsafe(24)

    config = HarnessSidecarConfig.from_env(env)
    payload = config.runtime_payload()

    assert config.transport == "apig_runtime_port"
    assert config.model_proxy.host == "0.0.0.0"
    assert config.model_proxy.port == 18787
    assert config.model_proxy.prefer_configured_upstream_api_key is True
    assert env["HARNESS_SIDECAR_TRANSPORT"] == "apig_runtime_port"
    assert env["HARNESS_MODEL_PROXY_PORT"] == "18787"
    assert payload["model_proxy"]["host"] == "0.0.0.0"
    assert payload["model_proxy"]["port"] == 18787
    assert payload["model_proxy"]["prefer_configured_upstream_api_key"] is True
    assert config.mcp_gateway.host == "0.0.0.0"
    assert config.mcp_gateway.port == 18788
    assert config.mcp_gateway.upstreams == ["https://toolset.example/mcp"]
    assert config.mcp_gateway.upstream_api_key_env == "TOOL_MCP_ROUTER_API_KEY"
    assert config.mcp_gateway.prefer_configured_upstream_api_key is True
    assert config.mcp_gateway.fail_open is False
    assert env["HARNESS_MCP_GATEWAY_PORT"] == "18788"
    assert payload["runtime_components"] == (
        config.resolved_plan.activation_targets.runtime_components
    )
    assert payload["mcp_gateway"]["enabled"] is True
    assert payload["mcp_gateway"]["port"] == 18788
    assert payload["mcp_gateway"]["prefer_configured_upstream_api_key"] is True
    assert "runtime_gateway_endpoint_env" not in payload
    assert "runtime_gateway_api_key_env" not in payload


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"fail_open": True}, "fail_open=false"),
        ({"model_proxy": {"host": "127.0.0.1"}}, "externally reachable"),
        ({"model_proxy": {"port": 0}}, "fixed model proxy port"),
        ({"mcp_gateway": {"host": "127.0.0.1"}}, "MCP gateway host"),
        ({"mcp_gateway": {"port": 0}}, "fixed MCP gateway port"),
        ({"mcp_gateway": {"fail_open": True}}, "MCP fail_open=false"),
        (
            {"mcp_gateway": {"prefer_configured_upstream_api_key": False}},
            "configured MCP-upstream authorization",
        ),
    ],
)
def test_apig_runtime_port_rejects_unsafe_config(
    override: dict[str, object], message: str
) -> None:
    values: dict[str, object] = {
        "profile": "default",
        "fail_open": False,
        "transport": "apig_runtime_port",
        "model_proxy": {
            "host": "0.0.0.0",
            "port": 18787,
            "prefer_configured_upstream_api_key": True,
        },
        "mcp_gateway": {
            "enabled": True,
            "host": "0.0.0.0",
            "port": 18788,
            "upstreams": ["https://toolset.example/mcp"],
            "upstreams_env": "TOOL_MCP_ROUTER_URL",
            "upstream_api_key_env": "TOOL_MCP_ROUTER_API_KEY",
            "prefer_configured_upstream_api_key": True,
            "fail_open": False,
        },
    }
    for key, value in override.items():
        if key in {"model_proxy", "mcp_gateway"} and isinstance(value, dict):
            values[key] = {**dict(values[key]), **value}
        else:
            values[key] = value

    with pytest.raises(ValueError, match=message):
        HarnessSidecarConfig.model_validate(values)


def test_explicit_browser_component_resolves_dependency_closure() -> None:
    config = HarnessSidecarConfig(
        profile="default",
        components=["browser"],
        model_proxy={"enabled": False},
    )

    assert config.runtime_flavor == "harness-sidecar"
    assert config.required_runtime_components == [
        "harness_core",
        "browser_runtime",
    ]


@pytest.mark.parametrize("legacy_alias", ["ops", "ops_kernel"])
def test_legacy_ops_component_alias_resolves_internal_dependency(
    legacy_alias: str,
) -> None:
    config = HarnessSidecarConfig(
        profile="default",
        components=[legacy_alias],
        model_proxy={"enabled": False},
    )

    assert config.required_runtime_components == ["harness_core", "ops"]


def test_full_optional_component_set_resolves_full_flavor() -> None:
    config = HarnessSidecarConfig(
        profile="ops",
        components=["browser", "eval", "shadow"],
    )

    assert config.runtime_flavor == "harness-sidecar"
    assert config.required_runtime_components[-3:] == [
        "browser_runtime",
        "eval_runtime",
        "shadow_runtime",
    ]


def test_env_round_trip_keeps_product_semantics() -> None:
    env = sidecar_config_to_env(
        {
            "profile": "ops",
            "mcp_gateway": {
                "presets": ["sql_readonly"],
                "readonly_segments": ["bqmcp"],
            },
            "components": ["browser"],
        }
    )
    config = HarnessSidecarConfig.from_env(env)

    assert config.enabled is True
    assert config.profile == "ops"
    assert config.mcp_gateway.presets == ["sql_readonly"]
    assert config.mcp_gateway.readonly_segments == ["bqmcp"]
    assert config.components == ["browser"]


def test_default_env_profile_does_not_enable_mcp_gateway_implicitly() -> None:
    config = HarnessSidecarConfig.from_env({"HARNESS_SIDECAR_ENABLED": "true"})

    assert config.profile == "default"
    assert config.model_proxy.enabled is True
    assert config.mcp_gateway.enabled is False
    assert config.required_runtime_components == [
        "harness_core",
        "goal_runtime",
        "model_proxy",
    ]


def test_ops_env_profile_keeps_profile_readonly_defaults() -> None:
    config = HarnessSidecarConfig.from_env(
        {"HARNESS_SIDECAR_ENABLED": "true", "HARNESS_PROFILE": "ops"}
    )

    assert config.mcp_gateway.enabled is True
    assert config.mcp_gateway.presets == ["sql_readonly"]
    assert config.mcp_gateway.readonly_segments == ["*"]


def test_mcp_upstreams_are_materialized_from_configured_env() -> None:
    config = HarnessSidecarConfig.from_env(
        {
            "HARNESS_SIDECAR_ENABLED": "true",
            "HARNESS_PROFILE": "ops",
            "HARNESS_MCP_UPSTREAMS_ENV": "YUMC_MCP_URLS",
            "YUMC_MCP_URLS": "http://mcp-a.example/mcp, http://mcp-b.example/mcp",
        }
    )

    assert config.mcp_gateway.upstreams_env == "YUMC_MCP_URLS"
    assert config.mcp_gateway.upstreams == [
        "http://mcp-a.example/mcp",
        "http://mcp-b.example/mcp",
    ]


def test_deploy_env_mapping_supports_nested_harness_sidecar() -> None:
    env = to_runtime_env(
        {
            "description": "Yum China operations agent",
            "harness": {
                "enabled": True,
                "profile": "ops",
                "sidecar": {
                    "enabled": True,
                    "model_proxy": {"enabled": True},
                    "mcp_gateway": {"enabled": True},
                },
            },
        }
    )

    assert env["HARNESS_SIDECAR_ENABLED"] == "true"
    assert env["HARNESS_PROFILE"] == "ops"
    assert env["HARNESS_MCP_PRESETS"] == "sql_readonly"
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == "*"
    assert env["HARNESS_ENABLED"] == "true"
    assert env["DESCRIPTION"] == "Yum China operations agent"
    assert not any(key.startswith("HARNESS_SIDECAR_MCP_GATEWAY_") for key in env)


def test_deploy_env_mapping_supports_boolean_sidecar_shorthand() -> None:
    env = to_runtime_env({"harness": {"profile": "ops", "sidecar": True}})

    assert env["HARNESS_SIDECAR_ENABLED"] == "true"
    assert env["HARNESS_PROFILE"] == "ops"
    assert env["HARNESS_MCP_GATEWAY_ENABLED"] == "true"
    assert env["HARNESS_MCP_PRESETS"] == "sql_readonly"
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == "*"


def test_product_component_overrides_drive_technical_config_and_plan_env() -> None:
    env = sidecar_config_to_env(
        {
            "profile": "ops",
            "component_overrides": {
                "verifier": False,
                "sql_readonly": False,
            },
        }
    )

    plan = json.loads(env["HARNESS_SIDECAR_PLAN"])
    assert "verifier" not in plan["effective_components"]
    assert "sql_readonly" not in plan["effective_components"]
    assert env["HARNESS_MCP_PRESETS"] == ""
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == ""


def test_disabled_sidecar_has_no_runtime_or_product_components() -> None:
    config = HarnessSidecarConfig(profile="ops", enabled=False)

    assert config.required_runtime_components == []
    assert config.resolved_plan.effective_components == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (False, False),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        (True, True),
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
    ],
)
def test_profile_enabled_uses_type_aware_boolean_parsing(
    value: bool | str, expected: bool
) -> None:
    config = resolve_sidecar_config({"profile": "ops", "enabled": value})

    assert config.enabled is expected
    assert bool(config.required_runtime_components) is expected


def test_profile_enabled_rejects_ambiguous_values() -> None:
    with pytest.raises(ValueError, match="enabled must be a boolean"):
        resolve_sidecar_config({"enabled": "sometimes"})
