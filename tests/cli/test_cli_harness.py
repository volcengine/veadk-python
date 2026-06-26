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

import json
from pathlib import Path

import yaml
from click.testing import CliRunner

from veadk.cli import cli_harness


def test_harness_create_add_show_core_workflow() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem():
        create_result = runner.invoke(cli_harness.harness, ["create", "harness-app"])
        assert create_result.exit_code == 0, create_result.output

        add_result = runner.invoke(
            cli_harness.harness,
            [
                "add",
                "--path",
                "harness-app",
                "--name",
                "research-agent",
                "--model-name",
                "model-a",
                "--tools",
                "web_search,run_code",
                "--skills",
                "summarizer",
                "--system-prompt",
                "Research carefully.",
                "--runtime",
                "adk",
                "--short-term-memory-type",
                "sqlite",
                "--max-llm-calls",
                "8",
            ],
        )
        assert add_result.exit_code == 0, add_result.output

        data = yaml.safe_load((Path("harness-app") / "harness.yaml").read_text())
        assert data["harness_name"] == "research-agent"
        assert data["model"]["name"] == "model-a"
        assert data["tools"] == ["web_search", "run_code"]
        assert data["skills"] == ["summarizer"]
        assert data["system_prompt"] == "Research carefully."
        assert data["runtime"] == "adk"
        assert data["short_term_memory"]["type"] == "sqlite"
        assert data["max_llm_calls"] == 8

        show_result = runner.invoke(
            cli_harness.harness,
            ["show", "--path", "harness-app"],
        )
        assert show_result.exit_code == 0, show_result.output
        assert "Configured agent params" in show_result.output
        assert "--model-name" in show_result.output
        assert "--system-prompt" in show_result.output
        assert "--registry-space-id" not in show_result.output


def test_harness_invoke_reads_record_and_sends_overrides(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_request(
        url: str,
        path: str,
        key: str | None,
        body: dict[str, object],
    ) -> dict[str, object]:
        calls.append({"url": url, "path": path, "key": key, "body": body})
        return {"output": "ok"}

    monkeypatch.setattr(cli_harness, "_harness_request", fake_request)
    runner = CliRunner()

    with runner.isolated_filesystem():
        Path("harness.json").write_text(
            json.dumps(
                {
                    "research-agent": {
                        "url": "https://example.invalid/runtime",
                        "key": "runtime-key",
                        "runtime_id": "runtime-id",
                    }
                }
            )
        )

        result = runner.invoke(
            cli_harness.harness,
            [
                "invoke",
                "--name",
                "research-agent",
                "--user-id",
                "u1",
                "--session-id",
                "s1",
                "--max-llm-calls",
                "3",
                "--model-name",
                "model-b",
                "--tools",
                "run_code",
                "find facts",
            ],
        )

    assert result.exit_code == 0, result.output
    assert result.output.strip() == "ok"
    assert calls == [
        {
            "url": "https://example.invalid/runtime",
            "path": "/harness/invoke",
            "key": "runtime-key",
            "body": {
                "prompt": "find facts",
                "harness_name": "research-agent",
                "run_agent_request": {
                    "user_id": "u1",
                    "session_id": "s1",
                    "max_llm_calls": 3,
                },
                "harness": {"model_name": "model-b", "tools": "run_code"},
            },
        }
    ]


def test_harness_invoke_requires_message() -> None:
    result = CliRunner().invoke(
        cli_harness.harness,
        ["invoke", "--name", "research-agent", "--url", "https://example.invalid"],
    )

    assert result.exit_code != 0
    assert "Provide a prompt" in result.output
