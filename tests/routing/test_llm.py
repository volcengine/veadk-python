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
from google.genai import types
from pydantic import Field

from veadk.configs.routing_configs import SimpleModelConfig
from veadk.routing.context import RouteSelection, set_route_selection
from veadk.routing.llm import RoutingLlm
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime
from veadk.routing.store import RouteStore


class FakeLlm(BaseLlm):
    model: str
    fail_before: bool = False
    fail_after: bool = False
    error: Exception | None = Field(default=None, exclude=True)
    seen_models: list[str] = Field(default_factory=list)
    calls: int = 0

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        self.seen_models.append(llm_request.model)
        if self.error is not None:
            raise self.error
        if self.fail_before:
            raise RuntimeError("before")
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.model)])
        )
        if self.fail_after:
            raise RuntimeError("after")


def build(fail_before=False, fail_after=False, error=None):
    strong = FakeLlm(model="strong")
    simple = FakeLlm(
        model="simple", fail_before=fail_before, fail_after=fail_after, error=error
    )
    runtime = SimpleModelRuntime(config=SimpleModelConfig(name="simple"), llm=simple)
    registry = ModelRegistry(runtimes=[runtime])
    store = RouteStore()
    router = RoutingLlm(
        model="strong",
        strong_model=strong,
        runtimes=[runtime],
        registry=registry,
        store=store,
    )
    return router, strong, simple, store


def request():
    return LlmRequest(
        model="strong",
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
    )


async def collect(router, req):
    return [item async for item in router.generate_content_async(req)]


@pytest.mark.asyncio
async def test_no_selection_uses_strong_model():
    router, strong, simple, _ = build()
    set_route_selection(None)
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "strong"
    assert strong.calls == 1
    assert simple.calls == 0


@pytest.mark.asyncio
async def test_simple_selection_uses_configured_model():
    router, strong, simple, _ = build()
    set_route_selection(
        RouteSelection(
            route="simple",
            reason="ok",
            invocation_id="inv",
            model_name="simple",
        )
    )
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "simple"
    assert simple.calls == 1
    assert strong.calls == 0
    assert simple.seen_models == ["simple"]


@pytest.mark.asyncio
async def test_unknown_selected_model_falls_back_to_strong():
    router, strong, simple, _ = build()
    set_route_selection(
        RouteSelection(
            route="simple",
            reason="ok",
            invocation_id="inv",
            model_name="missing",
        )
    )
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "strong"
    assert strong.calls == 1


@pytest.mark.asyncio
async def test_pre_chunk_failure_falls_back_and_upgrades_session():
    router, strong, simple, store = build(fail_before=True)
    set_route_selection(
        RouteSelection(
            route="simple",
            reason="ok",
            invocation_id="inv",
            session_id="s1",
            model_name="simple",
        )
    )
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "strong"
    assert strong.calls == 1
    assert store.session_upgraded("s1") is True


@pytest.mark.asyncio
async def test_post_chunk_failure_is_not_retried():
    router, strong, simple, _ = build(fail_after=True)
    set_route_selection(
        RouteSelection(
            route="simple",
            reason="ok",
            invocation_id="inv",
            model_name="simple",
        )
    )
    with pytest.raises(RuntimeError, match="after"):
        await collect(router, request())
    assert strong.calls == 0


@pytest.mark.asyncio
async def test_capability_error_marks_model_unhealthy():
    error = RuntimeError("bad request")
    error.status_code = 400
    router, strong, simple, _ = build(error=error)
    set_route_selection(
        RouteSelection(
            route="simple",
            reason="ok",
            invocation_id="inv",
            model_name="simple",
        )
    )
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "strong"
    assert router.registry.first_available(request()) is None


@pytest.mark.asyncio
async def test_shadow_route_uses_strong_even_with_model_name():
    router, strong, simple, _ = build()
    set_route_selection(
        RouteSelection(
            route="strong",
            reason="shadow",
            invocation_id="inv",
            model_name="simple",
            shadow=True,
        )
    )
    responses = await collect(router, request())
    assert responses[0].content.parts[0].text == "strong"
    assert simple.calls == 0
