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

"""Capture provider response IDs before ADK converts or aggregates responses.

Registration is lazy and idempotent. Each SDK request captures its owning
``call_llm`` span once; advancing a stream never looks up the consumer's span.
LiteLLM-generated IDs are marked on SDK objects without changing their values
or serialized fields. HTTP request IDs are never used as response IDs.
"""

from __future__ import annotations

import functools
import inspect
from contextvars import ContextVar

from opentelemetry import trace
from opentelemetry.sdk.trace import Span as SDKSpan

from veadk.tracing.telemetry.timing import response_field

GEN_AI_RESPONSE_ID = "gen_ai.response.id"
_patched = False
_active_recorder: ContextVar[ResponseIdRecorder | None] = ContextVar(
    "veadk_response_id_recorder", default=None
)
_GENERATED_ID = "_veadk_generated_response_id"
_WRAPPED = "_veadk_response_id_wrapped"


def _clear_previous_attempt(span: trace.Span | None) -> None:
    # OTel has no public attribute removal API. Use the SDK's locked attribute
    # map only to discard a provisional ID when a new attempt starts. Failed
    # attempts retain their ID on their own model_request span. This seam is
    # covered by fallback-without-ID tests against the supported OTel SDK.
    if isinstance(span, SDKSpan) and span.is_recording():
        with span._lock:
            if span.is_recording() and span._attributes is not None:
                span._attributes.pop(GEN_AI_RESPONSE_ID, None)


class ResponseIdRecorder:
    """One SDK attempt, isolated from other requests and stream consumers."""

    def __init__(self, *, attempt: trace.Span | None = None):
        current = trace.get_current_span()
        self.owner = (
            current
            if _patched and getattr(current, "name", None) == "call_llm"
            else None
        )
        self.attempt = attempt if self.owner is not None else None
        self.response_id: str | None = None
        self._token = None
        _clear_previous_attempt(self.owner)

    def __enter__(self):
        self._token = _active_recorder.set(self)
        return self

    def __exit__(self, *args):
        _active_recorder.reset(self._token)

    def observe(self, response: object, *, field: str = "id") -> None:
        if self.owner is None or self.response_id is not None:
            return
        value = response_field(response, field)
        if not isinstance(value, str) or not value.strip():
            return
        if value == getattr(response, _GENERATED_ID, None):
            return
        self.response_id = value
        for span in (self.owner, self.attempt):
            if span is not None and span.is_recording():
                span.set_attribute(GEN_AI_RESPONSE_ID, value)


class _ResponseIdStream:
    """Transparent async iterator; ID collection never buffers or reorders."""

    def __init__(self, response, recorder, *, field="id"):
        self._response = response
        self._iterator = response.__aiter__()
        self._recorder = recorder
        self._field = field

    def __getattr__(self, name):
        return getattr(self._response, name)

    def __aiter__(self):
        return self

    async def __anext__(self):
        chunk = await anext(self._iterator)
        self._recorder.observe(chunk, field=self._field)
        return chunk

    async def aclose(self):
        close = getattr(self._response, "aclose", None)
        if close is None:
            close = getattr(self._iterator, "aclose", None)
        if close is not None:
            await close()


def _mark_generated_ids(cls) -> None:
    original = cls.__init__
    if getattr(original, _WRAPPED, False):
        return
    # Both supported LiteLLM constructors generate an ID only when id is None.
    # Compute the positional index once, preserving their original signatures.
    id_index = list(inspect.signature(original).parameters).index("id") - 1

    @functools.wraps(original)
    def initialize(self, *args, **kwargs):
        supplied_id = kwargs.get("id", args[id_index] if len(args) > id_index else None)
        original(self, *args, **kwargs)
        object.__setattr__(
            self, _GENERATED_ID, self.id if supplied_id is None else None
        )

    setattr(initialize, _WRAPPED, True)
    cls.__init__ = initialize


def register() -> None:
    """Register Chat and native Gemini capture once, only with VeADK tracing."""
    global _patched
    if _patched:
        return
    from google.adk.models.lite_llm import LiteLLMClient
    from google.genai.models import AsyncModels
    from litellm import ModelResponse
    from litellm.types.utils import ModelResponseStream

    _mark_generated_ids(ModelResponse)
    _mark_generated_ids(ModelResponseStream)
    original = LiteLLMClient.acompletion
    if not getattr(original, _WRAPPED, False):

        @functools.wraps(original)
        async def acompletion(self, *args, **kwargs):
            active = _active_recorder.get()
            recorder = active or ResponseIdRecorder()
            response = await original(self, *args, **kwargs)
            if recorder.owner is None:
                return response
            if kwargs.get("stream"):
                # TimedLiteLLMClient already owns iteration and stream closing.
                return response if active else _ResponseIdStream(response, recorder)
            recorder.observe(response)
            return response

        setattr(acompletion, _WRAPPED, True)
        LiteLLMClient.acompletion = acompletion

    def wrap_gemini(method, streaming):
        if getattr(method, _WRAPPED, False):
            return method

        @functools.wraps(method)
        async def generate(self, *args, **kwargs):
            recorder = ResponseIdRecorder()
            response = await method(self, *args, **kwargs)
            if recorder.owner is None:
                return response
            if streaming:
                return _ResponseIdStream(response, recorder, field="response_id")
            recorder.observe(response, field="response_id")
            return response

        setattr(generate, _WRAPPED, True)
        return generate

    AsyncModels.generate_content = wrap_gemini(AsyncModels.generate_content, False)
    AsyncModels.generate_content_stream = wrap_gemini(
        AsyncModels.generate_content_stream, True
    )
    _patched = True
