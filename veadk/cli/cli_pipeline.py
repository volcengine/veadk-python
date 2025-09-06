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

import click
from veadk.config import getenv
from veadk.integrations.ve_code_pipeline.ve_code_pipeline import VeCodePipeline
from veadk.integrations.ve_faas.ve_faas import VeFaaS

warnings.filterwarnings(
    "ignore", category=UserWarning, module="pydantic._internal._fields"
)


def _render_volcengine_prompts() -> dict[str, str]:
    volcengine_access_key = click.prompt(
        "Volcengine Access Key", default="", show_default=False
    )
    if not volcengine_access_key:
        click.echo(
            "No Volcengine Access Key provided, will try to get it from environment variable VOLCENGINE_ACCESS_KEY."
        )
        volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")

    volcengine_secret_key = click.prompt(
        "Volcengine Secret Key", default="", show_default=False
    )
    if not volcengine_secret_key:
        click.echo(
            "No Volcengine Secret Key provided, will try to get it from environment variable VOLCENGINE_SECRET_KEY."
        )
        volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")

    volcengine_region = click.prompt("Volcengine Region", default="cn-beijing")
    return {
        "volcengine_access_key": volcengine_access_key,
        "volcengine_secret_key": volcengine_secret_key,
        "volcengine_region": volcengine_region,
    }


def _render_cr_prompts() -> dict[str, str] | None:
    cr_domain, cr_namespace_name, cr_region, cr_instance_name, cr_repo = (
        "",
        "",
        "",
        "",
        "",
    )
    cr_fields = [cr_domain, cr_namespace_name, cr_region, cr_instance_name, cr_repo]
    filled_fields = [field for field in cr_fields if field.strip()]

    while len(filled_fields) < len(cr_fields):
        click.echo(
            "Please provide all the Container Registry (CR) information, "
            "or press Enter to leave them all blank and let VeADK create the CR automatically."
        )
        cr_domain = click.prompt(
            "Container Registry domain", default="", show_default=False
        )
        cr_namespace_name = click.prompt(
            "Container Registry namespace name", default="", show_default=False
        )
        cr_region = click.prompt(
            "Container Registry region", default="", show_default=False
        )
        cr_instance_name = click.prompt(
            "Container Registry instance name", default="", show_default=False
        )
        cr_repo = click.prompt(
            "Container Registry repo", default="", show_default=False
        )

        cr_fields = [cr_domain, cr_namespace_name, cr_region, cr_instance_name, cr_repo]
        filled_fields = [field for field in cr_fields if field.strip()]

        if len(filled_fields) == 0:
            return None

    return {
        "cr_domain": cr_domain,
        "cr_namespace_name": cr_namespace_name,
        "cr_region": cr_region,
        "cr_instance_name": cr_instance_name,
        "cr_repo": cr_repo,
    }


@click.command()
def pipeline() -> None:
    """Integrate a veadk project to volcengine pipeline for CI/CD"""

    click.echo(
        "Welcome use VeADK to integrate your project to volcengine pipeline for CI/CD."
    )

    base_image_tag_options = ["preview", "0.0.1", "latest"]
    base_image_tag = click.prompt(
        "Choose a base image tag:", type=click.Choice(base_image_tag_options)
    )

    github_url = click.prompt("Github url", default="", show_default=False)
    while not github_url:
        click.echo("Please enter your github url.")
        github_url = click.prompt("Github url", default="", show_default=False)

    github_branch = click.prompt("Github branch", default="main")

    github_token = click.prompt("Github token", default="", show_default=False)
    while not github_token:
        click.echo("Please enter your github token.")
        github_token = click.prompt("Github token", default="", show_default=False)

    volcengine_settings = _render_volcengine_prompts()

    cr_settings = _render_cr_prompts()

    if cr_settings is None:
        click.echo("No CR information provided, will auto-create one.")
        # cr_settings = _auto_create_cr_config() # TODO

        # Using hardcoded values for demonstration
        cr_settings = {
            "cr_domain": "test-veadk-cn-beijing.cr.volces.com",
            "cr_namespace_name": "veadk",
            "cr_region": "cn-beijing",
            "cr_instance_name": "test-veadk",
            "cr_repo": "cicd-weather-test",
        }
        click.echo("Using the following auto-created CR configuration:")
        click.echo(f"Container Registry domain: {cr_settings['cr_domain']}")
        click.echo(
            f"Container Registry namespace name: {cr_settings['cr_namespace_name']}"
        )
        click.echo(f"Container Registry region: {cr_settings['cr_region']}")
        click.echo(
            f"Container Registry instance name: {cr_settings['cr_instance_name']}"
        )
        click.echo(f"Container Registry repo: {cr_settings['cr_repo']}")

    function_id = click.prompt(
        "Volcengine FaaS function ID", default="", show_default=False
    )

    if not function_id:
        click.echo("Function ID not provided, will auto-create one.")
        function_name = click.prompt(
            "Function name", default="veadk-function", show_default=False
        )
        vefaas_client = VeFaaS(
            access_key=volcengine_settings["volcengine_access_key"],
            secret_key=volcengine_settings["volcengine_secret_key"],
            region=volcengine_settings["volcengine_region"],
        )
        _, _, function_id = vefaas_client.deploy_image(
            name=function_name,
            image="veadk-cn-beijing.cr.volces.com/veadk/simple-fastapi:0.1",
        )
        click.echo(f"Created function {function_name} with ID: {function_id}")

    client = VeCodePipeline(
        volcengine_access_key=volcengine_settings["volcengine_access_key"],
        volcengine_secret_key=volcengine_settings["volcengine_secret_key"],
        region=volcengine_settings["volcengine_region"],
    )
    client.deploy(
        base_image_tag=base_image_tag,
        github_url=github_url,
        github_branch=github_branch,
        github_token=github_token,
        cr_domain=cr_settings["cr_domain"],
        cr_namespace_name=cr_settings["cr_namespace_name"],
        cr_region=cr_settings["cr_region"],
        cr_instance_name=cr_settings["cr_instance_name"],
        cr_repo=cr_settings["cr_repo"],
        function_id=function_id,
    )

    click.echo("Pipeline has been created successfully.")
