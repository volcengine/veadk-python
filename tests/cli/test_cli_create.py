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

from click.testing import CliRunner
from pathlib import Path
from veadk.cli.cli_create import create, _generate_files


def test_create_agent_with_options():
    runner = CliRunner()
    with runner.isolated_filesystem() as temp_dir:
        result = runner.invoke(create, ["test-agent", "--ark-api-key", "test-key"])
        assert result.exit_code == 0

        agent_folder = Path(temp_dir) / "test-agent"
        assert agent_folder.exists()

        config_path = agent_folder / ".env"
        assert config_path.exists()
        config_content = config_path.read_text()
        assert "MODEL_AGENT_API_KEY=test-key" in config_content

        agent_init_path = agent_folder / "__init__.py"
        assert agent_init_path.exists()

        agent_py_path = agent_folder / "agent.py"
        assert agent_py_path.exists()


def test_create_agent_overwrite_existing_directory():
    runner = CliRunner()
    with runner.isolated_filesystem() as temp_dir:
        # First, create the agent
        runner.invoke(create, ["test-agent", "--ark-api-key", "test-key"])

        # Attempt to create it again, but cancel the overwrite
        result = runner.invoke(
            create,
            ["test-agent", "--ark-api-key", "test-key"],
            input="n\n",
        )
        assert "Operation cancelled" in result.output

        # Attempt to create it again, and confirm the overwrite
        result = runner.invoke(
            create,
            ["test-agent", "--ark-api-key", "new-key"],
            input="y\n",
        )
        assert result.exit_code == 0
        agent_folder = Path(temp_dir) / "test-agent"
        config_path = agent_folder / ".env"
        config_content = config_path.read_text()
        assert "MODEL_AGENT_API_KEY=new-key" in config_content


def test_generate_files(tmp_path: Path):
    agent_name = "test-agent"
    api_key = "test-key"
    target_dir = tmp_path / agent_name

    _generate_files(api_key, target_dir)

    config_file = target_dir / ".env"
    assert config_file.is_file()
    content = config_file.read_text()
    assert f"MODEL_AGENT_API_KEY={api_key}" in content

    init_file = target_dir / "__init__.py"
    assert init_file.is_file()

    agent_file = target_dir / "agent.py"
    assert agent_file.is_file()


def test_prompt_for_ark_api_key_enter_now():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(create, input="test-agent\n1\nmy-secret-key\n")
        assert result.exit_code == 0
        assert "my-secret-key" in (Path("test-agent") / ".env").read_text()


def test_prompt_for_ark_api_key_configure_later():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(create, input="test-agent\n2\n")
        assert result.exit_code == 0
        assert "MODEL_AGENT_API_KEY=" in (Path("test-agent") / ".env").read_text()


def test_create_agent_with_prompts():
    runner = CliRunner()
    with runner.isolated_filesystem() as temp_dir:
        result = runner.invoke(create, input="test-agent\n1\ntest-key\n")
        assert result.exit_code == 0

        agent_folder = Path(temp_dir) / "test-agent"
        assert agent_folder.exists()

        config_path = agent_folder / ".env"
        assert config_path.exists()
        config_content = config_path.read_text()
        assert "MODEL_AGENT_API_KEY=test-key" in config_content

        agent_init_path = agent_folder / "__init__.py"
        assert agent_init_path.exists()

        agent_py_path = agent_folder / "agent.py"
        assert agent_py_path.exists()
