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

"""``veadk mpa`` — one-click provisioning of the veadk-version mpa-agent.

Deploys a prebuilt mpa-agent image to VeFaaS behind APIG (key auth), seeds the
external PostgreSQL ``mpa_meta`` row so the runtime skips ``GetMpaInstanceConf``,
injects the runtime env (PostgreSQL + OpenViking as external parameters, identity
adapted via ``IDENTITY_STARTUP_ENABLED=false`` + ``csi-<account_id>``), and
verifies the instance is Studio-connectable over A2A. The veadk-version
mpa-agent needs no control-plane ``mi-*`` record.
"""

from __future__ import annotations

from typing import Any

import click

from veadk.integrations.mpa.mpa_meta_seed import MpaMetaSeedError, seed_mpa_meta
from veadk.integrations.mpa.mpa_provision import (
    MpaProvisionParams,
    build_runtime_env,
    derive_claw_space_id,
    redact_env_for_display,
)
from veadk.integrations.mpa.mpa_verify import VerificationResult, verify_instance


def _make_seed_engine(params: MpaProvisionParams):
    """Create a synchronous SQLAlchemy engine for the mpa-agent PostgreSQL DB."""
    from urllib.parse import quote_plus

    from sqlalchemy import create_engine

    user = quote_plus(params.pg_user)
    password = quote_plus(params.pg_password)
    dsn = (
        f"postgresql+psycopg2://{user}:{password}@"
        f"{params.pg_host}:{params.pg_port}/{params.pg_database}"
    )
    connect_args: dict[str, Any] = {}
    if params.pg_sslmode:
        connect_args["sslmode"] = params.pg_sslmode
    return create_engine(dsn, connect_args=connect_args)


def _deploy_image(
    *,
    params: MpaProvisionParams,
    env: dict[str, str],
    app_name: str,
    gateway_name: str,
    enable_key_auth: bool = True,
) -> dict[str, str]:
    """Deploy the image via VeFaaS with key auth and return the resource info.

    After the public endpoint is known, re-release with the real
    ``A2A_PUBLIC_URL`` so the A2A agent-card advertises the correct URL (the
    agent-card ``url`` is what Studio uses to connect). This mirrors the
    frontend's two-phase deploy for ``OAUTH2_REDIRECT_URI``.
    """
    import veadk.config

    from veadk.integrations.ve_faas.ve_faas import VeFaaS
    from veadk.utils.misc import getenv

    # Runtime env is what the function should carry.
    veadk.config.veadk_environments.update(env)

    vefaas = VeFaaS(
        access_key=getenv("VOLCENGINE_ACCESS_KEY"),
        secret_key=getenv("VOLCENGINE_SECRET_KEY"),
        session_token=getenv("VOLCENGINE_SESSION_TOKEN", "", allow_false_values=True),
        region=params.region,
    )
    url, app_id, function_id, apig_instance_id, api_key = vefaas.deploy_image(
        app_name,
        params.image,
        params.registry_name,
        gateway_name=gateway_name,
        enable_key_auth=enable_key_auth,
    )

    # Phase two: now that the public endpoint is known, re-release with the real
    # A2A_PUBLIC_URL so the agent-card advertises a reachable URL.
    if url and env.get("A2A_PUBLIC_URL") != url:
        vefaas.update_function_envs_and_release(function_id, {"A2A_PUBLIC_URL": url})

    return {
        "public_endpoint": url,
        "app_id": app_id,
        "function_id": function_id,
        "apig_instance_id": apig_instance_id,
        "runtime_api_key": api_key,
    }


@click.group()
def mpa() -> None:
    """VeADK-version mpa-agent provisioning."""


@mpa.command("create")
@click.option("--image", required=True, help="Prebuilt mpa-agent container image URL.")
@click.option(
    "--registry-name", required=True, help="Container registry name for VPC tunnel."
)
@click.option("--mpa-agent-id", required=True, help="mpa-agent instance id (mi-*).")
@click.option(
    "--account-id",
    required=True,
    help="Cloud account id; used for resource_account_id and derived CLAW_SPACE_ID.",
)
@click.option("--region", default="cn-beijing", help="Deploy region.")
@click.option(
    "--claw-space-id", default="", help="Optional; defaults to csi-<account_id>."
)
@click.option("--pg-host", required=True)
@click.option("--pg-port", default="5432")
@click.option("--pg-database", required=True)
@click.option("--pg-user", required=True)
@click.option("--pg-password", required=True)
@click.option("--pg-sslmode", default="require")
@click.option("--pg-channel-binding", default="require")
@click.option("--model-provider", required=True)
@click.option("--model-api-base", required=True)
@click.option("--model-api-key", required=True)
@click.option("--model-name", required=True)
@click.option("--agentkit-tool-id", required=True)
@click.option("--agentkit-tool-region", default="cn-beijing")
@click.option("--skill-space-id", default="")
@click.option("--identity-region", default="cn-beijing")
@click.option("--openviking-url", default="")
@click.option("--openviking-resource-id", default="")
@click.option("--openviking-api-key", default="")
@click.option("--feishu-app-id", default="")
@click.option("--feishu-app-secret", default="")
@click.option("--app-name", default="mpa-agent", help="VeFaaS application name.")
@click.option("--gateway-name", default="", help="Optional APIG gateway name to reuse.")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Resolve and print the plan with masked secrets; no cloud or DB writes.",
)
def create(  # noqa: PLR0913 - explicit CLI options are clearer than a config blob
    image: str,
    registry_name: str,
    mpa_agent_id: str,
    account_id: str,
    region: str,
    claw_space_id: str,
    pg_host: str,
    pg_port: str,
    pg_database: str,
    pg_user: str,
    pg_password: str,
    pg_sslmode: str,
    pg_channel_binding: str,
    model_provider: str,
    model_api_base: str,
    model_api_key: str,
    model_name: str,
    agentkit_tool_id: str,
    agentkit_tool_region: str,
    skill_space_id: str,
    identity_region: str,
    openviking_url: str,
    openviking_resource_id: str,
    openviking_api_key: str,
    feishu_app_id: str,
    feishu_app_secret: str,
    app_name: str,
    gateway_name: str,
    dry_run: bool,
) -> None:
    """Provision one mpa-agent instance from a prebuilt image and wire it up."""
    # Interactive, optional Feishu secret (FR-8): prompt hidden when id given.
    if feishu_app_id and not feishu_app_secret:
        feishu_app_secret = click.prompt(
            "Feishu app secret (FEISHU_APP_SECRET)", hide_input=True
        )

    params = MpaProvisionParams(
        image=image,
        registry_name=registry_name,
        mpa_agent_id=mpa_agent_id,
        account_id=account_id,
        region=region,
        claw_space_id=claw_space_id or None,
        pg_host=pg_host,
        pg_port=pg_port,
        pg_database=pg_database,
        pg_user=pg_user,
        pg_password=pg_password,
        pg_sslmode=pg_sslmode,
        pg_channel_binding=pg_channel_binding,
        model_provider=model_provider,
        model_api_base=model_api_base,
        model_api_key=model_api_key,
        model_name=model_name,
        agentkit_tool_id=agentkit_tool_id,
        agentkit_tool_region=agentkit_tool_region,
        skill_space_id=skill_space_id,
        identity_region=identity_region,
        openviking_url=openviking_url,
        openviking_resource_id=openviking_resource_id,
        openviking_api_key=openviking_api_key,
        feishu_app_id=feishu_app_id,
        feishu_app_secret=feishu_app_secret,
    )

    # The env cannot include the runtime API key until after deploy; it is
    # injected by the function's own key-auth authorizer, not via env.
    space_id = derive_claw_space_id(params.claw_space_id, account_id=params.account_id)

    if dry_run:
        # Build env against a placeholder endpoint purely for display.
        preview_env = build_runtime_env(
            params, public_endpoint="https://<pending-endpoint>"
        )
        masked = redact_env_for_display(preview_env)
        click.echo("veadk mpa create — dry run plan")
        click.echo(f"  app_name           : {app_name}")
        click.echo(f"  image              : {image}")
        click.echo(f"  region             : {region}")
        click.echo(f"  CLAW_SPACE_ID      : {space_id}")
        click.echo("  runtime env (masked):")
        for key in sorted(masked):
            click.echo(f"    {key}={masked[key]}")
        click.echo("  mpa_meta fields to seed:")
        for field in (
            "account_id",
            "resource_account_id",
            "runtime_id(app_id)",
            "public_endpoint",
            "private_endpoint(=public)",
            "runtime_api_key(from key-auth)",
            "apig_instance_id(from deploy)",
        ):
            click.echo(f"    - {field}")
        click.echo("Dry run only: no cloud or database changes were made.")
        return

    # 1) Deploy the image (key auth) and collect resource info.
    env = build_runtime_env(params, public_endpoint="https://<pending-endpoint>")
    click.echo(f"Deploying image to VeFaaS application '{app_name}'...")
    resource = _deploy_image(
        params=params,
        env=env,
        app_name=app_name,
        gateway_name=gateway_name,
        enable_key_auth=True,
    )
    public_endpoint = resource["public_endpoint"]
    click.echo(f"Deployed. Public endpoint: {public_endpoint}")

    # 2) Seed mpa_meta so the runtime skips GetMpaInstanceConf.
    meta_values = {
        "account_id": params.account_id,
        "resource_account_id": params.account_id,
        "runtime_id": resource["app_id"],
        "public_endpoint": public_endpoint,
        "private_endpoint": public_endpoint,  # FR-11: public authoritative
        "runtime_api_key": resource["runtime_api_key"],
        "apig_instance_id": resource["apig_instance_id"],
    }
    engine = _make_seed_engine(params)
    try:
        seed_mpa_meta(engine, mpa_agent_id=params.mpa_agent_id, values=meta_values)
    except MpaMetaSeedError as exc:
        raise click.ClickException(f"mpa_meta seeding failed: {exc}") from exc
    click.echo("Seeded mpa_meta; runtime will skip GetMpaInstanceConf.")

    # 3) Verify the instance is Studio-connectable.
    result: VerificationResult = verify_instance(public_endpoint)
    if not result.passed:
        raise click.ClickException(
            "Post-deploy verification failed: " + result.summary()
        )
    click.echo("Verification passed: " + result.summary())

    # 4) Studio connection guidance (FR-7). The runtime API key is retrieved on
    # demand from the runtime; it is not printed here.
    agent_card = f"{public_endpoint.rstrip('/')}/.well-known/agent-card.json"
    click.echo("")
    click.echo("Connect in AgentKit Studio (veadk studio) as a remote A2A agent:")
    click.echo(f"  endpoint   : {public_endpoint}")
    click.echo(f"  agent-card : {agent_card}")
    click.echo(
        "  auth       : runtime uses APIG key auth; reveal the key from the "
        "runtime console when connecting."
    )
