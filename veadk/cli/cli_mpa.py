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

from pathlib import Path
from typing import Any

import click

from veadk.integrations.mpa.mpa_meta_seed import (
    MpaMetaSeedError,
    overwrite_mpa_meta,
    seed_mpa_meta,
)
from veadk.integrations.mpa.mpa_provision import (
    MpaProvisionParams,
    build_runtime_env,
    derive_claw_space_id,
    generate_mpa_agent_id,
    redact_env_for_display,
    tool_name_for_agent,
)
from veadk.integrations.mpa.mpa_runtime import provision_runtime
from veadk.integrations.mpa.mpa_skill_space import ensure_skill_space
from veadk.integrations.mpa.mpa_tool import ensure_codex_worker_tool
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
        phase_two_env = {"A2A_PUBLIC_URL": url}
        if api_key:
            phase_two_env["CODEX_MCP_RUNTIME_API_KEY"] = api_key
        vefaas.update_function_envs_and_release(function_id, phase_two_env)

    return {
        "public_endpoint": url,
        "app_id": app_id,
        "function_id": function_id,
        "apig_instance_id": apig_instance_id,
        "runtime_api_key": api_key,
    }


def _ve_credentials() -> tuple[str, str, str]:
    """Resolve Volcengine AK/SK/session-token for management API calls."""
    from veadk.utils.misc import getenv

    return (
        getenv("VOLCENGINE_ACCESS_KEY"),
        getenv("VOLCENGINE_SECRET_KEY"),
        getenv("VOLCENGINE_SESSION_TOKEN", "", allow_false_values=True),
    )


def _tools_client(region: str):
    from agentkit.sdk.tools.client import AgentkitToolsClient

    ak, sk, token = _ve_credentials()
    return AgentkitToolsClient(
        access_key=ak, secret_key=sk, region=region, session_token=token
    )


def _skills_client(region: str):
    from agentkit.sdk.skills.client import AgentkitSkillsClient

    ak, sk, token = _ve_credentials()
    return AgentkitSkillsClient(
        access_key=ak, secret_key=sk, region=region, session_token=token
    )


def _runtime_client(region: str):
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    ak, sk, token = _ve_credentials()
    return AgentkitRuntimeClient(
        access_key=ak, secret_key=sk, region=region, session_token=token
    )


def _resolve_apig_instance_id(region: str):
    """Return a callback mapping a public endpoint to its APIG gateway id.

    The gateway is provisioned by AgentKit together with the runtime; its id is
    read from the APIG gateway list by matching the endpoint host prefix.
    """

    def _resolve(public_endpoint: str) -> str:
        from urllib.parse import urlsplit

        from veadk.integrations.ve_apig.ve_apig import APIGateway
        from veadk.utils.misc import getenv

        host = urlsplit(public_endpoint).hostname or ""
        prefix = host.split(".", 1)[0] if host else ""
        gw = APIGateway(
            getenv("VOLCENGINE_ACCESS_KEY"),
            getenv("VOLCENGINE_SECRET_KEY"),
            region,
            session_token=getenv(
                "VOLCENGINE_SESSION_TOKEN", "", allow_false_values=True
            ),
        )
        result = gw.list_gateways()
        return _gateway_id_from_endpoint_prefix(
            prefix, getattr(result, "items", None) or []
        )

    return _resolve


def _gateway_id_from_endpoint_prefix(prefix: str, gateways: list[Any]) -> str:
    """Resolve only an endpoint prefix that identifies exactly one gateway.

    AgentKit shared-gateway Runtime endpoints currently do not embed an APIG
    gateway id. Returning an arbitrary account gateway would corrupt mpa_meta
    and could make IM setup mutate an unrelated gateway, so fail closed.
    """
    matches = []
    for item in gateways:
        gateway_id = str(getattr(item, "id", "") or "")
        if prefix and gateway_id and prefix.startswith(gateway_id):
            matches.append(gateway_id)
    unique = list(dict.fromkeys(matches))
    return unique[0] if len(unique) == 1 else ""


@click.group()
def mpa() -> None:
    """VeADK-version mpa-agent provisioning."""


@mpa.command("provision")
@click.option(
    "--config",
    "config_path",
    required=True,
    type=click.Path(exists=True, dir_okay=False),
)
@click.option(
    "--agent-id",
    required=True,
    help="Stable agent identity; reuse it to resume a failed deployment.",
)
@click.option("--description", default="")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Validate local configuration and show the resource plan without cloud calls.",
)
def provision_managed(
    config_path: str, agent_id: str, description: str, dry_run: bool
) -> None:
    """Prepare network, shared APIG, database, skills and worker before Runtime."""
    import asyncio
    import json
    import re

    from veadk.integrations.mpa.managed.config import ConfigurationError, load_profile
    from veadk.integrations.mpa.managed.database import DeploymentError
    from veadk.integrations.mpa.managed.service import provision

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", agent_id):
        raise click.BadParameter(
            "Use 1–64 lowercase letters, digits, underscores or hyphens",
            param_hint="--agent-id",
        )
    try:
        profile = load_profile(config_path)
        if dry_run:
            click.echo(
                json.dumps({**profile.summary(), "agentId": agent_id, "dryRun": True})
            )
            return
        result = asyncio.run(
            asyncio.wait_for(
                provision(
                    profile,
                    agent_id=agent_id,
                    owner="cli",
                    description=description,
                    progress=lambda stage: click.echo(f"MPA: {stage}"),
                ),
                timeout=profile.managed.timeout_seconds,
            )
        )
        click.echo(
            json.dumps(
                {
                    k: result[k]
                    for k in (
                        "agent_id",
                        "region",
                        "runtime_id",
                        "skill_space_id",
                        "gateway_id",
                        "state",
                    )
                }
            )
        )
    except (ConfigurationError, DeploymentError) as exc:
        raise click.ClickException(str(exc)) from None
    except Exception:
        raise click.ClickException(
            "MPA provisioning failed; check the current stage, credentials and resource permissions, then retry the same agent ID"
        ) from None


def _load_config_default_map(
    ctx: click.Context, _param: click.Parameter, value: str | None
) -> str | None:
    """Populate ``ctx.default_map`` from a YAML config so options can be omitted.

    Explicit CLI options always win: Click only falls back to ``default_map``
    for parameters not supplied on the command line. This lets operators fix
    PG/OpenViking (and any other) settings — including secrets — in a local YAML
    that must never be committed to git. Keys use the option name with dashes or
    underscores (e.g. ``pg-host`` or ``pg_host``).
    """
    if not value:
        return value
    import yaml

    path = Path(value)
    if not path.exists():
        raise click.BadParameter(f"config file not found: {value}")
    try:
        loaded = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise click.BadParameter(f"invalid YAML config {value}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise click.BadParameter(
            f"config {value} must be a YAML mapping of option names to values"
        )
    # Normalize keys to Click's underscored param names.
    normalized = {
        str(key).strip().replace("-", "_"): val for key, val in loaded.items()
    }
    existing = dict(ctx.default_map or {})
    existing.update(normalized)
    ctx.default_map = existing
    return value


@mpa.command("create")
@click.option(
    "--config",
    default="",
    is_eager=True,
    expose_value=False,
    callback=_load_config_default_map,
    help=(
        "YAML config supplying option defaults (e.g. PG/OpenViking settings and "
        "secrets). Explicit CLI options override it. The file must NOT be "
        "committed to git; see mpa-create.config.example.yaml."
    ),
)
@click.option("--image", required=True, help="Prebuilt mpa-agent container image URL.")
@click.option(
    "--registry-name", required=True, help="Container registry name for VPC tunnel."
)
@click.option(
    "--mpa-agent-id",
    default="",
    help=(
        "mpa-agent instance id (mi-*). Omit to auto-generate a globally-unique "
        "mi-<id> per agent (recommended)."
    ),
)
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
@click.option(
    "--selectable-model",
    "selectable_models",
    multiple=True,
    help=(
        "Additional model ID selectable per Studio conversation. Repeat the "
        "option; all models reuse the configured provider, endpoint, and key."
    ),
)
@click.option(
    "--compute-plane",
    type=click.Choice(["runtime", "vefaas"]),
    default="runtime",
    help="runtime: AgentKit CreateRuntime (r-*, default); vefaas: deploy_image.",
)
@click.option(
    "--agentkit-tool-id",
    default="",
    help="Existing Codex worker tool id (t-*). When set, CreateTool is skipped.",
)
@click.option(
    "--tool-image",
    default="",
    help="Codex worker image; create a Tool when set and --agentkit-tool-id is not.",
)
@click.option(
    "--tool-name",
    default="",
    help="Debug override; defaults to the agent id with '-' replaced by '_'.",
)
@click.option(
    "--tool-reference-id",
    default="",
    help="Reference tool id whose env set is cloned when creating the Tool.",
)
@click.option(
    "--tool-role-name",
    default="IDRoleForArkClawShareAgent",
    help="Execution role for the created Codex worker Tool.",
)
@click.option("--agentkit-tool-region", default="cn-beijing")
@click.option("--skill-space-id", default="")
@click.option(
    "--skill-space-name",
    default="",
    help="Create or select a Skill Space and inject SKILL_SPACE_ID.",
)
@click.option(
    "--runtime-role-name",
    default="IDRoleForArkClawShareAgent",
    help="Execution role for the AgentKit runtime (compute-plane runtime).",
)
@click.option(
    "--runtime-name",
    default="",
    help="Debug override; defaults to the generated mpa-agent id.",
)
@click.option("--min-instance", type=int, default=1)
@click.option("--max-instance", type=int, default=1)
@click.option("--identity-region", default="cn-beijing")
@click.option(
    "--apig-instance-id",
    default="",
    help=(
        "Dedicated customer APIG gateway id used by mpa-agent IM routing. "
        "Optional when the compute plane returns an unambiguous gateway id."
    ),
)
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
    selectable_models: tuple[str, ...],
    compute_plane: str,
    agentkit_tool_id: str,
    tool_image: str,
    tool_name: str,
    tool_reference_id: str,
    tool_role_name: str,
    agentkit_tool_region: str,
    skill_space_id: str,
    skill_space_name: str,
    runtime_role_name: str,
    runtime_name: str,
    min_instance: int,
    max_instance: int,
    identity_region: str,
    apig_instance_id: str,
    openviking_url: str,
    openviking_resource_id: str,
    openviking_api_key: str,
    feishu_app_id: str,
    feishu_app_secret: str,
    app_name: str,
    gateway_name: str,
    dry_run: bool,
) -> None:
    """Provision one mpa-agent instance from a prebuilt image and wire it up.

    Orchestration (reference-aligned): ensure Skill Space -> ensure Tool ->
    pre-seed mpa_meta -> compute plane -> validate/finalize bindings -> verify.
    """
    # Interactive, optional Feishu secret (FR-8): prompt hidden when id given.
    if feishu_app_id and not feishu_app_secret:
        feishu_app_secret = click.prompt(
            "Feishu app secret (FEISHU_APP_SECRET)", hide_input=True
        )

    # Auto-generate a globally-unique mi-* id when not supplied, so each agent
    # gets its own instance id (follows arkclaw-team's id strategy).
    mpa_agent_id = (mpa_agent_id or "").strip() or generate_mpa_agent_id()
    click.echo(f"mpa-agent-id: {mpa_agent_id}")

    # Runtime agents require a sandbox Tool. Validate before SkillSpace, Tool,
    # database, or Runtime calls so an incomplete config has no side effects.
    if compute_plane == "runtime" and not agentkit_tool_id and not tool_image:
        raise click.UsageError(
            "compute-plane runtime requires --tool-image so a dedicated Tool "
            "can be created (or --agentkit-tool-id as an explicit override)."
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
        selectable_models=selectable_models,
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

    space_id = derive_claw_space_id(params.claw_space_id, account_id=params.account_id)
    resolved_tool_name = tool_name or tool_name_for_agent(mpa_agent_id)
    resolved_runtime_name = runtime_name or mpa_agent_id

    if dry_run:
        preview_env = build_runtime_env(
            params, public_endpoint="https://<pending-endpoint>"
        )
        masked = redact_env_for_display(preview_env)
        click.echo("veadk mpa create — dry run plan")
        click.echo(f"  compute_plane      : {compute_plane}")
        click.echo(f"  app_name           : {app_name}")
        click.echo(f"  image              : {image}")
        click.echo(f"  region             : {region}")
        click.echo(f"  CLAW_SPACE_ID      : {space_id}")
        if skill_space_name:
            click.echo(f"  skill_space (name) : {skill_space_name} (create/select)")
        elif skill_space_id:
            click.echo(f"  skill_space_id     : {skill_space_id}")
        if agentkit_tool_id:
            click.echo(f"  tool               : reuse {agentkit_tool_id}")
        elif tool_image:
            click.echo(
                f"  tool               : create '{resolved_tool_name}' "
                f"from {tool_image}"
            )
        else:
            click.echo("  tool               : none (sandbox delegation disabled)")
        click.echo("  runtime env (masked):")
        for key in sorted(masked):
            click.echo(f"    {key}={masked[key]}")
        click.echo("  mpa_meta fields to seed:")
        rid = "runtime_id(r-*)" if compute_plane == "runtime" else "runtime_id(app_id)"
        for field in (
            "account_id",
            "resource_account_id",
            rid,
            "public_endpoint",
            "private_endpoint(=public)",
            "runtime_api_key(from key-auth)",
            "apig_instance_id(from deploy)",
        ):
            click.echo(f"    - {field}")
        click.echo("Dry run only: no cloud or database changes were made.")
        return

    # 1) Ensure Skill Space (FR-14) -> SKILL_SPACE_ID.
    resolved_skill_space_id = skill_space_id
    if skill_space_name:
        click.echo(f"Ensuring Skill Space '{skill_space_name}'...")
        resolved_skill_space_id = ensure_skill_space(
            _skills_client(region), name=skill_space_name
        )
        params.skill_space_id = resolved_skill_space_id
        click.echo(f"Skill Space id: {resolved_skill_space_id}")

    # 2) Ensure Tool (FR-12/13) -> tool_id.
    tool_id = agentkit_tool_id
    if not tool_id and tool_image:
        click.echo(f"Ensuring Codex worker Tool '{resolved_tool_name}'...")
        tool_id = ensure_codex_worker_tool(
            _tools_client(region),
            name=resolved_tool_name,
            image=tool_image,
            reference_tool_id=tool_reference_id,
            role_name=tool_role_name,
        )
        click.echo(f"Tool id: {tool_id}")
    if tool_id:
        params.agentkit_tool_id = tool_id

    # 3) Pre-seed mpa_meta (FR-19 phase 1) BEFORE the container starts, so the
    # runtime skips GetMpaInstanceConf at first start (it returns 403 on
    # accounts without arkclaw:GetMpaInstanceConf). Real values are finalized in
    # phase 2 after the endpoint/key are known.
    engine = _make_seed_engine(params)
    placeholder = "pending"
    try:
        seed_mpa_meta(
            engine,
            mpa_agent_id=params.mpa_agent_id,
            values={
                "account_id": params.account_id,
                "resource_account_id": params.account_id,
                "runtime_id": placeholder,
                "public_endpoint": placeholder,
                "private_endpoint": placeholder,
                "runtime_api_key": placeholder,
                "apig_instance_id": placeholder,
            },
        )
    except MpaMetaSeedError as exc:
        raise click.ClickException(f"mpa_meta pre-seed failed: {exc}") from exc
    click.echo("Pre-seeded mpa_meta; runtime will skip GetMpaInstanceConf.")

    # 4) Compute plane (FR-15/16): CreateRuntime (default) or deploy_image.
    env = build_runtime_env(params, public_endpoint="https://<pending-endpoint>")
    if compute_plane == "runtime":
        click.echo(f"Creating AgentKit runtime '{resolved_runtime_name}'...")
        resource = provision_runtime(
            _runtime_client(region),
            name=resolved_runtime_name,
            artifact_url=params.image,
            tool_id=tool_id,
            role_name=runtime_role_name,
            envs=env,
            min_instance=min_instance,
            max_instance=max_instance,
            resolve_apig_instance_id=_resolve_apig_instance_id(region),
            reinject_public_url=True,
            tags={"veadk:agent-type": "mpa"},
        )
        if apig_instance_id:
            resource["apig_instance_id"] = apig_instance_id.strip()
    else:
        click.echo(f"Deploying image to VeFaaS application '{app_name}'...")
        resource = _deploy_image(
            params=params,
            env=env,
            app_name=app_name,
            gateway_name=gateway_name,
            enable_key_auth=True,
        )
    public_endpoint = resource["public_endpoint"]
    click.echo(f"Provisioned. Public endpoint: {public_endpoint}")

    # 5) Finalize mpa_meta (FR-19 phase 2): overwrite placeholders with real
    # deploy-resolved values now that the runtime is Ready.
    real_runtime_id = resource.get("runtime_id") or resource.get("app_id", "")
    finalize_values = {
        "runtime_id": real_runtime_id,
        "public_endpoint": public_endpoint,
        "private_endpoint": public_endpoint,  # FR-11: public authoritative
        "runtime_api_key": resource["runtime_api_key"],
        "apig_instance_id": resource["apig_instance_id"],
    }
    unresolved = [
        key for key, value in finalize_values.items() if not str(value).strip()
    ]
    if unresolved:
        raise click.ClickException(
            "cannot finalize mpa_meta; provisioned resources returned no "
            + ", ".join(unresolved)
            + f" (runtime_id={real_runtime_id}, tool_id={tool_id or 'n/a'}). "
            "No arbitrary APIG gateway will be selected."
        )
    try:
        overwrite_mpa_meta(
            engine,
            mpa_agent_id=params.mpa_agent_id,
            values=finalize_values,
        )
    except MpaMetaSeedError as exc:
        raise click.ClickException(
            "mpa_meta finalize failed (resources created: "
            f"runtime_id={real_runtime_id}, tool_id={tool_id or 'n/a'}): {exc}"
        ) from exc
    click.echo("Finalized mpa_meta with real endpoint/key/apig values.")

    # 6) Verify the instance is Studio-connectable. Runtimes are key-auth by
    # default, so pass the runtime API key for the probe to avoid 401.
    result: VerificationResult = verify_instance(
        public_endpoint, api_key=resource.get("runtime_api_key", "")
    )
    if not result.passed:
        raise click.ClickException(
            "Post-deploy verification failed: " + result.summary()
        )
    click.echo("Verification passed: " + result.summary())

    # 6) Studio connection guidance (FR-7). The runtime API key is retrieved on
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
