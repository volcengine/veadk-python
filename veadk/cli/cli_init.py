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

import warnings
from typing import Any

import click

from veadk.version import VERSION

warnings.filterwarnings(
    "ignore", category=UserWarning, module="pydantic._internal._fields"
)


def _render_prompts() -> dict[str, Any]:
    vefaas_application_name = click.prompt(
        "Volcengine FaaS application name", default="veadk-cloud-agent"
    )

    veapig_instance_name = click.prompt(
        "Volcengine API Gateway instance name", default="", show_default=True
    )

    veapig_service_name = click.prompt(
        "Volcengine API Gateway service name", default="", show_default=True
    )

    veapig_upstream_name = click.prompt(
        "Volcengine API Gateway upstream name", default="", show_default=True
    )

    deploy_mode_options = {
        "1": "A2A/MCP Server",
        "2": "VeADK Web / Google ADK Web",
    }

    click.echo("Choose a deploy mode:")
    for key, value in deploy_mode_options.items():
        click.echo(f"  {key}. {value}")

    deploy_mode = click.prompt(
        "Enter your choice", type=click.Choice(deploy_mode_options.keys())
    )

    return {
        "vefaas_application_name": vefaas_application_name,
        "veapig_instance_name": veapig_instance_name,
        "veapig_service_name": veapig_service_name,
        "veapig_upstream_name": veapig_upstream_name,
        "use_adk_web": deploy_mode == "2",
        "veadk_version": VERSION,
    }


@click.command()
@click.option(
    "--vefaas-template-type", default="template", help="Expected template type"
)
def init(
    vefaas_template_type: str,
) -> None:
    """Init a veadk project that can be deployed to Volcengine VeFaaS.

    `template` is A2A/MCP/Web server template, `web_template` is for web applications (i.e., a simple blog).
    """
    import shutil
    from pathlib import Path

    from cookiecutter.main import cookiecutter

    import veadk.integrations.ve_faas as vefaas

    if vefaas_template_type == "web_template":
        click.echo(
            "Welcome use VeADK to create your project. We will generate a `simple-blog` web application for you."
        )
    else:
        click.echo(
            "Welcome use VeADK to create your project. We will generate a `weather-reporter` application for you."
        )

    cwd = Path.cwd()
    local_dir_name = click.prompt("Local directory name", default="veadk-cloud-proj")
    target_dir_path = cwd / local_dir_name

    if target_dir_path.exists():
        click.confirm(
            f"Directory '{target_dir_path}' already exists, do you want to overwrite it",
            abort=True,
        )
        shutil.rmtree(target_dir_path)

    settings = _render_prompts()
    settings["local_dir_name"] = local_dir_name

    if not vefaas_template_type:
        vefaas_template_type = "template"

    template_dir_path = Path(vefaas.__file__).parent / vefaas_template_type

    cookiecutter(
        template=str(template_dir_path),
        output_dir=str(cwd),
        extra_context=settings,
        no_input=True,
    )

    click.echo(f"Template project has been generated at {target_dir_path}")
    click.echo(f"Edit {target_dir_path / 'src/'} to define your agents")
    click.echo(
        f"Edit {target_dir_path / 'deploy.py'} to define your deployment attributes"
    )
    click.echo("Run python `deploy.py` for deployment on Volcengine FaaS platform.")
