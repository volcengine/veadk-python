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

from typing import Any

import pytest

from veadk.extensions.harness import sidecar


def _component(
    component_id: str,
    *,
    display_name: str,
    description: str,
    dependencies: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": component_id,
        "display_name": display_name,
        "description": description,
        "dependencies": dependencies or [],
        "risk_level": "standard",
        "status": "ga",
        "availability": {
            "available": True,
            "status": "ga",
            "reason": None,
            "min_runtime_version": None,
            "regions": [],
        },
    }


def _catalog() -> dict[str, Any]:
    components = [
        _component(
            "context_engine",
            display_name="上下文治理",
            description="上下文治理",
        ),
        _component(
            "compressor",
            display_name="上下文与结果压缩",
            description="压缩",
        ),
        _component(
            "verifier",
            display_name="回答校验与修复",
            description="校验",
        ),
        _component(
            "long_run_control",
            display_name="长任务控制",
            description="长任务",
        ),
        _component(
            "mcp_resilience",
            display_name="MCP 稳定性治理",
            description="MCP 治理",
        ),
        _component(
            "sql_readonly",
            display_name="SQL 只读保护",
            description="SQL 只读",
            dependencies=["mcp_resilience"],
        ),
    ]
    return {"catalog_version": "2026.07.1", "components": components}


def _plan(
    *,
    effective: list[str],
    model_components: list[str] | None = None,
    mcp_enabled: bool = False,
) -> dict[str, Any]:
    return {
        "valid": True,
        "enabled": True,
        "profile": "default",
        "requested_components": effective,
        "effective_components": effective,
        "auto_added_components": [],
        "warnings": [],
        "errors": [],
        "catalog_version": "2026.07.1",
        "plan_hash": "sha256:runtime-plan",
        "activation_targets": {
            "model_proxy": {
                "enabled": bool(model_components),
                "components": model_components or [],
            },
            "mcp_gateway": {"enabled": mcp_enabled},
        },
    }


def test_normalize_studio_intent_derives_enabled_and_fills_all_options() -> None:
    intent = sidecar.normalize_studio_harness_intent(
        {
            "enabled": False,
            "profile": "default",
            "componentOverrides": {"verifier": True},
            "planHash": "untrusted",
        }
    )

    assert intent.enabled is True
    assert intent.profile == "default"
    assert intent.component_overrides == {
        "context_engine": False,
        "compressor": False,
        "verifier": True,
        "long_run_control": False,
        "mcp_resilience": False,
    }
    assert intent.plan_hash == "untrusted"


def test_normalize_studio_intent_preserves_ops_profile() -> None:
    intent = sidecar.normalize_studio_harness_intent(
        {
            "profile": "ops",
            "componentOverrides": {
                component_id: True
                for component_id in sidecar.STUDIO_HARNESS_COMPONENT_IDS
            },
        }
    )

    assert intent.enabled is True
    assert intent.profile == "ops"
    assert all(intent.component_overrides.values())


def test_normalize_studio_intent_rejects_hidden_sql_override() -> None:
    with pytest.raises(ValueError, match="sql_readonly"):
        sidecar.normalize_studio_harness_intent(
            {"componentOverrides": {"sql_readonly": True}}
        )


def test_catalog_exposes_fixed_five_options_without_runtime_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_sidecar_runtime_api",
        lambda: pytest.fail("option metadata must not load the runtime integration"),
    )

    catalog = sidecar.get_studio_harness_sidecar_catalog()

    assert [item["id"] for item in catalog["components"]] == list(
        sidecar.STUDIO_HARNESS_COMPONENT_IDS
    )
    assert (
        next(
            item for item in catalog["components"] if item["id"] == "long_run_control"
        )["displayName"]
        == "Goal任务控制"
    )
    mcp = next(item for item in catalog["components"] if item["id"] == "mcp_resilience")
    assert "默认包含 SQL 只读保护" in mcp["description"]
    assert all(item["selectable"] for item in catalog["components"])
    assert [profile["id"] for profile in catalog["profiles"]] == ["default", "ops"]
    assert catalog["profiles"][0]["defaultComponents"] == [
        "context_engine",
        "compressor",
        "verifier",
        "long_run_control",
    ]
    assert catalog["profiles"][1]["defaultComponents"] == list(
        sidecar.STUDIO_HARNESS_COMPONENT_IDS
    )
    assert catalog["profiles"][1]["autoAddedComponents"] == ["sql_readonly"]


def test_resolver_adds_sql_readonly_only_on_the_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: list[str] = []

    def resolve(arguments: list[str]) -> dict[str, Any]:
        captured.extend(arguments)
        return _plan(
            effective=["mcp_resilience", "sql_readonly"],
            mcp_enabled=True,
        )

    monkeypatch.setattr(sidecar, "_run_agentkit_cli_json", resolve)

    result = sidecar.resolve_studio_harness_sidecar_selection(
        {"componentOverrides": {"mcp_resilience": True}}
    )

    components = [
        captured[index + 1]
        for index, argument in enumerate(captured[:-1])
        if argument == "--component"
    ]
    assert "mcp_resilience=true" in components
    assert all(not item.startswith("sql_readonly=") for item in components)
    assert result["requestedComponents"] == ["mcp_resilience"]
    assert result["effectiveComponents"] == ["mcp_resilience", "sql_readonly"]
    assert result["autoAddedComponents"] == [
        {"id": "sql_readonly", "requiredBy": ["mcp_resilience"]}
    ]
    assert result["planHash"] == "sha256:runtime-plan"


def test_runtime_env_uses_resolved_plan_without_private_artifact_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def to_env(config: dict[str, Any], *, profile: str) -> dict[str, str]:
        captured.update(config)
        captured["profile_arg"] = profile
        return {"HARNESS_SIDECAR_ENABLED": "true"}

    class RuntimeApi:
        sidecar_config_to_env = staticmethod(to_env)

    monkeypatch.setattr(sidecar, "_sidecar_runtime_api", RuntimeApi)
    monkeypatch.setattr(
        sidecar,
        "_run_agentkit_cli_json",
        lambda _arguments: _plan(
            effective=["context_engine"],
            model_components=["context_engine"],
        ),
    )

    env, plan = sidecar.studio_harness_runtime_env(
        {"componentOverrides": {"context_engine": True}},
        transport="apig_runtime_port",
    )

    assert captured["fail_open"] is False
    assert captured["transport"] == "apig_runtime_port"
    assert captured["model_proxy"]["port"] == 18787
    assert captured["mcp_gateway"]["enabled"] is False
    assert captured["component_overrides"]["sql_readonly"] is False
    assert captured["profile_arg"] == "default"
    assert env["HARNESS_SIDECAR_EXPECTED_PLAN_HASH"] == "sha256:runtime-plan"
    assert plan["planHash"] == "sha256:runtime-plan"
    assert "artifact" not in str(env).lower()


def test_deployment_config_keeps_only_public_intent_and_checks_plan_hash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_run_agentkit_cli_json",
        lambda _arguments: _plan(
            effective=["mcp_resilience", "sql_readonly"],
            mcp_enabled=True,
        ),
    )

    config, plan = sidecar.studio_harness_deployment_config(
        {
            "componentOverrides": {"mcp_resilience": True},
            "planHash": "sha256:runtime-plan",
        }
    )

    assert config == {
        "enabled": True,
        "profile": "default",
        "catalog_version": "2026.07.1",
        "component_overrides": {
            "context_engine": False,
            "compressor": False,
            "verifier": False,
            "long_run_control": False,
            "mcp_resilience": True,
        },
    }
    assert plan["planHash"] == "sha256:runtime-plan"
    assert "artifact" not in str(config).lower()

    with pytest.raises(ValueError, match="plan has changed"):
        sidecar.studio_harness_deployment_config(
            {
                "componentOverrides": {"mcp_resilience": True},
                "planHash": "sha256:stale",
            }
        )


def test_disabled_selection_never_loads_runtime_integration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_sidecar_runtime_api",
        lambda: pytest.fail(
            "disabled selection must not load the Sidecar runtime integration"
        ),
    )

    plan = sidecar.resolve_studio_harness_sidecar_selection(None)
    deployment, deployment_plan = sidecar.studio_harness_deployment_config(
        {"componentOverrides": {"mcp_resilience": False}}
    )
    runtime_env, runtime_plan = sidecar.studio_harness_runtime_env(
        None,
        transport="local",
    )

    assert plan["valid"] is True
    assert plan["enabled"] is False
    assert plan["requestedComponents"] == []
    assert plan["effectiveComponents"] == []
    assert plan["planHash"] == ""
    assert deployment == {}
    assert deployment_plan == plan
    assert runtime_env == {}
    assert runtime_plan == plan
