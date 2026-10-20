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

"""Security policy for backend-generated AgentDraft projects."""

from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Sequence
from urllib.parse import urlparse

from veadk.cli.generated_agent_catalog import (
    EXPORTER_BY_ID,
    KB_BY_ID,
    LTM_BY_ID,
    STM_BY_ID,
    TOOL_BY_ID,
)
from veadk.cli.generated_agent_codegen import AgentDraft
from veadk.cli.studio_model_catalog import (
    SUPPORTED_CLOUD_PROVIDERS,
    is_provider_modelark_base_url,
    modelark_base_url,
)


class DebugPolicyError(ValueError):
    """Raised when an AgentDraft is valid JSON but violates backend policy."""


MAX_NAME_LEN = 64
MAX_DESCRIPTION_LEN = 1024
MAX_INSTRUCTION_LEN = 40_000
MAX_SUBAGENTS = 32
MAX_DEPTH = 6
MAX_CUSTOM_TOOLS = 32
MAX_CUSTOM_TOOL_NAME_LEN = 64
MAX_CUSTOM_TOOL_DESCRIPTION_LEN = 2048
MAX_MCP_TOOLS = 16
MAX_MCP_ARG_LEN = 512
MAX_ITERATIONS = 20
MAX_KNOWLEDGEBASE_INDEX_LEN = 128

_METADATA_HOSTS = {
    "metadata.google.internal",
    "metadata.tencentyun.com",
    "metadata.aliyun.com",
}

_METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),
}

IpNetwork = ipaddress.IPv4Network | ipaddress.IPv6Network
PrivateNetworkResolver = Callable[[], Sequence[IpNetwork]]


def validate_project_policy(draft: AgentDraft) -> None:
    total = _validate_node(
        draft,
        depth=0,
        allow_local_runtime_resources=True,
        allow_stdio_mcp=True,
    )
    if total > MAX_SUBAGENTS + 1:
        raise DebugPolicyError(f"Too many agents: {total}")


def validate_debug_policy(
    draft: AgentDraft,
    *,
    allow_local_runtime_resources: bool = False,
    managed_cloud_provider: str | None = None,
    private_network_resolver: PrivateNetworkResolver | None = None,
) -> None:
    trusted_debug_model_api_base(
        draft,
        managed_cloud_provider=managed_cloud_provider,
    )
    private_networks: tuple[IpNetwork, ...] | None = None

    def resolve_private_networks() -> tuple[IpNetwork, ...]:
        nonlocal private_networks
        if private_networks is None:
            private_networks = tuple(
                private_network_resolver() if private_network_resolver else ()
            )
        return private_networks

    total = _validate_node(
        draft,
        depth=0,
        allow_local_runtime_resources=allow_local_runtime_resources,
        allow_stdio_mcp=False,
        private_network_resolver=resolve_private_networks,
    )
    if total > MAX_SUBAGENTS + 1:
        raise DebugPolicyError(f"Too many agents: {total}")


def trusted_debug_model_api_base(
    draft: AgentDraft,
    *,
    managed_cloud_provider: str | None = None,
) -> str:
    """Return the only model endpoint allowed to receive Studio credentials.

    Generated debug runners have one Studio-managed model credential. Keep that
    credential bound to the current Studio provider's canonical Ark endpoint;
    custom endpoints remain supported by generated projects and deployments,
    where users can supply their own endpoint-specific credential.
    """
    provider = (managed_cloud_provider or draft.cloudProvider or "volcengine").lower()
    if provider not in SUPPORTED_CLOUD_PROVIDERS:
        raise DebugPolicyError(f"Unsupported cloud provider: {provider}")
    trusted = modelark_base_url(provider)
    if managed_cloud_provider and draft.cloudProvider != provider:
        raise DebugPolicyError(
            "调试配置的云环境与当前 Studio 不一致，请切换到当前环境后重试。"
        )

    def visit(node: AgentDraft) -> None:
        if node.agentType == "llm" and node.modelApiBase.strip():
            if not is_provider_modelark_base_url(provider, node.modelApiBase):
                raise DebugPolicyError(
                    "自定义模型地址不能使用 Studio 提供的 Ark API Key 在线调试。"
                    "请改用当前云环境的官方 Ark 地址，或在部署页填写该 Agent "
                    "自己的模型 API Key。"
                )
        for sub_agent in node.subAgents:
            visit(sub_agent)

    visit(draft)
    return trusted


def _validate_node(
    draft: AgentDraft,
    *,
    depth: int,
    allow_local_runtime_resources: bool,
    allow_stdio_mcp: bool,
    private_network_resolver: PrivateNetworkResolver | None = None,
) -> int:
    if depth > MAX_DEPTH:
        raise DebugPolicyError(f"Agent tree is too deep (>{MAX_DEPTH})")
    registry_backed_remote = draft.agentType == "a2a" and draft.a2aRegistry.enabled
    if not registry_backed_remote and not draft.name.strip():
        raise DebugPolicyError("Agent name is required")
    _check_len("name", draft.name, MAX_NAME_LEN)
    _check_len("description", draft.description, MAX_DESCRIPTION_LEN)
    _check_len("instruction", draft.instruction, MAX_INSTRUCTION_LEN)

    if draft.agentType == "loop" and not (1 <= draft.maxIterations <= MAX_ITERATIONS):
        raise DebugPolicyError(f"maxIterations must be between 1 and {MAX_ITERATIONS}")
    if draft.agentType == "a2a":
        if not registry_backed_remote and not draft.a2aUrl.strip():
            raise DebugPolicyError("A2A URL is required")
        if not registry_backed_remote and not allow_local_runtime_resources:
            validate_url_not_private(
                draft.a2aUrl,
                field_name="a2aUrl",
                private_network_resolver=private_network_resolver,
            )
    if draft.a2aRegistry.enabled and not draft.a2aRegistry.registrySpaceId.strip():
        raise DebugPolicyError("A2A registry space id is required")

    _validate_catalog_ids("builtinTools", draft.builtinTools, TOOL_BY_ID)
    if draft.shortTermBackend not in STM_BY_ID:
        raise DebugPolicyError(
            f"Unsupported shortTermBackend: {draft.shortTermBackend}"
        )
    if draft.longTermBackend not in LTM_BY_ID:
        raise DebugPolicyError(f"Unsupported longTermBackend: {draft.longTermBackend}")
    _check_len(
        "longTermMemoryIndex",
        draft.longTermMemoryIndex,
        MAX_KNOWLEDGEBASE_INDEX_LEN,
    )
    if draft.knowledgebaseBackend not in KB_BY_ID:
        raise DebugPolicyError(
            f"Unsupported knowledgebaseBackend: {draft.knowledgebaseBackend}"
        )
    _check_len(
        "knowledgebaseIndex",
        draft.knowledgebaseIndex,
        MAX_KNOWLEDGEBASE_INDEX_LEN,
    )
    _validate_catalog_ids("tracingExporters", draft.tracingExporters, EXPORTER_BY_ID)

    if len(draft.customTools) > MAX_CUSTOM_TOOLS:
        raise DebugPolicyError("Too many custom tools")
    for tool in draft.customTools:
        _check_len("custom tool name", tool.name, MAX_CUSTOM_TOOL_NAME_LEN)
        _check_len(
            "custom tool description",
            tool.description,
            MAX_CUSTOM_TOOL_DESCRIPTION_LEN,
        )

    if len(draft.mcpTools) > MAX_MCP_TOOLS:
        raise DebugPolicyError("Too many MCP tools")
    for tool in draft.mcpTools:
        if tool.transport == "stdio" and not allow_stdio_mcp:
            raise DebugPolicyError("MCP stdio transport is disabled for debug runs")
        if tool.transport == "http" and not allow_local_runtime_resources:
            validate_url_not_private(
                tool.url,
                field_name="mcpTools.url",
                private_network_resolver=private_network_resolver,
            )
        for arg in tool.args:
            _check_len("MCP arg", arg, MAX_MCP_ARG_LEN)

    total = 1
    for sub in draft.subAgents:
        total += _validate_node(
            sub,
            depth=depth + 1,
            allow_local_runtime_resources=allow_local_runtime_resources,
            allow_stdio_mcp=allow_stdio_mcp,
            private_network_resolver=private_network_resolver,
        )
    return total


def validate_url_not_private(
    raw_url: str,
    *,
    field_name: str,
    resolve_dns: bool = True,
    private_network_resolver: PrivateNetworkResolver | None = None,
) -> None:
    raw = (raw_url or "").strip()
    if not raw:
        raise DebugPolicyError(f"{field_name} is required")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        raise DebugPolicyError(f"{field_name} must use http or https")
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise DebugPolicyError(f"{field_name} must include a hostname")
    if host == "localhost" or host.endswith(".localhost") or host in _METADATA_HOSTS:
        raise DebugPolicyError(f"{field_name} points to a forbidden host")

    try:
        literal_ip = ipaddress.ip_address(host)
    except ValueError:
        literal_ip = None
    if literal_ip is not None:
        _validate_target_ip(
            literal_ip,
            field_name=field_name,
            private_network_resolver=private_network_resolver,
        )
        return

    if not resolve_dns:
        return
    try:
        infos = socket.getaddrinfo(host, parsed.port or _default_port(parsed.scheme))
    except OSError as exc:
        raise DebugPolicyError(f"{field_name} cannot be resolved") from exc

    seen: set[str] = set()
    for info in infos:
        sockaddr = info[4]
        if not sockaddr:
            continue
        ip_raw = str(sockaddr[0])
        if ip_raw in seen:
            continue
        seen.add(ip_raw)
        try:
            resolved_ip = ipaddress.ip_address(ip_raw)
        except ValueError as exc:
            raise DebugPolicyError(f"{field_name} resolved to an invalid IP") from exc
        _validate_target_ip(
            resolved_ip,
            field_name=field_name,
            private_network_resolver=private_network_resolver,
        )


def _default_port(scheme: str) -> int:
    return 443 if scheme == "https" else 80


def _endpoint_label(field_name: str) -> str:
    return "MCP 地址" if field_name == "mcpTools.url" else "A2A 地址"


def _validate_target_ip(
    ip: ipaddress._BaseAddress,
    *,
    field_name: str,
    private_network_resolver: PrivateNetworkResolver | None,
) -> None:
    if (
        ip in _METADATA_IPS
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise DebugPolicyError(
            f"{_endpoint_label(field_name)}解析到禁止访问的系统地址 {ip}。"
            "云上 Studio 不允许访问环回、链路本地、云元数据或保留地址。"
        )
    if ip.is_global:
        return

    allowed_networks = tuple(
        private_network_resolver() if private_network_resolver else ()
    )
    if any(
        ip.version == network.version and ip in network for network in allowed_networks
    ):
        return
    raise DebugPolicyError(
        f"{_endpoint_label(field_name)}解析到私网地址 {ip}，"
        "但该地址不属于当前云上 Studio 所连接的 VPC 网段。"
        "请确认 Studio 与服务位于同一 VPC，或已通过 PrivateLink 连通。"
    )


def _validate_catalog_ids(
    name: str, values: list[str], catalog: dict[str, object]
) -> None:
    for value in values:
        if value not in catalog:
            raise DebugPolicyError(f"Unsupported {name}: {value}")


def _check_len(name: str, value: str, limit: int) -> None:
    if len(value or "") > limit:
        raise DebugPolicyError(f"{name} is too long (>{limit})")
