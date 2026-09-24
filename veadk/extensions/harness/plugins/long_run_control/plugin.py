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

from typing import TYPE_CHECKING, Literal

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.decisions import DecisionModelError
from veadk.extensions.harness.modules.long_run_control import (
    ConvergenceJudge,
    build_convergence_judge,
    trajectory_text,
)
from veadk.extensions.harness.plugins._shared.callback_utils import (
    run_context_from_callback,
    user_text_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import (
    append_system_instruction,
    contents_to_messages,
)
from veadk.extensions.harness.schemas import HarnessEvent, JsonObject
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext

logger = get_logger(__name__)

LongRunStrategy = Literal["counter", "decision"]


class HarnessLongRunControlPlugin(BasePlugin):
    """Steers long tool chains toward a final answer near the run budget.

    ``counter`` steers every call after ``trigger_after_model_calls``. The
    ``decision`` strategy steers only when a decision model judges that the
    run is not already able to answer, so a still-productive run is not cut
    short; ``unconditional_after_model_calls`` keeps steering guaranteed for
    very long runs.
    """

    def __init__(
        self,
        *,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
        trigger_after_model_calls: int = 8,
        strategy: LongRunStrategy = "counter",
        convergence_judge: ConvergenceJudge | None = None,
        unconditional_after_model_calls: int = 16,
        ready_threshold: float = 0.5,
    ) -> None:
        super().__init__(name="harness_long_run_control_plugin")
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self.trigger_after_model_calls = max(1, trigger_after_model_calls)
        self.strategy = strategy
        self.convergence_judge = convergence_judge or build_convergence_judge(strategy)
        self.unconditional_after_model_calls = max(
            self.trigger_after_model_calls, unconditional_after_model_calls
        )
        self.ready_threshold = ready_threshold
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

        ready = await self._ready_probability(callback_context, llm_request)
        if self._should_skip_guidance(ready=ready, model_calls=model_calls):
            self.store.append_event(
                HarnessEvent(
                    event_type="long_run_control.guidance_skipped",
                    run_context=run_context,
                    payload={
                        "model_calls": model_calls,
                        "decision_ready": ready,
                        "reason": "trajectory_is_still_collecting_evidence",
                    },
                )
            )
            return None

        append_system_instruction(
            llm_request,
            _long_run_control_instruction(model_calls=model_calls),
        )
        payload: JsonObject = {
            "model_calls": model_calls,
            "trigger_after_model_calls": self.trigger_after_model_calls,
        }
        if ready is not None:
            payload["decision_ready"] = ready
            payload["forced"] = model_calls >= self.unconditional_after_model_calls
        self.store.append_event(
            HarnessEvent(
                event_type="long_run_control.guidance_injected",
                run_context=run_context,
                payload=payload,
            )
        )
        return None

    def _should_skip_guidance(self, *, ready: float | None, model_calls: int) -> bool:
        """Whether the convergence judgement lets a run keep working."""
        if ready is None or ready >= self.ready_threshold:
            return False
        return model_calls < self.unconditional_after_model_calls

    async def _ready_probability(
        self,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> float | None:
        """Return the probability that the run can answer, or ``None``.

        Args:
            callback_context: Callback context carrying the user's request.
            llm_request: The request the run is about to send.

        Returns:
            The judged probability, or ``None`` when the plugin has no judge.
            A failing judge returns ``1.0`` so steering keeps working.
        """
        if self.convergence_judge is None:
            return None
        try:
            return await self.convergence_judge.aready_probability(
                goal=user_text_from_callback(callback_context),
                trajectory=trajectory_text(contents_to_messages(llm_request.contents)),
            )
        except DecisionModelError as exc:
            logger.warning(
                "long-run convergence judge unavailable, steering as before: %s",
                exc,
            )
            return 1.0


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
