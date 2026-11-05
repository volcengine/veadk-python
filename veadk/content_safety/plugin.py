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
"""ADK plugin that audits content at the four lifecycle checkpoints."""

from __future__ import annotations

import hashlib
import inspect
import json
from typing import Any, Mapping

from google.adk.models import LlmRequest, LlmResponse
from google.adk.plugins import BasePlugin
from google.genai import types

from veadk.decision import DecisionClientError, DecisionJudge, DecisionQuestion
from veadk.utils.logger import get_logger

from .config import ContentSafetyConfig, QuestionConfig
from .decider import ThresholdDecider
from .state import STATE_POLICY_PREFIX, StateBuilder, StatePayload
from .types import AuditAction, AuditResult, Checkpoint, Provider

logger = get_logger(__name__)

_MAX_INVOCATIONS = 256


def _is_visible_text_part(part: Any) -> bool:
    return isinstance(getattr(part, "text", None), str) and not getattr(
        part, "thought", False
    )


def _is_media_part(part: Any) -> bool:
    if getattr(part, "thought", False):
        return False
    return (
        getattr(part, "inline_data", None) is not None
        or getattr(part, "file_data", None) is not None
    )


def _text_of_content(content: Any) -> str:
    if content is None:
        return ""
    parts = getattr(content, "parts", None) or []
    return "".join(part.text for part in parts if _is_visible_text_part(part))


def _text_of_parts(parts: list[Any]) -> str:
    return "".join(part.text for part in parts if _is_visible_text_part(part))


def _visible_parts_of_content(content: Any) -> list[Any]:
    if content is None:
        return []
    return [
        part
        for part in (getattr(content, "parts", None) or [])
        if _is_visible_text_part(part) or _is_media_part(part)
    ]


def _coalesce_text_parts(parts: list[Any]) -> list[Any]:
    """Merge consecutive visible text parts so streamed chunks stay one part."""
    merged: list[Any] = []
    text_buffer: list[str] = []

    def flush() -> None:
        if text_buffer:
            merged.append(types.Part(text="".join(text_buffer)))
            text_buffer.clear()

    for part in parts:
        if _is_visible_text_part(part):
            text_buffer.append(part.text)
        else:
            flush()
            merged.append(part)
    flush()
    return merged


class DecisionPlugin(BasePlugin):
    """Audit model and tool content with the System One decision API.

    Mount it explicitly::

        plugin = build_content_safety(config)
        app = App(name="my_app", root_agent=agent, plugins=[plugin])

    The plugin never changes VeADK defaults: if the caller does not build and
    mount it, no network call is made.
    """

    def __init__(
        self,
        *,
        config: ContentSafetyConfig,
        client: DecisionJudge,
        decider: ThresholdDecider | None = None,
        state_builder: StateBuilder | None = None,
    ):
        if config.provider is not Provider.DECISION:
            raise ValueError("DecisionPlugin requires provider=decision")
        super().__init__(name="content_safety_decision")
        # Deep-copy through model validation so later mutation of the caller's
        # dict cannot change behavior mid-invocation.
        self._config = ContentSafetyConfig.model_validate(config.model_dump())
        self._client = client
        self._decider = decider or ThresholdDecider()
        self._state = state_builder or StateBuilder()
        self._audits: dict[str, dict[Checkpoint, AuditResult]] = {}
        self._stream_buffers: dict[str, list[Any]] = {}
        self._audited_text_hashes: dict[str, set[str]] = {}
        self._audited_state_hashes: dict[str, set[str]] = {}

    # ------------------------------------------------------------------
    # Public inspection helpers
    # ------------------------------------------------------------------
    @property
    def block_message(self) -> str:
        return self._config.block_message

    def last_result(
        self, invocation_id: str, checkpoint: Checkpoint | None = None
    ) -> AuditResult | dict[Checkpoint, AuditResult] | None:
        if checkpoint is not None:
            return self._audits.get(invocation_id, {}).get(checkpoint)
        results = self._audits.get(invocation_id)
        return dict(results) if results else None

    async def close(self) -> None:
        """ADK plugin lifecycle hook: close the pooled HTTP client."""
        close = getattr(self._client, "aclose", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    async def aclose(self) -> None:
        """Backward-compatible alias for the ADK plugin close hook."""
        await self.close()

    # ------------------------------------------------------------------
    # ADK callbacks
    # ------------------------------------------------------------------
    async def before_model_callback(
        self,
        *,
        callback_context: Any,
        llm_request: LlmRequest,
        **kwargs: Any,
    ) -> LlmResponse | None:
        invocation_id = callback_context.invocation_id
        state = self._state.build_before_model(llm_request)
        result = await self._audit(
            invocation_id=invocation_id,
            checkpoint=Checkpoint.BEFORE_MODEL,
            state=state,
        )
        if result.action is AuditAction.BLOCK:
            # The block response is synthetic: never send it back through the
            # decision API as if it were model output. It short-circuits this
            # invocation before any model call, so it must also be marked
            # turn_complete to terminate the turn.
            self._remember_audited_text(invocation_id, self._config.block_message)
            return self._block_response()
        return None

    async def after_model_callback(
        self,
        *,
        callback_context: Any,
        llm_response: LlmResponse,
        **kwargs: Any,
    ) -> LlmResponse | None:
        # Streaming chunks are handled by on_event_callback so that no
        # unaudited partial text or media reaches the caller.
        if getattr(llm_response, "partial", False):
            return None

        invocation_id = callback_context.invocation_id
        content = getattr(llm_response, "content", None)
        visible_parts = _visible_parts_of_content(content)
        if not visible_parts:
            return None
        raw_text = _text_of_content(content)
        state = self._state.build_after_model(llm_response)

        result = await self._audit(
            invocation_id=invocation_id,
            checkpoint=Checkpoint.AFTER_MODEL,
            state=state,
        )
        if raw_text:
            # Text-bearing responses are deduped by the visible text, which
            # also covers mixed text+media responses.
            self._remember_audited_text(invocation_id, raw_text)
        elif any(_is_media_part(part) for part in visible_parts):
            # Media-only responses have no text hash to consume, so remember
            # the audited state and let on_event_callback reuse that audit.
            self._remember_audited_state(invocation_id, state)
        if result.action is AuditAction.BLOCK:
            replacement = self._config.block_message
            self._remember_audited_text(invocation_id, replacement)
            # Preserve the original response's turn_complete: this callback
            # only replaces content, it must not change whether ADK considers
            # the turn finished.
            return llm_response.model_copy(
                update={
                    "content": types.Content(
                        role="model", parts=[types.Part(text=replacement)]
                    ),
                    "partial": False,
                }
            )
        return None

    async def before_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        state = self._state.build_before_tool(tool, tool_args)
        result = await self._audit(
            invocation_id=tool_context.invocation_id,
            checkpoint=Checkpoint.BEFORE_TOOL,
            state=state,
        )
        if result.action is AuditAction.BLOCK:
            return self._blocked_tool_result(result)
        return None

    async def after_tool_callback(
        self,
        *,
        tool: Any,
        tool_args: dict[str, Any],
        tool_context: Any,
        result: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any] | None:
        state = self._state.build_after_tool(tool, tool_args, result)
        audit = await self._audit(
            invocation_id=tool_context.invocation_id,
            checkpoint=Checkpoint.AFTER_TOOL,
            state=state,
        )
        if audit.action is AuditAction.BLOCK:
            return self._blocked_tool_result(audit)
        return None

    async def on_event_callback(
        self,
        *,
        invocation_context: Any,
        event: Any,
        **kwargs: Any,
    ) -> Any | None:
        visible_parts = self._event_parts(event)
        if visible_parts is None:
            return None

        invocation_id = invocation_context.invocation_id
        if getattr(event, "partial", False):
            if visible_parts:
                self._stream_buffers.setdefault(invocation_id, []).extend(visible_parts)
                self._prune_caches()
            if getattr(event, "turn_complete", False):
                buffered = self._stream_buffers.pop(invocation_id, [])
                if buffered:
                    return await self._finalize_stream(invocation_id, event, buffered)
            if visible_parts:
                return self._suppress_visible_parts(event)
            return None

        buffered = self._stream_buffers.pop(invocation_id, [])
        candidate_parts = visible_parts or buffered
        if not candidate_parts:
            return None
        candidate_text = _text_of_parts(candidate_parts)
        if candidate_text and self._consume_audited_text(invocation_id, candidate_text):
            return None
        return await self._finalize_stream(invocation_id, event, candidate_parts)

    async def after_run_callback(
        self, *, invocation_context: Any, **kwargs: Any
    ) -> None:
        invocation_id = invocation_context.invocation_id
        self._stream_buffers.pop(invocation_id, None)
        self._audited_text_hashes.pop(invocation_id, None)
        self._audited_state_hashes.pop(invocation_id, None)
        self._prune_caches()

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    async def _audit(
        self, *, invocation_id: str, checkpoint: Checkpoint, state: StatePayload
    ) -> AuditResult:
        if not self._state_has_content(state):
            result = AuditResult.skipped(
                provider=Provider.DECISION,
                checkpoint=checkpoint,
                reason="no content to audit",
            )
            self._record(invocation_id, result)
            return result

        questions = self._questions()
        try:
            response = await self._client.judge(
                # Keep the stable policy prefix first so repeated requests can
                # reuse it, and keep the dynamic audit payload at the end.
                state=self._api_state(checkpoint, state),
                questions=self._decision_questions(),
            )
        except DecisionClientError as exc:
            # An unauditable oversized request must not fail open when the
            # configured failure policy is allow: the content never reached
            # the decision service.
            on_error = (
                "block"
                if exc.error_type == "request_too_large"
                else self._config.on_error
            )
            result = AuditResult.error(
                provider=Provider.DECISION,
                checkpoint=checkpoint,
                on_error=on_error,
                error_type=exc.error_type,
                reason=exc.message,
            )
        except Exception as exc:  # never let a safety call crash the agent
            logger.exception("unexpected content-safety client failure")
            result = AuditResult.error(
                provider=Provider.DECISION,
                checkpoint=checkpoint,
                on_error=self._config.on_error,
                error_type="unexpected_error",
                reason=str(exc),
            )
        else:
            result = self._decider.decide(
                provider=Provider.DECISION,
                checkpoint=checkpoint,
                raw=response.raw,
                questions=questions,
                on_error=self._config.on_error,
            )

        self._record(invocation_id, result)
        return result

    @staticmethod
    def _state_has_content(state: StatePayload) -> bool:
        return bool(state)

    @staticmethod
    def _api_state(checkpoint: Checkpoint, state: StatePayload) -> StatePayload:
        prefix = f"{STATE_POLICY_PREFIX}\n检查点：{checkpoint.value}。"
        return [{"type": "text", "text": prefix}, *state]

    def _questions(self) -> Mapping[str, QuestionConfig]:
        return self._config.questions

    def _decision_questions(self) -> Mapping[str, DecisionQuestion]:
        return {
            name: DecisionQuestion(
                type=question.type,
                instructions=question.instructions,
            )
            for name, question in self._config.questions.items()
        }

    def _record(self, invocation_id: str, result: AuditResult) -> None:
        self._audits.setdefault(invocation_id, {})[result.checkpoint] = result
        self._prune_caches()
        logger.info(
            "content_safety_audit %s",
            json.dumps(result.to_dict(), ensure_ascii=False),
        )

    def _prune_caches(self) -> None:
        for cache in (
            self._audits,
            self._stream_buffers,
            self._audited_text_hashes,
            self._audited_state_hashes,
        ):
            while len(cache) > _MAX_INVOCATIONS:
                cache.pop(next(iter(cache)), None)

    def _block_response(self) -> LlmResponse:
        return LlmResponse(
            content=types.Content(
                role="model", parts=[types.Part(text=self._config.block_message)]
            ),
            turn_complete=True,
        )

    def _blocked_tool_result(self, result: AuditResult) -> dict[str, Any]:
        return {
            "error": self._config.block_message,
            "blocked": True,
            "content_safety": result.to_dict(),
        }

    def _event_parts(self, event: Any) -> list[Any] | None:
        content = getattr(event, "content", None)
        if content is None:
            return None
        if getattr(content, "role", None) != "model":
            return None
        return _visible_parts_of_content(content)

    def _suppress_visible_parts(self, event: Any) -> Any:
        if any(_is_media_part(part) for part in event.content.parts or []):
            return self._replace_event_parts(event, [types.Part(text="")])
        return self._replace_event_text(event, "")

    def _replace_event_parts(self, event: Any, parts: list[Any]) -> Any:
        content = event.content
        original_parts = list(getattr(content, "parts", None) or [])
        new_parts: list[Any] = []
        replaced = False
        for part in original_parts:
            if _is_visible_text_part(part) or _is_media_part(part):
                if not replaced:
                    new_parts.extend(parts)
                    replaced = True
                continue
            new_parts.append(part)
        if not replaced:
            new_parts.extend(parts)
        if not new_parts:
            # Keep the event shape stable while withholding all visible parts.
            new_parts.append(types.Part(text=""))

        old_text = _text_of_content(content)
        new_content = types.Content(role=content.role, parts=new_parts)
        updates: dict[str, Any] = {"content": new_content}
        if getattr(event, "output", None) == old_text:
            updates["output"] = _text_of_content(new_content)
        return event.model_copy(update=updates)

    def _replace_event_text(self, event: Any, text: str) -> Any:
        content = event.content
        parts = list(getattr(content, "parts", None) or [])
        new_parts: list[Any] = []
        replaced = False
        for part in parts:
            if _is_visible_text_part(part):
                if not replaced:
                    if text:
                        new_parts.append(part.model_copy(update={"text": text}))
                    replaced = True
                continue
            new_parts.append(part)
        if not replaced and text:
            new_parts.append(types.Part(text=text))
        elif replaced and not text:
            # Keep the event shape stable while withholding partial text.
            new_parts.append(types.Part(text=""))

        old_text = _text_of_content(content)
        updates: dict[str, Any] = {
            "content": types.Content(role=content.role, parts=new_parts)
        }
        if getattr(event, "output", None) == old_text:
            updates["output"] = text
        return event.model_copy(update=updates)

    async def _finalize_stream(
        self, invocation_id: str, event: Any, parts: list[Any]
    ) -> Any:
        state = self._state.build_parts(parts, label="model_output")
        if self._consume_audited_state(invocation_id, state):
            return None
        result = await self._audit(
            invocation_id=invocation_id,
            checkpoint=Checkpoint.AFTER_MODEL,
            state=state,
        )
        if result.action is AuditAction.BLOCK:
            return self._replace_event_parts(
                event, [types.Part(text=self._config.block_message)]
            )
        if all(_is_visible_text_part(part) for part in parts):
            return self._replace_event_text(event, _text_of_parts(parts))
        return self._replace_event_parts(event, _coalesce_text_parts(parts))

    @staticmethod
    def _state_hash(state: StatePayload) -> str:
        encoded = json.dumps(
            state, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()

    def _remember_audited_state(self, invocation_id: str, state: StatePayload) -> None:
        self._audited_state_hashes.setdefault(invocation_id, set()).add(
            self._state_hash(state)
        )
        self._prune_caches()

    def _consume_audited_state(self, invocation_id: str, state: StatePayload) -> bool:
        hashes = self._audited_state_hashes.get(invocation_id)
        if not hashes:
            return False
        digest = self._state_hash(state)
        if digest in hashes:
            hashes.discard(digest)
            return True
        return False

    def _remember_audited_text(self, invocation_id: str, text: str) -> None:
        self._audited_text_hashes.setdefault(invocation_id, set()).add(
            hashlib.sha256(text.encode("utf-8")).hexdigest()
        )
        self._prune_caches()

    def _consume_audited_text(self, invocation_id: str, text: str) -> bool:
        hashes = self._audited_text_hashes.get(invocation_id)
        if not hashes:
            return False
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if digest in hashes:
            hashes.discard(digest)
            return True
        return False
