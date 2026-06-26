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

"""Per-invocation metrics plugins for HarnessApp Runtime."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from google.adk.models import LlmResponse
from google.adk.plugins import BasePlugin

from veadk.cloud.harness_app.types import LlmUsageMetrics

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext


class HarnessLlmUsagePlugin(BasePlugin):
    """Collect aggregate LLM usage from ADK model callbacks."""

    def __init__(self) -> None:
        super().__init__(name="harness_llm_usage_collector")
        self.metrics = LlmUsageMetrics()

    async def after_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        usage = _usage_metrics_from_object(llm_response.usage_metadata)
        if usage.has_tokens():
            self.metrics.add(usage)
        return None


def _usage_metrics_from_object(value: object) -> LlmUsageMetrics:
    return LlmUsageMetrics(
        prompt_tokens=_int_value(
            value,
            "prompt_token_count",
            "prompt_tokens",
            "input_tokens",
        ),
        completion_tokens=_int_value(
            value,
            "candidates_token_count",
            "completion_tokens",
            "output_tokens",
        ),
        total_tokens=_int_value(
            value,
            "total_token_count",
            "total_tokens",
        ),
        cached_tokens=_int_value(
            value,
            "cached_content_token_count",
            "cached_tokens",
        ),
        usage_event_count=1,
    )


def _int_value(value: object, *names: str) -> int:
    for name in names:
        raw = _field_value(value, name)
        if raw is None:
            continue
        try:
            return int(raw)
        except (TypeError, ValueError):
            continue
    return 0


def _field_value(value: object, name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(name)
    return getattr(value, name, None)
