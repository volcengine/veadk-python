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

"""Regression tests against the actual ADK -> client request boundary."""

from __future__ import annotations

import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.models.llm_request import LlmRequest
from google.genai import types
from litellm import ModelResponse

from veadk.models.retrying_lite_llm import RetryingLiteLlm


class RecordingClient(LiteLLMClient):
    def __init__(self):
        self.requests = []

    async def acompletion(self, **kwargs):
        self.requests.append(kwargs)
        return ModelResponse(
            model="openai/context-test",
            choices=[{"message": {"role": "assistant", "content": "ok"}}],
        )


def make_model(client, **overrides):
    return RetryingLiteLlm(
        model="openai/context-test",
        llm_client=client,
        context_compression={
            "context_window": 4096,
            "output_reserve": 512,
            "safety_margin": 256,
            **overrides,
        },
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("oversized", ["user", "system", "tools"])
async def test_protected_input_over_budget_never_reaches_client(oversized):
    client = RecordingClient()
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    large = "上下文安全边界" * 5000
    if oversized == "user":
        request.contents[0].parts[0].text = large
    elif oversized == "system":
        request.config.system_instruction = large
    else:
        request.config.tools = [
            types.Tool(
                function_declarations=[
                    types.FunctionDeclaration(name="read", description=large)
                ]
            )
        ]
    with pytest.raises(ValueError, match="[Cc]ontext"):
        _ = [r async for r in make_model(client).generate_content_async(request)]
    assert client.requests == []


@pytest.mark.asyncio
async def test_short_request_unchanged_and_policy_never_sent_to_provider():
    client = RecordingClient()
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    _ = [r async for r in make_model(client).generate_content_async(request)]
    assert len(client.requests) == 1
    assert client.requests[0]["messages"] == [{"role": "user", "content": "hello"}]
    assert "context_compression" not in client.requests[0]


@pytest.mark.asyncio
async def test_default_seed_output_reservation_does_not_set_a_generation_cap():
    client = RecordingClient()
    model = RetryingLiteLlm(
        model="openai/doubao-seed-2-1-pro-260628", llm_client=client
    )
    request = LlmRequest(
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])]
    )
    _ = [r async for r in model.generate_content_async(request)]
    from veadk.context.budget import output_limit

    assert output_limit(client.requests[0]) is None
    assert model.context_compression_status["state"] == "configured"
