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

"""Explicit, operator-driven setup of the shared MPA management database."""

import asyncio
import json
import os
import re

import click


@click.command("init-admin-db")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--source-url-env",
    default="",
    help="Environment variable holding the old registry URL. Stop all registry writers through cutover before copying.",
)
def init_admin_db(config_path: str, source_url_env: str):
    """Prepare mpa_admin_db on the configured management Workspace."""
    from veadk.integrations.mpa.managed.admin_database import initialize_admin_database
    from veadk.integrations.mpa.managed.config import ConfigurationError, load_profile
    from veadk.integrations.mpa.managed.database import DeploymentError

    source_url = ""
    if source_url_env:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{0,127}", source_url_env):
            raise click.BadParameter(
                "Use an environment variable name", param_hint="--source-url-env"
            )
        source_url = os.environ.get(source_url_env, "").strip()
        if not source_url:
            raise click.ClickException(
                "Source registry environment variable is not configured"
            )
    try:
        profile = load_profile(config_path)
        if profile.managed.postgres and profile.managed.postgres.mode == "auto":
            from veadk.integrations.mpa.managed.pg_bootstrap import prepare_postgres
            from veadk.integrations.mpa.managed.pg_cloud import PGCloud
            from veadk.integrations.mpa.managed.runtime import RuntimeCloud

            async def prepare():
                cloud = RuntimeCloud(
                    region=profile.region,
                    credential_file=profile.managed.credential_file,
                )
                account = await cloud.account_id()
                expected = str(profile.values.get("account_id", ""))
                if expected and expected != account:
                    raise DeploymentError(
                        "Deployment credentials differ from the expected account"
                    )
                resolved = await prepare_postgres(
                    profile,
                    PGCloud(region=profile.region, credentials=cloud._credentials),
                    account,
                    source_url=source_url,
                )
                return {
                    "database": "mpa_admin_db",
                    "copied": bool(source_url),
                    "adminWorkspaceId": resolved.managed.postgres.admin_workspace_id,
                    "businessWorkspaceId": resolved.managed.postgres.business_workspace_id,
                }

            result = asyncio.run(prepare())
        else:
            result = asyncio.run(
                initialize_admin_database(profile, source_url=source_url)
            )
        click.echo(json.dumps(result))
    except (ConfigurationError, DeploymentError) as exc:
        raise click.ClickException(str(exc)) from None
    except Exception:
        raise click.ClickException(
            "Management database preparation failed; check configuration and connectivity"
        ) from None
