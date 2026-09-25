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

"""VeADK helpers for Harness plugin assembly."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from google.adk.plugins import BasePlugin


def harness_enabled_from_env(env: Mapping[str, str] | None = None) -> bool:
    """Return whether Harness plugins should be attached."""

    values = env or os.environ
    return _truthy(values.get("HARNESS_ENHANCE_ENABLED"))


def build_harness_plugins_from_env(
    env: Mapping[str, str] | None = None,
) -> list[BasePlugin]:
    """Build Harness plugins from generic runtime environment variables."""

    values = env or os.environ
    if not harness_enabled_from_env(values):
        return []
    from veadk.extensions.decisions import probability_threshold
    from veadk.extensions.harness.modules.final_response_verifier import (
        FinalResponseVerifierConfig,
    )
    from veadk.extensions.harness.modules.invocation_context import (
        HarnessInvocationContextConfig,
    )
    from veadk.extensions.harness.modules.skill_prefilter import (
        DEFAULT_MAX_CANDIDATES,
        HarnessSkillPrefilterConfig,
    )
    from veadk.extensions.harness.modules.tool_result_compactor import (
        ToolResultCompactorConfig,
    )
    from veadk.extensions.harness.plugins import build_harness_plugins
    from veadk.extensions.harness.stores import JsonlHarnessStore

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
            mode_strategy=_decision_strategy(
                values.get("HARNESS_MODE_STRATEGY")
                or values.get("HARNESS_ENHANCE_MODE_STRATEGY"),
                default="keywords",
            ),
            mode_decision_threshold=probability_threshold(
                _first(
                    values,
                    "HARNESS_MODE_DECISION_THRESHOLD",
                    "HARNESS_ENHANCE_MODE_DECISION_THRESHOLD",
                ),
                name="HARNESS_MODE_DECISION_THRESHOLD",
            ),
            max_context_chars=max_context_chars,
        ),
        compaction_config=ToolResultCompactorConfig(
            provider=values.get("HARNESS_COMPRESSION_PROVIDER")
            or values.get("HARNESS_ENHANCE_COMPRESSION_PROVIDER")
            or "builtin",
            strategy=_decision_strategy(
                values.get("HARNESS_COMPACTION_STRATEGY")
                or values.get("HARNESS_ENHANCE_COMPACTION_STRATEGY"),
                default="builtin",
            ),
            decision_keep_threshold=probability_threshold(
                _first(
                    values,
                    "HARNESS_COMPACTION_KEEP_THRESHOLD",
                    "HARNESS_ENHANCE_COMPACTION_KEEP_THRESHOLD",
                ),
                name="HARNESS_COMPACTION_KEEP_THRESHOLD",
            ),
            max_context_chars=max_context_chars,
            max_tool_result_chars=max_tool_result_chars,
        ),
        long_run_strategy=_decision_strategy(
            values.get("HARNESS_LONG_RUN_STRATEGY")
            or values.get("HARNESS_ENHANCE_LONG_RUN_STRATEGY"),
            default="counter",
        ),
        long_run_ready_threshold=probability_threshold(
            _first(
                values,
                "HARNESS_LONG_RUN_READY_THRESHOLD",
                "HARNESS_ENHANCE_LONG_RUN_READY_THRESHOLD",
            ),
            name="HARNESS_LONG_RUN_READY_THRESHOLD",
        ),
        long_run_min_confidence=probability_threshold(
            _first(
                values,
                "HARNESS_LONG_RUN_MIN_CONFIDENCE",
                "HARNESS_ENHANCE_LONG_RUN_MIN_CONFIDENCE",
            ),
            name="HARNESS_LONG_RUN_MIN_CONFIDENCE",
            default=0.0,
        ),
        verifier_config=FinalResponseVerifierConfig(
            mode=_verifier_mode(
                values.get("HARNESS_VERIFIER_MODE")
                or values.get("HARNESS_ENHANCE_VERIFIER_MODE")
            ),
            strategy=_decision_strategy(
                values.get("HARNESS_VERIFIER_STRATEGY")
                or values.get("HARNESS_ENHANCE_VERIFIER_STRATEGY"),
                default="deterministic",
            ),
            support_threshold=probability_threshold(
                _first(
                    values,
                    "HARNESS_VERIFIER_SUPPORT_THRESHOLD",
                    "HARNESS_ENHANCE_VERIFIER_SUPPORT_THRESHOLD",
                ),
                name="HARNESS_VERIFIER_SUPPORT_THRESHOLD",
            ),
            overclaim_threshold=probability_threshold(
                _first(
                    values,
                    "HARNESS_VERIFIER_OVERCLAIM_THRESHOLD",
                    "HARNESS_ENHANCE_VERIFIER_OVERCLAIM_THRESHOLD",
                ),
                name="HARNESS_VERIFIER_OVERCLAIM_THRESHOLD",
            ),
            min_confidence=probability_threshold(
                _first(
                    values,
                    "HARNESS_VERIFIER_MIN_CONFIDENCE",
                    "HARNESS_ENHANCE_VERIFIER_MIN_CONFIDENCE",
                ),
                name="HARNESS_VERIFIER_MIN_CONFIDENCE",
                default=0.0,
            ),
        ),
        skill_prefilter_config=HarnessSkillPrefilterConfig(
            strategy=_decision_strategy(
                values.get("HARNESS_SKILL_STRATEGY")
                or values.get("HARNESS_ENHANCE_SKILL_STRATEGY"),
                default="all",
            ),
            decision_threshold=probability_threshold(
                _first(
                    values,
                    "HARNESS_SKILL_DECISION_THRESHOLD",
                    "HARNESS_ENHANCE_SKILL_DECISION_THRESHOLD",
                ),
                name="HARNESS_SKILL_DECISION_THRESHOLD",
            ),
            max_candidates=_int_value(
                _first(
                    values,
                    "HARNESS_SKILL_MAX_CANDIDATES",
                    "HARNESS_ENHANCE_SKILL_MAX_CANDIDATES",
                ),
                default=DEFAULT_MAX_CANDIDATES,
            ),
        ),
        routing_strategy=_decision_strategy(
            values.get("HARNESS_ROUTING_STRATEGY")
            or values.get("HARNESS_ENHANCE_ROUTING_STRATEGY"),
            default="model",
        ),
        routing_confidence_threshold=probability_threshold(
            _first(
                values,
                "HARNESS_ROUTING_DECISION_THRESHOLD",
                "HARNESS_ENHANCE_ROUTING_DECISION_THRESHOLD",
            ),
            name="HARNESS_ROUTING_DECISION_THRESHOLD",
        ),
    )


def _truthy(value: str | None) -> bool:
    return bool(value and value.strip().lower() in {"1", "true", "yes", "on"})


def _first(values: Mapping[str, str], *names: str) -> str | None:
    """Return the first configured value among the accepted env spellings."""

    for name in names:
        value = values.get(name)
        if value not in (None, ""):
            return str(value)
    return None


def _int_value(value: str | None, *, default: int) -> int:
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _decision_strategy(value: str | None, *, default: str) -> str:
    """Return ``decision`` when explicitly requested, else the default."""
    return "decision" if (value or "").strip().lower() == "decision" else default


def _verifier_mode(value: str | None) -> Literal["observe", "block"]:
    normalized = (value or "observe").strip().lower()
    return "block" if normalized == "block" else "observe"


__all__ = ["build_harness_plugins_from_env", "harness_enabled_from_env"]
