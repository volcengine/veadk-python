# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""VeADK-owned public integration for the managed Harness Sidecar Runtime."""

from .component_catalog import (
    CATALOG_SCHEMA_VERSION,
    CATALOG_VERSION,
    PRODUCT_COMPONENT_ORDER,
    ComponentAvailability,
    HarnessComponentDefinition,
    HarnessProfileDefinition,
    HarnessSidecarCatalog,
    get_harness_sidecar_catalog,
)
from .deploy import build_runtime_network, deploy_harness, to_runtime_env
from .runtime_components import (
    RUNTIME_COMPONENT_ORDER,
    resolve_runtime_components,
    runtime_flavor_for_components,
)
from .selection import (
    PLAN_SCHEMA_VERSION,
    AutoAddedComponent,
    HarnessActivationTargets,
    HarnessSelectionIntent,
    ResolvedHarnessPlan,
    resolve_harness_sidecar_selection,
)
from .sidecar import (
    HarnessSidecarError,
    HarnessSidecarRuntimeUnavailable,
    SidecarBinding,
    doctor_harness_sidecar,
    export_sidecar_env,
    run_with_harness_sidecar,
    start_harness_sidecar,
)
from .sidecar_config import (
    HarnessSidecarConfig,
    MCPGatewayConfig,
    ModelProxyConfig,
    SidecarBindingSpec,
    resolve_sidecar_config,
    sidecar_config_to_env,
)

__all__ = [
    "AutoAddedComponent",
    "CATALOG_SCHEMA_VERSION",
    "CATALOG_VERSION",
    "ComponentAvailability",
    "HarnessActivationTargets",
    "HarnessComponentDefinition",
    "HarnessProfileDefinition",
    "HarnessSelectionIntent",
    "HarnessSidecarCatalog",
    "HarnessSidecarConfig",
    "HarnessSidecarError",
    "HarnessSidecarRuntimeUnavailable",
    "MCPGatewayConfig",
    "ModelProxyConfig",
    "PLAN_SCHEMA_VERSION",
    "PRODUCT_COMPONENT_ORDER",
    "RUNTIME_COMPONENT_ORDER",
    "ResolvedHarnessPlan",
    "SidecarBinding",
    "SidecarBindingSpec",
    "build_runtime_network",
    "deploy_harness",
    "doctor_harness_sidecar",
    "export_sidecar_env",
    "get_harness_sidecar_catalog",
    "resolve_harness_sidecar_selection",
    "resolve_runtime_components",
    "resolve_sidecar_config",
    "run_with_harness_sidecar",
    "runtime_flavor_for_components",
    "sidecar_config_to_env",
    "start_harness_sidecar",
    "to_runtime_env",
]
