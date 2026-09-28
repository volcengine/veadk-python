"""Ordered prerequisite preparation shared by the CLI and Studio jobs."""

from __future__ import annotations

import copy
import re

from sqlalchemy.engine import make_url

from .config import ConfigurationError, Profile, Runtime, validate_postgres_layout
from .database import AgentDatabaseProvisioner, AgentDeploymentRegistry, DeploymentError
from .gateway import SharedAPIGService
from .gateway_cloud import GatewayCloud
from .network import AccountNetworkProvisioner, NetworkOptions
from .runtime import AgentRuntimeDeployer, RuntimeCloud, env_map, template_from_runtime
from .worker import WorkerCloud, ensure_worker


def bind_postgres_workspaces(profile: Profile, record: dict):
    settings = profile.managed.postgres
    if settings is None:
        if record.get("admin_workspace_id") or record.get("business_workspace_id"):
            raise DeploymentError("Registered Workspace configuration must be retained")
        return
    binding = {
        "admin_workspace_id": settings.admin_workspace_id,
        "business_workspace_id": settings.business_workspace_id,
    }
    if any(key in record and record[key] != value for key, value in binding.items()):
        raise DeploymentError("Registered Workspace binding differs from configuration")
    business = make_url(profile.admin_url)
    if (
        "database_host" in record
        and str(record["database_host"]).lower() != (business.host or "").lower()
    ) or (
        "database_port" in record and record["database_port"] != (business.port or 5432)
    ):
        raise DeploymentError(
            "Registered business database endpoint differs from configuration"
        )
    record.update(binding)


def fresh_template(profile, agent_id, account):
    from veadk.integrations.mpa.mpa_provision import (
        MpaProvisionParams,
        build_runtime_env,
    )

    values = profile.values
    params = MpaProvisionParams(
        image=profile.managed.runtime.image or str(values["image"]),
        pg_host=str(values["pg_host"]),
        pg_user=str(values["pg_user"]),
        pg_password=str(values["pg_password"]),
        model_provider=str(values["model_provider"]),
        model_api_base=str(values["model_api_base"]),
        model_api_key=str(values["model_api_key"]),
        model_name=str(values["model_name"]),
        registry_name=str(values.get("registry_name", "")),
        mpa_agent_id=agent_id,
        account_id=account,
        region=profile.region,
        pg_database="",
        pg_port=str(values.get("pg_port", "5432")),
        agentkit_tool_id="",
        pg_sslmode=str(values.get("pg_sslmode", "require")),
        pg_channel_binding=str(values.get("pg_channel_binding", "require")),
    )
    env = build_runtime_env(params, public_endpoint="")
    env.pop("A2A_PUBLIC_URL", None)
    return {
        "ArtifactType": "image",
        "ArtifactUrl": params.image,
        "RoleName": values.get("runtime_role_name", "IDRoleForArkClawShareAgent"),
        "ApmplusEnable": True,
        "MinInstance": 1,
        "MaxInstance": 1,
        "ProjectName": values.get("project_name", "default"),
        "Envs": [{"Key": k, "Value": v} for k, v in env.items()],
    }


def apply_runtime_settings(template: dict, options: Runtime):
    fields = {
        "role_name": "RoleName",
        "cpu_milli": "CpuMilli",
        "memory_mb": "MemoryMb",
        "min_instance": "MinInstance",
        "max_instance": "MaxInstance",
        "max_concurrency": "MaxConcurrency",
        "apmplus_enable": "ApmplusEnable",
        "project_name": "ProjectName",
    }
    for field, target in fields.items():
        value = getattr(options, field)
        if value is not None:
            template[target] = value
    if options.image:
        template.update(ArtifactType="image", ArtifactUrl=options.image)
    if options.env:
        env = {**env_map(template), **options.env}
        template["Envs"] = [{"Key": k, "Value": v} for k, v in env.items()]
    minimum, maximum = template.get("MinInstance"), template.get("MaxInstance")
    if minimum is not None and maximum is not None and minimum > maximum:
        raise ConfigurationError("Minimum instances exceed maximum instances")


def apply_identity_settings(template: dict, values: dict):
    identity_env = {
        key: str(values.get(field) or "").strip()
        for key, field in (
            ("MPA_USER_POOL_NAME", "user_pool_name"),
            ("MPA_USER_POOL_CLIENT_NAME", "user_pool_client_name"),
            ("IDENTITY_CALLBACK_URL", "identity_callback_url"),
        )
    }
    if not any(identity_env.values()):
        return
    missing = [key for key, value in identity_env.items() if not value]
    if missing:
        raise ConfigurationError(
            "Incomplete MPA identity configuration: " + ", ".join(missing)
        )
    env = env_map(template)
    env.update(identity_env)
    if values.get("identity_region"):
        env["IDENTITY_REGION"] = str(values["identity_region"]).strip()
    env["IDENTITY_STARTUP_ENABLED"] = "true"
    template["Envs"] = [{"Key": key, "Value": value} for key, value in env.items()]


async def provision(
    profile: Profile,
    *,
    agent_id: str,
    owner: str,
    description: str = "",
    progress=lambda stage: None,
):
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", agent_id) or not owner:
        raise DeploymentError("Invalid agent identity or owner")
    validate_postgres_layout(profile)
    cloud = RuntimeCloud(
        region=profile.region, credential_file=profile.managed.credential_file
    )
    progress("checking")
    account = await cloud.account_id()
    expected = str(profile.values.get("account_id", ""))
    if expected and account != expected:
        raise DeploymentError("Deployment credentials differ from the expected account")
    if profile.managed.postgres and profile.managed.postgres.mode == "auto":
        from .pg_bootstrap import prepare_postgres
        from .pg_cloud import PGCloud

        profile = await prepare_postgres(
            profile,
            PGCloud(region=profile.region, credentials=cloud._credentials),
            account,
            progress=progress,
        )
    if profile.managed.from_runtime:
        template = template_from_runtime(
            await cloud.get(profile.managed.from_runtime), agent_id
        )
    elif profile.template:
        template = copy.deepcopy(profile.template)
    else:
        template = fresh_template(profile, agent_id, account)
    apply_runtime_settings(template, profile.managed.runtime)
    apply_identity_settings(template, profile.values)
    env = env_map(template)
    if profile.openviking_enabled is not None:
        selected_openviking = (
            {
                key: value
                for key, value in profile.managed.runtime.env.items()
                if key.startswith("OPENVIKING_")
            }
            if profile.openviking_enabled
            else {}
        )
        for key in list(env):
            if key.startswith("OPENVIKING_"):
                env.pop(key)
        env.update(selected_openviking)
    else:
        env.setdefault("OPENVIKING_USER", "default")
    for key in (
        "AGENTKIT_RUNTIME_ID",
        "A2A_PUBLIC_URL",
        "CODEX_MCP_RUNTIME_API_KEY",
        "DEPLOYMENT_DATABASE_ADMIN_URL",
        "MPA_ADMIN_DATABASE_ADMIN_URL",
        profile.managed.database_admin_url_env,
    ):
        env.pop(key, None)
    if profile.managed.postgres:
        env.pop(profile.managed.postgres.admin_database_url_env, None)
    env["MPA_AGENT_ID"] = agent_id
    template["Envs"] = [{"Key": k, "Value": v} for k, v in env.items()]
    template["Description"] = description[:512]
    template["AuthorizerConfiguration"] = {
        "AuthorizerType": "key_auth",
        "KeyAuth": {"ApiKeyLocation": "header", "ApiKeyName": "Authorization"},
    }
    network = profile.managed.network
    if network.vpc_id:
        template["NetworkConfiguration"] = {
            "EnablePublicNetwork": True,
            "EnablePrivateNetwork": True,
            "VpcConfiguration": {
                "VpcId": network.vpc_id,
                "SubnetIds": network.subnet_ids,
                "EnableSharedInternetAccess": True,
            },
        }
    from agentkit.sdk.runtime.types import CreateRuntimeRequest

    CreateRuntimeRequest.model_validate({**template, "Name": "validation-only"})
    options = NetworkOptions(network.vpc_cidr, network.subnet_prefix, network.zone)
    databases = AgentDatabaseProvisioner(admin_url=profile.admin_url, runtime_env=env)
    registry = AgentDeploymentRegistry(profile.shared_url)
    try:
        await databases.check()
        await registry.initialize()
        async with registry.lock(account, profile.region, agent_id) as entry:
            record = await entry.read()
            if record and record.get("studio_owner") != owner:
                raise DeploymentError(
                    "Agent belongs to another owner; use a new agent ID"
                )
            bind_postgres_workspaces(profile, record)
            record["studio_owner"] = owner
            await entry.save(record)
            current = (
                await cloud.get(record["runtime_id"])
                if record.get("runtime_id")
                else None
            )
            progress("network")
            template["NetworkConfiguration"] = await AccountNetworkProvisioner(
                cloud=cloud.network,
                account=account,
                region=profile.region,
                options=options,
            ).ensure(
                entry.network_entry(),
                template.get("NetworkConfiguration"),
                current=current,
                project_name=template.get("ProjectName") or "default",
            )
        # APIG takes the same account lock. Do not nest it inside the deployment lock.
        progress("gateway")
        vpc = template["NetworkConfiguration"]["VpcConfiguration"]
        gateway = await SharedAPIGService(
            registry=registry.shared, cloud=GatewayCloud(cloud), region=profile.region
        ).ensure(
            vpc_id=vpc["VpcId"],
            subnet_ids=vpc["SubnetIds"],
            adopt_id=profile.managed.apig.adopt_id,
        )
        async with registry.lock(account, profile.region, agent_id) as entry:
            progress("worker")
            tool_id = await ensure_worker(
                entry,
                WorkerCloud(cloud),
                profile.managed.worker,
                account=account,
                region=profile.region,
                agent_id=agent_id,
                project=template.get("ProjectName") or "default",
            )
        env.update(AGENTKIT_TOOL_ID=tool_id, AGENTKIT_TOOL_REGION=profile.region)
        template["ToolId"] = tool_id
        template["Envs"] = [{"Key": k, "Value": v} for k, v in env.items()]
        progress("deploying")
        result = await AgentRuntimeDeployer(
            registry=registry,
            databases=databases,
            cloud=cloud,
            region=profile.region,
            shared_database_url=profile.shared_url,
            timeout=profile.managed.timeout_seconds,
            network_options=options,
            progress=lambda message: progress("verifying")
            if message.startswith("Runtime ")
            else None,
        ).deploy(template)
        return {**result, "gateway_id": gateway["gateway_id"]}
    finally:
        await databases.close()
        await registry.close()
