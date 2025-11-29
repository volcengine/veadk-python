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
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


@click.command()
@click.option(
    "--vefaas-app-name",
    required=True,
    help="VeFaaS application name to clean",
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
def clean(
    vefaas_app_name: str, volcengine_access_key: str, volcengine_secret_key: str
) -> None:
    """
    Clean and delete a VeFaaS application from the cloud.

    This command deletes a specified VeFaaS application after user confirmation.
    It will prompt the user for confirmation before proceeding with the deletion
    and monitor the deletion process until completion.

    Args:
        vefaas_app_name (str): The name of the VeFaaS application to delete
        volcengine_access_key (str): Volcengine access key for authentication.
            If None, will use VOLCENGINE_ACCESS_KEY environment variable
        volcengine_secret_key (str): Volcengine secret key for authentication.
            If None, will use VOLCENGINE_SECRET_KEY environment variable

    Returns:
        None
    """
    import time
    from veadk.config import getenv
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    if not volcengine_access_key:
        volcengine_access_key = getenv("VOLCENGINE_ACCESS_KEY")
    if not volcengine_secret_key:
        volcengine_secret_key = getenv("VOLCENGINE_SECRET_KEY")

    confirm = input(f"Confirm delete cloud app {vefaas_app_name}? (y/N): ")
    if confirm.lower() != "y":
        click.echo("Delete cancelled.")
        return
    else:
        vefaas_client = VeFaaS(
            access_key=volcengine_access_key, secret_key=volcengine_secret_key
        )
        vefaas_application_id = vefaas_client.find_app_id_by_name(vefaas_app_name)
        vefaas_client.delete(vefaas_application_id)
        click.echo(
            f"Cloud app {vefaas_app_name} delete request has been sent to VeFaaS"
        )
        while True:
            try:
                id = vefaas_client.find_app_id_by_name(vefaas_app_name)
                if not id:
                    break
                time.sleep(3)
            except Exception as _:
                break
        click.echo("Delete application done.")
