# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Capture the response ID carried by the three model wire protocols.

The ID is the one the provider returns in the response body:

- Responses API: top-level ``id`` on a response, or ``response.id`` on the
  ``response.created`` / ``response.in_progress`` / terminal events. Incremental
  events such as ``response.output_text.delta`` carry no response ID.
- Chat Completions: ``id`` on the completion and on every stream chunk.
- Messages (Anthropic wire format): top-level ``id`` on a message, or
  ``message.id`` on the ``message_start`` event. Later stream events carry no
  message ID.

This module is additive on purpose: it never reads or writes the existing
``gen_ai.response.id`` behavior (which follows ``X-Request-Id`` for Ark chat).
It publishes to a dedicated ``veadk.response.id`` span attribute and one new
``[llm-dispatch]`` log line per request attempt, so existing logs and fields
keep their current shape.

Defensive rules: blank or non-string IDs, missing fields and empty response or
message objects are ignored; extraction and span writes are wrapped so a
malformed payload can never fail the model call. The log renders the ID as a
single bounded line while the span keeps the raw value.
"""

from __future__ import annotations

import functools
import re
import threading
from collections.abc import Mapping
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SDKSpan

from veadk.tracing.telemetry.timing import response_field
from veadk.utils.logger import get_logger, safe_info

logger = get_logger(__name__)

RESPONSE_ID_ATTRIBUTE = "veadk.response.id"
_LOG_ID_LIMIT = 128
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_WRAPPED = "_veadk_protocol_response_id_wrapped"
_register_lock = threading.Lock()
_patched = False

_active_capture: ContextVar[ProtocolResponseCapture | None] = ContextVar(
    "veadk_protocol_response_id_capture", default=None
)


@dataclass(frozen=True)
class ProtocolResponseId:
    """A provider response ID and the wire protocol that carried it."""

    api: str
    value: str


def _text(value: Any) -> str | None:
    if isinstance(value, str) and value.strip():
        return value
    return None


def _with_id(api: str, value: Any) -> ProtocolResponseId | None:
    response_id = _text(value)
    if response_id is None:
        return None
    return ProtocolResponseId(api, response_id)


def _log_id(value: str) -> str:
    """Keep the log line single-line and bounded; spans keep the raw ID."""

    return _CONTROL_CHARS.sub("?", value)[:_LOG_ID_LIMIT]


def _has_field(value: Any, name: str) -> bool:
    if isinstance(value, Mapping):
        return name in value
    return hasattr(value, name)


def _extract(value: Any) -> ProtocolResponseId | None:
    event_type = _text(response_field(value, "type"))

    if event_type == "message_start":
        return _with_id(
            "messages", response_field(response_field(value, "message"), "id")
        )

    if event_type is not None and event_type.startswith("response."):
        response = response_field(value, "response")
        if response is not None:
            return _with_id("responses", response_field(response, "id"))
        return None

    object_type = _text(response_field(value, "object"))
    if object_type == "response":
        return _with_id("responses", response_field(value, "id"))
    if object_type in ("chat.completion", "chat.completion.chunk"):
        return _with_id("chat", response_field(value, "id"))

    if event_type == "message":
        # Anthropic message objects carry `model` and `stop_reason`; Responses
        # output items also use `type: message` but have neither field.
        if response_field(value, "model") is not None and (
            _has_field(value, "stop_reason") or _has_field(value, "stop_sequence")
        ):
            return _with_id("messages", response_field(value, "id"))
        return None

    # Tolerate OpenAI-compatible SDK objects that omit `object`: a completion
    # shaped value still proved itself with an id, choices and created time.
    if object_type is None and event_type is None:
        if (
            response_field(value, "choices") is not None
            and response_field(value, "created") is not None
        ):
            return _with_id("chat", response_field(value, "id"))
    return None


def extract_response_id(value: Any) -> ProtocolResponseId | None:
    """Return the provider response ID carried by ``value``, if any.

    ``value`` may be a raw SSE event, an SDK response object, or a mapping. The
    function is best-effort telemetry: malformed or unknown shapes return
    ``None`` and never affect the model call.
    """

    if value is None:
        return None
    try:
        return _extract(value)
    except Exception as error:  # noqa: BLE001 - telemetry must not break calls
        logger.debug("Skipping protocol response id extraction: %s", error)
        return None


def _is_recording(span: trace.Span | None) -> bool:
    return span is not None and span.is_recording()


def _clear_attribute(span: trace.Span | None, key: str) -> None:
    """Drop a provisional value when a new attempt starts on the same span."""

    if _is_recording(span) and isinstance(span, SDKSpan):
        with span._lock:
            if span.is_recording() and span._attributes is not None:
                span._attributes.pop(key, None)


def _owner_span() -> trace.Span | None:
    """Return the enclosing ADK model span, when there is one.

    ADK opens ``call_llm`` around the flow; its LiteLLM/Gemini model wrappers
    open ``generate_content <model>`` closer to the SDK call, which is the span
    visible here. Other caller spans are left untouched.
    """

    current = trace.get_current_span()
    name = getattr(current, "name", None)
    if isinstance(name, str) and (
        name == "call_llm" or name.startswith("generate_content")
    ):
        return current
    return None


class ProtocolResponseCapture:
    """One model request attempt; publishes the first response ID it sees."""

    def __init__(
        self,
        *,
        model: Any,
        stream: bool,
        attempt_span: trace.Span | None = None,
    ) -> None:
        self.model = str(model)
        self.stream = bool(stream)
        self.attempt_span = attempt_span
        self.owner_span = _owner_span()
        self.response_id: ProtocolResponseId | None = None
        try:
            _clear_attribute(self.owner_span, RESPONSE_ID_ATTRIBUTE)
        except Exception as error:  # noqa: BLE001 - telemetry must not break calls
            logger.debug("Unable to clear protocol response id from span: %s", error)

    def __enter__(self) -> ProtocolResponseCapture:
        self._token = _active_capture.set(self)
        return self

    def __exit__(self, *args: object) -> None:
        _active_capture.reset(self._token)

    def observe(self, value: Any) -> None:
        """Record one response or stream event; only the first ID is kept."""

        if self.response_id is not None:
            return
        response_id = extract_response_id(value)
        if response_id is None:
            return
        self.response_id = response_id
        self._publish(response_id)

    def _publish(self, response_id: ProtocolResponseId) -> None:
        # A broken owner span must not cost the attempt span its own ID.
        for span in (self.owner_span, self.attempt_span):
            try:
                if _is_recording(span):
                    span.set_attribute(RESPONSE_ID_ATTRIBUTE, response_id.value)
            except Exception as error:  # noqa: BLE001 - telemetry must not break calls
                logger.debug("Unable to record protocol response id on span: %s", error)
        safe_info(
            logger,
            f"[llm-dispatch] response id model={self.model} api={response_id.api} "
            f"stream={self.stream} response_id={_log_id(response_id.value)}",
        )


def observe_response(value: Any) -> None:
    """Feed ``value`` to the active capture, if a model attempt is active."""

    capture = _active_capture.get()
    if capture is not None:
        capture.observe(value)


def _wrap_method(owner: type, name: str) -> None:
    original = getattr(owner, name, None)
    if original is None or getattr(original, _WRAPPED, False):
        return

    if name == "chunk_parser":

        @functools.wraps(original)
        def chunk_parser(self, chunk, *args, **kwargs):
            observe_response(chunk)
            return original(self, chunk, *args, **kwargs)

        setattr(chunk_parser, _WRAPPED, True)
        setattr(owner, name, chunk_parser)
        return

    @functools.wraps(original)
    def transform_parsed_response(self, completion_response, *args, **kwargs):
        observe_response(completion_response)
        return original(self, completion_response, *args, **kwargs)

    setattr(transform_parsed_response, _WRAPPED, True)
    setattr(owner, name, transform_parsed_response)


def register_litellm_protocol_patches() -> None:
    """Expose raw Anthropic messages to the active capture.

    LiteLLM normalizes the Messages wire format into chat-completions objects
    and substitutes a generated ``chatcmpl-`` ID, so the real ``message.id`` is
    only visible before that conversion. Registration is lazy and idempotent;
    missing or incompatible LiteLLM layouts leave the non-Anthropic protocols
    working unchanged.
    """

    global _patched
    if _patched:
        return
    with _register_lock:
        if _patched:
            return
        try:
            from litellm.llms.anthropic.chat.handler import ModelResponseIterator
            from litellm.llms.anthropic.chat.transformation import AnthropicConfig
        except Exception as error:  # noqa: BLE001 - optional compatibility seam
            logger.debug("Anthropic response-id seam unavailable: %s", error)
            return

        _wrap_method(ModelResponseIterator, "chunk_parser")
        _wrap_method(AnthropicConfig, "transform_parsed_response")
        _patched = True
