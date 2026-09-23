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

"""Create or reuse the Codex worker AgentKit Tool for mpa-agent (FR-12/13).

Mirrors the verified Codex worker Tool contract observed on the test account
(`t-yeslt9bv9ckgnctgwaaf`, built from the ``mpa_codex_worker`` image):
``ToolType=Private``, ``command=/opt/gem/run.sh``, ``port=8000``,
``cpu 2000 / mem 4096``, ``role IDRoleForArkClawShareAgent``, key auth. The env
set is cloned from a reference tool so the sandbox reaches Ready.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

# Verified contract for a Codex worker sandbox Tool (see design §4.4).
CODEX_WORKER_TOOL_DEFAULTS: dict[str, Any] = {
    "tool_type": "Private",
    "command": "/opt/gem/run.sh",
    "port": 8000,
    "cpu_milli": 2000,
    "memory_mb": 4096,
    "role_name": "IDRoleForArkClawShareAgent",
}
TOS_MOUNT_BASE_PATH = "/sandbox-session/default/default"
TOS_MOUNT_LOCAL_PATH = "/data/output"

_READY_TIMEOUT_SECONDS = 600.0
_READY_POLL_SECONDS = 5.0


class MpaToolError(RuntimeError):
    """Raised when the Codex worker Tool cannot be resolved or created."""


def tos_mount_enabled(
    *, tos_access_key: str = "", tos_secret_key: str = "", tos_bucket: str = ""
) -> bool:
    """Validate the all-or-none TOS tuple and return whether it is enabled."""
    values = tuple(
        value.strip() for value in (tos_access_key, tos_secret_key, tos_bucket)
    )
    if any(values) and not all(values):
        raise MpaToolError(
            "tos-access-key, tos-secret-key, and tos-bucket must all be provided"
        )
    return all(values)


def build_tos_mount_config(
    *, tos_access_key: str, tos_secret_key: str, tos_bucket: str, region: str
) -> Any:
    """Build the Tool-level TOS configuration for per-session output paths."""
    from agentkit.sdk.tools import types as t
    from agentkit.toolkit.volcengine.services.tos_service import TOSService

    return t.TosMountForCreateTool(
        EnableTos=True,
        CredentialType=t.CredentialType.TOS_CREDENTIAL_TYPE_ACCESS_KEY,
        Credentials=t.TosMountCredentialsForCreateTool(
            AccessKeyId=tos_access_key.strip(),
            SecretAccessKey=tos_secret_key.strip(),
        ),
        MountPoints=[
            t.TosMountMountPointsItemForCreateTool(
                BucketName=tos_bucket.strip(),
                BucketPath=TOS_MOUNT_BASE_PATH,
                Endpoint=TOSService.build_mount_endpoint(region.strip()),
                LocalMountPath=TOS_MOUNT_LOCAL_PATH,
                ReadOnly=False,
            )
        ],
    )


def _validate_existing_tos_mount(client: Any, tool_id: str, bucket: str) -> None:
    """Fail rather than silently reuse a Tool without the requested mount."""
    from agentkit.sdk.tools import types as t

    tool = client.get_tool(t.GetToolRequest(ToolId=tool_id))
    config = getattr(tool, "tos_mount_config", None)
    mounts = getattr(config, "mount_points", None) or []
    if not getattr(config, "enable_tos", False) or not any(
        getattr(mount, "bucket_name", "") == bucket.strip()
        and getattr(mount, "bucket_path", "") == TOS_MOUNT_BASE_PATH
        and getattr(mount, "local_mount_path", "") == TOS_MOUNT_LOCAL_PATH
        and getattr(mount, "read_only", None) is False
        for mount in mounts
    ):
        raise MpaToolError(
            "existing tool does not have the requested TOS /data/output mount"
        )


def _find_tool_by_name(client: Any, name: str) -> str:
    """Return the sole tool id with the exact name, or empty string."""
    from agentkit.sdk.tools import types as t

    request = t.ListToolsRequest(
        filters=[t.FiltersItemForListTools(name=name)],
        page_number=1,
        page_size=50,
    )
    resp = client.list_tools(request)
    matches: list[str] = []
    for tool in getattr(resp, "tools", None) or []:
        if getattr(tool, "name", None) == name:
            tool_id = str(getattr(tool, "tool_id", "") or "")
            if tool_id:
                matches.append(tool_id)
    unique = list(dict.fromkeys(matches))
    if len(unique) > 1:
        raise MpaToolError(
            f"multiple tools have the exact name {name!r}; "
            "use --tool-name or --agentkit-tool-id to disambiguate"
        )
    return unique[0] if unique else ""


def _clone_reference_envs(client: Any, reference_tool_id: str) -> list[Any]:
    """Clone the env items from a reference tool as CreateTool env items."""
    from agentkit.sdk.tools import types as t

    ref = client.get_tool(t.GetToolRequest(ToolId=reference_tool_id))
    items: list[Any] = []
    for env in getattr(ref, "envs", None) or []:
        key = getattr(env, "key", None)
        value = getattr(env, "value", None)
        if key is None:
            continue
        items.append(t.EnvsItemForCreateTool(key=key, value=value or ""))
    return items


def _wait_ready(
    client: Any,
    tool_id: str,
    *,
    timeout: float,
    poll_interval: float,
    sleep=time.sleep,
) -> None:
    from agentkit.sdk.tools import types as t

    deadline = time.monotonic() + timeout
    while True:
        tool = client.get_tool(t.GetToolRequest(ToolId=tool_id))
        status = str(getattr(tool, "status", "") or "")
        if status == "Ready":
            return
        if status in {"Failed", "Error", "Deleted"}:
            raise MpaToolError(f"tool {tool_id} entered terminal status {status}")
        if time.monotonic() >= deadline:
            raise MpaToolError(
                f"tool {tool_id} did not reach Ready within {timeout:.0f}s "
                f"(last status={status})"
            )
        if poll_interval > 0:
            sleep(poll_interval)
        else:
            # Non-blocking test path: one more read then bail if still not ready.
            tool = client.get_tool(t.GetToolRequest(ToolId=tool_id))
            if str(getattr(tool, "status", "") or "") == "Ready":
                return
            raise MpaToolError(f"tool {tool_id} not Ready (status={status})")


def ensure_codex_worker_tool(
    client: Any,
    *,
    name: str,
    image: str,
    reference_tool_id: str = "",
    role_name: str = CODEX_WORKER_TOOL_DEFAULTS["role_name"],
    project_name: str = "default",
    extra_envs: dict[str, str] | None = None,
    region: str = "cn-beijing",
    tos_access_key: str = "",
    tos_secret_key: str = "",
    tos_bucket: str = "",
    wait_ready: bool = True,
    timeout: float = _READY_TIMEOUT_SECONDS,
    poll_interval: float = _READY_POLL_SECONDS,
) -> str:
    """Reuse a Ready tool named ``name`` or create one from ``image``.

    Args:
        client: An ``AgentkitToolsClient``.
        name: Target tool name (idempotency key; a Ready tool with this name is
            reused).
        image: Codex worker image URL used when creating.
        reference_tool_id: Optional tool id whose env set is cloned so the
            sandbox reaches Ready (design OQ-5).
        role_name: Execution role used by the created Tool.
        project_name: AgentKit project name.
        extra_envs: Optional env overrides merged on top of the cloned set.
        wait_ready: Wait until the created tool is Ready before returning.

    Returns:
        The resolved tool id (``t-*``).
    """
    from agentkit.sdk.tools import types as t

    name = (name or "").strip()
    if not name:
        raise MpaToolError("tool name is required")

    mount_enabled = tos_mount_enabled(
        tos_access_key=tos_access_key,
        tos_secret_key=tos_secret_key,
        tos_bucket=tos_bucket,
    )

    existing = _find_tool_by_name(client, name)
    if existing:
        if wait_ready:
            _wait_ready(client, existing, timeout=timeout, poll_interval=poll_interval)
        if mount_enabled:
            _validate_existing_tos_mount(client, existing, tos_bucket)
        return existing

    if not image.strip():
        raise MpaToolError("a codex worker image is required to create the tool")

    envs: list[Any] = []
    if reference_tool_id:
        envs = _clone_reference_envs(client, reference_tool_id)
    if extra_envs:
        by_key = {getattr(e, "key", None): e for e in envs}
        for key, value in extra_envs.items():
            by_key[key] = t.EnvsItemForCreateTool(key=key, value=value)
        envs = list(by_key.values())

    request = t.CreateToolRequest(
        Name=name,
        ToolType=CODEX_WORKER_TOOL_DEFAULTS["tool_type"],
        ImageUrl=image,
        Command=CODEX_WORKER_TOOL_DEFAULTS["command"],
        Port=CODEX_WORKER_TOOL_DEFAULTS["port"],
        CpuMilli=CODEX_WORKER_TOOL_DEFAULTS["cpu_milli"],
        MemoryMb=CODEX_WORKER_TOOL_DEFAULTS["memory_mb"],
        RoleName=role_name,
        ProjectName=project_name,
        ClientToken=secrets.token_hex(16),
        AuthorizerConfiguration=t.AuthorizerForCreateTool(
            key_auth=t.AuthorizerKeyAuthForCreateTool(
                api_key_name=f"{name}-{secrets.token_hex(6)}",
                api_key_location="Header",
            )
        ),
        NetworkConfiguration=t.NetworkForCreateTool(
            enable_public_network=True,
            enable_private_network=False,
        ),
        TosMountConfig=(
            build_tos_mount_config(
                tos_access_key=tos_access_key,
                tos_secret_key=tos_secret_key,
                tos_bucket=tos_bucket,
                region=region,
            )
            if mount_enabled
            else None
        ),
        Envs=envs or None,
    )
    response = client.create_tool(request)
    tool_id = str(getattr(response, "tool_id", "") or "")
    if not tool_id:
        raise MpaToolError("CreateTool returned no tool id")

    if wait_ready:
        _wait_ready(client, tool_id, timeout=timeout, poll_interval=poll_interval)
    return tool_id
