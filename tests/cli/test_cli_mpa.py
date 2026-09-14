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

"""Tests for `veadk mpa create` command (FR-1/FR-2/FR-7/FR-8, VC-1/2/3/13/14/17)."""

from __future__ import annotations

from typing import Any

import pytest
from click.testing import CliRunner

from veadk.cli import cli_mpa


def _base_args(**overrides: str) -> list[str]:
    args = {
        "--image": "registry.example.com/mpa:latest",
        "--registry-name": "registry",
        "--mpa-agent-id": "mi-abc",
        "--account-id": "2100000001",
        "--pg-host": "pg.example.com",
        "--pg-database": "mpa",
        "--pg-user": "mpauser",
        "--pg-password": "pg-secret",
        "--model-provider": "openai",
        "--model-api-base": "https://ark.example.com/api/v3/",
        "--model-api-key": "model-secret",
        "--model-name": "doubao-seed",
        "--agentkit-tool-id": "tool-1",
    }
    for key, value in overrides.items():
        args[f"--{key.replace('_', '-')}"] = value
    flat: list[str] = ["create"]
    for key, value in args.items():
        flat.extend([key, value])
    return flat


def test_mpa_group_registers_create() -> None:
    """VC-1: `veadk mpa` exposes `create`."""
    runner = CliRunner()
    result = runner.invoke(cli_mpa.mpa, ["--help"])
    assert result.exit_code == 0
    assert "create" in result.output


def test_gateway_resolution_never_falls_back_to_an_unrelated_gateway() -> None:
    gateways = [
        type("Gateway", (), {"id": "gda-unrelated", "type": "standard"})(),
        type("Gateway", (), {"id": "gdb-unrelated", "type": "serverless"})(),
    ]
    assert cli_mpa._gateway_id_from_endpoint_prefix("shared-host", gateways) == ""


def test_gateway_resolution_accepts_only_an_exact_embedded_id() -> None:
    gateways = [type("Gateway", (), {"id": "gda-matching"})()]
    assert (
        cli_mpa._gateway_id_from_endpoint_prefix("gda-matching", gateways)
        == "gda-matching"
    )


def test_top_level_commands_still_resolve() -> None:
    """VC-1: registering mpa does not drop existing top-level commands."""
    from veadk.cli.cli import veadk

    runner = CliRunner()
    result = runner.invoke(veadk, ["--help"])
    assert result.exit_code == 0
    for name in ("deploy", "init", "create", "frontend", "studio", "agentkit", "mpa"):
        assert name in result.output


def test_create_missing_required_param_named_error() -> None:
    """VC-2: a missing required option fails with a named error, no side effects."""
    runner = CliRunner()
    args = _base_args()
    # Drop --image and its value.
    idx = args.index("--image")
    del args[idx : idx + 2]
    result = runner.invoke(cli_mpa.mpa, args)
    assert result.exit_code != 0
    assert "--image" in result.output


def test_create_config_yaml_supplies_defaults(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """--config YAML fills option defaults so they can be omitted on the CLI."""
    import yaml

    cfg = {
        "image": "registry.example.com/mpa:latest",
        "registry-name": "registry",
        "mpa-agent-id": "mi-abc",
        "account-id": "2100000001",
        "pg-host": "pg.example.com",
        "pg-database": "mpa",
        "pg-user": "mpauser",
        "pg-password": "pg-secret",
        "model-provider": "openai",
        "model-api-base": "https://ark.example.com/api/v3/",
        "model-api-key": "model-secret",
        "model-name": "doubao-seed",
        "agentkit-tool-id": "tool-1",
        "compute-plane": "vefaas",
    }
    cfg_path = tmp_path / "mpa-create.config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    runner = CliRunner()
    # Only --config + --dry-run; every required option comes from the YAML.
    result = runner.invoke(
        cli_mpa.mpa, ["create", "--config", str(cfg_path), "--dry-run"]
    )
    assert result.exit_code == 0, result.output
    assert "pg-secret" not in result.output  # secrets masked
    assert "MPA_AGENT_ID" in result.output or "mpa_meta" in result.output


def test_create_cli_option_overrides_config(tmp_path) -> None:
    """Explicit CLI options win over --config YAML values."""
    import yaml

    cfg = {
        "image": "registry.example.com/from-config:latest",
        "registry-name": "registry",
        "mpa-agent-id": "mi-config",
        "account-id": "2100000001",
        "pg-host": "pg.example.com",
        "pg-database": "mpa",
        "pg-user": "mpauser",
        "pg-password": "pg-secret",
        "model-provider": "openai",
        "model-api-base": "https://ark.example.com/api/v3/",
        "model-api-key": "model-secret",
        "model-name": "doubao-seed",
        "agentkit-tool-id": "tool-1",
        "compute-plane": "vefaas",
    }
    cfg_path = tmp_path / "mpa-create.config.yaml"
    cfg_path.write_text(yaml.safe_dump(cfg))

    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa,
        [
            "create",
            "--config",
            str(cfg_path),
            "--mpa-agent-id",
            "mi-override",
            "--dry-run",
        ],
    )
    assert result.exit_code == 0, result.output
    # Overridden id present; config id absent.
    assert "mi-override" in result.output
    assert "mi-config" not in result.output


def test_create_config_missing_file_errors() -> None:
    """A --config path that does not exist fails clearly without side effects."""
    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa, ["create", "--config", "/no/such/file.yaml", "--dry-run"]
    )
    assert result.exit_code != 0
    assert "config file not found" in result.output


def test_create_dry_run_masks_secrets_and_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-14: --dry-run prints the plan with masked secrets and mutates nothing."""
    calls: dict[str, int] = {"deploy": 0, "seed": 0}

    def _fail_deploy(*args: Any, **kwargs: Any):
        calls["deploy"] += 1
        raise AssertionError("dry-run must not deploy")

    def _fail_seed(*args: Any, **kwargs: Any):
        calls["seed"] += 1
        raise AssertionError("dry-run must not seed")

    monkeypatch.setattr(cli_mpa, "_deploy_image", _fail_deploy)
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", _fail_seed)

    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa, _base_args(compute_plane="vefaas") + ["--dry-run"]
    )
    assert result.exit_code == 0, result.output
    # Secrets masked.
    assert "pg-secret" not in result.output
    assert "model-secret" not in result.output
    # Plan shown.
    assert "mpa_meta" in result.output or "MPA_AGENT_ID" in result.output
    assert calls["deploy"] == 0
    assert calls["seed"] == 0


def test_create_accepts_repeatable_selectable_models_in_dry_run() -> None:
    result = CliRunner().invoke(
        cli_mpa.mpa,
        _base_args(compute_plane="vefaas")
        + [
            "--selectable-model",
            "doubao-alt-1",
            "--selectable-model",
            "doubao-alt-2",
            "--dry-run",
        ],
    )

    assert result.exit_code == 0, result.output
    assert (
        "MPA_SELECTABLE_MODELS=doubao-seed,doubao-alt-1,doubao-alt-2" in result.output
    )


def test_create_prompts_hidden_for_feishu_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-3: --feishu-app-id without a secret triggers a hidden prompt."""
    captured: dict[str, Any] = {}

    def _fake_prompt(text: str, *, hide_input: bool = False, **kwargs: Any) -> str:
        captured["text"] = text
        captured["hide_input"] = hide_input
        return "fs-secret"

    monkeypatch.setattr(cli_mpa.click, "prompt", _fake_prompt)

    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa,
        _base_args(feishu_app_id="cli_x") + ["--dry-run"],
    )
    assert result.exit_code == 0, result.output
    assert captured.get("hide_input") is True
    # The secret must not be echoed in the dry-run plan.
    assert "fs-secret" not in result.output


def test_create_full_flow_orchestration_vefaas(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-14: --compute-plane vefaas reproduces route A (deploy->seed->verify)."""
    order: list[str] = []

    def _deploy(**kwargs: Any):
        order.append("deploy")
        assert kwargs["enable_key_auth"] is True
        return {
            "public_endpoint": "https://app.example.com",
            "app_id": "app-1",
            "function_id": "fn-1",
            "apig_instance_id": "gw-1",
            "runtime_api_key": "rk-1",
        }

    def _pre_seed(engine: Any, *, mpa_agent_id: str, values: dict, **kwargs: Any):
        order.append("pre_seed")
        assert mpa_agent_id == "mi-abc"
        # phase 1 placeholders present and complete.
        assert values["runtime_id"] == "pending"
        return values

    def _finalize(engine: Any, *, mpa_agent_id: str, values: dict, **kwargs: Any):
        order.append("finalize")
        # vefaas plane: runtime_id is the app id.
        assert values["runtime_id"] == "app-1"
        assert values["private_endpoint"] == values["public_endpoint"]
        return values

    def _verify(endpoint: str, **kwargs: Any):
        order.append("verify")
        return cli_mpa.VerificationResult(endpoint=endpoint, passed=True)

    monkeypatch.setattr(cli_mpa, "_deploy_image", lambda **kw: _deploy(**kw))
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: object())
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", _pre_seed)
    monkeypatch.setattr(cli_mpa, "overwrite_mpa_meta", _finalize)
    monkeypatch.setattr(cli_mpa, "verify_instance", _verify)

    runner = CliRunner()
    result = runner.invoke(cli_mpa.mpa, _base_args(compute_plane="vefaas"))
    assert result.exit_code == 0, result.output
    assert order == ["pre_seed", "deploy", "finalize", "verify"]
    # FR-7: Studio guidance in output.
    assert "agent-card.json" in result.output
    assert "https://app.example.com" in result.output


def test_create_orchestration_order_runtime_plane(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC-15/19: order SkillSpace->Tool->pre-seed->runtime->finalize->verify."""
    order: list[str] = []

    monkeypatch.setattr(cli_mpa, "_skills_client", lambda region: object())
    monkeypatch.setattr(cli_mpa, "_tools_client", lambda region: object())
    monkeypatch.setattr(cli_mpa, "_runtime_client", lambda region: object())
    monkeypatch.setattr(
        cli_mpa, "_resolve_apig_instance_id", lambda region: (lambda ep: "gw-r")
    )

    def _ensure_space(client: Any, *, name: str, **kw: Any) -> str:
        order.append("skill_space")
        assert name == "my-space"
        return "ss-1"

    def _ensure_tool(client: Any, *, name: str, image: str, **kw: Any) -> str:
        order.append("tool")
        assert name == "mi_generated123"
        assert image == "registry.example.com/worker:tag"
        assert kw["role_name"] == "CustomMpaRole"
        return "t-created"

    def _provision(client: Any, **kwargs: Any):
        order.append("runtime")
        assert kwargs["name"] == "mi-generated123"
        assert kwargs["tool_id"] == "t-created"
        assert kwargs["artifact_url"] == "registry.example.com/mpa:latest"
        # SKILL_SPACE_ID injected into runtime env.
        assert kwargs["envs"].get("SKILL_SPACE_ID") == "ss-1"
        return {
            "public_endpoint": "https://rt.example.com",
            "runtime_id": "r-xyz",
            "apig_instance_id": "gw-r",
            "runtime_api_key": "rk-r",
        }

    def _pre_seed(engine: Any, *, mpa_agent_id: str, values: dict, **kwargs: Any):
        order.append("pre_seed")
        # FR-19 phase 1: all seven fields present (placeholders allowed).
        for field in (
            "account_id",
            "resource_account_id",
            "runtime_id",
            "public_endpoint",
            "private_endpoint",
            "runtime_api_key",
            "apig_instance_id",
        ):
            assert values.get(field)
        # runtime_id is still a placeholder at phase 1.
        assert values["runtime_id"] == "pending"
        return values

    def _finalize(engine: Any, *, mpa_agent_id: str, values: dict, **kwargs: Any):
        order.append("finalize")
        # FR-19 phase 2: real values overwrite placeholders.
        assert values["runtime_id"] == "r-xyz"
        assert values["public_endpoint"] == "https://rt.example.com"
        assert values["private_endpoint"] == "https://rt.example.com"
        return values

    def _verify(endpoint: str, **kwargs: Any):
        order.append("verify")
        return cli_mpa.VerificationResult(endpoint=endpoint, passed=True)

    monkeypatch.setattr(cli_mpa, "ensure_skill_space", _ensure_space)
    monkeypatch.setattr(cli_mpa, "ensure_codex_worker_tool", _ensure_tool)
    monkeypatch.setattr(cli_mpa, "provision_runtime", _provision)
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: object())
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", _pre_seed)
    monkeypatch.setattr(cli_mpa, "overwrite_mpa_meta", _finalize)
    monkeypatch.setattr(cli_mpa, "verify_instance", _verify)
    monkeypatch.setattr(cli_mpa, "generate_mpa_agent_id", lambda: "mi-generated123")

    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa,
        _base_args(
            mpa_agent_id="",
            agentkit_tool_id="",
            tool_image="registry.example.com/worker:tag",
            tool_role_name="CustomMpaRole",
            skill_space_name="my-space",
        ),
    )
    assert result.exit_code == 0, result.output
    assert order == [
        "skill_space",
        "tool",
        "pre_seed",
        "runtime",
        "finalize",
        "verify",
    ]
    assert "agent-card.json" in result.output
    assert "mpa-agent-id: mi-generated123" in result.output


def test_runtime_plane_without_gateway_id_fails_before_finalize(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Shared-gateway runtimes must not persist an arbitrary APIG id."""
    finalized: list[dict[str, Any]] = []
    monkeypatch.setattr(cli_mpa, "_runtime_client", lambda region: object())
    monkeypatch.setattr(
        cli_mpa, "_resolve_apig_instance_id", lambda region: (lambda ep: "")
    )
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: object())
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", lambda *a, **kw: kw["values"])
    monkeypatch.setattr(
        cli_mpa, "overwrite_mpa_meta", lambda *a, **kw: finalized.append(kw)
    )
    monkeypatch.setattr(
        cli_mpa,
        "provision_runtime",
        lambda *a, **kw: {
            "public_endpoint": "https://shared.example.com",
            "runtime_id": "r-shared",
            "apig_instance_id": "",
            "runtime_api_key": "rk-shared",
        },
    )

    result = CliRunner().invoke(cli_mpa.mpa, _base_args())

    assert result.exit_code != 0
    assert "returned no apig_instance_id" in result.output
    assert "No arbitrary APIG gateway" in result.output
    assert finalized == []


def test_explicit_gateway_id_finalizes_shared_gateway_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finalized: list[dict[str, Any]] = []
    monkeypatch.setattr(cli_mpa, "_runtime_client", lambda region: object())
    monkeypatch.setattr(
        cli_mpa, "_resolve_apig_instance_id", lambda region: (lambda ep: "")
    )
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: object())
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", lambda *a, **kw: kw["values"])
    monkeypatch.setattr(
        cli_mpa,
        "overwrite_mpa_meta",
        lambda *a, **kw: finalized.append(kw["values"]) or kw["values"],
    )
    monkeypatch.setattr(
        cli_mpa,
        "provision_runtime",
        lambda *a, **kw: {
            "public_endpoint": "https://shared.example.com",
            "runtime_id": "r-shared",
            "apig_instance_id": "",
            "runtime_api_key": "rk-shared",
        },
    )
    monkeypatch.setattr(
        cli_mpa,
        "verify_instance",
        lambda *a, **kw: cli_mpa.VerificationResult(endpoint=a[0], passed=True),
    )

    result = CliRunner().invoke(
        cli_mpa.mpa, _base_args(apig_instance_id="gda-dedicated")
    )

    assert result.exit_code == 0, result.output
    assert finalized[0]["apig_instance_id"] == "gda-dedicated"


def test_generated_identity_missing_tool_input_fails_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VC-22: runtime mode requires Tool input before any side effect."""
    calls: list[str] = []

    monkeypatch.setattr(cli_mpa, "generate_mpa_agent_id", lambda: "mi-generated123")
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: calls.append("db"))
    monkeypatch.setattr(
        cli_mpa, "_skills_client", lambda region: calls.append("skills")
    )
    monkeypatch.setattr(cli_mpa, "_tools_client", lambda region: calls.append("tools"))
    monkeypatch.setattr(
        cli_mpa, "_runtime_client", lambda region: calls.append("runtime")
    )

    runner = CliRunner()
    result = runner.invoke(
        cli_mpa.mpa,
        _base_args(mpa_agent_id="", agentkit_tool_id=""),
    )

    assert result.exit_code != 0
    assert "--tool-image" in result.output
    assert calls == []
