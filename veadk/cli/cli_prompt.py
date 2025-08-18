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


@click.command()
@click.option(
    "--path", default=".", help="Agent file path with global variable `agent=...`"
)
@click.option("--feedback", default=None, help="Suggestions for prompt optimization")
@click.option("--api-key", default=None, help="API Key of PromptPilot")
@click.option(
    "--model-name",
    default="doubao-1.5-pro-32k-250115",
    help="Model name for prompt optimization",
)
def prompt(path: str, feedback: str, api_key: str, model_name: str) -> None:
    """Optimize agent system prompt from a local file."""
    from pathlib import Path

    from veadk.agent import Agent
    from veadk.config import getenv
    from veadk.integrations.ve_prompt_pilot.ve_prompt_pilot import VePromptPilot
    from veadk.utils.misc import load_module_from_file

    module_name = "agents_for_prompt_pilot"
    module_abs_path = Path(path).resolve()

    module = load_module_from_file(
        module_name=module_name, file_path=str(module_abs_path)
    )

    # get all global variables from module
    globals_in_module = vars(module)

    agents = []
    for global_variable_name, global_variable_value in globals_in_module.items():
        if isinstance(global_variable_value, Agent):
            agent = global_variable_value
            agents.append(agent)

    if len(agents) > 0:
        click.echo(f"Found {len(agents)} agents in {module_abs_path}")

        if not api_key:
            api_key = getenv("PROMPT_PILOT_API_KEY")
        ve_prompt_pilot = VePromptPilot(api_key)
        ve_prompt_pilot.optimize(
            agents=agents, feedback=feedback, model_name=model_name
        )
    else:
        click.echo(f"No agents found in {module_abs_path}")
