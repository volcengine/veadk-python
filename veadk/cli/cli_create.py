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

_CONFIG_YAML_TEMPLATE = """\
model:
  agent:
    name: doubao-seed-1-6-251015
    api_key: {ark_api_key}
  video:
    name: doubao-seedance-1-0-pro-250528
    # if you want to use different api_key, just uncomment following line and complete api_key
    # api_key: 
  image:
    name: doubao-seedream-4-0-250828
    # if you want to use different api_key, just uncomment following line and complete api_key
    # api_key: 

logging:
  # ERROR
  # WARNING
  # INFO
  # DEBUG
  level: DEBUG
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
)
"""

_SUCCESS_MSG = """\
Agent '{agent_name}' created successfully at '{agent_folder}':
- config.yaml
- {agent_name}/__init__.py
- {agent_name}/agent.py

You can run the agent by executing: cd {agent_name} && veadk web
"""


def _prompt_for_ark_api_key() -> str:
    click.secho(
        "An API key is required to run the agent. See https://www.volcengine.com/docs/82379/1541594 for details.",
        fg="green",
    )
    click.echo("You have two options:")
    click.echo("  1. Enter the API key now.")
    click.echo("  2. Configure it later in the generated config.yaml file.")
    choice = click.prompt("Please select an option", type=click.Choice(["1", "2"]))
    if choice == "1":
        return click.prompt("Please enter your ARK API key")
    else:
        click.secho(
            "You can set the `api_key` in the config.yaml file later.", fg="yellow"
        )
        return ""


def _generate_files(agent_name: str, ark_api_key: str, target_dir_path: Path) -> None:
    agent_dir_path = target_dir_path / agent_name
    agent_dir_path.mkdir(parents=True, exist_ok=True)
    config_yaml_path = target_dir_path / "config.yaml"
    init_file_path = agent_dir_path / "__init__.py"
    agent_file_path = agent_dir_path / "agent.py"

    config_yaml_content = _CONFIG_YAML_TEMPLATE.format(ark_api_key=ark_api_key)
    config_yaml_path.write_text(config_yaml_content)
    init_file_path.write_text(_INIT_PY_TEMPLATE)
    agent_file_path.write_text(_AGENT_PY_TEMPLATE)

    click.secho(
        _SUCCESS_MSG.format(agent_name=agent_name, agent_folder=target_dir_path),
        fg="green",
    )


@click.command()
@click.option("--agent-name", help="The name of the agent.")
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

    _generate_files(agent_name, ark_api_key, target_dir_path)
