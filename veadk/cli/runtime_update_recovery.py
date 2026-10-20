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
"""Safe recovery primitives for editing an already deployed Studio Runtime.

The Runtime data plane is an untrusted compatibility boundary.  This module
keeps the recovery classification, draft validation and environment redaction
independent from HTTP routing so the security rules can be tested directly.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any, Iterable, Literal, Mapping
from urllib.parse import urlsplit

from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import AgentDraft

__all__ = [
    "RuntimeEnvironmentView",
    "RuntimeUpdateRecovery",
    "assess_legacy_recovered_agent",
    "assess_runtime_update_agent",
    "mcp_auth_environment_keys",
    "sanitize_runtime_agent_info",
    "sanitize_runtime_environment",
]


RecoveryStatus = Literal[
    "complete",
    "draft-only",
    "introspection-only",
    "missing-source",
    "incompatible",
]
EditMode = Literal["source-preserving", "regenerate", "blocked"]
RecoverySource = Literal[
    "editable-spec",
    "agent-info",
    "agent-draft",
    "legacy-runtime",
    "none",
]

_ENV_REFERENCE_RE = re.compile(r"^\$\{([A-Za-z_][A-Za-z0-9_]*)\}$")
_ENV_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PUBLIC_RUNTIME_ENV_KEYS = frozenset(
    {
        "MODEL_AGENT_NAME",
        "MODEL_NAME",
        "MODEL_AGENT_PROVIDER",
        "MODEL_AGENT_API_BASE",
        "MODEL_AGENT_API_KEY_ID",
        "MODEL_AGENT_API_KEY_NAME",
        # AgentKit code sandbox identifiers are resource metadata, not
        # credentials. The update editor must restore them so a published
        # Code Execution tool can be validated and released again.
        "AGENTKIT_TOOL_ID",
        "AGENTKIT_TOOL_REGION",
        "FEISHU_APP_ID",
        "FEISHU_APP_SECRET",
    }
)
_URL_RUNTIME_ENV_KEYS = frozenset({"MODEL_AGENT_API_BASE"})
_AGENT_TYPES = frozenset({"llm", "sequential", "parallel", "loop", "a2a"})
_SEARCH_SOURCES = frozenset({"knowledge", "memory", "web"})
_COMPONENT_FIELDS = ("kind", "name", "description", "backend", "source")
_MAX_INTROSPECTION_ITEMS = 256
_MAX_AGENT_GRAPH_DEPTH = 16

logger = logging.getLogger(__name__)


class _UnsafeEditableSnapshot(ValueError):
    """The snapshot cannot be made editable without losing authentication."""


@dataclass(frozen=True)
class RuntimeEnvironmentView:
    """Browser-safe environment metadata for one Runtime."""

    public_envs: tuple[dict[str, str], ...]
    configured_env_keys: tuple[str, ...]

    def as_payload(self) -> dict[str, object]:
        return {
            "envs": list(self.public_envs),
            "configuredEnvKeys": list(self.configured_env_keys),
        }


@dataclass(frozen=True)
class RuntimeUpdateRecovery:
    """Classified, sanitized update state returned by the Studio BFF."""

    can_update: bool
    status: RecoveryStatus
    edit_mode: EditMode
    source: RecoverySource
    reason: str
    reason_code: str
    warnings: tuple[str, ...]
    etag: str
    agent: dict[str, Any]

    def as_payload(self) -> dict[str, object]:
        return {
            "canUpdate": self.can_update,
            "recoveryStatus": self.status,
            "editMode": self.edit_mode,
            "recoverySource": self.source,
            "reason": self.reason,
            "reasonCode": self.reason_code,
            "warnings": list(self.warnings),
            "etag": self.etag,
            "agent": copy.deepcopy(self.agent),
        }


def _safe_public_environment_value(key: str, value: str) -> bool:
    if not value or "\r" in value or "\n" in value or len(value) > 8192:
        return False
    if key not in _URL_RUNTIME_ENV_KEYS:
        return True
    parsed = urlsplit(value)
    return bool(
        parsed.scheme in {"http", "https"}
        and parsed.netloc
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def sanitize_runtime_environment(
    envs: Iterable[tuple[str, str]],
) -> RuntimeEnvironmentView:
    """Return explicitly editable values and opaque configured-key state.

    Runtime environment variables are not public merely because their names do
    not contain ``SECRET`` or ``TOKEN``.  In particular, ``MCP_SERVERS_JSON``
    can embed arbitrary authentication headers.  The allowlist is intentionally
    limited to fields that the update UI must restore. Feishu credentials are
    editable deployment inputs, so both the App ID and App Secret are restored
    from the selected Runtime.
    """

    public_envs: list[dict[str, str]] = []
    configured_keys: list[str] = []
    seen_public: set[str] = set()
    seen_configured: set[str] = set()
    for raw_key, raw_value in envs:
        key = str(raw_key or "").strip()
        value = str(raw_value or "")
        if not key:
            continue
        if key in _PUBLIC_RUNTIME_ENV_KEYS and _safe_public_environment_value(
            key, value
        ):
            if key not in seen_public:
                public_envs.append({"key": key, "value": value})
                seen_public.add(key)
            continue
        if value and key not in seen_configured:
            configured_keys.append(key)
            seen_configured.add(key)
    return RuntimeEnvironmentView(
        public_envs=tuple(public_envs),
        configured_env_keys=tuple(configured_keys),
    )


def _sanitize_mcp_tool(tool: dict[str, Any]) -> None:
    raw_token = str(tool.get("authToken") or "").strip()
    explicit_env = str(tool.get("authTokenEnv") or "").strip()
    if explicit_env and _ENV_NAME_RE.fullmatch(explicit_env) is None:
        raise _UnsafeEditableSnapshot("MCP authentication reference is invalid")
    if raw_token:
        reference = _ENV_REFERENCE_RE.fullmatch(raw_token)
        if reference is None:
            raise _UnsafeEditableSnapshot("MCP authentication is not reference based")
        if explicit_env and explicit_env != reference.group(1):
            raise _UnsafeEditableSnapshot("MCP authentication references conflict")
        tool["authTokenEnv"] = reference.group(1)
    tool.pop("authToken", None)


def _bounded_draft_items(value: Any, *, field: str) -> list[Any] | None:
    if not isinstance(value, list):
        return None
    if len(value) > _MAX_INTROSPECTION_ITEMS:
        raise _UnsafeEditableSnapshot(f"editable draft {field} is too large")
    return value


def _sanitize_draft_node(node: dict[str, Any], *, depth: int = 0) -> None:
    if depth > _MAX_AGENT_GRAPH_DEPTH:
        raise _UnsafeEditableSnapshot("editable draft graph is too deep")

    tools = node.get("mcpTools")
    if (tools := _bounded_draft_items(tools, field="mcpTools")) is not None:
        for tool in tools:
            if isinstance(tool, dict):
                _sanitize_mcp_tool(tool)

    deployment = node.get("deployment")
    if isinstance(deployment, dict):
        raw_env_values = deployment.get("envValues")
        if isinstance(raw_env_values, Mapping):
            deployment["envValues"] = {
                str(key): str(value)
                for key, value in raw_env_values.items()
                if str(key) in _PUBLIC_RUNTIME_ENV_KEYS
                and _safe_public_environment_value(str(key), str(value))
            }

    sub_agents = node.get("subAgents")
    if (sub_agents := _bounded_draft_items(sub_agents, field="subAgents")) is not None:
        for child in sub_agents:
            if isinstance(child, dict):
                _sanitize_draft_node(child, depth=depth + 1)

    workflow = node.get("workflow")
    if (
        isinstance(workflow, dict)
        and (
            workflow_nodes := _bounded_draft_items(
                workflow.get("nodes"), field="workflow.nodes"
            )
        )
        is not None
    ):
        safe_nodes: list[dict[str, Any]] = []
        for workflow_node in workflow_nodes:
            if not isinstance(workflow_node, dict):
                continue
            child = workflow_node.get("agent")
            if not isinstance(child, dict):
                continue
            _sanitize_draft_node(child, depth=depth + 1)
            safe_nodes.append(
                {
                    "id": str(workflow_node.get("id") or ""),
                    "agent": child,
                }
            )
        safe_edges = []
        if (
            workflow_edges := _bounded_draft_items(
                workflow.get("edges"), field="workflow.edges"
            )
        ) is not None:
            safe_edges = [
                {
                    "from": str(edge.get("from") or ""),
                    "to": str(edge.get("to") or ""),
                }
                for edge in workflow_edges
                if isinstance(edge, Mapping)
            ]
        node["workflow"] = {
            "type": str(workflow.get("type") or ""),
            "nodes": safe_nodes,
            "edges": safe_edges,
        }


def mcp_auth_environment_keys(draft: Mapping[str, Any]) -> tuple[str, ...]:
    """Return the validated MCP credential references used by a draft tree.

    These names are safe identifiers, not credential values.  The deployment
    route uses them as a server-side allowlist when a customer explicitly
    removes MCP authentication from an update.
    """

    keys: list[str] = []
    seen: set[str] = set()

    def visit(node: Mapping[str, Any], *, depth: int) -> None:
        if depth > _MAX_AGENT_GRAPH_DEPTH:
            return
        tools = node.get("mcpTools")
        if isinstance(tools, list):
            for tool in tools[:_MAX_INTROSPECTION_ITEMS]:
                if not isinstance(tool, Mapping):
                    continue
                key = str(tool.get("authTokenEnv") or "").strip()
                if key and _ENV_NAME_RE.fullmatch(key) and key not in seen:
                    seen.add(key)
                    keys.append(key)
        children = node.get("subAgents")
        if isinstance(children, list):
            for child in children[:_MAX_INTROSPECTION_ITEMS]:
                if isinstance(child, Mapping):
                    visit(child, depth=depth + 1)
        workflow = node.get("workflow")
        if isinstance(workflow, Mapping):
            workflow_nodes = workflow.get("nodes")
            if isinstance(workflow_nodes, list):
                for workflow_node in workflow_nodes[:_MAX_INTROSPECTION_ITEMS]:
                    if not isinstance(workflow_node, Mapping):
                        continue
                    child = workflow_node.get("agent")
                    if isinstance(child, Mapping):
                        visit(child, depth=depth + 1)

    visit(draft, depth=0)
    return tuple(keys)


def _optional_text(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _safe_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:_MAX_INTROSPECTION_ITEMS] if isinstance(item, str)]


def _safe_skills(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    skills: list[dict[str, str]] = []
    for item in value[:_MAX_INTROSPECTION_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        name = _optional_text(item.get("name"))
        if name is None:
            continue
        skill = {"name": name}
        description = _optional_text(item.get("description"))
        if description is not None:
            skill["description"] = description
        skills.append(skill)
    return skills


def _safe_components(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    components: list[dict[str, str]] = []
    for item in value[:_MAX_INTROSPECTION_ITEMS]:
        if not isinstance(item, Mapping):
            continue
        component = {
            field: text
            for field in _COMPONENT_FIELDS
            if (text := _optional_text(item.get(field))) is not None
        }
        if component.get("kind") and component.get("name"):
            components.append(component)
    return components


def _safe_graph_node(value: Any, *, depth: int = 0) -> dict[str, Any] | None:
    if not isinstance(value, Mapping) or depth > _MAX_AGENT_GRAPH_DEPTH:
        return None
    node: dict[str, Any] = {}
    for field in ("id", "name", "description", "instruction", "model"):
        text = _optional_text(value.get(field))
        if text is not None:
            node[field] = text
    agent_type = _optional_text(value.get("type"))
    if agent_type in _AGENT_TYPES:
        node["type"] = agent_type
    if isinstance(value.get("tools"), list):
        node["tools"] = _safe_string_list(value.get("tools"))
    if isinstance(value.get("skills"), list):
        node["skills"] = _safe_skills(value.get("skills"))
    if isinstance(value.get("components"), list):
        node["components"] = _safe_components(value.get("components"))
    if isinstance(value.get("path"), list):
        node["path"] = _safe_string_list(value.get("path"))
    if isinstance(value.get("mentionable"), bool):
        node["mentionable"] = value["mentionable"]
    children = value.get("children")
    if isinstance(children, list):
        node["children"] = [
            child
            for item in children[:_MAX_INTROSPECTION_ITEMS]
            if (child := _safe_graph_node(item, depth=depth + 1)) is not None
        ]
    return node


def sanitize_runtime_agent_info(agent_info: Mapping[str, Any]) -> dict[str, Any]:
    """Keep only strictly shaped read-only introspection fields for the browser."""

    safe: dict[str, Any] = {}
    for field in ("name", "description", "instruction", "model"):
        text = _optional_text(agent_info.get(field))
        if text is not None:
            safe[field] = text
    agent_type = _optional_text(agent_info.get("type"))
    if agent_type in _AGENT_TYPES:
        safe["type"] = agent_type
    if isinstance(agent_info.get("tools"), list):
        safe["tools"] = _safe_string_list(agent_info.get("tools"))
    if isinstance(agent_info.get("skills"), list):
        safe["skills"] = _safe_skills(agent_info.get("skills"))
    if isinstance(agent_info.get("subAgents"), list):
        safe["subAgents"] = _safe_string_list(agent_info.get("subAgents"))
    if isinstance(agent_info.get("components"), list):
        safe["components"] = _safe_components(agent_info.get("components"))
    if isinstance(agent_info.get("searchSources"), list):
        search_sources = _safe_string_list(agent_info.get("searchSources"))
        safe["searchSources"] = [
            source for source in search_sources if source in _SEARCH_SOURCES
        ]
    graph = _safe_graph_node(agent_info.get("graph"))
    if graph is not None:
        safe["graph"] = graph
    return safe


def _validated_sanitized_draft(raw_draft: Any) -> dict[str, Any]:
    if not isinstance(raw_draft, Mapping):
        raise ValueError("editable draft must be an object")
    candidate = copy.deepcopy(dict(raw_draft))
    _sanitize_draft_node(candidate)
    return AgentDraft.model_validate(candidate).model_dump(mode="json", by_alias=True)


def _safe_validation_issues(error: ValidationError) -> tuple[dict[str, str], ...]:
    """Return diagnostic field paths and codes without values or error context."""

    issues: list[dict[str, str]] = []
    for item in error.errors(
        include_url=False, include_context=False, include_input=False
    ):
        path = ".".join(str(part)[:80] for part in item.get("loc", ()))[:320]
        issue_type = str(item.get("type") or "validation_error")[:96]
        if path:
            issues.append({"path": path, "type": issue_type})
        if len(issues) >= 32:
            break
    return tuple(issues)


def _draft_etag(
    *,
    runtime_id: str,
    current_version: int | None,
    agent_name: str,
    draft: Mapping[str, Any],
) -> str:
    canonical = json.dumps(
        {
            "runtimeId": runtime_id,
            "currentVersion": current_version,
            "agentName": agent_name,
            "draft": draft,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def assess_legacy_recovered_agent(
    *,
    agent_info: Mapping[str, Any],
    recovered_draft: Mapping[str, Any],
    source_identity: str,
    source_image: str,
    runtime_id: str,
    current_version: int | None,
) -> RuntimeUpdateRecovery:
    """Validate a server-recovered legacy snapshot for source-preserving edits.

    ``source_identity`` is the digest-pinned deployed image identity.  Folding it
    into the optimistic-lock input prevents a mutable tag or rebuilt image from
    being mistaken for the snapshot that the user reviewed.
    """

    safe_agent = sanitize_runtime_agent_info(agent_info)
    if (
        not source_identity.startswith("sha256:")
        or len(source_identity) != 71
        or not source_image.endswith("@" + source_identity)
    ):
        return RuntimeUpdateRecovery(
            can_update=False,
            status="missing-source",
            edit_mode="blocked",
            source="none",
            reason="当前 Runtime 镜像无法固定到不可变版本，暂时不能安全更新。",
            reason_code="runtime_legacy_image_unpinned",
            warnings=("未生成更新草稿，线上版本不会被覆盖。",),
            etag="",
            agent=safe_agent,
        )
    try:
        draft = _validated_sanitized_draft(recovered_draft)
    except ValidationError as error:
        logger.info(
            "legacy Runtime draft validation rejected issues=%s",
            _safe_validation_issues(error),
        )
        return RuntimeUpdateRecovery(
            can_update=False,
            status="incompatible",
            edit_mode="blocked",
            source="legacy-runtime",
            reason="从运行版本恢复的配置不完整或不安全，暂时不能更新。",
            reason_code="runtime_legacy_snapshot_incompatible",
            warnings=("未加载不完整配置，线上版本不会被覆盖。",),
            etag="",
            agent=safe_agent,
        )
    except (RecursionError, TypeError, ValueError):
        return RuntimeUpdateRecovery(
            can_update=False,
            status="incompatible",
            edit_mode="blocked",
            source="legacy-runtime",
            reason="从运行版本恢复的配置不完整或不安全，暂时不能更新。",
            reason_code="runtime_legacy_snapshot_incompatible",
            warnings=("未加载不完整配置，线上版本不会被覆盖。",),
            etag="",
            agent=safe_agent,
        )
    safe_agent["draft"] = draft
    safe_agent["sourceImage"] = source_image
    selected_skills = draft.get("selectedSkills")
    has_runtime_skills = bool(
        isinstance(selected_skills, list)
        and any(
            isinstance(item, Mapping) and item.get("source") == "runtime"
            for item in selected_skills
        )
    )
    warnings = ["更新将保留当前应用镜像，仅叠加已确认的 Skill 与 MCP 变更。"]
    if has_runtime_skills:
        warnings.append(
            "运行中的 Skill 默认原样保留；只有移除或选择同名 Skill 时才会变更。"
        )
    return RuntimeUpdateRecovery(
        can_update=True,
        status="complete",
        edit_mode="source-preserving",
        source="legacy-runtime",
        reason="",
        reason_code="",
        warnings=tuple(warnings),
        etag=_draft_etag(
            runtime_id=runtime_id,
            current_version=current_version,
            agent_name=str(safe_agent.get("name") or ""),
            draft={"sourceIdentity": source_identity, "draft": draft},
        ),
        agent=safe_agent,
    )


def assess_runtime_update_agent(
    *,
    agent_info: Mapping[str, Any],
    fallback_draft: Any,
    fallback_available: bool,
    runtime_id: str,
    current_version: int | None,
) -> RuntimeUpdateRecovery:
    """Classify whether cloud metadata is sufficient for a safe update."""

    safe_agent = sanitize_runtime_agent_info(agent_info)
    raw_draft = agent_info.get("draft")
    source: RecoverySource = "agent-info"
    if raw_draft is None and fallback_available:
        raw_draft = fallback_draft
        source = "agent-draft"

    if raw_draft is None and fallback_available:
        return RuntimeUpdateRecovery(
            can_update=False,
            status="incompatible",
            edit_mode="blocked",
            source=source,
            reason=(
                "该 Runtime 的原发布配置返回格式不兼容，暂时无法在 Studio 中安全更新。"
            ),
            reason_code="runtime_editable_snapshot_incompatible",
            warnings=("未加载不完整配置，线上版本不会被覆盖。",),
            etag="",
            agent=safe_agent,
        )

    if raw_draft is None:
        return RuntimeUpdateRecovery(
            can_update=False,
            status="introspection-only",
            edit_mode="blocked",
            source="none",
            reason=(
                "已检测到运行中的智能体，但原发布配置不可恢复，"
                "且当前运行镜像或 AgentKit 配置不足以完成安全恢复。"
            ),
            reason_code="runtime_editable_snapshot_missing",
            warnings=(
                "运行态名称不能还原 MCP 认证、Skill 文件或自定义源码，已阻止空配置覆盖。",
            ),
            etag="",
            agent=safe_agent,
        )

    try:
        draft = _validated_sanitized_draft(raw_draft)
    except (RecursionError, TypeError, ValueError):
        return RuntimeUpdateRecovery(
            can_update=False,
            status="incompatible",
            edit_mode="blocked",
            source=source,
            reason=(
                "该 Runtime 的原发布配置不兼容或包含无法安全继承的认证信息，"
                "暂时无法在 Studio 中安全更新。"
            ),
            reason_code="runtime_editable_snapshot_incompatible",
            warnings=("为避免泄漏密钥或覆盖线上配置，Studio 未加载该快照。",),
            etag="",
            agent=safe_agent,
        )

    safe_agent["draft"] = draft
    return RuntimeUpdateRecovery(
        can_update=True,
        status="draft-only",
        edit_mode="regenerate",
        source=source,
        reason="",
        reason_code="",
        warnings=("更新将依据已验证的 Studio 发布快照重新生成标准项目。",),
        etag=_draft_etag(
            runtime_id=runtime_id,
            current_version=current_version,
            agent_name=str(safe_agent.get("name") or ""),
            draft=draft,
        ),
        agent=safe_agent,
    )
