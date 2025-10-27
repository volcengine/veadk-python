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

import click
import shutil
from pathlib import Path

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
    model_name="doubao-seed-1-6-251015", # <---- you can change your model here
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
    """Creates a new agent in the current folder with prepopulated agent template."""
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
