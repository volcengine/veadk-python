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

"""Deterministic Harness Sidecar Product Component selection resolver."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .component_catalog import (
    CATALOG_VERSION,
    PRODUCT_COMPONENT_ORDER,
    ComponentAvailability,
    get_harness_sidecar_catalog,
)
from .profiles import PROFILE_DEFAULTS
from .runtime_components import resolve_runtime_components


PLAN_SCHEMA_VERSION = "agentkit.harness-sidecar.plan/v1"
_MODEL_COMPONENTS = (
    "context_engine",
    "compressor",
    "verifier",
    "long_run_control",
)
_VEADK_PLUGIN_TARGETS = {
    "context_engine": "invocation_context",
    "compressor": "compactor",
    "verifier": "response_verification",
    "long_run_control": "long_run_control",
}
_OPTIONAL_RUNTIME_TARGETS = {
    "long_run_control": "goal_runtime",
    "browser": "browser_runtime",
    "evaluation": "eval_runtime",
    "shadow": "shadow_runtime",
}


class SelectionModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class HarnessSelectionIntent(SelectionModel):
    enabled: bool = True
    profile: str = "ops"
    component_overrides: dict[str, bool] = Field(default_factory=dict)
    catalog_version: str | None = None
    runtime_version: str | None = None


class AutoAddedComponent(SelectionModel):
    id: str
    required_by: list[str]


class ModelProxyActivation(SelectionModel):
    enabled: bool
    components: list[str] = Field(default_factory=list)


class MCPGatewayActivation(SelectionModel):
    enabled: bool
    presets: list[str] = Field(default_factory=list)
    readonly_segments: list[str] = Field(default_factory=list)


class HarnessActivationTargets(SelectionModel):
    veadk_plugins: list[str] = Field(default_factory=list)
    model_proxy: ModelProxyActivation
    mcp_gateway: MCPGatewayActivation
    runtime_components: list[str] = Field(default_factory=list)


class ResolvedHarnessPlan(SelectionModel):
    schema_version: str = PLAN_SCHEMA_VERSION
    valid: bool
    enabled: bool
    profile: str
    requested_components: list[str] = Field(default_factory=list)
    effective_components: list[str] = Field(default_factory=list)
    auto_added_components: list[AutoAddedComponent] = Field(default_factory=list)
    profile_component_count: int
    total_component_count: int
    selectable_component_count: int
    effective_component_count: int
    activation_targets: HarnessActivationTargets
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    catalog_version: str = CATALOG_VERSION
    runtime_version: str | None = None
    plan_hash: str


def resolve_harness_sidecar_selection(
    *,
    enabled: bool = True,
    profile: str = "ops",
    component_overrides: Mapping[str, bool] | None = None,
    catalog_version: str | None = None,
    runtime_version: str | None = None,
    availability_overrides: Mapping[str, ComponentAvailability | Mapping[str, Any]]
    | None = None,
) -> ResolvedHarnessPlan:
    """Resolve a profile and explicit overrides into an immutable plan snapshot."""

    errors: list[str] = []
    warnings: list[str] = []
    overrides = dict(component_overrides or {})
    unknown_components = sorted(set(overrides) - set(PRODUCT_COMPONENT_ORDER))
    if unknown_components:
        errors.append(
            "Unknown Harness Product Component override: "
            + ", ".join(unknown_components)
        )
    invalid_values = sorted(
        component_id
        for component_id, value in overrides.items()
        if not isinstance(value, bool)
    )
    if invalid_values:
        errors.append(
            "Harness Product Component overrides must be boolean: "
            + ", ".join(invalid_values)
        )
    if catalog_version is not None and catalog_version != CATALOG_VERSION:
        errors.append(
            f"Unsupported Harness Catalog version '{catalog_version}'; "
            f"expected '{CATALOG_VERSION}'"
        )

    if profile in PROFILE_DEFAULTS:
        catalog = get_harness_sidecar_catalog(
            profile, availability_overrides=availability_overrides
        )
        profile_defaults = set(catalog.selected_profile.default_components)
        profile_component_count = catalog.selected_profile.profile_component_count
    else:
        errors.append(
            f"Unknown Harness Sidecar profile '{profile}'. "
            f"Known profiles: {', '.join(sorted(PROFILE_DEFAULTS))}"
        )
        catalog = get_harness_sidecar_catalog(
            "default", availability_overrides=availability_overrides
        )
        profile_defaults = set()
        profile_component_count = 0

    requested: set[str] = set()
    if enabled:
        requested.update(profile_defaults)
        for component_id, selected in overrides.items():
            if component_id not in PRODUCT_COMPONENT_ORDER or not isinstance(
                selected, bool
            ):
                continue
            if selected:
                requested.add(component_id)
            else:
                requested.discard(component_id)

    effective = set(requested)
    required_by: dict[str, set[str]] = {}
    definitions = {component.id: component for component in catalog.components}

    def include_dependencies(component_id: str) -> None:
        for dependency in definitions[component_id].dependencies:
            required_by.setdefault(dependency, set()).add(component_id)
            if dependency not in effective:
                effective.add(dependency)
                include_dependencies(dependency)

    for component_id in _ordered(requested):
        include_dependencies(component_id)

    if enabled and not effective:
        errors.append("Enabled Harness Sidecar must resolve at least one component")

    for component_id in _ordered(effective):
        availability = definitions[component_id].availability
        if not availability.available:
            detail = f": {availability.reason}" if availability.reason else ""
            errors.append(
                f"Harness Product Component '{component_id}' is unavailable{detail}"
            )

    if enabled and profile == "ops" and overrides.get("sql_readonly") is False:
        warnings.append("SQL readonly protection is disabled for the ops profile")

    requested_ordered = _ordered(requested)
    effective_ordered = _ordered(effective)
    auto_added = [
        AutoAddedComponent(
            id=component_id,
            required_by=_ordered(required_by.get(component_id, set())),
        )
        for component_id in effective_ordered
        if component_id not in requested
    ]
    activation_targets = _activation_targets(enabled, profile, effective_ordered)
    plan_values: dict[str, Any] = {
        "valid": not errors,
        "enabled": enabled,
        "profile": profile,
        "requested_components": requested_ordered,
        "effective_components": effective_ordered,
        "auto_added_components": auto_added,
        "profile_component_count": profile_component_count,
        "total_component_count": catalog.total_component_count,
        "selectable_component_count": catalog.selectable_component_count,
        "effective_component_count": len(effective_ordered),
        "activation_targets": activation_targets,
        "warnings": warnings,
        "errors": errors,
        "catalog_version": CATALOG_VERSION,
        "runtime_version": runtime_version,
    }
    plan_values["plan_hash"] = _plan_hash(plan_values)
    return ResolvedHarnessPlan.model_validate(plan_values)


def _activation_targets(
    enabled: bool, profile: str, effective_components: list[str]
) -> HarnessActivationTargets:
    selected = set(effective_components) if enabled else set()
    model_components = [item for item in _MODEL_COMPONENTS if item in selected]
    mcp_enabled = bool({"mcp_resilience", "sql_readonly"} & selected)
    optional_runtime = (["ops"] if profile == "ops" and selected else []) + [
        runtime_component
        for product_component, runtime_component in _OPTIONAL_RUNTIME_TARGETS.items()
        if product_component in selected
    ]
    runtime_components = (
        resolve_runtime_components(
            model_proxy_enabled=bool(model_components),
            mcp_gateway_enabled=mcp_enabled,
            components=optional_runtime,
        )
        if selected
        else []
    )
    return HarnessActivationTargets(
        veadk_plugins=[
            _VEADK_PLUGIN_TARGETS[item]
            for item in _MODEL_COMPONENTS
            if item in selected
        ],
        model_proxy=ModelProxyActivation(
            enabled=bool(model_components), components=model_components
        ),
        mcp_gateway=MCPGatewayActivation(
            enabled=mcp_enabled,
            presets=["sql_readonly"] if "sql_readonly" in selected else [],
            readonly_segments=["*"] if "sql_readonly" in selected else [],
        ),
        runtime_components=runtime_components,
    )


def _ordered(values: set[str]) -> list[str]:
    return [item for item in PRODUCT_COMPONENT_ORDER if item in values]


def _plan_hash(values: Mapping[str, Any]) -> str:
    payload = json.dumps(
        dict(values),
        default=_json_default,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


__all__ = [
    "PLAN_SCHEMA_VERSION",
    "AutoAddedComponent",
    "HarnessActivationTargets",
    "HarnessSelectionIntent",
    "MCPGatewayActivation",
    "ModelProxyActivation",
    "ResolvedHarnessPlan",
    "resolve_harness_sidecar_selection",
]
