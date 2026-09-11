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
    result = runner.invoke(cli_mpa.mpa, _base_args() + ["--dry-run"])
    assert result.exit_code == 0, result.output
    # Secrets masked.
    assert "pg-secret" not in result.output
    assert "model-secret" not in result.output
    # Plan shown.
    assert "mpa_meta" in result.output or "MPA_AGENT_ID" in result.output
    assert calls["deploy"] == 0
    assert calls["seed"] == 0


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


def test_create_full_flow_orchestration(monkeypatch: pytest.MonkeyPatch) -> None:
    """Parameters -> deploy -> seed -> verify are wired in order (happy path)."""
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

    def _seed(engine: Any, *, mpa_agent_id: str, values: dict, **kwargs: Any):
        order.append("seed")
        assert mpa_agent_id == "mi-abc"
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
        assert values["private_endpoint"] == values["public_endpoint"]
        return values

    def _verify(endpoint: str, **kwargs: Any):
        order.append("verify")
        return cli_mpa.VerificationResult(endpoint=endpoint, passed=True)

    monkeypatch.setattr(cli_mpa, "_deploy_image", lambda **kw: _deploy(**kw))
    monkeypatch.setattr(cli_mpa, "_make_seed_engine", lambda params: object())
    monkeypatch.setattr(cli_mpa, "seed_mpa_meta", _seed)
    monkeypatch.setattr(cli_mpa, "verify_instance", _verify)

    runner = CliRunner()
    result = runner.invoke(cli_mpa.mpa, _base_args())
    assert result.exit_code == 0, result.output
    assert order == ["deploy", "seed", "verify"]
    # FR-7: Studio guidance in output.
    assert "agent-card.json" in result.output
    assert "https://app.example.com" in result.output
