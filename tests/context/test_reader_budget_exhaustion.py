"""Budget exhaustion must retire the reader without discarding business tools."""

import copy
import json
import re

import pytest
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.sessions import InMemorySessionService
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context.tool_results import READ_CONTEXT_TOOL
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
@pytest.mark.parametrize("budget", [2, 8])
@pytest.mark.parametrize("stale_call", [False, True])
async def test_reader_budget_retires_only_reader_before_next_model_step(
    budget, stale_call
):
    sent = []
    source = "Evidence " * 12000

    def fetch() -> dict:
        raise AssertionError("Business tool must not run again")

    tool = FunctionTool(fetch)
    tool.custom_metadata = {"mcp_text_preview": True}

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            names = {t["function"]["name"] for t in kwargs.get("tools", [])}
            assert "fetch" in names
            sent.append(copy.deepcopy(kwargs))
            if READ_CONTEXT_TOOL in names or (stale_call and len(sent) == budget + 1):
                ref = re.search(r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"]))[0]
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "read-" + str(len(sent)),
                            "type": "function",
                            "function": {
                                "name": READ_CONTEXT_TOOL,
                                "arguments": json.dumps(
                                    {"reference": ref, "offset": (len(sent) - 1) * 1000}
                                ),
                            },
                        }
                    ],
                }
            else:
                message = {
                    "role": "assistant",
                    "content": "Evidence incomplete; no full-data conclusion.",
                }
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression={
            "context_window": 18000,
            "output_reserve": 1000,
            "max_retrieval_calls": budget,
        },
    )
    service = InMemorySessionService()
    identity = {"app_name": "budget_test", "user_id": "user", "session_id": "session"}
    session = await service.create_session(**identity)
    contents = [
        types.Content(role="user", parts=[types.Part(text="Load source")]),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        id="fetch-1", name="fetch", args={}
                    )
                )
            ],
        ),
        types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id="fetch-1",
                        name="fetch",
                        response={
                            "content": [{"type": "text", "text": source}],
                            "isError": False,
                        },
                    )
                )
            ],
        ),
    ]
    for i, c in enumerate(contents):
        await service.append_event(
            session, Event(author="user" if i == 0 else "agent", content=c)
        )
    originals = copy.deepcopy(session.events)
    runner = Runner(
        agent=Agent(
            name="agent", model=model, model_api_key="offline-test", tools=[tool]
        ),
        app_name=identity["app_name"],
        session_service=service,
    )
    events = [
        e
        async for e in runner.run_async(
            user_id="user",
            session_id="session",
            new_message=types.Content(
                role="user", parts=[types.Part(text="Inspect available source")]
            ),
            run_config=RunConfig(max_llm_calls=budget + 2),
        )
    ]
    assert events[-1].is_final_response() and len(sent) == budget + 1 + int(stale_call)
    assert READ_CONTEXT_TOOL not in {
        t["function"]["name"] for t in sent[-1].get("tools", [])
    }
    saved = await service.get_session(**identity)
    assert saved.events[: len(originals)] == originals
    results = [
        p.function_response.response
        for e in saved.events
        if e.content
        for p in e.content.parts or []
        if p.function_response and p.function_response.name == READ_CONTEXT_TOOL
    ]
    assert len(results) == budget + int(stale_call)
    assert sum("error" not in r for r in results) == budget
    assert results[budget - 1]["remaining_calls"] == 0
    assert "budget" in results[budget - 1]["guidance"].lower()
    if stale_call:
        assert results[-1]["error"] == "context_retrieval_budget_exhausted"
        assert results[-1]["remaining_calls"] == 0
        assert "text" not in results[-1] and results[-1]["complete"] is False
        assert "answer" in results[-1]["guidance"].lower()
