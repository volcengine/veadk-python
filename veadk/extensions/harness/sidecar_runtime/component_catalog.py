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

"""Stable Product Component Catalog for Harness Sidecar control planes."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .profiles import PROFILE_DEFAULTS, PROFILE_METADATA, profile_default_components


CATALOG_SCHEMA_VERSION = "agentkit.harness-sidecar.catalog/v1"
CATALOG_VERSION = "2026.07.1"
PRODUCT_COMPONENT_ORDER = (
    "context_engine",
    "compressor",
    "verifier",
    "long_run_control",
    "mcp_resilience",
    "sql_readonly",
    "browser",
    "evaluation",
    "shadow",
)


class CatalogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComponentAvailability(CatalogModel):
    available: bool
    status: str
    reason: str | None = None
    min_runtime_version: str | None = None
    regions: list[str] = Field(default_factory=list)


class HarnessComponentDefinition(CatalogModel):
    id: str
    display_name: str
    description: str
    category: str
    dependencies: list[str] = Field(default_factory=list)
    risk_level: str = "standard"
    status: str
    settings_schema_ref: str | None = None
    selected_by_profile: bool = False
    availability: ComponentAvailability


class HarnessProfileDefinition(CatalogModel):
    id: str
    display_name: str
    description: str
    default_components: list[str]
    profile_component_count: int


class HarnessSidecarCatalog(CatalogModel):
    schema_version: str = CATALOG_SCHEMA_VERSION
    catalog_version: str = CATALOG_VERSION
    profile_count: int
    profiles: list[HarnessProfileDefinition]
    selected_profile: HarnessProfileDefinition
    components: list[HarnessComponentDefinition]
    total_component_count: int
    selectable_component_count: int


_COMPONENT_REGISTRY: dict[str, dict[str, Any]] = {
    "context_engine": {
        "display_name": "上下文治理",
        "description": "治理上下文组装、任务锚定和上下文预算。",
        "category": "model",
    },
    "compressor": {
        "display_name": "上下文与结果压缩",
        "description": "压缩长上下文和大型工具结果，降低 Token 成本。",
        "category": "model",
    },
    "verifier": {
        "display_name": "回答校验与修复",
        "description": "校验证据和回答，在失败时执行修复或告警。",
        "category": "model",
    },
    "long_run_control": {
        "display_name": "长任务控制",
        "description": "管理长任务进度、续跑和结束条件。",
        "category": "model",
    },
    "mcp_resilience": {
        "display_name": "MCP 稳定性治理",
        "description": "治理连接、超时、空结果、大返回、预算和结构化错误。",
        "category": "tool",
    },
    "sql_readonly": {
        "display_name": "SQL 只读保护",
        "description": "拦截写 SQL，并对所选 MCP 路由提供只读保护。",
        "category": "security",
        "dependencies": ["mcp_resilience"],
        "risk_level": "high_when_disabled",
    },
    "browser": {
        "display_name": "浏览器任务增强",
        "description": "增强浏览器动作、结果、grounding 和 trace。",
        "category": "browser",
        "availability": {
            "available": False,
            "status": "preview",
            "reason": "当前 Runtime 尚未提供 Browser Controller",
        },
    },
    "evaluation": {
        "display_name": "在线评测",
        "description": "提供评测采样、指标和回归数据。",
        "category": "quality",
        "dependencies": ["browser"],
        "availability": {
            "available": False,
            "status": "preview",
            "reason": "当前 Runtime 尚未提供 Evaluation Controller",
        },
    },
    "shadow": {
        "display_name": "Shadow 对照运行",
        "description": "执行不影响主链路的影子运行和结果对照。",
        "category": "quality",
        "dependencies": ["evaluation"],
        "availability": {
            "available": False,
            "status": "preview",
            "reason": "当前 Runtime 尚未提供 Shadow Controller",
        },
    },
}


def get_harness_sidecar_catalog(
    profile: str = "ops",
    *,
    availability_overrides: Mapping[str, ComponentAvailability | Mapping[str, Any]]
    | None = None,
) -> HarnessSidecarCatalog:
    """Return a Runtime-independent Product Component Catalog snapshot."""

    selected_ids = set(profile_default_components(profile))
    overrides = dict(availability_overrides or {})
    unknown = sorted(set(overrides) - set(PRODUCT_COMPONENT_ORDER))
    if unknown:
        raise ValueError(
            "Unknown Harness Product Component availability override: "
            + ", ".join(unknown)
        )

    profiles = [_profile_definition(profile_id) for profile_id in PROFILE_DEFAULTS]
    selected_profile = next(item for item in profiles if item.id == profile)
    components = [
        _component_definition(
            component_id,
            selected=component_id in selected_ids,
            availability_override=overrides.get(component_id),
        )
        for component_id in PRODUCT_COMPONENT_ORDER
    ]
    return HarnessSidecarCatalog(
        profile_count=len(profiles),
        profiles=profiles,
        selected_profile=selected_profile,
        components=components,
        total_component_count=len(components),
        selectable_component_count=sum(
            component.availability.available for component in components
        ),
    )


def _profile_definition(profile: str) -> HarnessProfileDefinition:
    components = list(profile_default_components(profile))
    metadata = PROFILE_METADATA[profile]
    return HarnessProfileDefinition(
        id=profile,
        display_name=metadata["display_name"],
        description=metadata["description"],
        default_components=components,
        profile_component_count=len(components),
    )


def _component_definition(
    component_id: str,
    *,
    selected: bool,
    availability_override: ComponentAvailability | Mapping[str, Any] | None,
) -> HarnessComponentDefinition:
    definition = deepcopy(_COMPONENT_REGISTRY[component_id])
    availability_value = definition.pop(
        "availability", {"available": True, "status": "ga"}
    )
    if availability_override is not None:
        override = (
            availability_override.model_dump(exclude_unset=True)
            if isinstance(availability_override, ComponentAvailability)
            else dict(availability_override)
        )
        availability_value.update(override)
        if override.get("available") is True and "reason" not in override:
            availability_value["reason"] = None
    availability = ComponentAvailability.model_validate(availability_value)
    return HarnessComponentDefinition(
        id=component_id,
        dependencies=list(definition.pop("dependencies", [])),
        risk_level=definition.pop("risk_level", "standard"),
        status=availability.status,
        selected_by_profile=selected,
        availability=availability,
        **definition,
    )


__all__ = [
    "CATALOG_SCHEMA_VERSION",
    "CATALOG_VERSION",
    "PRODUCT_COMPONENT_ORDER",
    "ComponentAvailability",
    "HarnessComponentDefinition",
    "HarnessProfileDefinition",
    "HarnessSidecarCatalog",
    "get_harness_sidecar_catalog",
]
