"""Inspect and update published sandbox images within a provider and region."""

from __future__ import annotations

import copy
import threading
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, Field

from veadk.cli.agentkit_sandbox_region import (
    is_agentkit_resource_not_found,
    sandbox_region_candidates,
)
from veadk.cli.studio_sandbox_tools import _codex_model_environment_status, _tool_envs


class SandboxUpdateError(ValueError):
    """A diagnostic authored by Studio and safe to show without credentials."""


class _ListToolTypesRequest(BaseModel):
    max_results: int = Field(default=100, alias="MaxResults")
    next_token: str | None = Field(default=None, alias="NextToken")


class _ToolType(BaseModel):
    tool_type: str = Field(alias="ToolType")
    image_url: str = Field(alias="ImageUrl", min_length=1)


class _ListToolTypesResponse(BaseModel):
    tool_types: list[_ToolType] = Field(alias="ToolTypes")
    next_token: str = Field(default="", alias="NextToken")


class SandboxToolUpdates:
    """One service per Studio provider; aliases share locks by region and Tool ID."""

    def __init__(
        self,
        provider: str,
        client_factory: Callable[[str], Any],
        *,
        regions: tuple[str, ...] | None = None,
        timeout_seconds: float = 300,
    ) -> None:
        self.provider = provider
        self.client_factory = client_factory
        self.regions = regions or sandbox_region_candidates(provider=provider)
        self.timeout_seconds = timeout_seconds
        self._catalogs: dict[str, tuple[float, dict[str, str]]] = {}
        self._catalog_lock = threading.Lock()
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    def _catalog(
        self, client: Any, region: str, *, fresh: bool = False
    ) -> dict[str, str]:
        with self._catalog_lock:
            cached = self._catalogs.get(region)
            if not fresh and cached and time.monotonic() - cached[0] < 60:
                return cached[1]
            # Older SDKs do not register this action yet. Reuse their signing,
            # provider host, credential refresh and error handling.
            if hasattr(client, "api_info"):
                client.api_info = dict(client.api_info)
                info = copy.deepcopy(client.api_info["ListTools"])
                info.query["Action"] = "ListToolTypes"
                client.api_info["ListToolTypes"] = info
            images: dict[str, str] = {}
            token: str | None = None
            seen: set[str] = set()
            while True:
                response = client._invoke_api(
                    api_action="ListToolTypes",
                    request=_ListToolTypesRequest(NextToken=token),
                    response_type=_ListToolTypesResponse,
                )
                for item in response.tool_types:
                    if item.tool_type in images:
                        raise SandboxUpdateError("沙箱镜像目录中存在重复类型")
                    images[item.tool_type] = item.image_url.strip()
                token = response.next_token
                if not token:
                    break
                if token in seen:
                    raise SandboxUpdateError("沙箱镜像目录返回了重复分页标识")
                seen.add(token)
            self._catalogs[region] = (time.monotonic(), images)
            return images

    def _find(self, tool_id: str) -> tuple[Any, str, Any]:
        from agentkit.sdk.tools.types import GetToolRequest

        if not tool_id.strip():
            raise SandboxUpdateError("未配置 Sandbox Tool ID")
        last_error: Exception | None = None
        for region in self.regions:
            client = self.client_factory(region)
            try:
                return client, region, client.get_tool(GetToolRequest(ToolId=tool_id))
            except Exception as error:
                if not is_agentkit_resource_not_found(error):
                    raise
                last_error = error
        raise SandboxUpdateError("在当前云厂商的沙箱区域中未找到 Tool") from last_error

    def _state(self, tool: Any, region: str, images: dict[str, str]) -> dict[str, Any]:
        current = str(tool.image_url or "").strip()
        latest = images.get(tool.tool_type, "")
        managed = tool.tool_type != "Private" and bool(latest)
        needs_image = managed and bool(current) and current != latest
        env_status = (
            _codex_model_environment_status(_tool_envs(tool))
            if tool.tool_type == "CodeEnv"
            else None
        )
        needs_env = bool(env_status and env_status.needs_model_env_update)
        can_env = bool(env_status and env_status.can_update_model_env)
        error = ""
        if not managed:
            error = "当前类型没有可用的预置沙箱发布镜像"
        elif not current:
            error = "Tool 未返回当前镜像，无法判断是否需要更新"
        return {
            "provider": self.provider,
            "region": region,
            "toolId": tool.tool_id,
            "toolType": tool.tool_type,
            "status": tool.status,
            "currentImage": current,
            "latestImage": latest,
            "needsImageUpdate": needs_image,
            "needsModelEnvUpdate": needs_env,
            "canUpdateModelEnv": can_env,
            "modelEnvError": env_status.model_env_error
            if needs_env and env_status
            else "",
            "canUpdate": not error
            and tool.status == "Ready"
            and (needs_image or can_env),
            "error": error,
        }

    def inspect(self, tool_id: str) -> dict[str, Any]:
        client, region, tool = self._find(tool_id)
        return self._state(tool, region, self._catalog(client, region))

    def update(self, tool_id: str) -> dict[str, Any]:
        from agentkit.sdk.tools.types import (
            EnvsItemForUpdateTool,
            GetToolRequest,
            UpdateToolRequest,
        )

        client, region, _ = self._find(tool_id)
        with self._locks_guard:
            lock = self._locks.setdefault((region, tool_id), threading.Lock())
        with lock:
            tool = client.get_tool(GetToolRequest(ToolId=tool_id))
            if tool.status != "Ready":
                raise SandboxUpdateError(
                    f"Sandbox 当前状态为 {tool.status}，请等待就绪后重试"
                )
            images = self._catalog(client, region, fresh=True)
            state = self._state(tool, region, images)
            if state["error"]:
                raise SandboxUpdateError(state["error"])
            if not state["canUpdate"]:
                if state["modelEnvError"]:
                    raise SandboxUpdateError(state["modelEnvError"])
                return {"updated": False, "state": state}
            payload: dict[str, Any] = {"ToolId": tool_id}
            if state["needsImageUpdate"]:
                payload["ImageUrl"] = state["latestImage"]
            required_envs: dict[str, str] = {}
            if state["canUpdateModelEnv"]:
                envs = _tool_envs(tool)
                for target, source in (
                    ("MODEL_AGENT_API_KEY", "CODEX_API_KEY"),
                    ("MODEL_AGENT_BASE_URL", "CODEX_BASE_URL"),
                ):
                    if not str(envs.get(target) or "").strip():
                        envs[target] = str(envs[source]).strip()
                    required_envs[target] = str(envs[target])
                payload["Envs"] = [
                    EnvsItemForUpdateTool(Key=key, Value=value)
                    for key, value in envs.items()
                ]
            client.update_tool(UpdateToolRequest(**payload))
            deadline = time.monotonic() + self.timeout_seconds
            while True:
                tool = client.get_tool(GetToolRequest(ToolId=tool_id))
                state = self._state(tool, region, images)
                envs = _tool_envs(tool)
                if (
                    tool.status == "Ready"
                    and tool.image_url == images[tool.tool_type]
                    and all(envs.get(k) == v for k, v in required_envs.items())
                ):
                    return {"updated": True, "state": state}
                if tool.status not in {"Ready", "Updating", "Creating"}:
                    raise RuntimeError(f"Sandbox 更新未成功，当前状态为 {tool.status}")
                if time.monotonic() >= deadline:
                    raise TimeoutError("等待 Sandbox 更新完成超时，请刷新检查实际状态")
                time.sleep(2)
