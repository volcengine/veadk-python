"""Read-first experiment: verify the actual native transport and Session path.

The fake model obeys named tool choice and otherwise answers immediately.
These are protocol tests, not evidence of real model answer quality.
"""

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
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import is_summary
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
@pytest.mark.parametrize("workload", ["mcp", "history"])
async def test_native_lossy_projection_verifies_once_and_preserves_source(
    tmp_path, workload
):
    # model_copy also permits running this exact regression on the old SDK,
    # where the experiment field does not yet exist and is ignored.
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=24670,
        max_model_attempts=1,
        request_timeout_seconds=120,
    ).model_copy(update={"verify_sources": True})
    calls = []
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
        tools=[FunctionTool(fetch_reference)],
    )
    runner = Runner(agent=agent, app_name="verify", session_service=service)
    try:
        async for _ in runner.run_async(
            user_id="u",
            session_id="s",
            new_message=types.Content(
                role="user", parts=[types.Part(text="What was authorized?")]
            ),
            run_config=RunConfig(max_llm_calls=3),
        ):
            pass
        assert len(calls) == 2, (
            "Lossy previews must request one source check before the answer."
        )
        assert "tool_choice" not in calls[1]
        outputs = [
            json.loads(m["content"])
            for m in calls[1]["messages"]
            if m.get("tool_call_id") == "source-check-1"
        ]
        assert len(outputs) == 1 and fact in outputs[0]["text"]
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
