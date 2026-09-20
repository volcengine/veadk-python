"""Deployment of a Runtime, persistent database and Skill Space per agent."""

from __future__ import annotations

import asyncio
import copy
import hashlib
import json
import time

import httpx

from veadk.integrations.mpa.managed.database import DeploymentError, agent_suffix
from veadk.integrations.mpa.managed.network import (
    AccountNetworkProvisioner,
    NetworkOptions,
)
from veadk.integrations.mpa.managed.network_cloud import NetworkCloud


class RuntimeCloud:
    def __init__(self, *, region: str, credential_file: str):
        self.region, self.credential_file = region, credential_file
        self.account = ""
        self.network = NetworkCloud(region=region, credentials=self._credentials)

    def _credentials(self):
        from agentkit.auth.sts import get_caller_identity
        from veadk.integrations.mpa.managed.credentials import (
            load_volcengine_credentials,
        )

        credential = load_volcengine_credentials(self.credential_file)
        account = str(
            get_caller_identity(
                credential.access_key_id,
                credential.secret_access_key,
                credential.session_token,
                region=self.region,
            ).get("AccountId")
            or ""
        )
        if not account or self.account and account != self.account:
            raise DeploymentError(
                "Cloud credentials changed accounts during deployment"
            )
        self.account = account
        return credential

    def _client(self, *, skills=False):
        from agentkit.sdk.runtime.client import AgentkitRuntimeClient
        from agentkit.sdk.skills.client import AgentkitSkillsClient

        credential = self._credentials()
        client_type = AgentkitSkillsClient if skills else AgentkitRuntimeClient
        return client_type(
            region=self.region,
            access_key=credential.access_key_id,
            secret_key=credential.secret_access_key,
            session_token=credential.session_token,
        )

    async def account_id(self):
        await asyncio.to_thread(self._client)
        return self.account

    async def call(self, method: str, request, *, skills=False):
        def run():
            return getattr(self._client(skills=skills), method)(request).model_dump(
                by_alias=True, exclude_none=True
            )

        return await asyncio.to_thread(run)

    async def get_skill_space(self, space_id):
        from agentkit.sdk.skills.types import GetSkillSpaceRequest

        return await self.call(
            "get_skill_space", GetSkillSpaceRequest(Id=space_id), skills=True
        )

    async def create_skill_space(self, request):
        from agentkit.sdk.skills.types import CreateSkillSpaceRequest

        result = await self.call(
            "create_skill_space",
            CreateSkillSpaceRequest.model_validate(request),
            skills=True,
        )
        return result.get("Id", "")

    async def find_skill_spaces(self, name, project_name):
        from agentkit.sdk.skills.types import ListSkillSpacesRequest

        found = {}
        page, count = 1, 0
        while True:
            result = await self.call(
                "list_skill_spaces",
                ListSkillSpacesRequest(
                    PageNumber=page,
                    PageSize=100,
                    ProjectName=project_name or None,
                ),
                skills=True,
            )
            # Page through the project and compare exact names locally rather
            # than relying on server-side name filter matching semantics.
            items = result.get("Items") or []
            for item in items:
                if item.get("Name") == name:
                    found[item["Id"]] = item
            count += len(items)
            total = result.get("TotalCount")
            if (
                not items
                or (total is not None and count >= total)
                or (total is None and len(items) < 100)
            ):
                return list(found.values())
            page += 1

    async def get(self, runtime_id):
        from agentkit.sdk.runtime.types import GetRuntimeRequest

        return await self.call("get_runtime", GetRuntimeRequest(RuntimeId=runtime_id))

    async def create(self, request):
        from agentkit.sdk.runtime.types import CreateRuntimeRequest

        result = await self.call(
            "create_runtime", CreateRuntimeRequest.model_validate(request)
        )
        if not result.get("RuntimeId"):
            raise DeploymentError(
                "CreateRuntime returned no ID; retry with the same deployment configuration"
            )
        return result["RuntimeId"]

    async def update(self, request):
        from agentkit.sdk.runtime.types import UpdateRuntimeRequest

        await self.call("update_runtime", UpdateRuntimeRequest.model_validate(request))

    async def is_ready(self, runtime):
        nets = {
            n["NetworkType"].lower(): n["Endpoint"]
            for n in runtime.get("NetworkConfigurations", [])
        }
        key = (
            runtime["AuthorizerConfiguration"]["KeyAuth"]["ApiKey"]
            .removeprefix("Bearer ")
            .strip()
        )
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(
                    nets["public"] + "/readiness",
                    headers={"Authorization": "Bearer " + key},
                )
                return response.status_code == 200
        except httpx.HTTPError:
            return False


def env_map(runtime):
    return {x["Key"]: x.get("Value") or "" for x in runtime.get("Envs") or []}


def template_from_runtime(runtime, agent_id):
    """Copy deployment infrastructure, never the reference agent's identity."""
    fields = (
        "ArtifactType",
        "ArtifactUrl",
        "RoleName",
        "CpuMilli",
        "MemoryMb",
        "MinInstance",
        "MaxInstance",
        "MaxConcurrency",
        "ApmplusEnable",
        "ProjectName",
    )
    template = {k: runtime[k] for k in fields if k in runtime}
    networks = {
        n["NetworkType"].lower(): n for n in runtime.get("NetworkConfigurations") or []
    }
    vpc = networks.get("private", {}).get("VpcConfiguration") or {}
    if vpc.get("VpcId"):
        template["NetworkConfiguration"] = {
            "EnablePublicNetwork": True,
            "EnablePrivateNetwork": True,
            "VpcConfiguration": {
                k: vpc[k]
                for k in ("VpcId", "SubnetIds", "EnableSharedInternetAccess")
                if k in vpc
            },
        }
    template["AuthorizerConfiguration"] = {
        "AuthorizerType": "key_auth",
        "KeyAuth": {"ApiKeyLocation": "header", "ApiKeyName": "Authorization"},
    }
    excluded = {
        "AGENTKIT_RUNTIME_ID",
        "A2A_PUBLIC_URL",
        "CODEX_MCP_RUNTIME_API_KEY",
        "MODEL_AGENT_CLIENT_REQ_ID",
        "CHANNEL_STATE_ENCRYPTION_KEY",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
        "SKILL_SPACE_ID",
    }
    env = {k: v for k, v in env_map(runtime).items() if k not in excluded}
    env["MPA_AGENT_ID"] = agent_id
    template["Envs"] = [{"Key": k, "Value": v} for k, v in env.items()]
    return template


def matches(runtime, update):
    for key, value in update.items():
        if key == "Envs":
            if env_map(runtime) != env_map(update):
                return False
        elif key == "Tags":
            # AgentKit adds immutable sys: tags such as sys:tag:createdBy.
            # They cannot be supplied in UpdateRuntime and are not drift.
            actual = [
                t for t in runtime.get(key) or [] if not t["Key"].startswith("sys:")
            ]
            if sorted(actual, key=lambda t: (t["Key"], t["Value"])) != sorted(
                value, key=lambda t: (t["Key"], t["Value"])
            ):
                return False
        elif runtime.get(key) != value:
            return False
    return True


def validate_runtime(runtime, *, agent_id, database, template):
    env = env_map(runtime)
    if env.get("MPA_AGENT_ID") != agent_id or env.get("PGDATABASE") != database:
        raise DeploymentError(
            "Existing Runtime is attached to a different agent or database"
        )
    for key in ("PGHOST", "PGUSER", "PGPORT"):
        default = "5432" if key == "PGPORT" else ""
        if env.get(key, default) != env_map(template).get(key, default):
            raise DeploymentError(
                f"Existing Runtime {key} differs from deployment configuration"
            )
    if runtime.get("RoleName") != template["RoleName"]:
        raise DeploymentError(
            "Changing the Runtime IAM role requires a separate migration"
        )
    if runtime.get("NetworkConfigurations"):
        nets = {n["NetworkType"].lower(): n for n in runtime["NetworkConfigurations"]}
        if set(nets) != {"public", "private"}:
            raise DeploymentError(
                "Existing Runtime requires public and private endpoints"
            )
        actual = nets["private"].get("VpcConfiguration") or {}
        wanted = template["NetworkConfiguration"]["VpcConfiguration"]
        if any(
            actual.get(k) != wanted.get(k)
            for k in ("VpcId", "SubnetIds", "EnableSharedInternetAccess")
            if k in wanted
        ):
            raise DeploymentError(
                "Changing the Runtime VPC configuration requires a separate migration"
            )


class AgentRuntimeDeployer:
    def __init__(
        self,
        *,
        registry,
        databases,
        cloud,
        region,
        shared_database_url,
        timeout=900,
        interval=5,
        progress=None,
        network_options=None,
    ):
        self.registry, self.databases, self.cloud = registry, databases, cloud
        self.region, self.shared_url = region, shared_database_url
        self.timeout, self.interval = timeout, interval
        self.progress = progress or (lambda message: None)
        self.network_options = network_options or NetworkOptions()

    async def wait_platform(self, runtime_id, expected=None):
        deadline = time.monotonic() + self.timeout
        previous = None
        while time.monotonic() < deadline:
            runtime = await self.cloud.get(runtime_id)
            status = runtime.get("Status")
            if status != previous:
                self.progress(f"Runtime {runtime_id}: {status}")
                previous = status
            if status == "Ready" and (expected is None or matches(runtime, expected)):
                return runtime
            if status in {"Error", "Failed", "Deleting", "Deleted"}:
                raise DeploymentError(
                    "Runtime deployment failed; inspect its logs and retry using the registered ID"
                )
            await asyncio.sleep(self.interval)
        raise DeploymentError(
            "Runtime deployment is still pending; rerun the same command to resume"
        )

    async def deploy(self, template: dict, *, runtime_id: str = "") -> dict:
        from agentkit.sdk.runtime.types import CreateRuntimeRequest
        from veadk.integrations.mpa.managed.skills import ensure_skill_space

        account = await self.cloud.account_id()
        source_env = env_map(template)
        agent_id = source_env.get("MPA_AGENT_ID", "").strip()
        suffix = agent_suffix(account, self.region, agent_id)
        template = copy.deepcopy(template)
        # Validate supplied fields, including partial network settings, before
        # provisioning anything. Missing network fields are filled below.
        CreateRuntimeRequest.model_validate({**template, "Name": agent_id})
        network = template.get("NetworkConfiguration") or {}
        self.network_options.validate()
        if network.get("EnablePublicNetwork") is False or (
            (network.get("VpcConfiguration") or {}).get("VpcId")
            and network.get("EnablePrivateNetwork") is False
        ):
            raise DeploymentError("Runtime template requires public/private networks")
        await self.registry.initialize()
        async with self.registry.lock(account, self.region, agent_id) as entry:
            record = await entry.read()
            if runtime_id and record.get("runtime_id") not in (None, "", runtime_id):
                raise DeploymentError(
                    "Agent already has another Runtime; explicit migration is required"
                )
            runtime_id = runtime_id or record.get("runtime_id", "")
            current = await self.cloud.get(runtime_id) if runtime_id else None
            from veadk.integrations.mpa.managed.database import database_name

            name = database_name(account, self.region, agent_id)
            if current:
                # Check agent/database/role before even adopting network resources.
                identity_template = {
                    **template,
                    "NetworkConfiguration": {"VpcConfiguration": {}},
                }
                validate_runtime(
                    current,
                    agent_id=agent_id,
                    database=name,
                    template=identity_template,
                )
            self.progress("Preparing account VPC and subnet configuration")
            template["NetworkConfiguration"] = await AccountNetworkProvisioner(
                cloud=self.cloud.network,
                account=account,
                region=self.region,
                options=self.network_options,
                timeout=self.timeout,
                interval=self.interval,
            ).ensure(
                entry.network_entry(),
                network,
                current=current,
                project_name=template.get("ProjectName") or "default",
            )
            self.progress("Account VPC and subnet configuration ready")
            CreateRuntimeRequest.model_validate({**template, "Name": agent_id})
            if current:
                validate_runtime(
                    current, agent_id=agent_id, database=name, template=template
                )
            name = await self.databases.ensure(
                entry, account=account, region=self.region, agent_id=agent_id
            )
            skill_space_id = await ensure_skill_space(
                entry,
                self.cloud,
                account=account,
                region=self.region,
                agent_id=agent_id,
                project_name=template.get("ProjectName") or "",
                configured_id=source_env.get("SKILL_SPACE_ID", "").strip(),
                current_id=env_map(current).get("SKILL_SPACE_ID", "").strip()
                if current
                else "",
            )
            record = await entry.read()
            key = await self.databases.encryption_key(
                name,
                existing_key=env_map(current).get("CHANNEL_STATE_ENCRYPTION_KEY", "")
                if current
                else "",
            )
            env = {
                k: v
                for k, v in source_env.items()
                if k
                not in {
                    "AGENTKIT_RUNTIME_ID",
                    "A2A_PUBLIC_URL",
                    "CODEX_MCP_RUNTIME_API_KEY",
                    "MODEL_AGENT_CLIENT_REQ_ID",
                    "DEPLOYMENT_DATABASE_ADMIN_URL",
                    "CHANNEL_STATE_ENCRYPTION_KEY",
                }
            }
            env.update(
                PGDATABASE=name,
                MPA_AGENT_ID=agent_id,
                SHARED_APIG_DATABASE_URL=self.shared_url,
                REGION=self.region,
                SKILL_SPACE_ID=skill_space_id,
            )
            # This deployment owns metadata/APIG bootstrap, including when the
            # reference Runtime disabled initialization for manual seeding.
            env.update(
                MPA_META_STARTUP_ENABLED="true", IM_GATEWAY_STARTUP_ENABLED="true"
            )
            if template.get("ApmplusEnable"):
                env.pop("OTEL_SERVICE_NAME", None)
            if key:
                env["CHANNEL_STATE_ENCRYPTION_KEY"] = key
            desired = {
                **template,
                "Name": current["Name"] if current else agent_id,
                "Envs": [{"Key": k, "Value": v} for k, v in sorted(env.items())],
            }
            desired.pop("ClientToken", None)
            tags = [
                t
                for t in desired.get("Tags", [])
                if t["Key"] != "veadk:agent-type" and not t["Key"].startswith("sys:")
            ]
            desired["Tags"] = tags + [{"Key": "veadk:agent-type", "Value": "mpa"}]
            digest = hashlib.sha256(
                json.dumps(desired, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            if record.get("pending") and record.get("request_hash") != digest:
                # A legacy CreateRuntime may have succeeded without returning
                # its ID. Retry its exact payload with the recorded ClientToken.
                legacy = {**desired, "Name": "mpa-agent-" + suffix}
                legacy_digest = hashlib.sha256(
                    json.dumps(legacy, sort_keys=True, separators=(",", ":")).encode()
                ).hexdigest()
                if not runtime_id and record.get("request_hash") == legacy_digest:
                    desired, digest = legacy, legacy_digest
            if record.get("pending") and record.get("request_hash") != digest:
                raise DeploymentError(
                    "An unfinished deployment has different inputs; resume its original configuration first"
                )
            record.update(pending=True, request_hash=digest)
            await entry.save(record)
            if not runtime_id:
                # A lost response is retried using the same persisted ClientToken.
                runtime_id = await self.cloud.create(
                    {**desired, "ClientToken": record["client_token"]}
                )
            record["runtime_id"] = runtime_id
            await entry.save(record)
            await self.databases.seed_runtime(name, agent_id, runtime_id)
        # Cloud endpoint allocation and app initialization must not hold the
        # account lock: app initialization acquires it to provision shared APIG.
        current = await self.wait_platform(runtime_id)
        validate_runtime(current, agent_id=agent_id, database=name, template=template)
        nets = {
            n["NetworkType"].lower(): n["Endpoint"]
            for n in current.get("NetworkConfigurations", [])
        }
        api_key = (
            ((current.get("AuthorizerConfiguration") or {}).get("KeyAuth") or {})
            .get("ApiKey", "")
            .removeprefix("Bearer ")
            .strip()
        )
        if not api_key or not all(nets.get(k) for k in ("public", "private")):
            raise DeploymentError(
                "Runtime has no complete network/key metadata; repair the deployment before retrying"
            )
        env.update(
            AGENTKIT_RUNTIME_ID=runtime_id,
            A2A_PUBLIC_URL=nets["public"],
            CODEX_MCP_RUNTIME_API_KEY=api_key,
            MODEL_AGENT_CLIENT_REQ_ID="agentkit/" + runtime_id,
        )
        if template.get("ApmplusEnable"):
            env["OTEL_SERVICE_NAME"] = runtime_id + "." + current["Name"]
        update_fields = (
            "ArtifactType",
            "ArtifactUrl",
            "CpuMilli",
            "MemoryMb",
            "MinInstance",
            "MaxInstance",
            "MaxConcurrency",
            "Description",
            "ApmplusEnable",
            "Tags",
        )
        update = {k: desired[k] for k in update_fields if k in desired}
        update["Envs"] = [{"Key": k, "Value": v} for k, v in sorted(env.items())]
        async with self.registry.lock(account, self.region, agent_id) as entry:
            record = await entry.read()
            if (
                record.get("request_hash") != digest
                or record.get("runtime_id") != runtime_id
            ):
                raise DeploymentError("Deployment registration changed while waiting")
            current = await self.cloud.get(runtime_id)
            if current.get("Status") == "Ready" and not matches(current, update):
                await self.cloud.update(
                    {**update, "RuntimeId": runtime_id, "ReleaseEnable": True}
                )
        current = await self.wait_platform(runtime_id, expected=update)
        deadline = time.monotonic() + self.timeout
        while not await self.cloud.is_ready(current):
            if time.monotonic() >= deadline:
                raise DeploymentError(
                    "Runtime application readiness is pending; inspect metadata/APIG initialization logs"
                )
            await asyncio.sleep(self.interval)
        async with self.registry.lock(account, self.region, agent_id) as entry:
            record = await entry.read()
            if record.get("request_hash") != digest:
                raise DeploymentError(
                    "Deployment registration changed before completion"
                )
            record.update(pending=False, state="ready")
            await entry.save(record)
        return {
            "account_id": account,
            "region": self.region,
            "agent_id": agent_id,
            "database_name": name,
            "skill_space_id": skill_space_id,
            "runtime_id": runtime_id,
            "runtime_name": current.get("Name"),
            "endpoint": nets["public"],
            "image": current.get("ArtifactUrl"),
            "network": template["NetworkConfiguration"],
            "state": "ready",
        }
