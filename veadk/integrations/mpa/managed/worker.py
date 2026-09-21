"""Persistent sandbox worker provisioning under the account deployment lock."""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from .database import DeploymentError, agent_suffix
from .diagnostics import report, retry_worker


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
    entry,
    cloud,
    options,
    *,
    account,
    region,
    agent_id,
    project="default",
    timeout: float = 600,
):
    return await asyncio.wait_for(
        _ensure_worker(
            entry,
            cloud,
            options,
            account=account,
            region=region,
            agent_id=agent_id,
            project=project,
        ),
        timeout=timeout,
    )


async def _ensure_worker(entry, cloud, options, *, account, region, agent_id, project):
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
            source = await retry_worker(
                "get_reference_worker", lambda: cloud.get(options.reference_id)
            )
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
        matches = await retry_worker("find_worker", lambda: cloud.find(request["Name"]))
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
            create_request = {**request, "ClientToken": record["worker_token"]}
            tool_id = await retry_worker(
                "create_worker", lambda: cloud.create(create_request)
            )
        if not tool_id:
            raise DeploymentError(
                "Worker creation outcome unknown; resume the same agent"
            )
        record.update(worker_id=tool_id, worker_managed=True)
        await entry.save(record)
    incomplete_observations = 0
    while True:
        tool = await retry_worker(
            "get_worker",
            lambda: cloud.get(tool_id),
            retry_not_found=bool(
                record.get("worker_managed")
                and record.get("worker_token")
                and record.get("worker_id")
            ),
        )
        missing = _missing_worker_metadata(
            tool,
            tool_id=tool_id,
            project=project,
            owned=owned,
            agent_id=agent_id,
            managed=bool(record.get("worker_managed")),
        )
        status = tool.get("Status")
        if status in {"Failed", "Error", "Deleted", "Deleting"}:
            report("worker_state", "resource_failed")
            raise DeploymentError(
                "Worker is not ready; inspect it and retry the same agent"
            )
        if missing:
            incomplete_observations += 1
            retrying = (
                incomplete_observations < 4
                and status
                in {
                    None,
                    "",
                    "Creating",
                    "Pending",
                    "Starting",
                    "Initializing",
                    "Provisioning",
                }
                and bool(
                    record.get("worker_managed")
                    and record.get("worker_id")
                    and record.get("worker_token")
                    and record.get("worker_hash")
                )
            )
            for operation in missing:
                report(
                    operation,
                    "metadata_pending" if retrying else "metadata_missing",
                    attempt=incomplete_observations,
                    outcome="retrying" if retrying else "failed",
                )
            if not retrying:
                raise DeploymentError("Worker ownership metadata is incomplete")
            await asyncio.sleep(5 * 2 ** (incomplete_observations - 1))
            continue
        if status == "Ready":
            record.update(worker_id=tool_id)
            await entry.save(record)
            return tool_id
        await asyncio.sleep(5)


def _missing_worker_metadata(tool, *, tool_id, project, owned, agent_id, managed):
    """Reject any present conflict before considering incomplete metadata."""
    tags = {t["Key"]: t.get("Value") for t in tool.get("Tags") or []}
    env = {t["Key"]: t.get("Value") for t in tool.get("Envs") or []}
    checks = [
        ("worker_id", tool.get("ToolId"), tool_id),
        (
            "worker_project",
            tool.get("ProjectName", None if managed else "default"),
            project,
        ),
    ]
    if managed:
        checks.extend(
            [
                ("worker_managed_by", tags.get("managed_by"), owned["managed_by"]),
                ("worker_agent_key", tags.get("mpa_agent_key"), owned["mpa_agent_key"]),
            ]
        )
    # The agent environment is optional for existing workers, but must never conflict.
    for operation, value, expected in [
        *checks,
        ("worker_agent_binding", env.get("MPA_AGENT_ID"), agent_id),
    ]:
        if value not in (None, "") and value != expected:
            report(operation, "ownership")
            raise DeploymentError("Worker ownership does not match this agent")
    return [operation for operation, value, _ in checks if value in (None, "")]
