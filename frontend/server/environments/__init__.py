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

"""Studio execution-environment backend composition."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from frontend.server.agentkit_clients import create_agentkit_client
from frontend.server.storage import StudioProvider, StudioStorageConfig
from frontend.server.storage.tos import CredentialResolver, create_tos_client_factory
from veadk.auth.veauth.ark_veauth import get_ark_token
from veadk.cli.agentkit_sandbox_region import resolve_sandbox_client_region
from veadk.cli.studio_model_catalog import modelark_base_url, studio_agent_model_name
from veadk.utils.cloud_provider import default_region

from .repository import TosEnvironmentRepository
from .resources import EnvironmentResourceSettings, StudioEnvironmentCloudGateway
from .routes import mount_environment_routes
from .service import EnvironmentService, WorkspaceReferenceLookup
from .tool_provisioning import AgentkitEnvironmentToolProvisioner


def _environment_tool_model_env(
    *,
    provider: StudioProvider,
    region: str,
    source: Mapping[str, str],
    resolve_credentials: CredentialResolver,
) -> Mapping[str, str]:
    access_key, secret_key, session_token = resolve_credentials()
    model_api_key = str(
        source.get("MODEL_AGENT_API_KEY")
        or source.get("CODEX_API_KEY")
        or get_ark_token(
            region=resolve_sandbox_client_region(region, provider=provider),
            api_key_name=(
                str(source.get("MODEL_AGENT_API_KEY_NAME") or "").strip() or None
            ),
            cloud_provider=provider,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )
    ).strip()
    model_name = str(
        source.get("MODEL_AGENT_NAME")
        or source.get("CODEX_MODEL")
        or studio_agent_model_name(provider)
    ).strip()
    base_url = (
        str(
            source.get("MODEL_AGENT_BASE_URL")
            or source.get("MODEL_AGENT_API_BASE")
            or source.get("CODEX_BASE_URL")
            or modelark_base_url(provider)
        )
        .strip()
        .rstrip("/")
    )
    model_provider = str(source.get("MODEL_AGENT_PROVIDER") or "openai").strip()
    return {
        "MODEL_AGENT_API_KEY": model_api_key,
        "MODEL_AGENT_NAME": model_name,
        "MODEL_AGENT_API_BASE": base_url,
        "MODEL_AGENT_BASE_URL": base_url,
        "MODEL_AGENT_PROVIDER": model_provider,
        "CODEX_API_KEY": model_api_key,
        "CODEX_BASE_URL": base_url,
        "CODEX_MODEL": model_name,
    }


def create_environment_service(
    *,
    provider: StudioProvider = "volcengine",
    resolve_credentials: CredentialResolver | None = None,
    client_factory: Callable[[], Any] | None = None,
    environment: Mapping[str, str] | None = None,
    workspace_references: WorkspaceReferenceLookup | None = None,
) -> EnvironmentService:
    storage = StudioStorageConfig.from_env(provider, environment)
    if not storage.configured:
        return EnvironmentService(
            None,
            None,
            workspace_references=workspace_references,
            unavailable_reason=storage.unavailable_reason,
        )
    if client_factory is None:
        if resolve_credentials is None:
            return EnvironmentService(
                None,
                None,
                workspace_references=workspace_references,
                unavailable_reason="管理员未配置环境存储与构建凭据。",
            )
        client_factory = create_tos_client_factory(storage, resolve_credentials)
    source = environment if environment is not None else os.environ
    deploy_region = str(source.get("VEADK_STUDIO_DEPLOY_REGION") or "").strip()
    settings = EnvironmentResourceSettings.from_env(
        provider=provider,
        region=deploy_region or default_region(provider),
        bucket=storage.bucket,
        source=source,
    )
    tool_provisioner = None
    if resolve_credentials is not None:

        def _tool_client(tool_provider: str, region: str) -> Any:
            if tool_provider != provider:
                raise ValueError("环境 Tool 的云服务商与当前 Studio 不一致。")
            return _create_environment_tools_client(
                provider,
                region,
                resolve_credentials,
            )

        def _tool_model_environment(
            tool_provider: str,
            region: str,
        ) -> Mapping[str, str]:
            if tool_provider != provider:
                raise ValueError("环境 Tool 的云服务商与当前 Studio 不一致。")
            return _environment_tool_model_env(
                provider=provider,
                region=region,
                source=source,
                resolve_credentials=resolve_credentials,
            )

        tool_provisioner = AgentkitEnvironmentToolProvisioner(
            _tool_client,
            model_environment_resolver=_tool_model_environment,
        )
    return EnvironmentService(
        TosEnvironmentRepository(
            bucket=storage.bucket,
            client_factory=client_factory,
        ),
        StudioEnvironmentCloudGateway(
            settings,
            resolve_credentials=resolve_credentials,
        ),
        workspace_references=workspace_references,
        tool_provisioner=tool_provisioner,
    )


def _create_environment_tools_client(
    provider: StudioProvider,
    region: str,
    resolve_credentials: CredentialResolver,
) -> Any:
    from agentkit.sdk.tools.client import AgentkitToolsClient

    access_key, secret_key, session_token = resolve_credentials()
    client = create_agentkit_client(
        AgentkitToolsClient,
        provider=provider,
        access_key=access_key,
        secret_key=secret_key,
        region=resolve_sandbox_client_region(region, provider=provider),
        session_token=session_token or "",
    )
    if provider != "byteplus":
        client.set_host("open.volcengineapi.com")
    return client


__all__ = [
    "EnvironmentService",
    "create_environment_service",
    "mount_environment_routes",
]
