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

"""Resolve AgentKit control-plane resource ids into VeADK runtime config."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Any
from urllib.parse import urlsplit

from veadk.cloud.harness_app.types import HarnessResourceOverride
from veadk.tools.builtin_tools.create_agent.sources.cloud import (
    CloudCredentials,
    default_agentkit_region,
    resolve_cloud_credentials,
)
from veadk.utils.cloud_provider import cloud_provider_from_env
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

CredentialsResolver = Callable[[], CloudCredentials | None]
MemoryClientFactory = Callable[[CloudCredentials, str], Any]
KnowledgeClientFactory = Callable[[CloudCredentials, str], Any]
McpClientFactory = Callable[[CloudCredentials, str], Any]

_SUPPORTED_AUTH_TYPES = {"", "aksk", "sts", "temporaryaksk", "temporarycredentials"}


class AgentKitResourceResolver:
    """Resolve memory/knowledge resource ids with the AgentKit SDK clients."""

    def __init__(
        self,
        *,
        region: str | None = None,
        credential_resolver: CredentialsResolver | None = None,
        memory_client_factory: MemoryClientFactory | None = None,
        knowledge_client_factory: KnowledgeClientFactory | None = None,
    ) -> None:
        self.region = region or default_agentkit_region()
        self._credential_resolver = credential_resolver or resolve_cloud_credentials
        self._memory_client_factory = (
            memory_client_factory or _default_memory_client_factory
        )
        self._knowledge_client_factory = (
            knowledge_client_factory or _default_knowledge_client_factory
        )

    def __call__(
        self,
        kind: str,
        resource: HarnessResourceOverride,
    ) -> HarnessResourceOverride | None:
        if not resource.id:
            return resource

        credentials = self._credential_resolver()
        if credentials is None:
            logger.warning(
                "AgentKit credentials are unavailable; cannot resolve %s id=%s.",
                kind,
                resource.id,
            )
            return None

        if kind == "knowledgebase":
            return self._resolve_knowledgebase(resource, credentials)
        if kind == "longterm_memory":
            return self._resolve_longterm_memory(resource, credentials)
        raise ValueError(f"Unsupported Harness resource kind: {kind}")

    def _resolve_knowledgebase(
        self,
        resource: HarnessResourceOverride,
        credentials: CloudCredentials,
    ) -> HarnessResourceOverride:
        from agentkit.sdk.knowledge import types

        client = self._knowledge_client_factory(credentials, self.region)
        knowledge_id = resource.id or ""
        detail = client.get_knowledge_base(
            types.GetKnowledgeBaseRequest(KnowledgeId=knowledge_id)
        )
        connection = client.get_knowledge_connection_info(
            types.GetKnowledgeConnectionInfoRequest(KnowledgeId=knowledge_id)
        )
        info = _preferred_connection_info(connection.connection_infos or [])
        provider_type = _text(
            getattr(connection, "provider_type", "")
            or getattr(detail, "provider_type", "")
        )
        backend = _knowledge_backend_type(provider_type)
        _validate_requested_type(resource.type, backend, "knowledgebase")
        config = _resolved_knowledge_config(
            detail=detail,
            connection=connection,
            info=info,
            credentials=credentials,
            control_plane_region=self.region,
        )
        config.update(resource.config or {})
        return HarnessResourceOverride(
            type=backend,
            id=resource.id,
            config=config,
        )

    def _resolve_longterm_memory(
        self,
        resource: HarnessResourceOverride,
        credentials: CloudCredentials,
    ) -> HarnessResourceOverride:
        from agentkit.sdk.memory import types

        client = self._memory_client_factory(credentials, self.region)
        memory_id = resource.id or ""
        detail = client.get_memory_collection(
            types.GetMemoryCollectionRequest(MemoryId=memory_id)
        )
        connection = client.get_memory_connection_info(
            types.GetMemoryConnectionInfoRequest(MemoryId=memory_id)
        )
        info = _preferred_connection_info(connection.connection_infos or [])
        provider_type = _text(
            getattr(connection, "provider_type", "")
            or getattr(detail, "provider_type", "")
        )
        backend = _memory_backend_type(provider_type)
        _validate_requested_type(resource.type, backend, "longterm_memory")
        config = _resolved_memory_config(
            backend=backend,
            detail=detail,
            connection=connection,
            info=info,
            credentials=credentials,
            control_plane_region=self.region,
        )
        config.update(resource.config or {})
        return HarnessResourceOverride(
            type=backend,
            id=resource.id,
            config=config,
        )


class AgentKitMcpRouterResolver:
    """Resolve an AgentKit MCP toolset id into mcp_router runtime config."""

    def __init__(
        self,
        *,
        region: str | None = None,
        credential_resolver: CredentialsResolver | None = None,
        mcp_client_factory: McpClientFactory | None = None,
    ) -> None:
        self.region = region or default_agentkit_region()
        self._credential_resolver = credential_resolver or resolve_cloud_credentials
        self._mcp_client_factory = mcp_client_factory or _default_mcp_client_factory

    def __call__(
        self,
        mcp_router_id: str,
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        credentials = self._credential_resolver()
        if credentials is None:
            logger.warning(
                "AgentKit credentials are unavailable; cannot resolve MCP router id=%s.",
                mcp_router_id,
            )
            return None

        from agentkit.sdk.mcp import types

        client = self._mcp_client_factory(credentials, self.region)
        response = client.get_mcp_toolset(
            types.GetMCPToolsetRequest(MCPToolsetId=mcp_router_id)
        )
        toolset = getattr(response, "mcp_toolset", None)
        if toolset is None:
            raise ValueError(f"AgentKit MCP toolset '{mcp_router_id}' was not found.")

        url = _mcp_toolset_url(toolset)
        api_key = _mcp_toolset_api_key(toolset)
        resolved = {
            "mcp_router_id": mcp_router_id,
            "url": url,
            "api_key": api_key,
            "name": _text(getattr(toolset, "name", "")),
        }
        resolved = {
            key: value for key, value in resolved.items() if value not in {None, ""}
        }
        resolved.update(config or {})
        return resolved


def default_agentkit_resource_resolver() -> AgentKitResourceResolver:
    """Build the default resolver used by HarnessApp at runtime."""

    return AgentKitResourceResolver()


def default_agentkit_mcp_router_resolver() -> AgentKitMcpRouterResolver:
    """Build the default MCP router resolver used by HarnessApp at runtime."""

    return AgentKitMcpRouterResolver()


def _default_memory_client_factory(credentials: CloudCredentials, region: str) -> Any:
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.memory.client import AgentkitMemoryClient

    with default_cloud_provider(cloud_provider_from_env()):
        return AgentkitMemoryClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token,
            region=region,
        )


def _default_knowledge_client_factory(
    credentials: CloudCredentials, region: str
) -> Any:
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.knowledge.client import AgentkitKnowledgeClient

    with default_cloud_provider(cloud_provider_from_env()):
        return AgentkitKnowledgeClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token,
            region=region,
        )


def _default_mcp_client_factory(credentials: CloudCredentials, region: str) -> Any:
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.mcp.client import AgentkitMCPClient

    with default_cloud_provider(cloud_provider_from_env()):
        return AgentkitMCPClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token,
            region=region,
        )


def _preferred_connection_info(infos: list[Any]) -> Any:
    info = next(
        (
            item
            for item in infos
            if _text(getattr(item, "status", "")).casefold()
            in {"", "ready", "available", "active"}
            and _text(getattr(item, "addr_type", "")).casefold()
            in {"", "public", "internet"}
        ),
        infos[0] if infos else None,
    )
    if info is None:
        raise ValueError("AgentKit returned no provider connection info.")
    return info


def _knowledge_backend_type(provider_type: str) -> str:
    normalized = _provider_type(provider_type)
    if normalized == "vikingdbknowledge":
        return "viking"
    raise ValueError(f"Unsupported AgentKit knowledge provider type: {provider_type}")


def _memory_backend_type(provider_type: str) -> str:
    normalized = _provider_type(provider_type)
    if normalized == "mem0":
        return "mem0"
    if normalized == "vikingdbmemory":
        return "viking"
    raise ValueError(f"Unsupported AgentKit memory provider type: {provider_type}")


def _provider_type(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _validate_requested_type(
    requested_type: str, resolved_type: str, kind: str
) -> None:
    requested = requested_type.strip().casefold()
    if requested and requested != resolved_type:
        raise ValueError(
            f"AgentKit {kind} provider resolved to '{resolved_type}', "
            f"but request specified '{requested_type}'."
        )


def _resolved_knowledge_config(
    *,
    detail: Any,
    connection: Any,
    info: Any,
    credentials: CloudCredentials,
    control_plane_region: str,
) -> dict[str, Any]:
    provider_id = _text(
        getattr(connection, "provider_knowledge_id", "")
        or getattr(detail, "provider_knowledge_id", "")
    )
    knowledge_id = _text(getattr(detail, "knowledge_id", ""))
    name = _text(getattr(detail, "name", ""))
    region = (
        _text(getattr(info, "region", ""))
        or _text(getattr(detail, "region", ""))
        or control_plane_region
    )
    project_name = _text(getattr(detail, "project_name", "")) or "default"
    access_key, secret_key, session_token = _connection_credentials(
        auth_type=_text(getattr(info, "auth_type", "")),
        auth_key=_text(getattr(info, "auth_key", "")),
        extra_config=_text(getattr(info, "extra_config", "")),
        fallback=credentials,
    )
    base_url_config = _base_url_config(_text(getattr(info, "base_url", "")))
    resource_id = (
        provider_id
        if provider_id.startswith("kb-")
        else (knowledge_id if knowledge_id.startswith("kb-") else "")
    )
    index = _viking_index(provider_id, name or knowledge_id)
    config = {
        "name": name or knowledge_id,
        "description": _text(getattr(detail, "description", "")),
        "index": index,
        "app_name": index,
        "resource_id": resource_id,
        "region": region,
        "volcengine_project": project_name,
        "volcengine_access_key": access_key,
        "volcengine_secret_key": secret_key,
        "session_token": session_token or "",
        "cloud_provider": cloud_provider_from_env(),
        **base_url_config,
    }
    return {key: value for key, value in config.items() if value not in {None, ""}}


def _resolved_memory_config(
    *,
    backend: str,
    detail: Any,
    connection: Any,
    info: Any,
    credentials: CloudCredentials,
    control_plane_region: str,
) -> dict[str, Any]:
    provider_id = _text(
        getattr(connection, "provider_collection_id", "")
        or getattr(detail, "provider_collection_id", "")
    )
    memory_id = _text(getattr(detail, "memory_id", ""))
    name = _text(getattr(detail, "name", ""))
    region = (
        _text(getattr(info, "region", ""))
        or _text(getattr(detail, "region", ""))
        or control_plane_region
    )
    project_name = _text(getattr(detail, "project_name", "")) or "default"
    if backend == "mem0":
        return _resolved_mem0_config(
            provider_id=provider_id,
            memory_id=memory_id,
            name=name,
            info=info,
        )
    access_key, secret_key, session_token = _connection_credentials(
        auth_type=_text(getattr(info, "auth_type", "")),
        auth_key=_text(getattr(info, "auth_key", "")),
        extra_config=_text(getattr(info, "extra_config", "")),
        fallback=credentials,
    )
    index = _viking_index(provider_id, name or memory_id)
    config = {
        "index": index,
        "app_name": index,
        "region": region,
        "volcengine_project": project_name,
        "volcengine_access_key": access_key,
        "volcengine_secret_key": secret_key,
        "session_token": session_token or "",
        "cloud_provider": cloud_provider_from_env(),
    }
    return {key: value for key, value in config.items() if value not in {None, ""}}


def _resolved_mem0_config(
    *,
    provider_id: str,
    memory_id: str,
    name: str,
    info: Any,
) -> dict[str, Any]:
    extra = _json_object(_text(getattr(info, "extra_config", "")))
    auth = _json_object(_text(getattr(info, "auth_key", "")))
    api_key = (
        _credential_value(auth, {"apikey", "token", "authkey"})
        or _credential_value(extra, {"apikey", "token", "authkey"})
        or _text(getattr(info, "auth_key", ""))
    )
    base_url = _text(getattr(info, "base_url", "")) or _string_value(
        extra, "base_url", "BaseUrl", "host", "Host"
    )
    index = provider_id or name or memory_id
    config = {
        "index": index,
        "app_name": index,
        "api_key": api_key,
        "base_url": base_url,
        "project_id": provider_id,
    }
    return {key: value for key, value in config.items() if value not in {None, ""}}


def _connection_credentials(
    *,
    auth_type: str,
    auth_key: str,
    extra_config: str,
    fallback: CloudCredentials,
) -> tuple[str, str, str]:
    normalized_auth_type = _provider_type(auth_type)
    if not auth_key and normalized_auth_type in {"", "aksk"}:
        return fallback.access_key, fallback.secret_key, fallback.session_token
    if normalized_auth_type not in _SUPPORTED_AUTH_TYPES:
        raise ValueError(f"Unsupported AgentKit provider auth type: {auth_type}")

    combined: dict[str, Any] = {}
    for raw in (auth_key, extra_config):
        if not raw:
            continue
        combined.update(_json_object_or_error(raw))

    access_key = _credential_value(combined, {"ak", "accesskey", "accesskeyid"})
    secret_key = _credential_value(combined, {"sk", "secretkey", "secretaccesskey"})
    session_token = _credential_value(
        combined,
        {"sessiontoken", "securitytoken", "ststoken"},
    )
    if not access_key or not secret_key:
        return fallback.access_key, fallback.secret_key, fallback.session_token
    if (
        normalized_auth_type in {"sts", "temporaryaksk", "temporarycredentials"}
        and not session_token
    ):
        raise ValueError("AgentKit provider temporary credentials lack STS token.")
    return access_key, secret_key, session_token


def _credential_value(payload: dict[str, Any], aliases: set[str]) -> str:
    pending: list[tuple[dict[str, Any], int]] = [(payload, 0)]
    while pending:
        current, depth = pending.pop()
        for key, value in current.items():
            normalized = _provider_type(str(key))
            if normalized in aliases and isinstance(value, str) and value.strip():
                return value.strip()
            if depth < 2 and isinstance(value, dict):
                pending.append((value, depth + 1))
    return ""


def _json_object(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _json_object_or_error(raw: str) -> dict[str, Any]:
    raw = raw.strip()
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError("AgentKit provider auth info is not valid JSON.") from e
    if not isinstance(value, dict):
        raise TypeError("AgentKit provider auth info must be a JSON object.")
    return value


def _string_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _text(value: Any) -> str:
    return str(value or "").strip()


def _viking_index(provider_id: str, fallback: str) -> str:
    provider_id = provider_id.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", provider_id):
        return provider_id
    return fallback


def _base_url_config(base_url: str) -> dict[str, str]:
    if not base_url:
        return {}
    parsed = urlsplit(base_url)
    host = parsed.netloc or parsed.path.split("/", 1)[0]
    return {
        "base_url": base_url,
        "host": host,
        "schema": parsed.scheme or "https",
    }


def _mcp_toolset_url(toolset: Any) -> str:
    path = _text(getattr(toolset, "path", ""))
    endpoint = _preferred_mcp_endpoint(
        getattr(toolset, "network_configurations", None) or []
    )
    if not endpoint:
        for service in getattr(toolset, "mcp_services", None) or []:
            endpoint = _preferred_mcp_endpoint(
                getattr(service, "network_configurations", None) or []
            )
            path = path or _text(getattr(service, "path", ""))
            if endpoint:
                break
    if not endpoint:
        raise ValueError("AgentKit MCP toolset has no network endpoint.")
    return _join_url_path(endpoint, path)


def _preferred_mcp_endpoint(networks: list[Any]) -> str:
    selected = next(
        (
            network
            for network in networks
            if _text(getattr(network, "network_type", "")).casefold()
            in {"", "public", "internet"}
            and _text(getattr(network, "endpoint", ""))
        ),
        networks[0] if networks else None,
    )
    return _text(getattr(selected, "endpoint", "")) if selected else ""


def _join_url_path(endpoint: str, path: str) -> str:
    endpoint = endpoint.strip()
    path = path.strip()
    if not path:
        return endpoint
    if not path.startswith("/"):
        path = f"/{path}"
    if endpoint.endswith(path):
        return endpoint
    return f"{endpoint.rstrip('/')}{path}"


def _mcp_toolset_api_key(toolset: Any) -> str:
    authorizer_config = getattr(toolset, "authorizer_configuration", None)
    auth_type = _provider_type(getattr(authorizer_config, "authorizer_type", ""))
    if auth_type and auth_type not in {"apikey", "keyauth"}:
        raise ValueError(
            "Unsupported AgentKit MCP router authorizer type: "
            f"{getattr(authorizer_config, 'authorizer_type', '')}"
        )
    authorizer = getattr(authorizer_config, "authorizer", None)
    key_auth = getattr(authorizer, "key_auth", None)
    for item in getattr(key_auth, "api_keys", None) or []:
        key = _text(getattr(item, "key", ""))
        if key:
            return key
    if auth_type in {"apikey", "keyauth"}:
        raise ValueError("AgentKit MCP router ApiKey authorizer has no api key.")
    return ""
