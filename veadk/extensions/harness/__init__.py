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

from veadk.extensions.harness.extension import HarnessExtension, HarnessExtensionConfig
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    ResultVerifier,
)
from veadk.extensions.harness.modules.invocation_context import (
    ContextEngine,
    HarnessInvocationContextBuilder,
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    HeadroomCompressionProvider,
    ToolResultCompactor,
    ToolResultCompressor,
)
from veadk.extensions.harness.plugins import HarnessLongRunControlPlugin
from veadk.extensions.harness.schemas import (
    CapabilityReceipt,
    CompactionReport,
    CompactionResult,
    CompressionReport,
    CompressionRequest,
    CompressionResult,
    ContextBundle,
    ConversationMessage,
    EvidenceRef,
    HarnessEvent,
    HarnessIntervention,
    HarnessInvocationRef,
    HarnessRunContext,
    InvocationContextBlock,
    TaskContract,
    ToolReceipt,
    VerificationDecision,
    VerificationReport,
)
from veadk.extensions.harness.sidecar import HarnessSidecarDependencyError

__all__ = [
    "CapabilityReceipt",
    "CompactionReport",
    "CompactionResult",
    "CompressionReport",
    "CompressionRequest",
    "CompressionResult",
    "ContextBundle",
    "ContextEngine",
    "ConversationMessage",
    "EvidenceRef",
    "FinalResponseVerifier",
    "HarnessEvent",
    "HarnessExtension",
    "HarnessExtensionConfig",
    "HarnessIntervention",
    "HarnessInvocationContextBuilder",
    "HarnessInvocationContextConfig",
    "HarnessInvocationRef",
    "HarnessLongRunControlPlugin",
    "HarnessRunContext",
    "HarnessSidecarDependencyError",
    "HeadroomCompressionProvider",
    "InvocationContextBlock",
    "ResultVerifier",
    "TaskContract",
    "ToolReceipt",
    "ToolResultCompactor",
    "ToolResultCompressor",
    "VerificationDecision",
    "VerificationReport",
]
