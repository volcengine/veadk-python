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
import warnings
from pathlib import Path

import click
from cookiecutter.main import cookiecutter
from InquirerPy.resolver import prompt
from InquirerPy.utils import InquirerPySessionResult

import veadk.integrations.ve_faas as vefaas
from veadk.version import VERSION

warnings.filterwarnings(
    "ignore", category=UserWarning, module="pydantic._internal._fields"
)

DEPLOY_CONFIGS = [
    {
        "name": "local_dir_name",
        "type": "input",
        "message": "Local project name:",
        "default": "veadk-cloud-proj",
    },
    {
        "name": "vefaas_application_name",
        "type": "input",
        "message": "VeFaaS application name:",
        "default": "veadk-cloud-application",
    },
    {
        "name": "veapig_instance_name",
        "type": "input",
        "message": "VeAPI Gateway instance name:",
    },
    {
        "name": "veapig_service_name",
        "type": "input",
        "message": "VeAPI Gateway service name:",
    },
    {
        "name": "veapig_upstream_name",
        "type": "input",
        "message": "VeAPI Gateway upstream name:",
    },
    {
        "name": "deploy_mode",
        "type": "list",
        "message": "Deploy mode:",
        "choices": ["A2A/MCP", "Web"],
    },
]


def _get_user_configs() -> dict:
    user_configs = prompt(DEPLOY_CONFIGS)
    user_configs["veadk_version"] = VERSION
    return user_configs


def _check_local_dir_exists(configs: InquirerPySessionResult) -> None:
    target_dir_path = Path.cwd() / str(configs["local_dir_name"])
    if target_dir_path.exists():
        click.confirm(
            f"Directory '{target_dir_path}' already exists, do you want to overwrite it",
            abort=True,
        )
        shutil.rmtree(target_dir_path)


@click.command()
def init() -> None:
    """Init a veadk project that can be deployed to Volcengine VeFaaS."""

    click.echo(
        "Welcome use VeADK to create your project. We will generate a `weather-reporter` application for you."
    )

    # 1. get user configurations by rendering prompts
    user_configs = _get_user_configs()
    _check_local_dir_exists(user_configs)

    # 2. copy template files
    template_path = Path(vefaas.__file__).parent / "template"

    cookiecutter(
        template=str(template_path),
        output_dir=str(Path.cwd()),
        extra_context=user_configs,
        no_input=True,
    )

    click.echo(
        f"🎉 Template project has been generated at {Path.cwd() / str(user_configs['local_dir_name'])}"
    )

    click.echo(f"""Run:
  - cd {user_configs["local_dir_name"]}
  - veadk deploy
for deployment on Volcengine FaaS platform.""")
