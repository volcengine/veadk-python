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
from types import SimpleNamespace

from click.testing import CliRunner

from veadk.cli import cli_harness


def test_harness_create_writes_gitignore_for_local_credentials() -> None:
    runner = CliRunner()

    with runner.isolated_filesystem() as temp_dir:
        result = runner.invoke(cli_harness.harness, ["create", "my-harness"])

        assert result.exit_code == 0
        harness_dir = Path(temp_dir) / "my-harness"
        gitignore = harness_dir / ".gitignore"
        assert gitignore.is_file()
        content = gitignore.read_text()
        assert ".env" in content
        assert "!.env.example" in content
        assert "harness.json" in content
        assert "agentkit*.yaml" in content


def test_harness_dockerfile_uses_accelerated_source_with_official_fallback() -> None:
    assert (
        "https://ghfast.top/https://github.com/volcengine/veadk-python.git"
        in cli_harness._DOCKERFILE
    )
    assert "https://github.com/volcengine/veadk-python.git" in cli_harness._DOCKERFILE
    assert '"./src[harness]"' in cli_harness._DOCKERFILE
    old_package_path = "packages/" + "agentkit" + "-harness-python"
    assert old_package_path not in cli_harness._DOCKERFILE


def test_harness_deploy_does_not_print_runtime_api_key(monkeypatch) -> None:
    runtime_key = "placeholder-runtime-key"

    def fake_launch(**_: object) -> SimpleNamespace:
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://example.invalid/runtime",
                metadata={
                    "runtime_id": "runtime-id",
                    "runtime_apikey": runtime_key,
                },
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", fake_launch)
    monkeypatch.setenv("VOLC_ACCESSKEY", "test-access-key")
    monkeypatch.setenv("VOLC_SECRETKEY", "placeholder-credential")

    runner = CliRunner()
    with runner.isolated_filesystem() as temp_dir:
        harness_dir = Path(temp_dir)
        (harness_dir / "harness.yaml").write_text("harness_name: test-harness\n")

        result = runner.invoke(
            cli_harness.harness,
            ["deploy", "--path", str(harness_dir)],
        )

        assert result.exit_code == 0
        assert runtime_key not in result.output
        assert "saved in local harness.json (not printed)" in result.output

        record = cli_harness._load_harness_json(str(harness_dir))
        assert record["test-harness"]["key"] == runtime_key
