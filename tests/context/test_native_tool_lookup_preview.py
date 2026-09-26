"""Read-first experiment: verify the actual native transport and Session path.

The fake model obeys named tool choice and otherwise answers immediately.
These are protocol tests, not evidence of real model answer quality.
"""

import asyncio
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
@pytest.mark.parametrize("source_format", ["string", "mcp"])
@pytest.mark.parametrize("sessions", [1, 2])
async def test_native_tool_lookup_preview_preserves_normal_second_request(
    tmp_path, source_format, sessions, monkeypatch
):
    normal = {f"s-{i}": [] for i in range(sessions)}
    actual_client = BudgetedLiteLLMClient.acompletion

    async def capture(self, model, messages, tools=None, **kwargs):
        scope = current_scope.get()
        normal[scope.session.id].append(copy.deepcopy(messages))
        headroom = scope.retrieval_headroom
        response = await actual_client(self, model, messages, tools, **kwargs)
        assert current_scope.get() is scope
        assert scope.retrieval_headroom == headroom
        return response

    monkeypatch.setattr(BudgetedLiteLLMClient, "acompletion", capture)
    arrived = 0
    ready = asyncio.Event()

    async def checkpoint():
        nonlocal arrived
        arrived += 1
        if arrived == sessions:
            ready.set()
        await ready.wait()

    await asyncio.gather(
        *(
            run_case(tmp_path, source_format, label, normal[label], checkpoint)
            for label in normal
        )
    )


async def run_case(
    tmp_path, source_format, label, normal, checkpoint, *, question_clues=False
):
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=24670,
        max_model_attempts=1,
        request_timeout_seconds=120,
    ).model_copy(update={"verify_sources": True})
    calls = []
    fact = f"Authorization code KQ-783 for {label} permits 42 units."
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
            if len(calls) == 1:
                await checkpoint()
            assert current_scope.get().session.id == label
            if kwargs.get("tool_choice") == {
                "type": "function",
                "function": {"name": "veadk_read_context"},
            }:
                reference = re.search(
                    r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"])
                )[0]
                message = {
                    "role": "assistant",
                    "tool_calls": [
                        {
                            "id": "source-check-1",
                            "type": "function",
                            "function": {
                                "name": "veadk_read_context",
                                "arguments": json.dumps(
                                    {
                                        "reference": reference,
                                        "operation": "read",
                                        "query": "KQ-783",
                                    }
                                ),
                            },
                        }
                    ],
                }
            else:
                message = {"role": "assistant", "content": "Protocol completed."}
            return ModelResponse(
                model=kwargs["model"],
                choices=[{"message": message}],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    path = str(tmp_path / f"{label}.sqlite3")
    identity = {"app_name": "verify", "user_id": label, "session_id": label}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    session = await service.create_session(**identity)
    call = types.Part.from_function_call(name="fetch_reference", args={})
    call.function_call.id = "fetch-1"
    response_value = (
        {"result": "\n".join(bodies)}
        if source_format == "string"
        else {
            "content": [
                {"type": "text", "text": "\n".join(bodies)},
                {"type": "text", "text": "\n".join(reversed(bodies))},
            ],
            "isError": False,
        }
    )
    response = types.Part.from_function_response(
        name="fetch_reference", response=response_value
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
    business_tool = FunctionTool(fetch_reference)
    if source_format == "mcp":
        business_tool.custom_metadata = {"mcp_text_preview": True}
    agent = Agent(
        name="verify_agent",
        model=model,
        model_api_key="offline-test",
        instruction="Find evidence in saved sources.",
        tools=[business_tool],
    )
    runner = Runner(agent=agent, app_name="verify", session_service=service)
    try:
        async for _ in runner.run_async(
            user_id=label,
            session_id=label,
            new_message=types.Content(
                role="user",
                parts=[
                    types.Part(
                        text=(
                            f"What authorization code and quantity belong to {label}?"
                            if question_clues
                            else "What was authorized?"
                        )
                    )
                ],
            ),
            run_config=RunConfig(max_llm_calls=3),
        ):
            pass
        assert len(calls) == 2, (
            "Lossy previews must request one source check before the answer."
        )
        assert "tool_choice" not in calls[1]
        assert calls[1]["messages"] == normal[1]
        assert len(normal) == 2
        assert calls[0]["messages"] != normal[0]
        assert (
            len(json.dumps(calls[0]["messages"]).encode())
            < len(json.dumps(normal[0]).encode()) * 0.65
        )
        assert calls[0]["messages"][-1] == normal[0][-1]
        assert calls[0]["messages"][0] == normal[0][0]
        assert len(calls[0]["messages"]) == len(normal[0])
        for before, after in zip(normal[0], calls[0]["messages"]):
            if before.get("role") != "tool":
                assert after == before
                continue
            assert {k: v for k, v in after.items() if k != "content"} == {
                k: v for k, v in before.items() if k != "content"
            }
            if question_clues:
                value = json.loads(after["content"])
                texts = (
                    [value["result"]]
                    if source_format == "string"
                    else [item["text"] for item in value["content"]]
                )
                assert all(fact in text for text in texts), (
                    "The real Runner first lookup lost the relevant source clue."
                )
                assert all(len(text.encode()) <= 2048 for text in texts)
        outputs = [
            json.loads(m["content"])
            for m in calls[1]["messages"]
            if m.get("tool_call_id") == "source-check-1"
        ]
        assert len(outputs) == 1 and fact in outputs[0]["text"]
        other_label = "s-1" if label == "s-0" else "s-0"
        assert f"KQ-783 for {other_label}" not in outputs[0]["text"]
        assert outputs[0]["source_sha256"] and outputs[0]["reference"]
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
