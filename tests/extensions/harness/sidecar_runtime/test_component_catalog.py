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

from __future__ import annotations

import json

from veadk.extensions.harness.sidecar_runtime import (
    CATALOG_VERSION,
    PRODUCT_COMPONENT_ORDER,
    ComponentAvailability,
    get_harness_sidecar_catalog,
    resolve_harness_sidecar_selection,
)


def test_catalog_exposes_nine_product_components_and_two_profiles() -> None:
    catalog = get_harness_sidecar_catalog(profile="ops")

    assert catalog.catalog_version == CATALOG_VERSION
    assert catalog.profile_count == 2
    assert catalog.total_component_count == 9
    assert catalog.selectable_component_count == 6
    assert catalog.selected_profile.profile_component_count == 6
    assert catalog.selected_profile.default_components == list(
        PRODUCT_COMPONENT_ORDER[:6]
    )
    assert [component.id for component in catalog.components] == list(
        PRODUCT_COMPONENT_ORDER
    )


def test_catalog_hides_internal_runtime_module_names() -> None:
    payload = get_harness_sidecar_catalog(profile="ops").model_dump_json()

    for internal_name in (
        "harness_core",
        "runtime_core",
        "goal_runtime",
        "model_proxy",
        "mcp_gateway",
        "browser_runtime",
    ):
        assert internal_name not in payload


def test_preview_components_are_visible_with_unavailable_reasons() -> None:
    catalog = get_harness_sidecar_catalog(profile="default")
    components = {component.id: component for component in catalog.components}

    for component_id in ("browser", "evaluation", "shadow"):
        availability = components[component_id].availability
        assert availability.available is False
        assert availability.status == "preview"
        assert availability.reason


def test_catalog_dependencies_exist_and_are_acyclic() -> None:
    catalog = get_harness_sidecar_catalog(profile="ops")
    dependencies = {
        component.id: component.dependencies for component in catalog.components
    }

    def visit(component_id: str, path: tuple[str, ...] = ()) -> None:
        assert component_id not in path
        for dependency in dependencies[component_id]:
            assert dependency in dependencies
            visit(dependency, (*path, component_id))

    for component_id in dependencies:
        visit(component_id)


def test_catalog_accepts_control_plane_availability_overrides() -> None:
    catalog = get_harness_sidecar_catalog(
        profile="default",
        availability_overrides={
            "browser": ComponentAvailability(
                available=True,
                status="ga",
                min_runtime_version="0.2.0",
                regions=["cn-beijing"],
            )
        },
    )

    browser = next(item for item in catalog.components if item.id == "browser")
    assert browser.availability.available is True
    assert browser.availability.reason is None
    assert browser.availability.min_runtime_version == "0.2.0"
    assert catalog.selectable_component_count == 7


def test_default_and_ops_resolve_exact_product_defaults() -> None:
    default = resolve_harness_sidecar_selection(profile="default")
    ops = resolve_harness_sidecar_selection(profile="ops")

    assert default.valid is True
    assert default.effective_components == list(PRODUCT_COMPONENT_ORDER[:4])
    assert default.effective_component_count == 4
    assert ops.valid is True
    assert ops.effective_components == list(PRODUCT_COMPONENT_ORDER[:6])
    assert ops.effective_component_count == 6
    assert ops.activation_targets.mcp_gateway.presets == ["sql_readonly"]
    assert ops.activation_targets.mcp_gateway.readonly_segments == ["*"]


def test_resolver_applies_overrides_and_product_dependencies() -> None:
    plan = resolve_harness_sidecar_selection(
        profile="default",
        component_overrides={"sql_readonly": True, "verifier": False},
    )

    assert plan.valid is True
    assert plan.requested_components == [
        "context_engine",
        "compressor",
        "long_run_control",
        "sql_readonly",
    ]
    assert plan.effective_components == [
        "context_engine",
        "compressor",
        "long_run_control",
        "mcp_resilience",
        "sql_readonly",
    ]
    assert [item.model_dump() for item in plan.auto_added_components] == [
        {"id": "mcp_resilience", "required_by": ["sql_readonly"]}
    ]


def test_disabled_selection_resolves_to_zero_components() -> None:
    plan = resolve_harness_sidecar_selection(
        enabled=False,
        profile="ops",
        component_overrides={"browser": True},
    )

    assert plan.valid is True
    assert plan.requested_components == []
    assert plan.effective_components == []
    assert plan.effective_component_count == 0
    assert plan.activation_targets.runtime_components == []


def test_unavailable_dependency_chain_returns_actionable_errors() -> None:
    plan = resolve_harness_sidecar_selection(
        profile="default",
        component_overrides={"shadow": True},
    )

    assert plan.valid is False
    assert plan.effective_components[-3:] == ["browser", "evaluation", "shadow"]
    assert {item.id for item in plan.auto_added_components} == {
        "browser",
        "evaluation",
    }
    assert len(plan.errors) == 3
    assert all("unavailable" in error for error in plan.errors)


def test_plan_hash_is_stable_across_mapping_order_and_json_round_trip() -> None:
    first = resolve_harness_sidecar_selection(
        profile="ops",
        component_overrides={"verifier": False, "sql_readonly": True},
        runtime_version="0.1.0",
    )
    second = resolve_harness_sidecar_selection(
        profile="ops",
        component_overrides={"sql_readonly": True, "verifier": False},
        runtime_version="0.1.0",
    )

    assert first.plan_hash == second.plan_hash
    assert first.plan_hash.startswith("sha256:")
    assert json.loads(first.model_dump_json()) == json.loads(second.model_dump_json())


def test_unknown_component_and_catalog_version_return_invalid_plan() -> None:
    plan = resolve_harness_sidecar_selection(
        profile="ops",
        component_overrides={"not_a_component": True},
        catalog_version="old",
    )

    assert plan.valid is False
    assert any("not_a_component" in error for error in plan.errors)
    assert any("Catalog version" in error for error in plan.errors)
