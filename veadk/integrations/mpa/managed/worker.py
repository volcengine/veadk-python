"""Persistent sandbox worker provisioning under the account deployment lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
import uuid

from .database import DeploymentError, agent_suffix


class WorkerCloud:
    def __init__(self, runtime):
        self.runtime = runtime

    async def call(self, method, request_type, **values):
        def run():
            from agentkit.sdk.tools import types
            from agentkit.sdk.tools.client import AgentkitToolsClient

            credential = self.runtime._credentials()
            client = AgentkitToolsClient(
                region=self.runtime.region,
                access_key=credential.access_key_id,
                secret_key=credential.secret_access_key,
                session_token=credential.session_token,
            )
            result = getattr(client, method)(
                getattr(types, request_type).model_validate(values)
            )
            return result.model_dump(by_alias=True, exclude_none=True)

        return await asyncio.to_thread(run)

    async def get(self, tool_id):
        return await self.call("get_tool", "GetToolRequest", ToolId=tool_id)

    async def create(self, request):
        return (await self.call("create_tool", "CreateToolRequest", **request)).get(
            "ToolId", ""
        )

    async def find(self, name):
        matches = []
        seen_ids = set()
        seen_tokens = set()
        next_token = None
        for _ in range(1000):
            result = await self.call(
                "list_tools",
                "ListToolsRequest",
                MaxResults=100,
                **({"NextToken": next_token} if next_token else {}),
            )
            for tool in result.get("Tools") or []:
                if tool.get("Name") != name:
                    continue
                tool_id = tool.get("ToolId")
                if not tool_id or tool_id not in seen_ids:
                    matches.append(tool)
                    seen_ids.add(tool_id)
            next_token = result.get("NextToken")
            if not next_token:
                return matches
            if next_token in seen_tokens:
                raise DeploymentError("Worker discovery repeated pagination token")
            seen_tokens.add(next_token)
        raise DeploymentError("Worker discovery exceeded pagination limit")


async def ensure_worker(
    entry, cloud, options, *, account, region, agent_id, project="default", timeout=600
):
    record = await entry.read()
    suffix = agent_suffix(account, region, agent_id)
    owned = {"managed_by": "mpa-deployment", "mpa_agent_key": suffix}
    tool_id = record.get("worker_id") or options.existing_id
    if (
        record.get("worker_id")
        and options.existing_id
        and record["worker_id"] != options.existing_id
    ):
        raise DeploymentError("Worker differs from registered binding")
    if not tool_id:
        env = {}
        if options.reference_id:
            source = await cloud.get(options.reference_id)
            excluded = {
                "MPA_AGENT_ID",
                "AGENTKIT_RUNTIME_ID",
                "SKILL_SPACE_ID",
                "CODEX_MCP_RUNTIME_API_KEY",
                "A2A_PUBLIC_URL",
                "FEISHU_APP_ID",
                "FEISHU_APP_SECRET",
                "CHANNEL_STATE_ENCRYPTION_KEY",
            }
            env = {
                item["Key"]: item.get("Value", "")
                for item in source.get("Envs", [])
                if item["Key"] not in excluded
            }
        env["MPA_AGENT_ID"] = agent_id
        request = {
            "Name": "mpa_worker_" + suffix,
            "ToolType": "Private",
            "ImageUrl": options.image,
            "Command": "/opt/gem/run.sh",
            "Port": 8000,
            "CpuMilli": 2000,
            "MemoryMb": 4096,
            "RoleName": options.role_name,
            "ProjectName": project,
            "NetworkConfiguration": {
                "EnablePublicNetwork": True,
                "EnablePrivateNetwork": False,
            },
            "AuthorizerConfiguration": {
                "KeyAuth": {"ApiKeyName": "Authorization", "ApiKeyLocation": "Header"}
            },
            "Tags": [{"Key": k, "Value": v} for k, v in owned.items()],
            "Envs": [{"Key": k, "Value": v} for k, v in sorted(env.items())],
        }
        digest = hashlib.sha256(
            json.dumps(request, sort_keys=True).encode()
        ).hexdigest()
        if record.get("worker_hash") and record["worker_hash"] != digest:
            raise DeploymentError(
                "Unfinished worker configuration changed; resume original inputs"
            )
        matches = await cloud.find(request["Name"])
        if matches:
            if len(matches) != 1 or not record.get("worker_token"):
                raise DeploymentError(
                    "Worker name collision without a recorded creation intent"
                )
            tool_id = matches[0].get("ToolId", "")
        else:
            record.setdefault("worker_token", str(uuid.uuid4()))
            record.update(worker_hash=digest, worker_managed=True)
            await entry.save(record)
            tool_id = await cloud.create(
                {**request, "ClientToken": record["worker_token"]}
            )
        if not tool_id:
            raise DeploymentError(
                "Worker creation outcome unknown; resume the same agent"
            )
        record.update(worker_id=tool_id, worker_managed=True)
        await entry.save(record)
    deadline = time.monotonic() + timeout
    while True:
        tool = await cloud.get(tool_id)
        tags = {t["Key"]: t.get("Value") for t in tool.get("Tags", [])}
        env = {t["Key"]: t.get("Value") for t in tool.get("Envs", [])}
        if (
            tool.get("ToolId") != tool_id
            or tool.get("ProjectName", "default") != project
        ):
            raise DeploymentError("Worker is missing or belongs to another project")
        if record.get("worker_managed") and any(
            tags.get(k) != v for k, v in owned.items()
        ):
            raise DeploymentError("Worker ownership does not match this agent")
        if env.get("MPA_AGENT_ID") and env["MPA_AGENT_ID"] != agent_id:
            raise DeploymentError("Worker is attached to another agent")
        if tool.get("Status") == "Ready":
            record.update(worker_id=tool_id)
            await entry.save(record)
            return tool_id
        if (
            tool.get("Status") in {"Failed", "Error", "Deleted", "Deleting"}
            or time.monotonic() >= deadline
        ):
            raise DeploymentError(
                "Worker is not ready; inspect it and retry the same agent"
            )
        await asyncio.sleep(5)
