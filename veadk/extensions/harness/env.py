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

"""veADK helpers for Harness plugin assembly."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Literal

from google.adk.plugins import BasePlugin

from veadk.extensions.harness.adk import build_harness_plugins
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.stores import JsonlHarnessStore


def harness_enabled_from_env(env: Mapping[str, str] | None = None) -> bool:
    """Return whether Harness plugins should be attached."""

    values = env or os.environ
    return _truthy(
        values.get("HARNESS_ENHANCE_ENABLED")
        or values.get("HARNESS_ENABLE")
        or values.get("HARNESS_ENABLED")
    )


def build_harness_plugins_from_env(
    env: Mapping[str, str] | None = None,
) -> list[BasePlugin]:
    """Build Harness plugins from generic runtime environment variables."""

    values = env or os.environ
    if not harness_enabled_from_env(values):
        return []
    components = (
        values.get("HARNESS_ENHANCE_COMPONENTS")
        or values.get("HARNESS_COMPONENTS")
        or "invocation_context,compactor,response_verification"
    )
    profile = (
        values.get("HARNESS_ENHANCE_PROFILE")
        or values.get("HARNESS_PROFILE")
        or "default"
    )
    max_context_chars = _int_value(
        values.get("HARNESS_MAX_CONTEXT_CHARS")
        or values.get("HARNESS_ENHANCE_MAX_CONTEXT_CHARS"),
        default=24000,
    )
    max_tool_result_chars = _int_value(
        values.get("HARNESS_MAX_TOOL_RESULT_CHARS")
        or values.get("HARNESS_ENHANCE_MAX_TOOL_RESULT_CHARS"),
        default=4000,
    )
    store_path = values.get("HARNESS_STORE_PATH") or values.get(
        "HARNESS_ENHANCE_STORE_PATH"
    )
    store = JsonlHarnessStore(store_path) if store_path else None
    return build_harness_plugins(
        components=components,
        profile=profile,
        store=store,
        context_config=HarnessInvocationContextConfig(
            max_context_chars=max_context_chars
        ),
        compaction_config=ToolResultCompactorConfig(
            provider=values.get("HARNESS_COMPRESSION_PROVIDER")
            or values.get("HARNESS_ENHANCE_COMPRESSION_PROVIDER")
            or "builtin",
            max_context_chars=max_context_chars,
            max_tool_result_chars=max_tool_result_chars,
        ),
        verifier_config=FinalResponseVerifierConfig(
            mode=_verifier_mode(
                values.get("HARNESS_VERIFIER_MODE")
                or values.get("HARNESS_ENHANCE_VERIFIER_MODE")
            )
        ),
    )


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _int_value(value: str | None, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _verifier_mode(value: str | None) -> Literal["observe", "block"]:
    normalized = (value or "observe").strip().lower()
    return "block" if normalized == "block" else "observe"


__all__ = ["build_harness_plugins_from_env", "harness_enabled_from_env"]
