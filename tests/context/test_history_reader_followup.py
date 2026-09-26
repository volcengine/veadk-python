"""Native history lookup remains advertised after an unsuccessful source search."""

import copy
import json
import re

import pytest
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.tools.function_tool import FunctionTool
from google.genai import types
from litellm import ModelResponse
from veadk import Agent, Runner
from veadk.context.budget import check_payload
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import current_scope, is_summary
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
@pytest.mark.parametrize("business_tool", [False, True])
@pytest.mark.parametrize("verify", [False, True])
async def test_history_reader_remains_on_wire_for_followup_search(
    tmp_path, business_tool, verify, monkeypatch
):
    workload = "history"
    # model_copy also permits running this exact regression on the old SDK,
    # where the experiment field does not yet exist and is ignored.
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=24670,
        max_model_attempts=1,
        request_timeout_seconds=120,
    ).model_copy(update={"verify_sources": verify})
    calls = []
    normal = []
    actual_client = BudgetedLiteLLMClient.acompletion

    async def capture(self, model, messages, tools=None, **kwargs):
        normal.append(copy.deepcopy(messages))
        scope = current_scope.get()
        headroom = scope.retrieval_headroom
        response = await actual_client(self, model, messages, tools, **kwargs)
        assert scope.retrieval_headroom == headroom
        return response

    monkeypatch.setattr(BudgetedLiteLLMClient, "acompletion", capture)
    fact = "Authorization code KQ-783 permits 42 units."
    bodies = [
        (f"Archive {i}: approval evidence is pending; preserve the record. " * 60)[
            :2800
        ]
        for i in range(8)
    ]
    bodies[4] += "\n" + fact

    def fetch_reference() -> str:
        """Fetch a reference once."""
        raise AssertionError("Business source tools must never be reexecuted.")

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get()
            check_payload(kwargs, policy)
            calls.append(copy.deepcopy(kwargs))
            names = [tool["function"]["name"] for tool in kwargs.get("tools") or []]
            assert names.count("veadk_read_context") == 1, (
                "Reader missing at the actual provider boundary"
            )
            if len(calls) <= 2:
                if len(calls) == 2:
                    previous = [
                        json.loads(m["content"])
                        for m in kwargs["messages"]
                        if m.get("tool_call_id") == "source-check-1"
                    ]
                    assert len(previous) == 1 and previous[0]["found"] is False
                reference = re.search(
                    r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"])
                )[0]
                query = "nonexistent_locator_934791" if len(calls) == 1 else "KQ-783"
                message = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "source-check-" + str(len(calls)),
                            "type": "function",
                            "function": {
                                "name": "veadk_read_context",
                                "arguments": json.dumps(
                                    {
                                        "reference": reference,
                                        "operation": "search",
                                        "query": query,
                                    }
                                ),
                            },
                        }
                    ],
                }
            else:
                result = [
                    json.loads(m["content"])
                    for m in kwargs["messages"]
                    if m.get("tool_call_id") == "source-check-2"
                ]
                assert len(result) == 1 and result[0]["found"] is True
                assert fact in "".join(m["text"] for m in result[0]["matches"])
                message = {"role": "assistant", "content": "Protocol completed."}
            return ModelResponse(
                model=kwargs["model"],
                choices=[{"message": message}],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    path = str(tmp_path / "verify.sqlite3")
    identity = {"app_name": "verify", "user_id": "u", "session_id": "s"}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    session = await service.create_session(**identity)
    contents = []
    if workload == "history":
        for body in bodies:
            contents.extend(
                [
                    types.Content(role="user", parts=[types.Part(text=body)]),
                    types.Content(role="model", parts=[types.Part(text="Received.")]),
                ]
            )
        contents.extend(
            [
                types.Content(
                    role="user", parts=[types.Part(text="Keep the archive.")]
                ),
                types.Content(role="model", parts=[types.Part(text="Ready.")]),
            ]
        )
    else:
        call = types.Part.from_function_call(name="fetch_reference", args={})
        call.function_call.id = "fetch-1"
        response = types.Part.from_function_response(
            name="fetch_reference", response={"result": "\n".join(bodies)}
        )
        response.function_response.id = "fetch-1"
        contents = [
            types.Content(role="model", parts=[call]),
            types.Content(role="user", parts=[response]),
        ]
    for i, content in enumerate(contents):
        await service.append_event(
            session=session,
            event=Event(
                id=f"seed-{i}",
                timestamp=1700000000 + i,
                author="user"
                if content.role == "user" and not content.parts[0].function_response
                else "verify_agent",
                content=content,
            ),
        )
    originals = copy.deepcopy(session.events)
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    model = RetryingLiteLlm(
        model="openai/deepseek-v4-1-flash-260910",
        api_key="offline-test",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        extra_body={"thinking": {"type": "disabled"}},
        llm_client=Client(),
        context_compression=policy,
        max_tokens=1024,
    )
    agent = Agent(
        name="verify_agent",
        model=model,
        model_api_key="offline-test",
        instruction="Find evidence in saved sources.",
        tools=[FunctionTool(fetch_reference)] if business_tool else [],
    )
    runner = Runner(agent=agent, app_name="verify", session_service=service)
    try:
        async for _ in runner.run_async(
            user_id="u",
            session_id="s",
            new_message=types.Content(
                role="user", parts=[types.Part(text="What was authorized?")]
            ),
            run_config=RunConfig(max_llm_calls=4),
        ):
            pass
        assert len(calls) == 3
        assert "tool_choice" not in calls[1] and "tool_choice" not in calls[2]
        assert calls[1]["messages"] == normal[1]
        assert len(normal) == 3
        saved = await service.get_session(**identity)
        assert saved.events[: len(originals)] == originals
    finally:
        await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    try:
        assert (
            await service.get_session(**identity)
        ).model_dump() == saved.model_dump()
    finally:
        await service.close()
