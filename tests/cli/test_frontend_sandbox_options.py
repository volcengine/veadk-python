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

from typing import Any

import pytest
from click import Command
from click.testing import CliRunner

from veadk.cli.cli_frontend import frontend, studio


@pytest.mark.parametrize("command", [frontend, studio])
def test_sandbox_tool_options_are_shared_by_local_serve_commands(
    monkeypatch: pytest.MonkeyPatch,
    command: Command,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "chat-from-env")
    monkeypatch.setenv("SANDBOX_SKILL_CREATOR", "skill-from-env")
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "openclaw-from-env")
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-from-env")
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(
        command,
        [
            "--sandbox-chat-codex-tool-id",
            "chat-from-cli",
            "--sandbox-skill-creator-tool-id",
            "skill-from-cli",
            "--sandbox-openclaw-tool-id",
            "openclaw-from-cli",
            "--sandbox-hermes-tool-id",
            "hermes-from-cli",
        ],
    )

    assert result.exit_code == 0, result.output
    assert captured["sandbox_chat_codex_tool_id"] == "chat-from-cli"
    assert captured["sandbox_skill_creator_tool_id"] == "skill-from-cli"
    assert captured["sandbox_openclaw_tool_id"] == "openclaw-from-cli"
    assert captured["sandbox_hermes_tool_id"] == "hermes-from-cli"


def test_local_sandbox_tool_options_fall_back_to_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "chat-from-env")
    monkeypatch.setenv("SANDBOX_SKILL_CREATOR", "skill-from-env")
    monkeypatch.setenv("SANDBOX_OPENCLAW_TOOL", "openclaw-from-env")
    monkeypatch.setenv("SANDBOX_HERMES_TOOL", "hermes-from-env")
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._run_frontend_server",
        lambda **kwargs: captured.update(kwargs),
    )

    result = CliRunner().invoke(studio)

    assert result.exit_code == 0, result.output
    assert captured["sandbox_chat_codex_tool_id"] == "chat-from-env"
    assert captured["sandbox_skill_creator_tool_id"] == "skill-from-env"
    assert captured["sandbox_openclaw_tool_id"] == "openclaw-from-env"
    assert captured["sandbox_hermes_tool_id"] == "hermes-from-env"
