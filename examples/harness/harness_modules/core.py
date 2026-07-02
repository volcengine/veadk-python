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

"""Shared Harness types and a veADK run processor.

This file intentionally lives under ``examples/harness``. It demonstrates the
minimal lifecycle glue needed to compose Harness-like modules with veADK without
adding a new public ``veadk.harness`` API.
"""

from __future__ import annotations

import contextlib
import contextvars
import time
import uuid
from datetime import datetime, timezone
from typing import AsyncGenerator, Callable, Iterator, Protocol, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, JsonValue as JSONValue

from veadk.processors.base_run_processor import BaseRunProcessor

JSONDict: TypeAlias = dict[str, JSONValue]


def utc_now() -> str:
    """Return a stable UTC timestamp for JSONL records."""

    return datetime.now(timezone.utc).isoformat()


class HarnessBaseModel(BaseModel):
    """Pydantic base config for strict example Harness records."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AcceptanceCriterion(HarnessBaseModel):
    """A single checkable requirement derived from the task prompt."""

    id: str
    description: str
    required: bool = True
    source: str = "auto"


class TaskContract(HarnessBaseModel):
    """Pinned task boundary used to prevent prompt drift across turns."""

    task_id: str
    original_prompt: str
    turn_type: str
    acceptance: list[AcceptanceCriterion] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    created_at: str = Field(default_factory=utc_now)
    metadata: JSONDict = Field(default_factory=dict)


class HarnessBudgetReport(HarnessBaseModel):
    """Approximate prompt budget after context assembly."""

    estimated_tokens: int
    max_context_chars: int
    truncated: bool = False
    omitted_count: int = 0
    kept_history_count: int = 0


class EvidenceRef(HarnessBaseModel):
    """A local evidence object created from a tool result or external source."""

    ref_id: str
    kind: str
    uri: str
    digest: str
    preview: str
    created_at: str = Field(default_factory=utc_now)
    metadata: JSONDict = Field(default_factory=dict)


class CapabilityReceipt(HarnessBaseModel):
    """Auditable record for one tool/capability invocation."""

    id: str
    run_id: str
    session_id: str
    tool_name: str
    input_summary: str
    result_summary: str
    status: str
    duration_ms: float
    evidence_refs: list[EvidenceRef] = Field(default_factory=list)
    sources: list[JSONDict] = Field(default_factory=list)
    artifacts: list[JSONDict] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    created_at: str = Field(default_factory=utc_now)
    metadata: JSONDict = Field(default_factory=dict)


class AcceptanceCheck(HarnessBaseModel):
    """Verifier output for one acceptance criterion or evidence rule."""

    id: str
    passed: bool
    message: str
    severity: str = "error"
    evidence_refs: list[str] = Field(default_factory=list)


class VerificationReport(HarnessBaseModel):
    """Final answer verification report."""

    run_id: str
    session_id: str
    done: bool
    checks: list[AcceptanceCheck] = Field(default_factory=list)
    missing_requirements: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    follow_up_guidance: str = ""
    created_at: str = Field(default_factory=utc_now)


class HarnessEvent(HarnessBaseModel):
    """Lightweight local event written by the example store."""

    event_type: str
    session_id: str
    run_id: str
    payload: JSONDict = Field(default_factory=dict)
    created_at: str = Field(default_factory=utc_now)


class HarnessContext(HarnessBaseModel):
    """Runtime context shared by the processor, tools, and verifier."""

    user_id: str
    session_id: str
    run_id: str
    original_prompt: str
    turn_type: str = "new_task"
    task_contract: TaskContract | None = None
    history_projection: list[JSONDict] = Field(default_factory=list)
    receipts: list[CapabilityReceipt] = Field(default_factory=list)
    budget: HarnessBudgetReport | None = None
    metadata: JSONDict = Field(default_factory=dict)


class HarnessRunStoreProtocol(Protocol):
    def append_event(self, event: HarnessEvent) -> None: ...

    def append_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        run_id: str = "",
        metadata: JSONDict | None = None,
    ) -> None: ...

    def load_receipts(
        self,
        *,
        run_id: str | None = None,
        session_id: str | None = None,
    ) -> list[CapabilityReceipt]: ...

    def save_report(self, report: VerificationReport) -> None: ...


class ContextEngineProtocol(Protocol):
    def prepare_context(self, context: HarnessContext) -> HarnessContext: ...

    def build_user_prompt(
        self, *, context: HarnessContext, user_prompt: str
    ) -> str: ...


class ResultVerifierProtocol(Protocol):
    def verify(
        self,
        *,
        final_text: str,
        context: HarnessContext,
        receipts: list[CapabilityReceipt] | None = None,
    ) -> VerificationReport: ...


_CURRENT_CONTEXT: contextvars.ContextVar[HarnessContext | None] = (
    contextvars.ContextVar("harness_current_context", default=None)
)


def current_harness_context() -> HarnessContext | None:
    """Return the current run context so tool wrappers can tag receipts."""

    return _CURRENT_CONTEXT.get()


def _set_current_context(
    context: HarnessContext,
) -> contextvars.Token[HarnessContext | None]:
    return _CURRENT_CONTEXT.set(context)


def _reset_current_context(token: contextvars.Token[HarnessContext | None]) -> None:
    _CURRENT_CONTEXT.reset(token)


def summarize_text(value: object, *, max_chars: int = 500) -> str:
    """Make a compact, stable preview suitable for receipts and events."""

    text = str(value)
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 18].rstrip() + " ... [truncated]"


def extract_text_from_message(message: object) -> str:
    """Best-effort text extraction for ADK ``Content`` and simple test doubles."""

    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        return str(message.get("text") or message.get("content") or "")

    parts = getattr(message, "parts", None)
    if parts:
        texts: list[str] = []
        for part in parts:
            text = getattr(part, "text", None)
            if text:
                texts.append(str(text))
        return "\n".join(texts).strip()

    content = getattr(message, "content", None)
    if content is not None:
        return extract_text_from_message(content)

    return ""


def replace_message_text(message: object, text: str) -> bool:
    """Replace the first text part in an ADK message in place.

    The helper returns ``False`` if the object shape is immutable or unsupported.
    The example keeps this best-effort to avoid depending on ADK object details beyond
    the standard ``Content(parts=[Part(text=...)])`` shape.
    """

    parts = getattr(message, "parts", None)
    if not parts:
        return False

    for part in parts:
        if getattr(part, "text", None) is not None:
            try:
                setattr(part, "text", text)
                return True
            except Exception:
                return False
    return False


def extract_text_from_event(event: object) -> str:
    """Best-effort assistant text extraction from an ADK event."""

    content = getattr(event, "content", None)
    if content is None:
        return ""
    parts = getattr(content, "parts", None) or []
    for part in parts:
        if bool(getattr(part, "thought", False)):
            continue
        text = getattr(part, "text", None)
        if text and str(text).strip():
            return str(text)
    return ""


class HarnessRunProcessor(BaseRunProcessor):
    """Run-level wrapper that injects context and records verification reports."""

    def __init__(
        self,
        *,
        store: HarnessRunStoreProtocol | None = None,
        context_engine: ContextEngineProtocol | None = None,
        verifier: ResultVerifierProtocol | None = None,
        verify: bool = True,
    ) -> None:
        self.store = store
        self.context_engine = context_engine
        self.verifier = verifier
        self.verify = verify
        self.last_context: HarnessContext | None = None
        self.last_report: VerificationReport | None = None
        self._bound_run: contextvars.ContextVar[dict[str, str] | None] = (
            contextvars.ContextVar("harness_bound_run", default=None)
        )

    @contextlib.contextmanager
    def bind_run(
        self,
        *,
        user_id: str = "",
        session_id: str = "",
        original_prompt: str = "",
        run_id: str = "",
    ) -> Iterator[None]:
        """Bind metadata for the next ``Runner.run`` call.

        ``Runner.run`` currently does not pass ``user_id`` / ``session_id`` to
        ``BaseRunProcessor.process_run``. This context manager keeps the example
        backward-compatible while still producing useful local harness records.
        """

        token = self._bound_run.set(
            {
                "user_id": user_id,
                "session_id": session_id,
                "original_prompt": original_prompt,
                "run_id": run_id,
            }
        )
        try:
            yield
        finally:
            self._bound_run.reset(token)

    def process_run(
        self,
        runner: object,
        message: object,
        **kwargs: object,
    ) -> Callable[
        [Callable[[], AsyncGenerator[object, None]]],
        Callable[[], AsyncGenerator[object, None]],
    ]:
        bound = self._bound_run.get() or {}
        user_id = bound.get("user_id") or getattr(runner, "user_id", "") or ""
        session_id = bound.get("session_id") or "unknown-session"
        original_prompt = bound.get("original_prompt") or extract_text_from_message(
            message
        )
        run_id = bound.get("run_id") or f"harness-{uuid.uuid4().hex[:12]}"

        context = HarnessContext(
            user_id=user_id,
            session_id=session_id,
            run_id=run_id,
            original_prompt=original_prompt,
        )

        if self.context_engine is not None:
            context = self.context_engine.prepare_context(context)
            injected_prompt = self.context_engine.build_user_prompt(
                context=context,
                user_prompt=original_prompt,
            )
            replaced = replace_message_text(message, injected_prompt)
            context.metadata["message_injected"] = replaced

        self.last_context = context
        if self.store is not None:
            self.store.append_event(
                HarnessEvent(
                    event_type="harness.run.started",
                    session_id=session_id,
                    run_id=run_id,
                    payload={
                        "user_id": user_id,
                        "turn_type": context.turn_type,
                        "message_injected": context.metadata.get(
                            "message_injected", False
                        ),
                    },
                )
            )
            self.store.append_message(
                session_id=session_id,
                role="user",
                content=original_prompt,
                run_id=run_id,
            )

        def decorator(
            event_generator_func: Callable[[], AsyncGenerator[object, None]],
        ) -> Callable[[], AsyncGenerator[object, None]]:
            async def wrapper() -> AsyncGenerator[object, None]:
                token = _set_current_context(context)
                final_text = ""
                started = time.perf_counter()
                try:
                    async for event in event_generator_func():
                        event_text = extract_text_from_event(event)
                        if event_text:
                            final_text = event_text
                        yield event
                except Exception as exc:
                    if self.store is not None:
                        self.store.append_event(
                            HarnessEvent(
                                event_type="harness.run.failed",
                                session_id=session_id,
                                run_id=run_id,
                                payload={
                                    "error_type": type(exc).__name__,
                                    "error_message": str(exc),
                                },
                            )
                        )
                    raise
                finally:
                    _reset_current_context(token)

                if self.store is not None and final_text:
                    self.store.append_message(
                        session_id=session_id,
                        role="assistant",
                        content=final_text,
                        run_id=run_id,
                    )

                receipts = []
                if self.store is not None:
                    receipts = self.store.load_receipts(run_id=run_id)
                context.receipts = receipts

                if self.verify and self.verifier is not None:
                    report = self.verifier.verify(
                        final_text=final_text,
                        context=context,
                        receipts=receipts,
                    )
                    self.last_report = report
                    if self.store is not None:
                        self.store.save_report(report)

                if self.store is not None:
                    self.store.append_event(
                        HarnessEvent(
                            event_type="harness.run.finished",
                            session_id=session_id,
                            run_id=run_id,
                            payload={
                                "duration_ms": round(
                                    (time.perf_counter() - started) * 1000, 3
                                ),
                                "final_text_preview": summarize_text(
                                    final_text, max_chars=300
                                ),
                                "verified": self.last_report.done
                                if self.last_report
                                else None,
                            },
                        )
                    )

            return wrapper

        return decorator
