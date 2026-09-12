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

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from google.adk.models.lite_llm import LiteLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools.base_tool import BaseTool
from google.genai import types

from veadk.models.retrying_lite_llm import RetryingLiteLlm


class _RateLimitError(RuntimeError):
    status_code = 429

    def __init__(self, retry_after: str = "0") -> None:
        super().__init__("rate limited")
        self.response = SimpleNamespace(headers={"Retry-After": retry_after})


def _request() -> LlmRequest:
    return LlmRequest(
        model="openai/test-model",
        contents=[
            types.Content(role="user", parts=[types.Part.from_text(text="hello")])
        ],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("retry", [False, True])
@pytest.mark.parametrize("stream", [False, True])
async def test_snapshot_preserves_live_tools_and_isolates_request_data(
    monkeypatch: pytest.MonkeyPatch, retry: bool, stream: bool
) -> None:
    tool = BaseTool(name="live_tool", description="Tool with asynchronous state")
    tool.pending = asyncio.get_running_loop().create_future()
    request = _request()
    request.tools_dict = {tool.name: tool}
    request.config.temperature = 0.5
    seen: list[LlmRequest] = []

    async def generate(_self, llm_request, stream=False):
        seen.append(llm_request)
        assert llm_request.tools_dict[tool.name] is tool
        assert llm_request.contents[0].parts[0].text == "hello"
        assert llm_request.config.temperature == 0.5
        if retry and len(seen) == 1:
            llm_request.contents[0].parts[0].text = "mutated"
            llm_request.config.temperature = 0.1
            llm_request.tools_dict.clear()
            raise _RateLimitError()
        yield LlmResponse(content=types.Content(role="model", parts=[]))

    monkeypatch.setattr(LiteLlm, "generate_content_async", generate)
    model = RetryingLiteLlm(model="openai/test-model")
    try:
        responses = [
            response
            async for response in model.generate_content_async(request, stream=stream)
        ]
    finally:
        tool.pending.cancel()

    assert len(responses) == 1
    assert len(seen) == (2 if retry else 1)
    if retry:
        assert seen[1] is not request
        assert seen[1].tools_dict is not request.tools_dict


@pytest.mark.asyncio
async def test_retries_one_pre_output_429_from_pristine_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen_lengths: list[int] = []
    sleeps: list[float] = []

    async def generate(
        _self: LiteLlm,
        request: LlmRequest,
        stream: bool = False,
    ):
        del stream
        seen_lengths.append(len(request.contents))
        request.contents.append(
            types.Content(role="user", parts=[types.Part.from_text(text="mutated")])
        )
        if len(seen_lengths) == 1:
            raise _RateLimitError("0.25")
        yield LlmResponse(content=types.Content(role="model", parts=[]))

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    monkeypatch.setattr(LiteLlm, "generate_content_async", generate)
    monkeypatch.setattr("veadk.models.retrying_lite_llm.asyncio.sleep", sleep)
    model = RetryingLiteLlm(model="openai/test-model")

    responses = [
        response async for response in model.generate_content_async(_request())
    ]

    assert len(responses) == 1
    assert seen_lengths == [1, 1]
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_does_not_replay_after_any_llm_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    async def generate(
        _self: LiteLlm,
        request: LlmRequest,
        stream: bool = False,
    ):
        nonlocal attempts
        del request, stream
        attempts += 1
        yield LlmResponse(content=types.Content(role="model", parts=[]))
        raise _RateLimitError()

    monkeypatch.setattr(LiteLlm, "generate_content_async", generate)
    model = RetryingLiteLlm(model="openai/test-model")

    with pytest.raises(_RateLimitError):
        _ = [response async for response in model.generate_content_async(_request())]

    assert attempts == 1


@pytest.mark.asyncio
async def test_does_not_retry_non_429(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0

    async def generate(
        _self: LiteLlm,
        request: LlmRequest,
        stream: bool = False,
    ):
        nonlocal attempts
        del request, stream
        attempts += 1
        raise RuntimeError("not a rate limit")
        yield  # pragma: no cover

    monkeypatch.setattr(LiteLlm, "generate_content_async", generate)
    model = RetryingLiteLlm(model="openai/test-model")

    with pytest.raises(RuntimeError, match="not a rate limit"):
        _ = [response async for response in model.generate_content_async(_request())]

    assert attempts == 1
