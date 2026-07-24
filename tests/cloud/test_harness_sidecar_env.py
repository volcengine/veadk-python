import json

from veadk.cloud.harness_app.env_mapping import to_runtime_env


def test_nested_harness_sidecar_uses_public_product_env_names() -> None:
    env = to_runtime_env(
        {
            "harness": {
                "profile": "ops",
                "sidecar": {
                    "enabled": True,
                    "model_proxy": {"enabled": False},
                    "mcp_gateway": {
                        "enabled": True,
                    },
                },
            }
        }
    )

    assert env["HARNESS_SIDECAR_ENABLED"] == "true"
    assert env["HARNESS_PROFILE"] == "ops"
    assert env["HARNESS_MODEL_PROXY_ENABLED"] == "false"
    assert env["HARNESS_MCP_PRESETS"] == "sql_readonly"
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == "*"
    assert not any(key.startswith("HARNESS_SIDECAR_MCP_") for key in env)


def test_boolean_sidecar_shorthand_uses_profile_defaults() -> None:
    env = to_runtime_env({"harness": {"profile": "ops", "sidecar": True}})

    assert env["HARNESS_SIDECAR_ENABLED"] == "true"
    assert env["HARNESS_PROFILE"] == "ops"
    assert env["HARNESS_MCP_GATEWAY_ENABLED"] == "true"
    assert env["HARNESS_MCP_PRESETS"] == "sql_readonly"
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == "*"


def test_product_component_overrides_are_carried_by_versioned_plan() -> None:
    env = to_runtime_env(
        {
            "harness": {
                "profile": "ops",
                "sidecar": {
                    "enabled": True,
                    "component_overrides": {
                        "verifier": False,
                        "sql_readonly": False,
                    },
                },
            }
        }
    )

    plan = json.loads(env["HARNESS_SIDECAR_PLAN"])
    assert plan["schema_version"] == "agentkit.harness-sidecar.plan/v1"
    assert "verifier" not in plan["effective_components"]
    assert "sql_readonly" not in plan["effective_components"]
    assert env["HARNESS_MCP_PRESETS"] == ""
    assert env["HARNESS_MCP_READONLY_SEGMENTS"] == ""
