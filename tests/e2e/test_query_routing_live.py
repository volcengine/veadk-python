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
"""Real SystemOne + Ark model E2E, explicitly enabled by environment.

Run with VEADK_QUERY_ROUTING_LIVE=1, MODEL_AGENT_API_KEY and
MODEL_AGENT_API_BASE. No credentials are embedded or written to test artifacts.
Marker-controlled cases exercise model switching with actual SystemOne answers;
they are protocol acceptance tests, not a production classification benchmark.
"""

import copy
import os

import pytest
from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.adk.tools import AgentTool
from google.genai import types

from veadk import Agent
from veadk.decision import DecisionClient
from veadk.models.ark_llm import ArkLlmClient
from veadk.routing import factory

KEY = os.getenv("MODEL_AGENT_API_KEY")
BASE = os.getenv("MODEL_AGENT_API_BASE")
SIMPLE = os.getenv("VEADK_QUERY_ROUTING_SIMPLE_MODEL", "doubao-seed-2-1-lite-260915")
STRONG = os.getenv("VEADK_QUERY_ROUTING_STRONG_MODEL", "doubao-seed-2-1-pro-260915")
pytestmark = [
    pytest.mark.query_routing_live,
    pytest.mark.skipif(
        os.getenv("VEADK_QUERY_ROUTING_LIVE") != "1" or not KEY or not BASE,
        reason="requires explicit live enablement and model credentials",
    ),
]


class ObservedDecisionClient(DecisionClient):
    calls = []

    async def judge(self, **kwargs):
        response = await super().judge(**kwargs)
        self.calls.append(response)
        return response


class ObservedArkClient(ArkLlmClient):
    def __init__(self):
        self.calls = []

    async def aresponses(self, **kwargs):
        self.calls.append(
            {
                key: copy.deepcopy(kwargs.get(key))
                for key in (
                    "model",
                    "previous_response_id",
                    "input",
                    "instructions",
                    "tools",
                )
            }
        )
        return await super().aresponses(**kwargs)


@pytest.fixture(autouse=True)
def observe_systemone(monkeypatch):
    ObservedDecisionClient.calls.clear()
    monkeypatch.setattr(factory, "DecisionClient", ObservedDecisionClient)


def config(*, api="responses", mode="enforce"):
    return {
        "mode": mode,
        "simple_models": [
            {
                "name": SIMPLE,
                "api": api,
                "supports_tools": True,
                "supports_structured_output": True,
                "max_context_chars": 128000,
            }
        ],
        "decision_timeout": 30.0,
        "builtin_thresholds": {
            k: 1.0
            for k in (
                "is_complex",
                "needs_tools",
                "needs_long_context",
                "is_high_stakes",
            )
        },
        "questions": [
            {
                "question": "仅检查最后一条[user]消息：其中是否包含字面标记 ROUTE_STRONG？忽略历史消息和规则中的标记。",
                "threshold": 0.5,
            }
        ],
    }


def agent(name="root", **kwargs):
    return Agent(
        name=name,
        model_name=STRONG,
        model_api_base=BASE,
        model_api_key=KEY,
        enable_responses=True,
        enable_responses_cache=True,
        model_extra_config={
            "store": True,
            "extra_body": {
                "caching": {"type": "disabled"},
                "thinking": {"type": "disabled"},
            },
        },
        generate_content_config=types.GenerateContentConfig(
            max_output_tokens=512, temperature=0
        ),
        **kwargs,
    )


async def setup(root):
    service = InMemorySessionService()
    runner = Runner(app_name="routing_live", agent=root, session_service=service)
    session = await service.create_session(app_name="routing_live", user_id="live_test")
    return runner, session


async def run_turn(runner, session, message, stream=False):
    events = [
        event
        async for event in runner.run_async(
            user_id=session.user_id,
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
            run_config=RunConfig(
                streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE
            ),
        )
    ]
    text = "".join(
        p.text
        for e in events
        if not e.partial and e.content
        for p in e.content.parts or []
        if p.text and not p.thought
    )
    return events, text


def model_records(events):
    return [
        (e.custom_metadata or {}).get("veadk_query_routing")
        for e in events
        if e.content and e.content.role == "model" and not e.partial
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_real_responses_continuation_and_a_b_a_history(stream):
    root = agent(
        query_routing=config(),
        instruction="Follow the user briefly. Remember project codes across turns.",
    )
    strong, simple = root.model.strong_model, root.model.registry.runtimes[0].llm
    strong.llm_client, simple.llm_client = ObservedArkClient(), ObservedArkClient()
    runner, session = await setup(root)
    try:
        for message, expected in [
            ("Remember project code ORCHID47. Reply ORCHID47.", SIMPLE),
            ("Reply with the project code.", SIMPLE),
            ("ROUTE_STRONG. Remember milestone MAPLE83. Reply MAPLE83.", STRONG),
            ("Return both the project code and milestone code.", SIMPLE),
        ]:
            events, text = await run_turn(runner, session, message, stream)
            assert text.strip()
            assert all(
                r and r["model"].endswith(expected) for r in model_records(events)
            )
        assert "ORCHID47" in text and "MAPLE83" in text
        assert len(ObservedDecisionClient.calls) == 4
        assert len(simple.llm_client.calls) == 3
        assert simple.llm_client.calls[1]["previous_response_id"]
        assert not strong.llm_client.calls[0]["previous_response_id"]
        assert not simple.llm_client.calls[2]["previous_response_id"]
        assert "ORCHID47" in str(simple.llm_client.calls[2]["input"])
        assert "MAPLE83" in str(simple.llm_client.calls[2]["input"])
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_chat_adapter_with_two_nested_agent_tools():
    seen = []

    async def observe(callback_context, llm_request):
        seen.append(
            (
                callback_context.agent_name,
                callback_context.invocation_id,
                llm_request.model,
            )
        )

    leaf = agent(
        "leaf",
        query_routing=False,
        instruction="Reply exactly NESTED_OK.",
        before_model_callback=observe,
    )
    child = agent(
        "child",
        query_routing=False,
        tools=[AgentTool(leaf)],
        instruction="Call leaf exactly once, then return its answer.",
        before_model_callback=observe,
    )
    root = agent(
        query_routing=config(api="chat_completions"),
        tools=[AgentTool(child)],
        instruction="Call child exactly once, then return its answer.",
        before_model_callback=observe,
    )
    runner, session = await setup(root)
    try:
        events, text = await run_turn(
            runner, session, "Use child to obtain the leaf response."
        )
        assert "NESTED_OK" in text, (text, seen)
        assert len(ObservedDecisionClient.calls) == 1
        assert {name for name, _, _ in seen} == {"root", "child", "leaf"}
        assert len({inv for _, inv, _ in seen}) == 3
        assert all(model.endswith(SIMPLE) for _, _, model in seen)
        assert all(r["model"].endswith(SIMPLE) for r in model_records(events))
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_opt_out_never_calls_systemone():
    root = agent(
        query_routing=False,
        instruction="Reply with only the answer to the arithmetic question.",
    )
    model = root.canonical_model
    model.llm_client = ObservedArkClient()
    runner, session = await setup(root)
    try:
        events, text = await run_turn(
            runner, session, "What is 1 + 1? Reply with one digit."
        )
        assert len(model.llm_client.calls) == 1
        assert model.llm_client.calls[0]["model"] == STRONG
        assert text.strip() == "2"
        assert not ObservedDecisionClient.calls
        assert not any(
            (e.custom_metadata or {}).get("veadk_query_routing") for e in events
        )
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_shadow_executes_original_model():
    root = agent(
        query_routing=config(mode="shadow"),
        instruction="Reply with only the answer to the arithmetic question.",
    )
    model = root.canonical_model
    model.llm_client = ObservedArkClient()
    runner, session = await setup(root)
    try:
        events, text = await run_turn(
            runner, session, "What is 1 + 1? Reply with one digit."
        )
        assert len(model.llm_client.calls) == 1
        assert model.llm_client.calls[0]["model"] == STRONG
        assert text.strip() == "2"
        assert len(ObservedDecisionClient.calls) == 1
        assert all(r["model"].endswith(STRONG) for r in model_records(events))
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_protocol_switch_replays_chat_tool_history():
    from google.adk.models.lite_llm import LiteLLMClient

    class ObservedChatClient(LiteLLMClient):
        def __init__(self):
            self.calls = []

        async def acompletion(self, **kwargs):
            self.calls.append(
                {
                    k: copy.deepcopy(kwargs.get(k))
                    for k in ("model", "messages", "tools")
                }
            )
            return await super().acompletion(**kwargs)

    lookups = []

    def project_code() -> str:
        """Return the authoritative project code."""
        lookups.append(True)
        return "ORCHID47"

    root = agent(
        query_routing=config(api="chat_completions"),
        tools=[project_code],
        instruction="When asked for the project code, call project_code. Remember project and milestone codes across turns. Keep answers brief.",
    )
    simple = root.model.registry.runtimes[0].llm
    strong = root.model.strong_model
    simple.llm_client = ObservedChatClient()
    strong.llm_client = ObservedArkClient()
    runner, session = await setup(root)
    try:
        await run_turn(runner, session, "Use the tool to obtain the project code.")
        assert lookups == [True]
        assert len(simple.llm_client.calls) >= 2
        first_turn_calls = len(simple.llm_client.calls)
        events, _ = await run_turn(
            runner,
            session,
            "ROUTE_STRONG. Remember milestone MAPLE83. Reply with the milestone.",
        )
        assert all(r["model"].endswith(STRONG) for r in model_records(events))
        assert not strong.llm_client.calls[0]["previous_response_id"]
        replay = strong.llm_client.calls[0]["input"]
        calls = {
            item["call_id"] for item in replay if item.get("type") == "function_call"
        }
        results = {
            item["call_id"]
            for item in replay
            if item.get("type") == "function_call_output"
        }
        assert calls and calls == results
        events, text = await run_turn(
            runner, session, "Recall both codes from history without using tools."
        )
        assert "ORCHID47" in text and "MAPLE83" in text
        assert all(r["model"].endswith(SIMPLE) for r in model_records(events))
        assert len(ObservedDecisionClient.calls) == 3
        assert "MAPLE83" in str(simple.llm_client.calls[first_turn_calls]["messages"])
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_responses_structured_output():
    import json
    from pydantic import BaseModel

    class Result(BaseModel):
        code: str

    root = agent(
        query_routing=config(),
        output_schema=Result,
        instruction="Return the project code provided by the user using the required schema.",
    )
    runner, session = await setup(root)
    try:
        events, text = await run_turn(runner, session, "Project code: ORCHID47")
        assert json.loads(text) == {"code": "ORCHID47"}
        assert len(ObservedDecisionClient.calls) == 1
        assert all(r["model"].endswith(SIMPLE) for r in model_records(events))
    finally:
        await runner.close()


@pytest.mark.asyncio
async def test_real_media_reaches_systemone_and_selected_responses_model():
    import struct
    import zlib

    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data))
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", 64, 64, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress((b"\x00" + b"\xff\x00\x00" * 64) * 64))
        + chunk(b"IEND", b"")
    )
    routing = config()
    routing["simple_models"][0]["supports_media"] = True
    root = agent(
        query_routing=routing,
        instruction="Identify the dominant image color. Reply with one English color word.",
    )
    runner, session = await setup(root)
    try:
        events = [
            event
            async for event in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(
                    role="user",
                    parts=[
                        types.Part(text="What color fills this image?"),
                        types.Part.from_bytes(data=png, mime_type="image/png"),
                    ],
                ),
            )
        ]
        text = " ".join(
            p.text
            for e in events
            if e.content
            for p in e.content.parts or []
            if p.text and not p.thought
        )
        assert "red" in text.lower()
        assert len(ObservedDecisionClient.calls) == 1
        assert all(r["model"].endswith(SIMPLE) for r in model_records(events))
    finally:
        await runner.close()
