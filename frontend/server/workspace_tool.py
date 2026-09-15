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

"""Provision an isolated Studio workspace Tool from an immutable CR image."""

from __future__ import annotations

import hashlib
import os
import secrets
import time
from collections.abc import Mapping
from typing import Any

from agentkit.sdk.tools import types

DEFAULT_WORKSPACE_IMAGES = {
    (
        "volcengine",
        "cn-beijing",
    ): "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/agentkit-sandbox:studio-sandbox-1.0.1",
    (
        "volcengine",
        "cn-shanghai",
    ): "enterprise-cn-shanghai-cn-shanghai.cr.volces.com/vefaas-public/agentkit-sandbox:studio-sandbox-1.0.1",
    (
        "byteplus",
        "ap-southeast-1",
    ): "enterprise-public-ap-southeast-1.cr.volces.com/vefaas-public/agentkit-sandbox:studio-sandbox-1.0.1",
}


def resolve_workspace_image(provider: str, region: str) -> str:
    override = os.getenv("STUDIO_WORKSPACE_IMAGE", "").strip()
    if override:
        return override
    image = DEFAULT_WORKSPACE_IMAGES.get((provider, region))
    if not image:
        raise ValueError(
            f"No default Studio Sandbox image for {provider}/{region}; set STUDIO_WORKSPACE_IMAGE"
        )
    return image


def workspace_tool_request(
    image: str, provider: str, model_environment: Mapping[str, str]
) -> Any:
    if provider not in {"volcengine", "byteplus"}:
        raise ValueError("Unsupported workspace provider")
    if not image or image != image.strip() or "://" in image or "/" not in image:
        raise ValueError("A registry image reference is required")
    required = {"MODEL_AGENT_NAME", "MODEL_AGENT_BASE_URL", "MODEL_AGENT_API_KEY"}
    if any(not model_environment.get(key) for key in required):
        raise ValueError("Workspace model configuration is incomplete")
    envs = {key: model_environment[key] for key in required}
    envs.update(
        {
            "VSCODE_LANG": "en" if provider == "byteplus" else "zh-CN",
            "WORKSPACE": "/home/gem/Projects",
            "AIO_USER": "gem",
            "DISABLE_CODE_SERVER": "false",
            "UV_DEFAULT_INDEX": os.getenv(
                "STUDIO_WORKSPACE_DEPENDENCY_INDEX",
                "https://mirrors.aliyun.com/pypi/simple/",
            ),
            "UV_INDEX_URL": os.getenv(
                "STUDIO_WORKSPACE_DEPENDENCY_INDEX",
                "https://mirrors.aliyun.com/pypi/simple/",
            ),
        }
    )
    name = (
        "studio-workspace-"
        + hashlib.sha256((provider + image + "persistent-v1").encode()).hexdigest()[:16]
    )
    return types.CreateToolRequest(
        Name=name,
        ToolType="StudioEnv" if provider == "byteplus" else "Private",
        EnableSnapshot=True,
        ProjectName="default",
        Description="AgentKit Studio Sandbox",
        ImageUrl=image,
        Command="/opt/gem/run.sh",
        Port=8080,
        CpuMilli=8000,
        MemoryMb=16384,
        ModelAgentName=envs["MODEL_AGENT_NAME"],
        ClientToken=secrets.token_hex(16),
        Envs=[types.EnvsItemForCreateTool(Key=k, Value=v) for k, v in envs.items()],
        AuthorizerConfiguration=types.AuthorizerForCreateTool(
            KeyAuth=types.AuthorizerKeyAuthForCreateTool(
                ApiKeyName=name, ApiKeyLocation="Header"
            )
        ),
        NetworkConfiguration=types.NetworkForCreateTool(
            EnablePublicNetwork=True, EnablePrivateNetwork=False
        ),
    )


def ensure_workspace_tool(
    client: Any,
    image: str,
    provider: str,
    model_environment: Mapping[str, str],
    timeout: float = 600,
) -> str:
    request = workspace_tool_request(image, provider, model_environment)
    response = client.list_tools(
        types.ListToolsRequest(
            ProjectName="default",
            MaxResults=100,
            Filters=[types.FiltersItemForListTools(Name="Name", Values=[request.name])],
        )
    )
    matches = [tool for tool in response.tools or [] if tool.name == request.name]
    if len(matches) > 1:
        raise RuntimeError("Multiple workspace tools match the image")
    if matches:
        tool_id = matches[0].tool_id
        if matches[0].tool_type != request.tool_type or matches[0].image_url != image:
            raise RuntimeError(
                "Existing workspace tool does not match the requested image"
            )
        current = client.get_tool(types.GetToolRequest(ToolId=tool_id))
        if not current.enable_snapshot:
            raise RuntimeError("Workspace tool must have snapshots enabled")
        current_env = {item.key: item.value for item in current.envs or []}
        required_env = {item.key: item.value for item in request.envs or []}
        if current.command != request.command or any(
            current_env.get(key) != value for key, value in required_env.items()
        ):
            current_env.update(required_env)
            client.update_tool(
                types.UpdateToolRequest(
                    ToolId=tool_id,
                    Command=request.command,
                    Envs=[
                        types.EnvsItemForUpdateTool(Key=k, Value=v)
                        for k, v in current_env.items()
                    ],
                )
            )
    else:
        tool_id = client.create_tool(request).tool_id
    if not tool_id:
        raise RuntimeError("AgentKit returned no Tool ID")
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        tool = client.get_tool(types.GetToolRequest(ToolId=tool_id))
        status = (tool.status or "").lower()
        if status == "ready":
            return tool_id
        if status in {"failed", "error", "createfailed", "deleted"}:
            raise RuntimeError(f"Workspace tool is {status}")
        time.sleep(3)
    raise TimeoutError("Workspace tool did not become ready")


def provision_workspace_tool(
    *,
    provider: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str = "",
    image: str = "",
) -> str:
    """Provision the image and model environment during Studio deployment."""
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.tools.client import AgentkitToolsClient
    from veadk.auth.veauth.ark_veauth import get_ark_token
    from veadk.cli.studio_sandbox_tools import (
        studio_sandbox_agent_model_name,
        studio_sandbox_model_base_url,
    )

    image = image.strip() or resolve_workspace_image(provider, region)
    # Deployment provisions resources in worker threads without inherited context.
    with default_cloud_provider(provider):
        client = AgentkitToolsClient(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=region,
        )
    key = get_ark_token(
        cloud_provider=provider,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token or None,
    )
    return ensure_workspace_tool(
        client,
        image,
        provider,
        {
            "MODEL_AGENT_NAME": studio_sandbox_agent_model_name(provider),
            "MODEL_AGENT_BASE_URL": studio_sandbox_model_base_url(provider),
            "MODEL_AGENT_API_KEY": key,
        },
    )


def workspace_update_environment(
    environment: Mapping[str, str],
    *,
    provider: str,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str = "",
) -> dict[str, str]:
    """Add a workspace binding without changing existing users' storage identity."""
    if environment.get("STUDIO_WORKSPACE_TOOL_ID", "").strip():
        return {}
    tool_id = provision_workspace_tool(
        provider=provider,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        image=environment.get("STUDIO_WORKSPACE_IMAGE", ""),
    )
    if not tool_id:
        raise RuntimeError("Studio Sandbox provisioning returned no Tool ID")
    return {"STUDIO_WORKSPACE_TOOL_ID": tool_id}


def repair_deployed_workspace_binding(*, provider: str, resolve_credentials) -> str:
    """Backfill older releases whose updater did not know about workspace Tools."""
    import volcenginesdkvefaas as faas
    from veadk.integrations.ve_faas.ve_faas import VeFaaS

    function_id = os.environ["VEADK_STUDIO_FUNCTION_ID"]
    region = (
        os.getenv("VEADK_STUDIO_DEPLOY_REGION") or os.environ["AGENTKIT_SANDBOX_REGION"]
    )
    access_key, secret_key, session_token = resolve_credentials()
    service = VeFaaS(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token or "",
        region=region,
        provider=provider,
    )

    def read_environment():
        function = service.client.get_function(faas.GetFunctionRequest(id=function_id))
        return {item.key: item.value for item in function.envs or []}

    environment = read_environment()
    overrides = workspace_update_environment(
        environment,
        provider=provider,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token or "",
    )
    if not overrides:
        return environment["STUDIO_WORKSPACE_TOOL_ID"]
    # Re-read before writing so concurrent configuration changes are preserved.
    current = read_environment()
    if current.get("STUDIO_WORKSPACE_TOOL_ID", "").strip():
        return current["STUDIO_WORKSPACE_TOOL_ID"]
    service.client.update_function(
        faas.UpdateFunctionRequest(
            id=function_id,
            envs=[
                faas.EnvForUpdateFunctionInput(key=k, value=v)
                for k, v in {**current, **overrides}.items()
            ],
        )
    )
    service.client.release(
        faas.ReleaseRequest(function_id=function_id, revision_number=0)
    )
    return overrides["STUDIO_WORKSPACE_TOOL_ID"]


def mount_workspace_upgrade_repair(app, *, provider: str, resolve_credentials) -> None:
    """Run only for deployed Studios lacking the new binding, without blocking HTTP."""
    if os.getenv("STUDIO_WORKSPACE_TOOL_ID", "").strip() or not os.getenv(
        "VEADK_STUDIO_FUNCTION_ID"
    ):
        return
    import asyncio
    import logging
    from contextlib import asynccontextmanager

    original_lifespan = app.router.lifespan_context

    async def repair():
        try:
            tool_id = await asyncio.to_thread(
                repair_deployed_workspace_binding,
                provider=provider,
                resolve_credentials=resolve_credentials,
            )
            os.environ["STUDIO_WORKSPACE_TOOL_ID"] = tool_id
        except Exception:
            logging.getLogger(__name__).error(
                "Studio workspace setup failed; retry the Studio update after checking cloud permissions"
            )

    @asynccontextmanager
    async def lifespan(current_app):
        async with original_lifespan(current_app):
            task = asyncio.create_task(repair())
            try:
                yield
            finally:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)

    app.router.lifespan_context = lifespan
