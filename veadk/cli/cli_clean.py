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


def _resolve_clean_target(
    provider: str | None,
    region: str | None,
) -> tuple[str, str]:
    from veadk.utils.cloud_provider import (
        CloudProvider,
        cloud_provider_from_env,
        default_region,
        normalize_cloud_provider,
    )

    provider_id: CloudProvider = (
        normalize_cloud_provider(provider) if provider else cloud_provider_from_env()
    )
    return provider_id, region or default_region(provider_id)


def _resolve_clean_credentials(
    *,
    provider: str,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    volcengine_session_token: str | None,
    byteplus_access_key: str | None,
    byteplus_secret_key: str | None,
    byteplus_session_token: str | None,
) -> tuple[str, str, str]:
    from veadk.config import getenv

    if provider == "byteplus":
        access_key = byteplus_access_key or getenv(
            "BYTEPLUS_ACCESS_KEY", "", allow_false_values=True
        )
        secret_key = byteplus_secret_key or getenv(
            "BYTEPLUS_SECRET_KEY", "", allow_false_values=True
        )
        session_token = byteplus_session_token or getenv(
            "BYTEPLUS_SESSION_TOKEN", "", allow_false_values=True
        )
        if not access_key or not secret_key:
            raise click.ClickException(
                "BytePlus credentials required: pass --byteplus-access-key/"
                "--byteplus-secret-key, or set BYTEPLUS_ACCESS_KEY/"
                "BYTEPLUS_SECRET_KEY."
            )
        return access_key, secret_key, session_token

    access_key = volcengine_access_key or getenv("VOLCENGINE_ACCESS_KEY")
    secret_key = volcengine_secret_key or getenv("VOLCENGINE_SECRET_KEY")
    session_token = (
        volcengine_session_token
        or getenv("VOLCENGINE_SESSION_TOKEN", "", allow_false_values=True)
        or getenv("VOLC_SESSIONTOKEN", "", allow_false_values=True)
    )
    return access_key, secret_key, session_token


@click.command()
@click.option(
    "--vefaas-app-name",
    required=True,
    help="VeFaaS application name to clean",
)
@click.option(
    "--volcengine-access-key",
    default=None,
    help=(
        "Volcengine access key, if not set, will use the value of environment "
        "variable VOLCENGINE_ACCESS_KEY"
    ),
)
@click.option(
    "--volcengine-secret-key",
    default=None,
    help=(
        "Volcengine secret key, if not set, will use the value of environment "
        "variable VOLCENGINE_SECRET_KEY"
    ),
)
@click.option(
    "--volcengine-session-token",
    default=None,
    help="Volcengine session token, if not set, will use VOLCENGINE_SESSION_TOKEN",
)
@click.option("--byteplus-access-key", default=None, envvar="BYTEPLUS_ACCESS_KEY")
@click.option("--byteplus-secret-key", default=None, envvar="BYTEPLUS_SECRET_KEY")
@click.option("--byteplus-session-token", default=None, envvar="BYTEPLUS_SESSION_TOKEN")
@click.option(
    "--provider",
    type=click.Choice(["volcengine", "byteplus"]),
    default=None,
    help=(
        "Cloud provider to clean. Defaults to "
        "AGENTKIT_CLOUD_PROVIDER/CLOUD_PROVIDER, then volcengine."
    ),
)
@click.option(
    "--region",
    default=None,
    help=(
        "Cloud region to clean. Defaults to BYTEPLUS_REGION for BytePlus, or "
        "REGION/cn-beijing for Volcengine."
    ),
)
def clean(
    vefaas_app_name: str,
    volcengine_access_key: str | None,
    volcengine_secret_key: str | None,
    volcengine_session_token: str | None,
    byteplus_access_key: str | None,
    byteplus_secret_key: str | None,
    byteplus_session_token: str | None,
    provider: str | None,
    region: str | None,
) -> None:
    """Clean and delete a VeFaaS application from the cloud."""
    import time
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    provider_id, resolved_region = _resolve_clean_target(provider, region)
    access_key, secret_key, session_token = _resolve_clean_credentials(
        provider=provider_id,
        volcengine_access_key=volcengine_access_key,
        volcengine_secret_key=volcengine_secret_key,
        volcengine_session_token=volcengine_session_token,
        byteplus_access_key=byteplus_access_key,
        byteplus_secret_key=byteplus_secret_key,
        byteplus_session_token=byteplus_session_token,
    )

    confirm = input(
        f"Confirm delete cloud app {vefaas_app_name} "
        f"from {provider_id}/{resolved_region}? (y/N): "
    )
    if confirm.lower() != "y":
        click.echo("Delete cancelled.")
        return
    else:
        vefaas_client = VeFaaS(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=resolved_region,
            provider=provider_id,
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
