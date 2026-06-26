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

"""Harness plugin bundle assembly."""

from __future__ import annotations

from collections.abc import Iterable

from google.adk.plugins import BasePlugin

from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextBuilder,
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.plugins.compactor import HarnessCompressPlugin
from veadk.extensions.harness.plugins.invocation_context import (
    HarnessInvocationContextPlugin,
)
from veadk.extensions.harness.plugins.long_run_control import (
    HarnessLongRunControlPlugin,
)
from veadk.extensions.harness.plugins.response_verification import (
    HarnessResponseVerificationPlugin,
)
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore

ComponentName = str


def build_harness_plugins(
    *,
    components: Iterable[ComponentName] | str | None = None,
    profile: str = "default",
    store: HarnessStoreProtocol | None = None,
    context_config: HarnessInvocationContextConfig | None = None,
    compaction_config: ToolResultCompactorConfig | None = None,
    compression_config: ToolResultCompactorConfig | None = None,
    verifier_config: FinalResponseVerifierConfig | None = None,
) -> list[BasePlugin]:
    """Build a shared-store Harness plugin bundle."""

    selected = _normalize_components(components)
    shared_store = store or InMemoryHarnessStore()
    compactor_config = compaction_config or compression_config
    plugins: list[BasePlugin] = []
    if "context_engine" in selected:
        plugins.append(
            HarnessInvocationContextPlugin(
                context_builder=HarnessInvocationContextBuilder(context_config),
                store=shared_store,
                profile=profile,
            )
        )
    if "compressor" in selected:
        plugins.append(
            HarnessCompressPlugin(
                compactor=ToolResultCompactor(compactor_config),
                store=shared_store,
                profile=profile,
            )
        )
    if "hallucination" in selected:
        plugins.append(
            HarnessResponseVerificationPlugin(
                verifier=FinalResponseVerifier(verifier_config),
                store=shared_store,
                profile=profile,
            )
        )
    if "long_run_control" in selected:
        plugins.append(
            HarnessLongRunControlPlugin(
                store=shared_store,
                profile=profile,
            )
        )
    return plugins


def _normalize_components(components: Iterable[ComponentName] | str | None) -> set[str]:
    if components is None:
        raw = ["invocation_context", "compactor", "response_verification"]
    elif isinstance(components, str):
        raw = [item.strip() for item in components.split(",")]
    else:
        raw = [str(item).strip() for item in components]
    aliases = {
        "context": "context_engine",
        "context_engine": "context_engine",
        "harness_context_plugin": "context_engine",
        "invocation_context": "context_engine",
        "harness_invocation_context_builder": "context_engine",
        "compress": "compressor",
        "compression": "compressor",
        "compressor": "compressor",
        "compact": "compressor",
        "compaction": "compressor",
        "compactor": "compressor",
        "tool_compactor": "compressor",
        "tool_compressor": "compressor",
        "harness_compress_plugin": "compressor",
        "hallucination": "hallucination",
        "verifier": "hallucination",
        "result_verifier": "hallucination",
        "response_verification": "hallucination",
        "final_response_verifier": "hallucination",
        "harness_hallucination_plugin": "hallucination",
        "harness_response_verification_plugin": "hallucination",
        "long_run": "long_run_control",
        "long_run_control": "long_run_control",
        "long_running": "long_run_control",
        "run_control": "long_run_control",
        "harness_long_run_control_plugin": "long_run_control",
    }
    return {aliases[item] for item in raw if item in aliases}
