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

from veadk.tracing.telemetry.timing import ModelTiming, litellm_output_type


class TimedLiteLLMClient(LiteLLMClient):
    async def acompletion(self, model, messages, tools, **kwargs):
        timing = ModelTiming(streaming=bool(kwargs.get("stream")), model=model)
        try:
            response = await super().acompletion(model, messages, tools, **kwargs)
        except BaseException as error:
            timing.__exit__(type(error), error, error.__traceback__)
            raise
        if not timing.streaming:
            timing.__exit__(None, None, None)
            return response
        return _TimedStream(response, timing)


class _TimedStream:
    """End an attempt even when a returned stream is closed before iteration."""

    def __init__(self, response, timing):
        self._response = response
        self._iterator = response.__aiter__()
        self._timing = timing
        self._closed = False

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._closed:
            raise StopAsyncIteration
        try:
            chunk = await anext(self._iterator)
        except StopAsyncIteration:
            await self._finish(None)
            raise
        except BaseException as error:
            await self._finish(error)
            raise
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
        self._timing.__exit__(
            type(error) if error is not None else None,
            error,
            error.__traceback__ if error is not None else None,
        )

    async def aclose(self):
        await self._finish(GeneratorExit())
