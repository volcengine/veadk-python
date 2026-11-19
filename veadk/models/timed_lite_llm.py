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

"""Capture LiteLLM SDK receipt timestamps before response aggregation."""

from google.adk.models.lite_llm import LiteLLMClient
from litellm import CustomStreamWrapper

from veadk.tracing.telemetry.litellm_response_id import ResponseIdRecorder
from veadk.tracing.telemetry.timing import (
    ModelTiming,
    response_field,
    litellm_output_type,
    output_tokens_for_tpot,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


def _stream_output_tokens(response) -> int | None:
    """Read upstream metadata, excluding LiteLLM's synthesized usage and stop.

    This SDK-internal compatibility seam is tested against supported versions.
    Unknown providers/wrappers deliberately omit TPOT instead of estimating it.
    """
    if (
        not isinstance(response, CustomStreamWrapper)
        or response.custom_llm_provider != "openai"
    ):
        return None
    if response.received_finish_reason not in {"stop", "tool_calls", "function_call"}:
        return None
    usage = None
    reasoning_seen = False
    for chunk in response.chunks:
        if response_field(chunk, "usage") is not None:
            usage = response_field(chunk, "usage")
        choices = response_field(chunk, "choices", []) or []
        if len(choices) > 1:
            return None
        for choice in choices:
            if response_field(choice, "index") != 0:
                return None
            delta = response_field(choice, "delta")
            if any(
                response_field(delta, name)
                for name in ("audio", "refusal", "reasoning_content_encrypted")
            ):
                return None
            if response_field(delta, "content") and not isinstance(
                response_field(delta, "content"), str
            ):
                return None
            reasoning_seen |= bool(response_field(delta, "reasoning_content"))
    return output_tokens_for_tpot(usage, "completion_tokens", reasoning_seen)


class TimedLiteLLMClient(LiteLLMClient):
    async def acompletion(self, model, messages, tools, **kwargs):
        timing = ModelTiming(streaming=bool(kwargs.get("stream")), model=model)
        if kwargs.get("n", 1) != 1:
            timing.disable_tpot()
        recorder = ResponseIdRecorder(attempt=timing.span)
        try:
            with recorder:
                response = await super().acompletion(model, messages, tools, **kwargs)
        except BaseException as error:
            timing.__exit__(type(error), error, error.__traceback__)
            raise
        if not timing.streaming:
            timing.__exit__(None, None, None)
            return response
        return _TimedStream(response, timing, recorder)


class _TimedStream:
    """End an attempt even when a returned stream is closed before iteration."""

    def __init__(self, response, timing, recorder):
        self._response = response
        self._iterator = response.__aiter__()
        self._timing = timing
        self._recorder = recorder
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed:
            raise StopAsyncIteration
        try:
            with self._recorder:
                chunk = await anext(self._iterator)
        except StopAsyncIteration:
            await self._finish(None)
            raise
        except BaseException as error:
            await self._finish(error)
            raise
        # Native LiteLLM streams record at the raw boundary while advancing.
        # Normalized IDs may be synthesized or lose provenance after copying.
        if not isinstance(self._response, CustomStreamWrapper):
            self._recorder.observe(chunk)
        self._timing.observe(litellm_output_type(chunk))
        return chunk

    async def _finish(self, error):
        if self._closed:
            return
        self._closed = True
        try:
            close = getattr(self._response, "aclose", None)
            if close is not None:
                await close()
        except BaseException as close_error:
            self._timing.__exit__(
                type(close_error), close_error, close_error.__traceback__
            )
            raise
        if error is None:
            try:
                self._timing.complete(_stream_output_tokens(self._response))
            except Exception:
                self._timing.disable_tpot()
                logger.warning("Skipping TPOT because stream metadata is unavailable")
        self._timing.__exit__(
            type(error) if error is not None else None,
            error,
            error.__traceback__ if error is not None else None,
        )

    async def aclose(self):
        await self._finish(GeneratorExit())
