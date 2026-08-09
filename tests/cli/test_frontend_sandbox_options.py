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

"""Tests for shared local Sandbox serve options."""

import os
from typing import Any

import pytest
from click import ClickException, Command
from click.testing import CliRunner

from veadk.cli.cli_frontend import frontend, studio
from veadk.cli.cli import _bootstrap_serve_provider


def test_serve_provider_is_bootstrapped_before_command_modules_load(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setenv("CLOUD_PROVIDER", "byteplus")

    _bootstrap_serve_provider(["frontend"])

    assert os.environ["AGENTKIT_CLOUD_PROVIDER"] == "volcengine"
    assert os.environ["CLOUD_PROVIDER"] == "volcengine"

    _bootstrap_serve_provider(["studio", "--provider", "byteplus"])

    assert os.environ["AGENTKIT_CLOUD_PROVIDER"] == "byteplus"
    assert os.environ["CLOUD_PROVIDER"] == "byteplus"


@pytest.mark.parametrize("command", [frontend, studio])
def test_sandbox_tool_options_are_shared_by_local_serve_commands(
    monkeypatch: pytest.MonkeyPatch,
    command: Command,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "chat-from-env")
    monkeypatch.setenv("SANDBOX_CHAT_OPENCLAW", "openclaw-from-env")
    monkeypatch.setenv("SANDBOX_CHAT_HERMES", "hermes-from-env")
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(
        command,
        [
            "--sandbox-chat-codex-tool-id",
            "chat-from-cli",
            "--sandbox-chat-openclaw-tool-id",
            "openclaw-from-cli",
            "--sandbox-chat-hermes-tool-id",
            "hermes-from-cli",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["sandbox_chat_codex_tool_id"] == "chat-from-cli"
    assert captured["sandbox_chat_openclaw_tool_id"] == "openclaw-from-cli"
    assert captured["sandbox_chat_hermes_tool_id"] == "hermes-from-cli"
    assert "sandbox_skill_creator_tool_id" not in captured


def test_local_sandbox_tool_options_fall_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "chat-from-env")
    monkeypatch.setenv("SANDBOX_CHAT_OPENCLAW", "openclaw-from-env")
    monkeypatch.setenv("SANDBOX_CHAT_HERMES", "hermes-from-env")
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(studio)

    assert result.exit_code == 0, result.output
    assert captured["sandbox_chat_codex_tool_id"] == "chat-from-env"
    assert captured["sandbox_chat_openclaw_tool_id"] == "openclaw-from-env"
    assert captured["sandbox_chat_hermes_tool_id"] == "hermes-from-env"
    assert "sandbox_skill_creator_tool_id" not in captured


@pytest.mark.parametrize("command", [frontend, studio])
def test_local_serve_commands_default_to_volcengine(
    monkeypatch: pytest.MonkeyPatch,
    command: Command,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("AGENTKIT_CLOUD_PROVIDER", "byteplus")
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(command)

    assert result.exit_code == 0, result.output
    assert captured["provider"] == "volcengine"


@pytest.mark.parametrize("command", [frontend, studio])
def test_local_serve_commands_accept_explicit_byteplus_provider(
    monkeypatch: pytest.MonkeyPatch,
    command: Command,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(command, ["--provider", "byteplus"])

    assert result.exit_code == 0, result.output
    assert captured["provider"] == "byteplus"


def test_studio_deploy_byteplus_uses_builtin_application_template(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SESSION_TOKEN", raising=False)
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._resolve_studio_cloud_credentials",
        lambda *_, **__: (_ for _ in ()).throw(
            ClickException("BytePlus credentials required.")
        ),
    )

    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--provider",
            "byteplus",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
            "--iam-role",
            "trn:iam::3001037806:role/dev",
        ],
    )

    assert result.exit_code != 0
    assert "BytePlus credentials required" in result.output
    assert "--vefaas-application-template-id" not in result.output


def test_studio_deploy_byteplus_rejects_non_singapore_region() -> None:
    result = CliRunner().invoke(
        studio,
        [
            "deploy",
            "--provider",
            "byteplus",
            "--region",
            "cn-beijing",
            "--user-pool-id",
            "pool-id",
            "--allowed-client-id",
            "client-id",
            "--vefaas-app-name",
            "studio-app",
        ],
    )

    assert result.exit_code != 0
    assert "currently supports only ap-southeast-1" in result.output
