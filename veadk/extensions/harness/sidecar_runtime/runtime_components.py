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

"""Resolve public Sidecar settings to private Runtime module requirements."""

from __future__ import annotations

from collections.abc import Iterable

# Internal artifact inventory. Product Catalog responses must never expose these
# module names as customer-selectable components.
RUNTIME_COMPONENT_ORDER = (
    "harness_core",
    "ops",
    "goal_runtime",
    "model_proxy",
    "mcp_gateway",
    "browser_runtime",
    "eval_runtime",
    "shadow_runtime",
)
RUNTIME_COMPONENT_DEPENDENCIES = {
    "harness_core": (),
    "ops": ("harness_core",),
    "goal_runtime": ("harness_core",),
    "model_proxy": ("harness_core",),
    "mcp_gateway": ("harness_core",),
    "browser_runtime": ("harness_core",),
    "eval_runtime": ("harness_core",),
    "shadow_runtime": ("harness_core",),
}
RUNTIME_COMPONENT_ALIASES = {
    "core": "harness_core",
    "harness": "harness_core",
    "harness_core": "harness_core",
    "runtime": "harness_core",
    "runtime_core": "harness_core",
    "model": "model_proxy",
    "model_proxy": "model_proxy",
    "mcp": "mcp_gateway",
    "mcp_gateway": "mcp_gateway",
    "ops": "ops",
    "ops_kernel": "ops",
    "goal": "goal_runtime",
    "goal_loop": "goal_runtime",
    "goal_runtime": "goal_runtime",
    "browser": "browser_runtime",
    "browser_runtime": "browser_runtime",
    "eval": "eval_runtime",
    "evaluation": "eval_runtime",
    "eval_runtime": "eval_runtime",
    "shadow": "shadow_runtime",
    "shadow_runtime": "shadow_runtime",
}
RUNTIME_FLAVOR = "harness-sidecar"
RUNTIME_FLAVOR_CORE = RUNTIME_FLAVOR
RUNTIME_FLAVOR_OPS = RUNTIME_FLAVOR
RUNTIME_FLAVOR_FULL = RUNTIME_FLAVOR
RUNTIME_FLAVOR_CUSTOM = RUNTIME_FLAVOR


def normalize_runtime_component(value: str) -> str:
    name = value.strip().lower().replace("-", "_")
    try:
        return RUNTIME_COMPONENT_ALIASES[name]
    except KeyError as error:
        known = ", ".join(RUNTIME_COMPONENT_ORDER)
        raise ValueError(
            f"Unknown Harness Runtime component '{value}'. Known components: {known}"
        ) from error


def resolve_runtime_components(
    *,
    model_proxy_enabled: bool,
    mcp_gateway_enabled: bool,
    components: Iterable[str] = (),
) -> list[str]:
    requested = ["harness_core"]
    if model_proxy_enabled:
        requested.append("model_proxy")
    if mcp_gateway_enabled:
        requested.append("mcp_gateway")
    requested.extend(normalize_runtime_component(item) for item in components)
    selected: set[str] = set()

    def include(component: str) -> None:
        if component in selected:
            return
        for dependency in RUNTIME_COMPONENT_DEPENDENCIES[component]:
            include(dependency)
        selected.add(component)

    for component in requested:
        include(component)
    return [component for component in RUNTIME_COMPONENT_ORDER if component in selected]


def runtime_flavor_for_components(components: Iterable[str]) -> str:
    return RUNTIME_FLAVOR


__all__ = [
    "RUNTIME_COMPONENT_DEPENDENCIES",
    "RUNTIME_COMPONENT_ORDER",
    "RUNTIME_FLAVOR",
    "RUNTIME_FLAVOR_CORE",
    "RUNTIME_FLAVOR_CUSTOM",
    "RUNTIME_FLAVOR_FULL",
    "RUNTIME_FLAVOR_OPS",
    "normalize_runtime_component",
    "resolve_runtime_components",
    "runtime_flavor_for_components",
]
