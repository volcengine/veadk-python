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

import shutil
from pathlib import Path

import click

_ENV_TEMPLATE = """\
MODEL_AGENT_API_KEY={ark_api_key}
"""

_INIT_PY_TEMPLATE = """\
from . import agent
"""

_AGENT_PY_TEMPLATE = """\
from veadk import Agent

root_agent = Agent(
    name="root_agent",
    description="A helpful assistant for user questions.",
    instruction="Answer user questions to the best of your knowledge",
    model_name="doubao-seed-1-8-251215", # <---- change model here
)
"""

_SUCCESS_MSG = """\
Agent created in {agent_folder}:
- .env
- __init__.py
- agent.py

You can run the agent by executing: veadk web
"""


def _prompt_for_ark_api_key() -> str:
    """Prompt user to enter ARK API key with guidance and options.

    Displays instructions for obtaining an ARK API key and provides the user
    with two options: enter the key immediately or configure it later in the
    generated .env file. Includes helpful documentation links and clear choices.

    Returns:
        str: The ARK API key entered by the user, or empty string if they
            choose to configure it later
    """
    click.secho(
        "An API key is required to run the agent. See https://www.volcengine.com/docs/82379/1541594 for details.",
        fg="green",
    )
    click.echo("You have two options:")
    click.echo("  1. Enter the API key now.")
    click.echo("  2. Configure it later in the generated .env file.")
    choice = click.prompt("Please select an option", type=click.Choice(["1", "2"]))
    if choice == "1":
        return click.prompt("Please enter your ARK API key")
    else:
        click.secho("You can set the `api_key` in the .env file later.", fg="yellow")
        return ""


def _generate_files(ark_api_key: str, target_dir_path: Path) -> None:
    """Generate agent project files from templates in the target directory.

    Creates the essential files for a new VeADK agent project including
    environment configuration, Python package initialization, and the main
    agent definition file. Uses predefined templates to ensure consistent
    project structure and proper configuration.

    Args:
        ark_api_key: ARK API key to be written to the .env file for
            model authentication. Can be empty string if not provided
        target_dir_path: Path object pointing to the target directory
            where files should be created

    Files Created:
        - .env: Environment file with ARK API key configuration
        - __init__.py: Python package initialization file
        - agent.py: Main agent definition with default configuration

    Note:
        - Creates target directory if it doesn't exist
        - Overwrites existing files without warning
        - Uses template formatting to inject API key into .env file
        - Displays success message with project location after completion
    """
    target_dir_path.mkdir(exist_ok=True)
    env_path = target_dir_path / ".env"
    init_file_path = target_dir_path / "__init__.py"
    agent_file_path = target_dir_path / "agent.py"

    env_content = _ENV_TEMPLATE.format(ark_api_key=ark_api_key)
    env_path.write_text(env_content)
    init_file_path.write_text(_INIT_PY_TEMPLATE)
    agent_file_path.write_text(_AGENT_PY_TEMPLATE)

    click.secho(
        _SUCCESS_MSG.format(agent_folder=target_dir_path),
        fg="green",
    )


@click.command()
@click.argument("agent_name", required=False)
@click.option("--ark-api-key", help="The ARK API key.")
def create(agent_name: str, ark_api_key: str) -> None:
    """Create a new VeADK agent project with prepopulated template files.

    This command creates a new agent project directory with all necessary
    files to get started with VeADK agent development. It sets up a complete
    project structure including environment configuration, agent definition,
    and package initialization.

    The command handles interactive prompts for missing parameters and provides
    safety checks for existing directories to prevent accidental overwrites.

    Project Structure Created:
        agent_name/
        ├── .env                 # Environment configuration with API key
        ├── __init__.py         # Python package initialization
        └── agent.py            # Main agent definition with default settings

    Args:
        agent_name: Name of the agent and directory to create. If not provided
            as an argument, the user will be prompted to enter it interactively
        ark_api_key: ARK API key for model authentication. If not provided,
            the user will be prompted with options to enter it or configure later

    Note:
        - Agent name becomes both the directory name and project identifier
        - API key can be configured later by editing the .env file
        - Generated agent is immediately runnable with 'veadk web' command
        - Template includes comments guiding users to customize model settings
    """
    if not agent_name:
        agent_name = click.prompt("Enter the agent name")
    if not ark_api_key:
        ark_api_key = _prompt_for_ark_api_key()

    cwd = Path.cwd()
    target_dir_path = cwd / agent_name

    if target_dir_path.exists() and any(target_dir_path.iterdir()):
        if not click.confirm(
            f"Directory '{target_dir_path}' already exists and is not empty. Do you want to overwrite it?"
        ):
            click.secho("Operation cancelled.", fg="red")
            return
        shutil.rmtree(target_dir_path)

    _generate_files(ark_api_key, target_dir_path)
