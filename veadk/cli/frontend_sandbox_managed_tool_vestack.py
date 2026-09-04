# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""VeStack per-agent Tool provisioning for Studio Sandbox sessions."""

from __future__ import annotations

import asyncio
import secrets
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from veadk.cli.agentkit_sandbox_region import is_agentkit_resource_not_found
from veadk.cli.agentkit_session_metadata import session_display_name_metadata_value
from veadk.cli.frontend_sandbox import (
    AgentkitSandboxGateway,
    SandboxError,
    SandboxProvisioningError,
    _safe_error_message,
)

_TAG_AGENT_KIND = "veadk_agent_kind"
_TAG_CREATED_BY = "veadk_creator_name"
_TAG_DISPLAY_NAME = "veadk_display_name"
_TAG_MANAGED_BY = "veadk_managed_by"
_TAG_OWNER = "veadk_owner"
_TAG_MANAGED_BY_VALUE = "studio"
_READY_ATTEMPTS = 30
_READY_INTERVAL_SECONDS = 2


@dataclass(frozen=True)
class VeStackManagedTool:
    """One Studio-owned VeStack AgentKit Tool for one personal agent."""

    tool_id: str
    name: str
    region: str = ""
    status: str = "Unknown"
    created_at: str = ""
    display_name: str = ""
    created_by: str = ""
    creator_name: str = ""
    agent_kind: str = ""


@dataclass(frozen=True)
class VeStackManagedToolSpec:
    """VeStack deployment configuration for creating independent Tools."""

    tool_type: str
    role_name: str
    model_agent_name: str = ""
    model_agent_api_base: str = ""
    model_agent_api_key: str = field(default="", repr=False)
    model_agent_model_id: str = ""
    project_name: str = "default"
    cpu_milli: int = 2000
    memory_mb: int = 4096
    port: int = 8080
    disk_gb: int = 10


def _tool_tag(value: Any, key: str) -> str:
    for tag in getattr(value, "tags", None) or ():
        tag_key = (
            tag.get("Key") or tag.get("key")
            if isinstance(tag, dict)
            else getattr(tag, "key", "")
        )
        if tag_key != key:
            continue
        tag_value = (
            tag.get("Value") or tag.get("value")
            if isinstance(tag, dict)
            else getattr(tag, "value", "")
        )
        return str(tag_value or "").strip()
    return ""


class VeStackAgentkitSandboxGateway(AgentkitSandboxGateway):
    """AgentKit gateway extended with VeStack per-agent Tool lifecycle APIs."""

    @staticmethod
    def _managed_tool(value: Any, *, region: str = "") -> VeStackManagedTool:
        return VeStackManagedTool(
            tool_id=str(getattr(value, "tool_id", "") or "").strip(),
            name=str(getattr(value, "name", "") or "").strip(),
            region=region,
            status=str(getattr(value, "status", "") or "Unknown").strip(),
            created_at=str(getattr(value, "created_at", "") or "").strip(),
            display_name=_tool_tag(value, _TAG_DISPLAY_NAME),
            created_by=_tool_tag(value, _TAG_OWNER),
            creator_name=_tool_tag(value, _TAG_CREATED_BY),
            agent_kind=_tool_tag(value, _TAG_AGENT_KIND),
        )

    async def list_managed_tools(
        self, agent_kind: str, owner_id: str | None = None
    ) -> list[VeStackManagedTool]:
        from agentkit.sdk.tools import types as tools_types

        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            tools: dict[str, VeStackManagedTool] = {}
            next_token: str | None = None
            try:
                for _page in range(100):
                    tag_filters = [
                        tools_types.TagFiltersItemForListTools(
                            Key=_TAG_MANAGED_BY,
                            Values=[_TAG_MANAGED_BY_VALUE],
                        ),
                        tools_types.TagFiltersItemForListTools(
                            Key=_TAG_AGENT_KIND,
                            Values=[agent_kind],
                        ),
                    ]
                    if owner_id is not None:
                        tag_filters.append(
                            tools_types.TagFiltersItemForListTools(
                                Key=_TAG_OWNER,
                                Values=[owner_id],
                            )
                        )
                    response = await self._call(
                        "list_tools",
                        tools_types.ListToolsRequest(
                            MaxResults=100,
                            NextToken=next_token,
                            TagFilters=tag_filters,
                        ),
                        region=region,
                    )
                    for value in response.tools or []:
                        tool = self._managed_tool(value, region=region)
                        if tool.tool_id:
                            tools[tool.tool_id] = tool
                    next_token = str(response.next_token or "").strip() or None
                    if next_token is None:
                        return sorted(
                            tools.values(),
                            key=lambda item: item.created_at,
                            reverse=True,
                        )
                raise SandboxProvisioningError("AgentKit ListTools 分页超过安全上限。")
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                raise SandboxProvisioningError(
                    f"读取 AgentKit Tool 列表失败：{_safe_error_message(error)}"
                ) from error
        return []

    async def create_managed_tool(
        self,
        spec: VeStackManagedToolSpec,
        *,
        display_name: str,
        owner_id: str,
        creator_name: str,
        agent_kind: str,
    ) -> VeStackManagedTool:
        from agentkit.sdk.tools import types as tools_types

        display_name = session_display_name_metadata_value(display_name)
        creator_name = session_display_name_metadata_value(creator_name)
        owner_id = session_display_name_metadata_value(owner_id)
        suffix = secrets.token_hex(4)
        request_data: dict[str, Any] = {
            "Name": f"VeADK-{agent_kind.title()}-{suffix}",
            "ToolType": spec.tool_type,
            "ProjectName": spec.project_name,
            "RoleName": spec.role_name,
            "Description": "Created by VeADK Studio",
            "EnableSecurity": True,
            "EnableSnapshot": False,
            "CpuMilli": spec.cpu_milli,
            "MemoryMb": spec.memory_mb,
            "Port": spec.port,
            "ClientToken": f"veadk-studio-{uuid.uuid4().hex}",
            "AuthorizerConfiguration": tools_types.AuthorizerForCreateTool(
                KeyAuth=tools_types.AuthorizerKeyAuthForCreateTool(
                    ApiKeyLocation="Header",
                    ApiKeyName=f"apikey_{suffix}",
                )
            ),
            # VeStack requires DiskGb in Envs because the generated SDK does not
            # expose it as a top-level CreateTool field.
            "Envs": [
                tools_types.EnvsItemForCreateTool(
                    Key="DiskGb",
                    Value=str(spec.disk_gb),
                ),
                *[
                    tools_types.EnvsItemForCreateTool(Key=key, Value=value)
                    for key, value in (
                        ("MODEL_AGENT_API_BASE", spec.model_agent_api_base),
                        ("MODEL_AGENT_API_KEY", spec.model_agent_api_key),
                        ("MODEL_AGENT_MODEL_ID", spec.model_agent_model_id),
                    )
                    if value
                ],
            ],
            "Tags": [
                tools_types.TagsItemForCreateTool(
                    Key=_TAG_MANAGED_BY,
                    Type="String",
                    Value=_TAG_MANAGED_BY_VALUE,
                ),
                tools_types.TagsItemForCreateTool(
                    Key=_TAG_AGENT_KIND,
                    Type="String",
                    Value=agent_kind,
                ),
                tools_types.TagsItemForCreateTool(
                    Key=_TAG_OWNER,
                    Type="String",
                    Value=owner_id,
                ),
                tools_types.TagsItemForCreateTool(
                    Key=_TAG_CREATED_BY,
                    Type="String",
                    Value=creator_name,
                ),
                tools_types.TagsItemForCreateTool(
                    Key=_TAG_DISPLAY_NAME,
                    Type="String",
                    Value=display_name,
                ),
            ],
        }
        if spec.model_agent_name:
            request_data["ModelAgentName"] = spec.model_agent_name
        request = tools_types.CreateToolRequest(**request_data)
        regions = self._region_candidates or ("",)
        for index, region in enumerate(regions):
            try:
                created = await self._call("create_tool", request, region=region)
                tool_id = str(getattr(created, "tool_id", "") or "").strip()
                if not tool_id:
                    raise SandboxProvisioningError(
                        "AgentKit 创建 Tool 响应缺少 ToolId。"
                    )
                for attempt in range(_READY_ATTEMPTS):
                    latest = await self._call(
                        "get_tool",
                        tools_types.GetToolRequest(ToolId=tool_id),
                        region=region,
                    )
                    status = str(getattr(latest, "status", "") or "").lower()
                    if status == "ready":
                        tool = self._managed_tool(latest, region=region)
                        return replace(
                            tool,
                            display_name=tool.display_name or display_name,
                            created_by=tool.created_by or owner_id,
                            creator_name=tool.creator_name or creator_name,
                            agent_kind=tool.agent_kind or agent_kind,
                        )
                    if status in {"failed", "error", "deleted"}:
                        raise SandboxProvisioningError(
                            f"AgentKit Tool 创建失败，当前状态：{status}。"
                        )
                    if attempt + 1 < _READY_ATTEMPTS:
                        await asyncio.sleep(_READY_INTERVAL_SECONDS)
                raise SandboxProvisioningError("AgentKit Tool 创建超时。")
            except SandboxError:
                raise
            except Exception as error:
                if is_agentkit_resource_not_found(error) and index + 1 < len(regions):
                    continue
                raise SandboxProvisioningError(
                    f"创建 AgentKit Tool 失败：{_safe_error_message(error)}"
                ) from error
        raise SandboxProvisioningError("无法在支持的地域创建 AgentKit Tool。")

    async def delete_managed_tool(self, tool: VeStackManagedTool) -> None:
        from agentkit.sdk.tools import types as tools_types

        try:
            await self._call(
                "delete_tool",
                tools_types.DeleteToolRequest(ToolId=tool.tool_id),
                region=tool.region,
            )
        except Exception as error:
            if is_agentkit_resource_not_found(error):
                return
            raise SandboxProvisioningError(
                f"删除 AgentKit Tool 失败：{_safe_error_message(error)}"
            ) from error
