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

from types import SimpleNamespace

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.configs.routing_configs import QueryRoutingConfig
from veadk.routing.callback import build_before_model_callback
from veadk.routing.context import (
    RouteSelection,
    get_route_selection,
    set_route_selection,
)
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime
from veadk.routing.store import RouteStore


class FakeOuterLlm:
    model = "simple"


class Classifier:
    def __init__(self, selection):
        self.selection = selection
        self.calls = 0
        self.registry = ModelRegistry(
            runtimes=[
                SimpleModelRuntime(
                    config=QueryRoutingConfig(simple_models=["simple"]).simple_models[
                        0
                    ],
                    llm=FakeOuterLlm(),
                )
            ]
        )

    async def classify(self, llm_request, *, invocation_id, session_id=""):
        self.calls += 1
        return self.selection


def request():
    return LlmRequest(
        model="strong",
        contents=[types.Content(role="user", parts=[types.Part(text="hello")])],
    )


def context(state=None, session_id="s1", invocation_id="inv1"):
    return SimpleNamespace(
        invocation_id=invocation_id,
        session=SimpleNamespace(id=session_id),
        state=state if state is not None else {},
    )


def config():
    return QueryRoutingConfig(simple_models=["simple"])


@pytest.mark.asyncio
async def test_cache_miss_classifies_and_writes_state():
    set_route_selection(None)
    selection = RouteSelection(
        route="simple", reason="ok", invocation_id="inv1", model_name="simple"
    )
    classifier = Classifier(selection)
    callback = build_before_model_callback(classifier, RouteStore(), config())
    state = {}

    assert await callback(context(state), request()) is None
    assert classifier.calls == 1
    assert state["temp:veadk_query_route"] == "simple"
    assert get_route_selection() == selection


@pytest.mark.asyncio
async def test_same_invocation_is_classified_once():
    set_route_selection(None)
    selection = RouteSelection(
        route="simple", reason="ok", invocation_id="inv1", model_name="simple"
    )
    classifier = Classifier(selection)
    store = RouteStore()
    callback = build_before_model_callback(classifier, store, config())

    first_state = {}
    second_state = {}
    await callback(context(first_state), request())
    await callback(context(second_state), request())

    assert classifier.calls == 1
    assert second_state["temp:veadk_query_route"] == "simple"


@pytest.mark.asyncio
async def test_cached_strong_skips_classification():
    set_route_selection(None)
    classifier = Classifier(
        RouteSelection(route="simple", reason="ok", invocation_id="inv")
    )
    callback = build_before_model_callback(classifier, RouteStore(), config())
    state = {"temp:veadk_query_route": "strong"}

    await callback(context(state), request())
    assert classifier.calls == 0
    assert get_route_selection().route == "strong"
    assert get_route_selection().reason == "invocation_cached"


@pytest.mark.asyncio
async def test_cached_simple_rechecks_local_capability():
    set_route_selection(None)
    classifier = Classifier(
        RouteSelection(route="simple", reason="ok", invocation_id="inv")
    )
    callback = build_before_model_callback(classifier, RouteStore(), config())
    state = {"temp:veadk_query_route": "simple"}

    await callback(context(state), request())
    assert classifier.calls == 0
    assert get_route_selection().route == "simple"
    assert get_route_selection().model_name == "simple"


@pytest.mark.asyncio
async def test_cached_simple_without_capable_model_routes_strong():
    set_route_selection(None)
    classifier = Classifier(
        RouteSelection(route="simple", reason="ok", invocation_id="inv")
    )
    callback = build_before_model_callback(classifier, RouteStore(), config())
    req = request()
    req.tools_dict = {"tool": object()}

    await callback(context({"temp:veadk_query_route": "simple"}), req)
    assert classifier.calls == 0
    assert get_route_selection().route == "strong"
    assert get_route_selection().reason == "no_capable_simple_model"


@pytest.mark.asyncio
async def test_upgraded_session_skips_classification():
    set_route_selection(None)
    classifier = Classifier(
        RouteSelection(route="simple", reason="ok", invocation_id="inv")
    )
    store = RouteStore()
    store.upgrade_session("s1")
    callback = build_before_model_callback(classifier, store, config())

    await callback(context({}), request())
    assert classifier.calls == 0
    assert get_route_selection().route == "strong"
    assert get_route_selection().reason == "session_upgraded"


@pytest.mark.asyncio
async def test_selection_that_upgrades_session_is_persisted():
    set_route_selection(None)
    selection = RouteSelection(
        route="strong",
        reason="is_complex_above_threshold",
        invocation_id="inv1",
        upgrade_session=True,
    )
    classifier = Classifier(selection)
    store = RouteStore()
    callback = build_before_model_callback(classifier, store, config())
    state = {}

    await callback(context(state), request())
    assert store.session_upgraded("s1") is True
    assert state["temp:veadk_query_route"] == "strong"


@pytest.mark.asyncio
async def test_missing_state_object_still_routes():
    set_route_selection(None)
    selection = RouteSelection(
        route="simple", reason="ok", invocation_id="inv1", model_name="simple"
    )
    classifier = Classifier(selection)
    callback = build_before_model_callback(classifier, RouteStore(), config())
    ctx = SimpleNamespace(
        invocation_id="inv1", session=SimpleNamespace(id="s1"), state=None
    )

    await callback(ctx, request())
    assert get_route_selection() == selection
