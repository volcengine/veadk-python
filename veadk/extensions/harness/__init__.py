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

"""Composable Agent Harness SDK."""

from typing import TYPE_CHECKING, Any

from veadk.extensions.harness.plugins import HarnessLongRunControlPlugin
from veadk.extensions.harness.extension import HarnessExtension, HarnessExtensionConfig
from veadk.extensions.harness.modules.invocation_context import (
    ContextEngine,
    HarnessInvocationContextBuilder,
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    ResultVerifier,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    HeadroomCompressionProvider,
    ToolResultCompactor,
    ToolResultCompressor,
)
from veadk.extensions.harness.schemas import (
    CapabilityReceipt,
    ToolReceipt,
    CompactionReport,
    CompressionReport,
    CompressionRequest,
    CompactionResult,
    CompressionResult,
    ContextBundle,
    InvocationContextBlock,
    ConversationMessage,
    EvidenceRef,
    HarnessEvent,
    HarnessIntervention,
    VerificationDecision,
    HarnessRunContext,
    HarnessInvocationRef,
    TaskContract,
    VerificationReport,
)
from veadk.extensions.harness.sidecar import HarnessSidecarDependencyError

if TYPE_CHECKING:
    from veadk.extensions.harness.sidecar_runtime import (
        HarnessSelectionIntent,
        HarnessSidecarConfig,
        HarnessSidecarError,
        HarnessSidecarRuntimeUnavailable,
        MCPGatewayConfig,
        ModelProxyConfig,
        ResolvedHarnessPlan,
        SidecarBinding,
        SidecarBindingSpec,
        deploy_harness,
        doctor_harness_sidecar,
        export_sidecar_env,
        get_harness_sidecar_catalog,
        resolve_harness_sidecar_selection,
        resolve_sidecar_config,
        run_with_harness_sidecar,
        start_harness_sidecar,
    )


_SIDECAR_RUNTIME_EXPORTS = {
    "HarnessSelectionIntent",
    "HarnessSidecarConfig",
    "HarnessSidecarError",
    "HarnessSidecarRuntimeUnavailable",
    "MCPGatewayConfig",
    "ModelProxyConfig",
    "ResolvedHarnessPlan",
    "SidecarBinding",
    "SidecarBindingSpec",
    "deploy_harness",
    "doctor_harness_sidecar",
    "export_sidecar_env",
    "get_harness_sidecar_catalog",
    "resolve_harness_sidecar_selection",
    "resolve_sidecar_config",
    "run_with_harness_sidecar",
    "start_harness_sidecar",
}


def __getattr__(name: str) -> Any:
    if name in _SIDECAR_RUNTIME_EXPORTS:
        from importlib import import_module

        sidecar_runtime = import_module("veadk.extensions.harness.sidecar_runtime")
        value = getattr(sidecar_runtime, name)
        globals()[name] = value
        return value
    raise AttributeError(f"module 'veadk.extensions.harness' has no attribute {name!r}")


__all__ = [
    "CapabilityReceipt",
    "ToolReceipt",
    "CompactionReport",
    "CompressionReport",
    "CompressionRequest",
    "CompactionResult",
    "CompressionResult",
    "ContextBundle",
    "InvocationContextBlock",
    "ContextEngine",
    "ConversationMessage",
    "EvidenceRef",
    "HeadroomCompressionProvider",
    "HarnessIntervention",
    "VerificationDecision",
    "HarnessEvent",
    "HarnessExtension",
    "HarnessExtensionConfig",
    "HarnessInvocationContextBuilder",
    "HarnessInvocationContextConfig",
    "HarnessRunContext",
    "HarnessInvocationRef",
    "HarnessLongRunControlPlugin",
    "HarnessSidecarDependencyError",
    "HarnessSelectionIntent",
    "HarnessSidecarConfig",
    "HarnessSidecarError",
    "HarnessSidecarRuntimeUnavailable",
    "MCPGatewayConfig",
    "ModelProxyConfig",
    "ResolvedHarnessPlan",
    "SidecarBinding",
    "SidecarBindingSpec",
    "FinalResponseVerifier",
    "ResultVerifier",
    "TaskContract",
    "ToolResultCompactor",
    "ToolResultCompressor",
    "VerificationReport",
    "deploy_harness",
    "doctor_harness_sidecar",
    "export_sidecar_env",
    "get_harness_sidecar_catalog",
    "resolve_harness_sidecar_selection",
    "resolve_sidecar_config",
    "run_with_harness_sidecar",
    "start_harness_sidecar",
]
