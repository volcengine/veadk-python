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
from veadk.consts import (
    DEFAULT_CR_INSTANCE_NAME,
    DEFAULT_CR_NAMESPACE_NAME,
    DEFAULT_CR_REPO_NAME,
)
from veadk.integrations.ve_code_pipeline.ve_code_pipeline import VeCodePipeline
from veadk.integrations.ve_cr.ve_cr import VeCR
from veadk.integrations.ve_faas.ve_faas import VeFaaS
from veadk.utils.logger import get_logger
from veadk.version import VERSION

logger = get_logger(__name__)


warnings.filterwarnings(
    "ignore", category=UserWarning, module="pydantic._internal._fields"
)


def _create_cr(volcengine_settings: dict[str, str], cr_settings: dict[str, str]):
    vecr = VeCR(
        access_key=volcengine_settings["volcengine_access_key"],
        secret_key=volcengine_settings["volcengine_secret_key"],
        region=volcengine_settings["volcengine_region"],
    )
    try:
        vecr._create_instance(cr_settings["cr_instance_name"])
    except Exception as e:
        click.echo(f"Failed to create CR instance: {e}")
        raise

    try:
        vecr._create_namespace(
            instance_name=cr_settings["cr_instance_name"],
            namespace_name=cr_settings["cr_namespace_name"],
        )
    except Exception as e:
        click.echo(f"Failed to create CR namespace: {e}")
        raise

    try:
        vecr._create_repo(
            instance_name=cr_settings["cr_instance_name"],
            namespace_name=cr_settings["cr_namespace_name"],
            repo_name=cr_settings["cr_repo_name"],
        )
    except Exception as e:
        click.echo(f"Failed to create CR repo: {e}")
        raise


@click.command()
@click.option(
    "--veadk-version",
    default=VERSION,
    help=f"Base VeADK image tag can be 'preview', 'latest', or a specific VeADK version (e.g., {VERSION})",
)
@click.option(
    "--github-url",
    required=True,
    help="The github url of your project",
)
@click.option(
    "--github-branch",
    required=True,
    help="The github branch of your project",
)
@click.option(
    "--github-token",
    required=True,
    help="The github token to manage your project",
)
@click.option(
    "--volcengine-access-key",
    default=None,
    help="Volcengine access key, if not set, will use the value of environment variable VOLCENGINE_ACCESS_KEY",
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help="Volcengine secret key, if not set, will use the value of environment variable VOLCENGINE_SECRET_KEY",
)
@click.option(
    "--region",
    default="cn-beijing",
    help="Region for Volcengine VeFaaS, CR, and Pipeline. Default is cn-beijing",
)
@click.option(
    "--cr-instance-name",
    default=DEFAULT_CR_INSTANCE_NAME,
    help="Volcengine Container Registry instance name, default is veadk-user-instance",
)
@click.option(
    "--cr-namespace-name",
    default=DEFAULT_CR_NAMESPACE_NAME,
    help="Volcengine Container Registry namespace name, default is veadk-user-namespace",
)
@click.option(
    "--cr-repo-name",
    default=DEFAULT_CR_REPO_NAME,
    help="Volcengine Container Registry repo name, default is veadk-user-repo",
)
@click.option(
    "--vefaas-function-id",
    default=None,
    help="Volcengine FaaS function ID, if not set, a new function will be created automatically",
)
def pipeline(
    veadk_version: str,
    github_url: str,
    github_branch: str,
    github_token: str,
    volcengine_access_key: str,
    volcengine_secret_key: str,
    region: str,
    cr_instance_name: str,
    cr_namespace_name: str,
    cr_repo_name: str,
    vefaas_function_id: str,
) -> None:
    """Integrate a veadk project to volcengine pipeline for CI/CD"""

    click.echo(
        "Welcome use VeADK to integrate your project to volcengine pipeline for CI/CD."
    )

    if not volcengine_access_key:
        volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")
    if not volcengine_secret_key:
        volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")

    volcengine_settings = {
        "volcengine_access_key": volcengine_access_key,
        "volcengine_secret_key": volcengine_secret_key,
        "volcengine_region": region,
    }

    cr_settings = {
        "cr_domain": f"{cr_instance_name}-{region}.cr.volces.com",
        "cr_instance_name": cr_instance_name,
        "cr_namespace_name": cr_namespace_name,
        "cr_repo_name": cr_repo_name,
        "cr_region": region,
    }

    if not vefaas_function_id:
        click.echo(
            "No Function ID specified. VeADK will create one automatically. Please specify a function name:"
        )
        function_name = click.prompt(
            "Function name", default="veadk-image-function", show_default=False
        )

    _create_cr(volcengine_settings, cr_settings)

    if not vefaas_function_id:
        vefaas_client = VeFaaS(
            access_key=volcengine_settings["volcengine_access_key"],
            secret_key=volcengine_settings["volcengine_secret_key"],
            region=volcengine_settings["volcengine_region"],
        )
        _, _, function_id = vefaas_client.deploy_image(
            name=function_name,
            image="veadk-cn-beijing.cr.volces.com/veadk/simple-fastapi:0.1",
            registry_name=cr_settings["cr_instance_name"],
        )
        logger.debug(f"Created function {function_name} with ID: {function_id}")

    client = VeCodePipeline(
        volcengine_access_key=volcengine_settings["volcengine_access_key"],
        volcengine_secret_key=volcengine_settings["volcengine_secret_key"],
        region=volcengine_settings["volcengine_region"],
    )

    click.echo("=====================================================")
    click.echo("Using the following configuration to create pipeline:")
    click.echo(f"Use VeADK version: {veadk_version}")
    click.echo(f"Github url: {github_url}")
    click.echo(f"Github branch: {github_branch}")
    click.echo(f"VeFaaS function name: {function_name}")
    click.echo(f"VeFaaS function ID: {function_id}")
    click.echo(f"Container Registry domain: {cr_settings['cr_domain']}")
    click.echo(f"Container Registry namespace name: {cr_settings['cr_namespace_name']}")
    click.echo(f"Container Registry region: {region}")
    click.echo(f"Container Registry instance name: {cr_settings['cr_instance_name']}")
    click.echo(f"Container Registry repo name: {cr_settings['cr_repo_name']}")

    client.deploy(
        base_image_tag=veadk_version,
        github_url=github_url,
        github_branch=github_branch,
        github_token=github_token,
        cr_domain=cr_settings["cr_domain"],
        cr_namespace_name=cr_settings["cr_namespace_name"],
        cr_region=cr_settings["cr_region"],
        cr_instance_name=cr_settings["cr_instance_name"],
        cr_repo_name=cr_settings["cr_repo_name"],
        function_id=function_id,
    )

    click.echo("Pipeline has been created successfully.")
