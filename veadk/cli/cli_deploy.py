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

import os

import click

from veadk.version import VERSION

TEMP_PATH = "/tmp"
_DEPLOY_PROCESS_ENV_KEYS = (
    "CLOUD_PROVIDER",
    "AGENTKIT_CLOUD_PROVIDER",
    "BYTEPLUS_REGION",
    "BYTEPLUS_ACCESS_KEY",
    "BYTEPLUS_SECRET_KEY",
    "BYTEPLUS_SESSION_TOKEN",
    "VOLCENGINE_ACCESS_KEY",
    "VOLCENGINE_SECRET_KEY",
    "VOLCENGINE_SESSION_TOKEN",
    "VOLC_SESSIONTOKEN",
    "REGION",
    "IAM_ROLE",
)


def _restore_process_env_on_click_close(keys: tuple[str, ...]) -> None:
    ctx = click.get_current_context(silent=True)
    if ctx is None:
        return
    original = {key: os.environ.get(key) for key in keys}

    def _restore() -> None:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    ctx.call_on_close(_restore)


@click.command()
@click.option(
    "--volcengine-access-key",
    default=None,
    help="Volcengine access key",
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help="Volcengine secret key",
)
@click.option(
    "--volcengine-session-token",
    default=None,
    help="Volcengine session token",
)
@click.option("--byteplus-access-key", default=None, envvar="BYTEPLUS_ACCESS_KEY")
@click.option("--byteplus-secret-key", default=None, envvar="BYTEPLUS_SECRET_KEY")
@click.option("--byteplus-session-token", default=None, envvar="BYTEPLUS_SESSION_TOKEN")
@click.option(
    "--provider",
    type=click.Choice(["volcengine", "byteplus"]),
    default=None,
    help="Cloud provider. Defaults to AGENTKIT_CLOUD_PROVIDER/CLOUD_PROVIDER, then volcengine.",
)
@click.option(
    "--region",
    default=None,
    help=(
        "Cloud region. Defaults to BYTEPLUS_REGION for BytePlus, or "
        "REGION/cn-beijing for Volcengine."
    ),
)
@click.option(
    "--vefaas-app-name", required=True, help="Expected Volcengine FaaS application name"
)
@click.option(
    "--veapig-instance-name", default="", help="Expected Volcengine APIG instance name"
)
@click.option(
    "--veapig-service-name", default="", help="Expected Volcengine APIG service name"
)
@click.option(
    "--veapig-upstream-name", default="", help="Expected Volcengine APIG upstream name"
)
@click.option(
    "--short-term-memory-backend",
    default="local",
    type=click.Choice(["local", "mysql"]),
    help="Backend for short-term memory",
)
@click.option("--use-adk-web", is_flag=True, help="Whether to use ADK Web")
@click.option(
    "--auth-method",
    default="none",
    type=click.Choice(["none", "api-key", "oauth2"]),
    help="=Authentication method for agent",
)
@click.option(
    "--user-pool-name",
    default="",
    help="Expected Volcengine Identity user pool name",
)
@click.option(
    "--client-name",
    default="",
    help="Expected Volcengine Identity client name",
)
@click.option("--path", default=".", help="Local project path")
@click.option("--iam-role", default=None, help="iam role for the vefaas function")
def deploy(
    volcengine_access_key: str,
    volcengine_secret_key: str,
    volcengine_session_token: str,
    byteplus_access_key: str,
    byteplus_secret_key: str,
    byteplus_session_token: str,
    provider: str | None,
    region: str | None,
    vefaas_app_name: str,
    veapig_instance_name: str,
    veapig_service_name: str,
    veapig_upstream_name: str,
    short_term_memory_backend: str,
    use_adk_web: bool,
    auth_method: str,
    user_pool_name: str,
    client_name: str,
    path: str,
    iam_role: str,
) -> None:
    """Deploy a user project to Volcengine FaaS application.

    This command deploys a VeADK agent project to Volcengine's Function as a Service (FaaS)
    platform. It creates a deployment package from the local project, configures the necessary
    cloud resources, and manages the deployment process including template generation,
    file copying, and cloud resource provisioning.

    The deployment process includes:
    1. Creating a temporary deployment package using cookiecutter templates
    2. Copying the user's project files to the deployment structure
    3. Processing configuration files and requirements
    4. Executing the deployment to Volcengine FaaS
    5. Cleaning up temporary files

    Args:
        volcengine_access_key: Volcengine access key for API authentication. If not provided,
            will use VOLCENGINE_ACCESS_KEY environment variable
        volcengine_secret_key: Volcengine secret key for API authentication. If not provided,
            will use VOLCENGINE_SECRET_KEY environment variable
        volcengine_session_token: Volcengine session token for API authentication.
        byteplus_access_key: BytePlus access key for API authentication.
        byteplus_secret_key: BytePlus secret key for API authentication.
        byteplus_session_token: BytePlus session token for API authentication.
        provider: Cloud provider for the deployment.
        region: Cloud region for the deployment.
        vefaas_app_name: Name of the target Volcengine FaaS application where the
            project will be deployed
        veapig_instance_name: Optional Volcengine API Gateway instance name for
            external API access configuration
        veapig_service_name: Optional Volcengine API Gateway service name
        veapig_upstream_name: Optional Volcengine API Gateway upstream name
        short_term_memory_backend: Backend type for short-term memory storage.
            Choices are 'local' or 'mysql'
        use_adk_web: Flag to enable ADK Web interface for the deployed agent
        auth_method: Authentication for the agent.
            Choices are 'none', 'api-key' or 'oauth2'.
        veidentity_user_pool_name: Optional Volcengine Identity user pool name
        veidentity_client_name: Optional Volcengine Identity client name
        path: Local directory path containing the VeADK project to deploy

    Note:
        - The function automatically processes and copies requirements.txt if present in the project
        - config.yaml files are excluded from deployment for security reasons
        - Temporary files are created in /tmp and cleaned up after deployment
        - The deployment uses cookiecutter templates for standardized project structure
    """
    import asyncio
    import shutil
    from pathlib import Path

    from cookiecutter.main import cookiecutter

    import veadk.integrations.ve_faas as vefaas
    from veadk.config import getenv, veadk_environments
    from veadk.utils.logger import get_logger
    from veadk.utils.misc import formatted_timestamp, load_module_from_file
    from veadk.utils.cloud_provider import (
        cloud_provider_from_env,
        default_region,
        normalize_cloud_provider,
    )

    logger = get_logger(__name__)

    _restore_process_env_on_click_close(_DEPLOY_PROCESS_ENV_KEYS)
    provider_id = (
        normalize_cloud_provider(provider) if provider else cloud_provider_from_env()
    )
    resolved_region = region or default_region(provider_id)
    os.environ["CLOUD_PROVIDER"] = provider_id
    os.environ["AGENTKIT_CLOUD_PROVIDER"] = provider_id
    veadk_environments["CLOUD_PROVIDER"] = provider_id
    veadk_environments["AGENTKIT_CLOUD_PROVIDER"] = provider_id

    if provider_id == "byteplus":
        if not byteplus_access_key:
            byteplus_access_key = getenv(
                "BYTEPLUS_ACCESS_KEY", "", allow_false_values=True
            )
        if not byteplus_secret_key:
            byteplus_secret_key = getenv(
                "BYTEPLUS_SECRET_KEY", "", allow_false_values=True
            )
        if not byteplus_access_key or not byteplus_secret_key:
            raise click.ClickException(
                "BytePlus credentials required: pass --byteplus-access-key/"
                "--byteplus-secret-key, or set BYTEPLUS_ACCESS_KEY/"
                "BYTEPLUS_SECRET_KEY."
            )
        byteplus_session_token = byteplus_session_token or getenv(
            "BYTEPLUS_SESSION_TOKEN", "", allow_false_values=True
        )
        volcengine_access_key = byteplus_access_key
        volcengine_secret_key = byteplus_secret_key
        volcengine_session_token = byteplus_session_token
        os.environ["BYTEPLUS_ACCESS_KEY"] = byteplus_access_key
        os.environ["BYTEPLUS_SECRET_KEY"] = byteplus_secret_key
        os.environ["BYTEPLUS_REGION"] = resolved_region
        veadk_environments["BYTEPLUS_REGION"] = resolved_region
        if byteplus_session_token:
            os.environ["BYTEPLUS_SESSION_TOKEN"] = byteplus_session_token
    else:
        if not volcengine_access_key:
            volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")
        if not volcengine_secret_key:
            volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")
        volcengine_session_token = (
            volcengine_session_token
            or getenv("VOLCENGINE_SESSION_TOKEN", "", allow_false_values=True)
            or getenv("VOLC_SESSIONTOKEN", "", allow_false_values=True)
        )

    os.environ["VOLCENGINE_ACCESS_KEY"] = volcengine_access_key
    os.environ["VOLCENGINE_SECRET_KEY"] = volcengine_secret_key
    if volcengine_session_token:
        os.environ["VOLCENGINE_SESSION_TOKEN"] = volcengine_session_token
    else:
        os.environ.pop("VOLCENGINE_SESSION_TOKEN", None)
    os.environ["REGION"] = resolved_region

    if not iam_role:
        iam_role = getenv("IAM_ROLE", None, allow_false_values=True)
    else:
        os.environ["IAM_ROLE"] = iam_role
        veadk_environments["IAM_ROLE"] = iam_role

    user_proj_abs_path = Path(path).resolve()
    template_dir_path = Path(vefaas.__file__).parent / "template"

    tmp_dir_name = f"{user_proj_abs_path.name}_{formatted_timestamp()}"
    rendered_tmp_dir_name = tmp_dir_name.replace("-", "_")
    tmp_dir_path = Path(TEMP_PATH) / rendered_tmp_dir_name

    settings = {
        "local_dir_name": rendered_tmp_dir_name,
        "app_name": user_proj_abs_path.name.replace("-", "_"),
        "agent_module_name": user_proj_abs_path.name,
        "short_term_memory_backend": short_term_memory_backend,
        "vefaas_application_name": vefaas_app_name,
        "veapig_instance_name": veapig_instance_name,
        "veapig_service_name": veapig_service_name,
        "veapig_upstream_name": veapig_upstream_name,
        "use_adk_web": use_adk_web,
        "auth_method": auth_method,
        "veidentity_user_pool_name": user_pool_name,
        "veidentity_client_name": client_name,
        "provider": provider_id,
        "region": resolved_region,
        "veadk_version": VERSION,
    }

    cookiecutter(
        template=str(template_dir_path),
        output_dir=TEMP_PATH,
        no_input=True,
        extra_context=settings,
    )
    logger.debug(f"Create a template project at {tmp_dir_path}")

    agent_dir = tmp_dir_path / "src" / user_proj_abs_path.name.replace("-", "_")

    # remove /tmp/tmp_dir_name/src/user_proj_abs_path.name
    shutil.rmtree(agent_dir)
    agent_dir.mkdir(parents=True, exist_ok=True)

    # copy
    shutil.copytree(user_proj_abs_path, agent_dir, dirs_exist_ok=True)
    logger.debug(f"Remove agent module from {user_proj_abs_path} to {agent_dir}")

    # copy requirements.txt
    if (user_proj_abs_path / "requirements.txt").exists():
        logger.debug(
            f"Find a requirements.txt in {user_proj_abs_path}/requirements.txt, copy it to temp project."
        )
        shutil.copy(
            user_proj_abs_path / "requirements.txt",
            tmp_dir_path / "src" / "requirements.txt",
        )
    else:
        logger.warning(
            "No requirements.txt found in the user project, we will use a default one."
        )

    # avoid upload user's config.yaml
    if (user_proj_abs_path / "config.yaml").exists():
        logger.warning(
            f"Find a config.yaml in {user_proj_abs_path}/config.yaml, we will not upload it by default."
        )
        shutil.move(agent_dir / "config.yaml", tmp_dir_path)
    else:
        logger.info(
            "No config.yaml found in the user project. Some environment variables may not be set."
        )

    # load
    logger.debug(f"Load deploy module from {tmp_dir_path / 'deploy.py'}")
    deploy_module = load_module_from_file(
        module_name="deploy_module",
        file_path=str(tmp_dir_path / "deploy.py"),
    )
    logger.info(f"Begin deploy from {tmp_dir_path / 'src'}")
    asyncio.run(deploy_module.main())

    # remove tmp file
    logger.info("Deploy done. Delete temp dir.")
    shutil.rmtree(tmp_dir_path)
