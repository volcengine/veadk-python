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

import click
from InquirerPy.resolver import prompt
from jinja2 import Template
from yaml import safe_load

import veadk.integrations.ve_faas as vefaas
from veadk.configs.deploy_config import VeDeployConfig
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


TEMP_PATH = "/tmp"


DEPLOY_CONFIGS = [
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
        "name": "entrypoint_agent",
        "type": "input",
        "message": "The entrypoint agent (e.g. agent_dir.agent_module:agent)",
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
    return user_configs


@click.command()
@click.option(
    "--volcengine-access-key",
    envvar="VOLCENGINE_ACCESS_KEY",
    default=None,
    help="Volcengine access key",
)
@click.option(
    "--volcengine-secret-key",
    envvar="VOLCENGINE_SECRET_KEY",
    default=None,
    help="Volcengine secret key",
)
@click.option("--project-path", default=".", help="Local project path")
@click.option(
    "--deploy-config-file", default="./deploy.yaml", help="Deploy config file path"
)
def deploy(
    volcengine_access_key: str,
    volcengine_secret_key: str,
    project_path: str,
    deploy_config_file: str,
) -> None:
    """Deploy a user project to Volcengine FaaS application."""

    if not volcengine_access_key or not volcengine_secret_key:
        raise Exception("Volcengine access key and secret key must be set.")

    if not Path(deploy_config_file).exists():
        click.echo(f"Deployment configuration file not found in {deploy_config_file}.")

        user_configs = _get_user_configs()

        deploy_config_template_file_path = (
            Path(vefaas.__file__).parent
            / "template"
            / "{{cookiecutter.local_dir_name}}"
            / "deploy.yaml"
        )

        with open(deploy_config_template_file_path, "r", encoding="utf-8") as f:
            template_content = f.read()

        template = Template(template_content)

        rendered_content = template.render({"cookiecutter": user_configs})

        output_path = Path.cwd() / "deploy.yaml"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(rendered_content)

        click.echo("Deployment configuration file generated.")

    # read deploy.yaml
    with open(output_path, "r", encoding="utf-8") as yaml_file:
        deploy_config_dict = safe_load(yaml_file)

    deploy_config = VeDeployConfig(**deploy_config_dict)

    # vefaas_client = VeFaaS(
    #     access_key=volcengine_access_key,
    #     secret_key=volcengine_secret_key,
    #     region="cn-beijing",
    # )

    print(deploy_config)

    # vefaas_client.deploy(
    #     name=deploy_config.vefaas.application_name,
    #     path=project_path,
    #     gateway_name=deploy_config.veapig.gateway_name,
    #     gateway_service_name=deploy_config.veapig.gateway_service_name,
    #     gateway_upstream_name=deploy_config.veapig.gateway_upstream_name,
    # )
