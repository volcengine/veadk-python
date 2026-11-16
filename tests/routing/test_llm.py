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

from collections.abc import AsyncGenerator

import pytest
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.adk.tools import FunctionTool
from google.genai import types
from pydantic import Field

from veadk.configs.routing_configs import SimpleModelConfig
from veadk.routing.llm import RoutingLlm
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime
from veadk.routing.store import RouteStore


class FakeLlm(BaseLlm):
    model: str
    seen_requests: list[LlmRequest] = Field(default_factory=list, exclude=True)

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.seen_requests.append(llm_request)
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.model)])
        )


class FakeClassifier:
    def __init__(self):
        self.closed = False

    async def aclose(self):
        self.closed = True


def build():
    strong = FakeLlm(model="strong")
    simple = FakeLlm(model="simple")
    runtime = SimpleModelRuntime(config=SimpleModelConfig(name="simple"), llm=simple)
    classifier = FakeClassifier()
    router = RoutingLlm(
        model="strong",
        strong_model=strong,
        runtimes=[runtime],
        registry=ModelRegistry(runtimes=[runtime]),
        store=RouteStore(),
        classifier=classifier,
    )
    return router, strong, simple, classifier


def ping() -> str:
    """Return a fixed value."""
    return "pong"


def request():
    return LlmRequest(
        model="strong",
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
        tools_dict={"tool": FunctionTool(ping)},
    )


@pytest.mark.asyncio
async def test_direct_path_always_uses_the_strong_model():
    router, strong, simple, _ = build()
    req = request()
    responses = [
        item async for item in router.generate_content_async(req, stream=False)
    ]
    assert responses[0].content.parts[0].text == "strong"
    assert len(strong.seen_requests) == 1
    assert simple.seen_requests == []


@pytest.mark.asyncio
async def test_direct_path_does_not_mutate_the_caller_request():
    router, strong, _, _ = build()
    req = request()
    tools = req.tools_dict
    await anext(router.generate_content_async(req))
    assert req.model == "strong"
    assert req.tools_dict is tools
    forwarded = strong.seen_requests[0]
    assert forwarded is not req
    assert forwarded.tools_dict is not req.tools_dict


@pytest.mark.asyncio
async def test_aclose_closes_the_classifier_client():
    router, _, _, classifier = build()
    await router.aclose()
    assert classifier.closed is True
