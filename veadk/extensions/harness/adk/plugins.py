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

"""Runner plugins backed by atomic Harness modules."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin

from veadk.extensions.harness.adk.content_adapter import (
    append_system_instruction,
    contents_to_messages,
    response_text,
    text_response,
)
from veadk.extensions.harness.modules.invocation_context import (
    HarnessInvocationContextBuilder,
    HarnessInvocationContextConfig,
)
from veadk.extensions.harness.modules.final_response_verifier import (
    FinalResponseVerifier,
    FinalResponseVerifierConfig,
)
from veadk.extensions.harness.modules.tool_result_compactor import (
    ToolResultCompactor,
    ToolResultCompactorConfig,
)
from veadk.extensions.harness.schemas import (
    ToolReceipt,
    CompactionReport,
    CompressionRequest,
    ConversationMessage,
    EvidenceRef,
    HarnessEvent,
    HarnessInvocationRef,
    TaskContract,
)
from veadk.extensions.harness.stores import HarnessStoreProtocol, InMemoryHarnessStore
from veadk.extensions.harness.utils import (
    coerce_json_object,
    stringify_json_value,
    summarize_text,
)

if TYPE_CHECKING:
    from google.adk.agents.callback_context import CallbackContext
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event
    from google.adk.tools.base_tool import BaseTool
    from google.adk.tools.tool_context import ToolContext
    from google.genai import types


ComponentName = str


class HarnessInvocationContextPlugin(BasePlugin):
    """Injects task context and guardrails before model calls."""

    def __init__(
        self,
        *,
        context_builder: HarnessInvocationContextBuilder | None = None,
        context_engine: HarnessInvocationContextBuilder | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_invocation_context_plugin")
        self.context_builder = (
            context_builder or context_engine or HarnessInvocationContextBuilder()
        )
        self.context_engine = self.context_builder
        self.store = store or InMemoryHarnessStore()
        self.profile = profile

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        run_context = _run_context_from_callback(callback_context, profile=self.profile)
        user_text = _user_text_from_callback(callback_context)
        history = contents_to_messages(llm_request.contents)
        receipts = self.store.load_receipts(
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            limit=8,
        )
        bundle = self.context_builder.prepare_context(
            run_context,
            user_input=user_text,
            history=history,
            receipts=receipts,
            has_tools=bool(llm_request.tools_dict),
        )
        if bundle.header:
            append_system_instruction(llm_request, bundle.header)
            self.store.append_event(
                HarnessEvent(
                    event_type="invocation_context.injected",
                    run_context=run_context,
                    payload={
                        "context_chars": bundle.context_chars,
                        "history_messages": len(history),
                        "receipt_count": len(receipts),
                    },
                )
            )
        return None

    async def on_user_message_callback(
        self,
        *,
        invocation_context: "InvocationContext",
        user_message: "types.Content",
    ) -> "types.Content | None":
        text = stringify_json_value(user_message.model_dump(), max_chars=4000)
        run_context = _run_context_from_invocation(
            invocation_context,
            profile=self.profile,
        )
        self.store.append_message(
            run_context.session_id,
            _message_from_text("user", text),
        )
        return None


class HarnessCompressPlugin(BasePlugin):
    """Compacts oversized tool results and historical tool context."""

    def __init__(
        self,
        *,
        compactor: ToolResultCompactor | None = None,
        compressor: ToolResultCompactor | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_compress_plugin")
        self.compactor = compactor or compressor or ToolResultCompactor()
        self.compressor = self.compactor
        self.store = store or InMemoryHarnessStore()
        self.profile = profile
        self.compaction_reports: list[CompactionReport] = []

    async def before_model_callback(
        self,
        *,
        callback_context: "CallbackContext",
        llm_request: LlmRequest,
    ) -> LlmResponse | None:
        tool_reports = self._compact_function_responses(llm_request)
        messages = contents_to_messages(llm_request.contents)
        self.compaction_reports.extend(tool_reports)
        if not messages:
            return None
        result = self.compactor.compress_messages(
            CompressionRequest(
                messages=messages,
                max_context_chars=self.compactor.config.max_context_chars,
            )
        )
        if result.report.changed or tool_reports:
            self.store.append_event(
                HarnessEvent(
                    event_type="compressor.model_context",
                    run_context=_run_context_from_callback(
                        callback_context,
                        profile=self.profile,
                    ),
                    payload={
                        "context_report": result.report.model_dump(mode="json"),
                        "tool_reports": [
                            report.model_dump(mode="json") for report in tool_reports
                        ],
                    },
                )
            )
            if result.report.changed:
                self.compaction_reports.append(result.report)
        return None

    async def after_tool_callback(
        self,
        *,
        tool: "BaseTool",
        tool_args: dict[str, object],
        tool_context: "ToolContext",
        result: dict[str, object],
    ) -> dict[str, object] | None:
        compressed, report = self.compactor.compress_tool_result(result)
        if not report.changed:
            return None
        self.compaction_reports.append(report)
        self.store.append_event(
            HarnessEvent(
                event_type="compressor.tool_result",
                run_context=_run_context_from_tool(tool_context, profile=self.profile),
                payload={
                    "tool": _tool_name(tool),
                    "tool_args": coerce_json_object(tool_args),
                    "report": report.model_dump(mode="json"),
                },
            )
        )
        return compressed if isinstance(compressed, dict) else {"result": compressed}

    def reset_diagnostics(self) -> None:
        self.compaction_reports.clear()

    def _compact_function_responses(
        self, llm_request: LlmRequest
    ) -> list[CompactionReport]:
        reports: list[CompactionReport] = []
        for content in llm_request.contents:
            for part in content.parts or []:
                function_response = part.function_response
                if function_response is None:
                    continue
                response = function_response.response
                if not isinstance(response, dict):
                    continue
                compressed, report = self.compactor.compress_tool_result(response)
                if not report.changed:
                    continue
                function_response.response = compressed
                reports.append(report)
        return reports


class HarnessResponseVerificationPlugin(BasePlugin):
    """Records receipts and suppresses unsupported final claims."""

    def __init__(
        self,
        *,
        verifier: FinalResponseVerifier | None = None,
        store: HarnessStoreProtocol | None = None,
        profile: str = "default",
    ) -> None:
        super().__init__(name="harness_response_verification_plugin")
        self.verifier = verifier or FinalResponseVerifier()
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
        run_context = _run_context_from_tool(tool_context, profile=self.profile)
        tool_name = _tool_name(tool)
        result_object = result if isinstance(result, dict) else {"result": result}
        summary = summarize_text(stringify_json_value(result_object), max_chars=1200)
        status = "error" if _looks_like_error_result(result_object) else "success"
        receipt = ToolReceipt(
            name=tool_name,
            status=status,
            summary=summary,
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            evidence=[EvidenceRef(source=tool_name, content=summary)],
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
        run_context = _run_context_from_callback(callback_context, profile=self.profile)
        receipts = self.store.load_receipts(
            run_id=run_context.invocation_id,
            session_id=run_context.session_id,
            limit=20,
        )
        report = self.verifier.verify_text(text, receipts=receipts)
        intervention = self.verifier.decide(report)
        self.store.append_event(
            HarnessEvent(
                event_type="verifier.report",
                run_context=run_context,
                payload={
                    "intervention": intervention.model_dump(mode="json"),
                    "receipt_count": len(receipts),
                },
            )
        )
        if intervention.action == "block":
            return LlmResponse(
                content=text_response(
                    "I cannot verify that result from the available tool evidence. "
                    "Please rerun the required tool step or provide supporting evidence."
                ),
                custom_metadata={
                    "harness_verification": report.model_dump(mode="json")
                },
            )
        metadata = dict(llm_response.custom_metadata or {})
        metadata["harness_verification"] = report.model_dump(mode="json")
        llm_response.custom_metadata = metadata
        return None

    async def on_event_callback(
        self,
        *,
        invocation_context: "InvocationContext",
        event: "Event",
    ) -> "Event | None":
        run_context = _run_context_from_invocation(
            invocation_context,
            profile=self.profile,
        )
        self.store.append_event(
            HarnessEvent(
                event_type="adk.event",
                run_context=run_context,
                payload={"author": str(getattr(event, "author", ""))},
            )
        )
        return None


HarnessContextPlugin = HarnessInvocationContextPlugin
HarnessHallucinationPlugin = HarnessResponseVerificationPlugin


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
    }
    return {aliases[item] for item in raw if item in aliases}


def _run_context_from_callback(
    callback_context: "CallbackContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = callback_context.session
    goal = _user_text_from_callback(callback_context)
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(callback_context, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(callback_context, "invocation_id", ""),
        profile=profile,
        task=TaskContract(goal=goal) if goal else None,
    )


def _run_context_from_invocation(
    invocation_context: "InvocationContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = invocation_context.session
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(session, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(invocation_context, "invocation_id", ""),
        profile=profile,
    )


def _run_context_from_tool(
    tool_context: "ToolContext",
    *,
    profile: str,
) -> HarnessInvocationRef:
    session = tool_context.session
    return HarnessInvocationRef(
        app_name=getattr(session, "app_name", ""),
        user_id=getattr(tool_context, "user_id", ""),
        session_id=getattr(session, "id", ""),
        invocation_id=getattr(tool_context, "invocation_id", ""),
        profile=profile,
    )


def _user_text_from_callback(callback_context: "CallbackContext") -> str:
    user_content = getattr(callback_context, "user_content", None)
    return stringify_json_value(user_content.model_dump()) if user_content else ""


def _message_from_text(role: str, text: str) -> "ConversationMessage":
    return ConversationMessage(role=role, content=text)


def _tool_name(tool: "BaseTool") -> str:
    return str(getattr(tool, "name", tool.__class__.__name__))


def _looks_like_error_result(result: Mapping[str, object]) -> bool:
    if "error" in result or "exception" in result:
        return True
    status = str(result.get("status", "")).lower()
    return status in {"error", "failed", "failure"}
