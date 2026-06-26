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

import importlib
import sys

import pytest

from veadk.extensions.harness import (
    CapabilityReceipt,
    CompactionReport,
    CompactionResult,
    CompressionReport,
    CompressionResult,
    ContextBundle,
    HarnessIntervention,
    HarnessInvocationRef,
    HarnessRunContext,
    InvocationContextBlock,
    ToolReceipt,
    ToolResultCompactor,
    ToolResultCompressor,
    VerificationDecision,
)
from veadk.extensions.harness.plugins import (
    HarnessContextPlugin,
    HarnessHallucinationPlugin,
    HarnessInvocationContextPlugin,
    HarnessResponseVerificationPlugin,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    ResultVerifier,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ContextCompactionPolicy,
    ContextCompressionPolicy,
)


def test_renamed_public_objects_keep_backward_compatible_aliases():
    assert HarnessRunContext is HarnessInvocationRef
    assert ContextBundle is InvocationContextBlock
    assert CompressionReport is CompactionReport
    assert CompressionResult is CompactionResult
    assert CapabilityReceipt is ToolReceipt
    assert HarnessIntervention is VerificationDecision
    assert ToolResultCompressor is ToolResultCompactor
    assert ResultVerifier is FinalResponseVerifier
    assert ContextCompressionPolicy is ContextCompactionPolicy
    assert HarnessContextPlugin is HarnessInvocationContextPlugin
    assert HarnessHallucinationPlugin is HarnessResponseVerificationPlugin


def test_deprecated_module_paths_warn_and_reexport_canonical_objects():
    deprecated_modules = [
        (
            "veadk.extensions.harness.modules.builtin_provider",
            "BuiltinCompressionProvider",
        ),
        (
            "veadk.extensions.harness.modules.headroom_provider",
            "HeadroomCompressionProvider",
        ),
        ("veadk.extensions.harness.modules.context_engine", "ContextEngine"),
    ]

    for module_name, attr_name in deprecated_modules:
        sys.modules.pop(module_name, None)
        with pytest.warns(DeprecationWarning, match="deprecated"):
            module = importlib.import_module(module_name)

        assert getattr(module, attr_name)
