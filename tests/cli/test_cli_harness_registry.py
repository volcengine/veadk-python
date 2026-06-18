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


def test_harness_add_no_longer_exposes_registry_flags():
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
                "--registry-space-id",
                "space-test",
            ],
        )

        assert result.exit_code != 0
        assert "No such option" in result.output


def test_harness_show_does_not_list_registry_override_flags():
    runner = CliRunner()
    with runner.isolated_filesystem():
        runner.invoke(harness, ["create", "harness-app"])

        result = runner.invoke(harness, ["show", "--path", "harness-app"])

        assert result.exit_code == 0, result.output
        assert "--registry-space-id" not in result.output
        assert "--registry-top-k" not in result.output


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
