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

"""Final-response verification plugin for VeADK Runner."""

from __future__ import annotations

from typing import TYPE_CHECKING

from google.adk.models import LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.decisions import DecisionModelError
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
)
from veadk.extensions.harness.modules.final_response_verifier.support_judge import (
    SupportJudge,
    SupportJudgement,
    build_support_judge,
)
from veadk.extensions.harness.plugins._shared.callback_utils import (
    looks_like_error_result,
    run_context_from_callback,
    run_context_from_invocation,
    run_context_from_tool,
    tool_name,
    user_text_from_callback,
)
from veadk.extensions.harness.plugins.content_adapter import (
    response_text,
    text_response,
)
from veadk.extensions.harness.schemas import (
    EvidenceRef,
    HarnessEvent,
    JsonObject,
    ToolReceipt,
)
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.extensions.harness.utils import (
    coerce_json_object,
    stringify_json_value,
    summarize_text,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext


class HarnessResponseVerificationPlugin(BasePlugin):
    """Records receipts and suppresses unsupported final claims."""

    def __init__(
        self,
        *,
        verifier: FinalResponseVerifier | None = None,
        support_judge: SupportJudge | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_response_verification_plugin")
        self.verifier = verifier or FinalResponseVerifier()
        self.support_judge = support_judge or build_support_judge(
            self.verifier.config.strategy,
            min_confidence=self.verifier.config.min_confidence,
        )
        self.store = store or InMemoryHarnessStore()
        self.profile = profile

    async def after_tool_callback(
        self,
        *,
        tool: "BaseTool",
        tool_args: dict[str, object],
        tool_context: "ToolContext",
        result: object,
    ) -> dict[str, object] | None:
        run_context = run_context_from_tool(tool_context, profile=self.profile)
        name = tool_name(tool)
        result_object = result if isinstance(result, dict) else {"result": result}
        summary = summarize_text(stringify_json_value(result_object), max_chars=1200)
        status = "error" if looks_like_error_result(result_object) else "success"
        receipt = ToolReceipt(
            name=name,
            status=status,
            summary=summary,
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            evidence=[EvidenceRef(source=name, content=summary)],
            metadata={"tool_args": coerce_json_object(tool_args)},
        )
        self.store.append_receipt(receipt)
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_response: LlmResponse,
    ) -> LlmResponse | None:
        text = response_text(llm_response.content)
        if not text:
            return None
        run_context = run_context_from_callback(
            callback_context,
            profile=self.profile,
        )
        receipts = self.store.load_receipts(
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            limit=20,
        )
        report = self.verifier.verify_text(text, receipts=receipts)
        judgement = await self._review(callback_context, answer=text, receipts=receipts)
        intervention = self.verifier.decide(report, judgement=judgement)
        effective_report = intervention.report or report
        payload: JsonObject = {
            "intervention": intervention.model_dump(mode="json"),
            "receipt_count": len(receipts),
        }
        if judgement is not None:
            payload["judgement"] = {
                "support": judgement.support,
                "verdict": judgement.verdict,
                "coverage": judgement.coverage,
                "overclaim": judgement.overclaim,
                "action": judgement.action,
                "confidence": judgement.confidence,
            }
        self.store.append_event(
            HarnessEvent(
                event_type="verifier.report",
                run_context=run_context,
                payload=payload,
            )
        )
        if intervention.action == "block":
            return LlmResponse(
                content=text_response(
                    "I cannot verify that result from the available tool evidence. "
                    "Please rerun the required tool step or provide supporting evidence."
                ),
                custom_metadata={
                    "harness_verification": effective_report.model_dump(mode="json")
                },
            )
        metadata = dict(llm_response.custom_metadata or {})
        metadata["harness_verification"] = effective_report.model_dump(mode="json")
        if intervention.instruction:
            metadata["harness_repair_instruction"] = intervention.instruction
        llm_response.custom_metadata = metadata
        return None

    async def _review(
        self,
        callback_context: "CallbackContext",
        *,
        answer: str,
        receipts: list[ToolReceipt],
    ) -> SupportJudgement | None:
        """Return the judged support of one answer, or ``None``.

        Returns:
            The judgement, or ``None`` when the plugin has no judge. A judge
            that cannot answer also returns ``None``, so the builtin rules
            decide instead of the answer passing unverified.
        """
        if self.support_judge is None:
            return None
        try:
            return await self.support_judge.areview(
                answer=answer,
                receipts=receipts,
                goal=user_text_from_callback(callback_context),
            )
        except DecisionModelError as exc:
            logger.warning(
                "support judge unavailable, using the builtin rules: %s", exc
            )
            return None

    async def on_event_callback(
        self,
        *,
        invocation_context: "InvocationContext",
        event: "Event",
    ) -> "Event | None":
        run_context = run_context_from_invocation(
            invocation_context,
            profile=self.profile,
        )
        self.store.append_event(
            HarnessEvent(
                event_type="runner.event",
                run_context=run_context,
                payload={"author": str(getattr(event, "author", ""))},
            )
        )
        return None
