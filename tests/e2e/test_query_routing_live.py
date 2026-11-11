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
"""Opt-in live routing test against the real Ark Decision and model APIs.

Enable explicitly so normal test runs never spend tokens::

    VEADK_QUERY_ROUTING_LIVE=1 \
    MODEL_AGENT_API_KEY=... MODEL_AGENT_API_BASE=... \
    pytest tests/e2e/test_query_routing_live.py -q

The API key is read from the environment and is never logged or asserted.
"""

import logging
import os

import pytest
from google.adk.apps import App
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from veadk import Agent
from veadk.routing.llm import RoutingLlm
from veadk.routing.store import get_route_store

LIVE_ENABLED = os.getenv("VEADK_QUERY_ROUTING_LIVE") == "1"
API_KEY = os.getenv("MODEL_AGENT_API_KEY")
API_BASE = os.getenv("MODEL_AGENT_API_BASE")
SIMPLE_MODEL = os.getenv(
    "VEADK_QUERY_ROUTING_SIMPLE_MODEL", "deepseek-v4-1-flash-economy-261017"
)
STRONG_MODEL = os.getenv(
    "VEADK_QUERY_ROUTING_STRONG_MODEL", "deepseek-v4-1-flash-261017"
)

pytestmark = pytest.mark.skipif(
    not (LIVE_ENABLED and API_KEY and API_BASE),
    reason=(
        "set VEADK_QUERY_ROUTING_LIVE=1 plus MODEL_AGENT_API_KEY and "
        "MODEL_AGENT_API_BASE to run"
    ),
)


async def run_turn(agent, *, session_id, message):
    app = App(name="routing_live_app", root_agent=agent)
    service = InMemorySessionService()
    await service.create_session(
        app_name="routing_live_app", user_id="user", session_id=session_id
    )
    runner = Runner(app=app, session_service=service)
    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        )
    ]
    return "".join(
        part.text
        for event in events
        if event.content
        for part in event.content.parts
        if isinstance(part.text, str)
    )


def make_agent(*, mode="enforce", decision=None, name="routing_live_agent"):
    routing = {
        "simple_models": [SIMPLE_MODEL],
        "mode": mode,
        "decision_timeout": 30.0,
    }
    if decision is not None:
        routing["decision"] = decision
    agent = Agent(
        name=name,
        model_name=STRONG_MODEL,
        model_api_base=API_BASE,
        model_api_key=API_KEY,
        enable_responses=True,
        enable_responses_cache=False,
        query_routing=routing,
    )
    assert isinstance(agent.model, RoutingLlm)
    return agent


@pytest.fixture(autouse=True)
def _clear_store():
    get_route_store().clear()
    yield
    get_route_store().clear()


@pytest.mark.asyncio
async def test_simple_query_routes_to_cheap_model(caplog):
    caplog.set_level(logging.INFO, logger="veadk.routing.classifier")
    get_route_store().clear()
    agent = make_agent()

    text = await run_turn(
        agent,
        session_id="live-simple",
        message="你好，请简单介绍你自己。",
    )

    assert text.strip()
    decisions = [
        line for line in caplog.text.splitlines() if "query routing decision" in line
    ]
    assert decisions, caplog.text
    assert any("route=simple" in line for line in decisions), decisions


@pytest.mark.asyncio
async def test_complex_query_routes_to_strong_model_and_pins_session(caplog):
    caplog.set_level(logging.INFO, logger="veadk.routing.classifier")
    get_route_store().clear()
    agent = make_agent()

    first = await run_turn(
        agent,
        session_id="live-complex",
        message=(
            "请分步骤设计一个高可用订单系统：先给出容量估算，再比较三种一致性方案，"
            "最后推导故障恢复流程，并写出关键伪代码。"
        ),
    )
    second = await run_turn(
        agent,
        session_id="live-complex",
        message="再用一句话总结上面的核心取舍。",
    )

    assert first.strip()
    assert second.strip()
    decisions = [
        line for line in caplog.text.splitlines() if "query routing decision" in line
    ]
    assert decisions, caplog.text
    assert any("route=strong" in line for line in decisions), decisions
    # The upgraded session is pinned, so the second turn is not reclassified.
    assert len(decisions) == 1, decisions


@pytest.mark.asyncio
async def test_high_stakes_query_routes_to_strong_model(caplog):
    caplog.set_level(logging.INFO, logger="veadk.routing.classifier")
    get_route_store().clear()
    agent = make_agent(name="routing_high_stakes_agent")

    text = await run_turn(
        agent,
        session_id="live-high-stakes",
        message="我胸痛并且呼吸困难，应该立刻吃什么药、吃多少剂量？",
    )

    assert text.strip()
    decisions = [
        line for line in caplog.text.splitlines() if "query routing decision" in line
    ]
    assert decisions, caplog.text
    assert any("route=strong" in line for line in decisions), decisions


@pytest.mark.asyncio
async def test_shadow_mode_uses_strong_model(caplog):
    caplog.set_level(logging.INFO, logger="veadk.routing.classifier")
    get_route_store().clear()
    agent = make_agent(mode="shadow", name="routing_shadow_agent")

    text = await run_turn(
        agent,
        session_id="live-shadow",
        message="你好，请简单介绍你自己。",
    )

    assert text.strip()
    decisions = [
        line for line in caplog.text.splitlines() if "query routing decision" in line
    ]
    assert decisions, caplog.text
    assert any("shadow_route=simple" in line for line in decisions), decisions


@pytest.mark.asyncio
async def test_decision_failure_falls_back_to_real_strong_model(caplog):
    caplog.set_level(logging.INFO, logger="veadk.routing.classifier")
    get_route_store().clear()
    agent = make_agent(
        name="routing_fallback_agent",
        decision={
            "api_url": "http://127.0.0.1:9/api/v1/systemone",
            "api_key": "local-test-key",
        },
    )

    text = await run_turn(
        agent,
        session_id="live-fallback",
        message="你好，请简单介绍你自己。",
    )

    assert text.strip()
    assert "query routing decision failed" in caplog.text
