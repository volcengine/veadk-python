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

"""Long-run control plugin for VeADK Runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.harness.plugins._shared.callback_utils import (
    run_context_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import append_system_instruction
from veadk.extensions.harness.schemas import HarnessEvent
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext


class HarnessLongRunControlPlugin(BasePlugin):
    """Steers long tool chains toward a final answer near the run budget."""

    def __init__(
        self,
        *,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
        trigger_after_model_calls: int = 8,
    ) -> None:
        super().__init__(name="harness_long_run_control_plugin")
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self.trigger_after_model_calls = max(1, trigger_after_model_calls)
        self._model_call_counts: dict[tuple[str, str], int] = {}

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        run_context = run_context_from_callback(
            callback_context,
            profile=self.profile,
        )
        key = (run_context.session_id, run_context.invocation_id)
        model_calls = self._model_call_counts.get(key, 0) + 1
        self._model_call_counts[key] = model_calls
        if model_calls < self.trigger_after_model_calls:
            return None

        append_system_instruction(
            llm_request,
            _long_run_control_instruction(model_calls=model_calls),
        )
        self.store.append_event(
            HarnessEvent(
                event_type="long_run_control.guidance_injected",
                run_context=run_context,
                payload={
                    "model_calls": model_calls,
                    "trigger_after_model_calls": self.trigger_after_model_calls,
                },
            )
        )
        return None


def _long_run_control_instruction(*, model_calls: int) -> str:
    return (
        "[Harness Long Run Control]\n"
        f"model_calls_so_far: {model_calls}\n"
        "objective: finish the current run within the remaining budget.\n"
        "guidance:\n"
        "- If the task has enough evidence, a complete answer, or generated "
        "artifacts, stop calling tools and return the final response now.\n"
        "- If files or artifacts were produced, include their filenames, paths, "
        "or URIs and a concise summary.\n"
        "- Call another tool only when it is strictly required to create the "
        "missing final result; avoid repeating searches or code runs.\n"
        "[/Harness Long Run Control]"
    )
