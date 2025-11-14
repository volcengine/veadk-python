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

from veadk.cloud.cloud_agent_engine import CloudAgentEngine
from veadk.utils.logger import get_logger
from veadk.config import getenv

logger = get_logger(__name__)


@click.command()
@click.option(
    "--volcengine-access-key",
    default=None,
    help="Volcengine access key for authentication. Defaults to VOLCENGINE_ACCESS_KEY environment variable.",
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help="Volcengine secret key for authentication. Defaults to VOLCENGINE_SECRET_KEY environment variable.",
)
@click.option(
    "--vefaas-app-name",
    required=True,
    help="Name of the cloud application to update.",
)
@click.option(
    "--path",
    default=".",
    help="Local path containing the updated code. Defaults to current directory.",
)
def update(
    volcengine_access_key: str,
    volcengine_secret_key: str,
    vefaas_app_name: str,
    path: str,
) -> None:
    """Update function code of a deployed cloud application on Volcengine FaaS.

    This command updates the code of an existing cloud application without changing
    the endpoint or other resources. It uploads the local project code to replace
    the existing function implementation.

    The update process:
    1. Authenticates with Volcengine using provided credentials
    2. Validates the local project path and application name
    3. Uploads the updated code to the existing application
    4. Preserves the existing endpoint and gateway configuration

    Args:
        volcengine_access_key: Volcengine platform access key for authentication.
            If not provided, uses VOLCENGINE_ACCESS_KEY environment variable.
        volcengine_secret_key: Volcengine platform secret key for authentication.
            If not provided, uses VOLCENGINE_SECRET_KEY environment variable.
        vefaas_app_name: Name of the existing cloud application to update.
        path: Local directory path containing the updated agent project.
            Defaults to current directory if not specified.

    Note:
        - Application must already exist on Volcengine FaaS
        - Only function code is updated, endpoint remains unchanged
        - Uses default region 'cn-beijing' for Volcengine services

    Raises:
        ValueError: If authentication fails or application not found.
        FileNotFoundError: If local path does not exist.
    """
    # Set environment variables if provided
    if not volcengine_access_key:
        volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")
    if not volcengine_secret_key:
        volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")

    # Initialize cloud agent engine
    engine = CloudAgentEngine(
        volcengine_access_key=volcengine_access_key,
        volcengine_secret_key=volcengine_secret_key,
    )

    try:
        # Update function code
        updated_app = engine.update_function_code(
            application_name=vefaas_app_name,
            path=path,
        )

        logger.info(f"Successfully updated cloud application '{vefaas_app_name}'")
        logger.info(f"Endpoint: {updated_app.vefaas_endpoint}")
        logger.info(f"Application ID: {updated_app.vefaas_application_id}")

    except Exception as e:
        logger.error(f"Failed to update cloud application: {e}")
        raise
