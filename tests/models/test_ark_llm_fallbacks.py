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

import httpx
import pytest
from google.adk.models import LlmResponse
from volcenginesdkarkruntime._exceptions import ArkBadRequestError

from veadk.models.ark_llm import ArkLlm


@pytest.mark.asyncio
async def test_ark_llm_uses_next_model_when_primary_fails(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []

    async def fake_generate(self, responses_args, stream=False):
        calls.append((responses_args["model"], stream))
        if responses_args["model"] == "openai/primary-model":
            raise RuntimeError("primary failed")
        yield LlmResponse(model_version=responses_args["model"])

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    responses = [
        response
        async for response in model._generate_content_with_fallbacks(
            {"input": []}, stream=True
        )
    ]

    assert calls == [
        ("openai/primary-model", True),
        ("openai/fallback-model", True),
    ]
    assert [response.model_version for response in responses] == [
        "openai/fallback-model"
    ]


@pytest.mark.asyncio
async def test_ark_llm_raises_last_error_when_all_models_fail(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )

    async def fake_generate(self, responses_args, stream=False):
        if False:
            yield
        raise RuntimeError(f"{responses_args['model']} failed")

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    with pytest.raises(RuntimeError, match="openai/fallback-model failed"):
        async for _ in model._generate_content_with_fallbacks({"input": []}):
            pass


@pytest.mark.asyncio
async def test_ark_llm_does_not_fallback_after_stream_output(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []

    async def fake_generate(self, responses_args, stream=False):
        calls.append(responses_args["model"])
        yield LlmResponse(model_version=responses_args["model"], partial=True)
        raise RuntimeError("stream interrupted")

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    generator = model._generate_content_with_fallbacks({"input": []}, stream=True)
    first_response = await anext(generator)
    assert first_response.model_version == "openai/primary-model"

    with pytest.raises(RuntimeError, match="stream interrupted"):
        await anext(generator)

    assert calls == ["openai/primary-model"]


@pytest.mark.asyncio
async def test_ark_llm_retries_expired_response_before_fallback(monkeypatch):
    model = ArkLlm(
        model="openai/primary-model",
        fallbacks=["openai/fallback-model"],
    )
    calls = []
    request = httpx.Request("POST", "https://ark.example/v1/responses")
    expired_error = ArkBadRequestError(
        "previous response expired",
        response=httpx.Response(400, request=request),
        body={"code": "InvalidParameter.PreviousResponseNotFound"},
        request_id="request-id",
    )

    async def fake_generate(self, responses_args, stream=False):
        calls.append(
            (responses_args["model"], responses_args.get("previous_response_id"))
        )
        if len(calls) == 1:
            raise expired_error
        if responses_args["model"] == "openai/primary-model":
            raise RuntimeError("primary failed without cache")
        yield LlmResponse(model_version=responses_args["model"])

    monkeypatch.setattr(ArkLlm, "generate_content_via_responses", fake_generate)

    responses = [
        response
        async for response in model._generate_content_with_fallbacks(
            {"input": [], "previous_response_id": "expired-id"}
        )
    ]

    assert calls == [
        ("openai/primary-model", "expired-id"),
        ("openai/primary-model", None),
        ("openai/fallback-model", None),
    ]
    assert responses[0].model_version == "openai/fallback-model"
