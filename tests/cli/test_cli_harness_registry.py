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

from pathlib import Path

import yaml
from click.testing import CliRunner

from veadk.cli.cli_harness import harness


def test_harness_add_registry_uri_writes_agentkit_a2a_section():
    runner = CliRunner()
    with runner.isolated_filesystem():
        create_result = runner.invoke(harness, ["create", "harness-app"])
        assert create_result.exit_code == 0

        result = runner.invoke(
            harness,
            [
                "add",
                "--path",
                "harness-app",
                "--registry",
                "agentkit://a2a-registry?space_id=space-test&top_k=5&region=cn-beijing",
            ],
        )

        assert result.exit_code == 0, result.output
        data = yaml.safe_load((Path("harness-app") / "harness.yaml").read_text())
        assert data["registry"] == {
            "type": "agentkit_a2a",
            "space_id": "space-test",
            "top_k": 5,
            "region": "cn-beijing",
        }


def test_harness_add_registry_flags_override_uri_values():
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(harness, ["create", "harness-app"])

        result = runner.invoke(
            harness,
            [
                "add",
                "--path",
                "harness-app",
                "--registry",
                "agentkit://a2a-registry?space_id=from-uri&top_k=2",
                "--registry-space-id",
                "from-flag",
                "--registry-top-k",
                "7",
            ],
        )

        assert result.exit_code == 0, result.output
        data = yaml.safe_load((Path("harness-app") / "harness.yaml").read_text())
        assert data["registry"]["type"] == "agentkit_a2a"
        assert data["registry"]["space_id"] == "from-flag"
        assert data["registry"]["top_k"] == 7


def test_harness_add_registry_rejects_direct_agent_card_url():
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(harness, ["create", "harness-app"])

        result = runner.invoke(
            harness,
            [
                "add",
                "--path",
                "harness-app",
                "--registry",
                "https://example.test/.well-known/agent-card.json",
            ],
        )

        assert result.exit_code != 0
        assert "only `agentkit://a2a-registry" in result.output


def test_harness_add_tool_calling_flags_write_top_level_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(harness, ["create", "harness-app"])

        result = runner.invoke(
            harness,
            [
                "add",
                "--path",
                "harness-app",
                "--structured-tool-calls",
                "--include-tools-every-turn",
            ],
        )

        assert result.exit_code == 0, result.output
        data = yaml.safe_load((Path("harness-app") / "harness.yaml").read_text())
        assert data["structured_tool_calls"] is True
        assert data["include_tools_every_turn"] is True


def test_harness_add_removes_old_responses_config_names():
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(harness, ["create", "harness-app"])
        yaml_path = Path("harness-app") / "harness.yaml"
        data = yaml.safe_load(yaml_path.read_text())
        data["enable_responses"] = True
        data["enable_responses_cache"] = False
        yaml_path.write_text(yaml.safe_dump(data, sort_keys=False))

        result = runner.invoke(
            harness,
            [
                "add",
                "--path",
                "harness-app",
                "--structured-tool-calls",
            ],
        )

        assert result.exit_code == 0, result.output
        data = yaml.safe_load(yaml_path.read_text())
        assert "enable_responses" not in data
        assert "enable_responses_cache" not in data
        assert data["structured_tool_calls"] is True
