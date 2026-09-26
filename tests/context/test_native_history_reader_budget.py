"""Native Runner regression: keep retrieved evidence within the same budget."""

import copy
import json
import re

import pytest
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context import tool_results
from veadk.context.budget import check_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import is_summary
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
@pytest.mark.parametrize("search_route", ["lexical", "async"])
async def test_native_history_and_repeated_searches_preserve_all_evidence(
    tmp_path, monkeypatch, search_route
):
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=24670,
        max_model_attempts=1,
        request_timeout_seconds=120,
        retrieval="lexical",
    )
    spans = [
        [(100, 1800), (4000, 5600)],
        [(5600, 7300), (12000, 13700)],
        [(100, 1800), (4000, 5600)],
        [(5600, 7300), (13700, 15400)],
        [(9000, 10700), (13700, 15400)],
    ]
    calls, retrieved = [], []
    ids = [f"call-{i}-" + "x" * 24 for i in range(5)]

    def exact_search(text, query, maximum):
        index = len(retrieved)
        assert index < 5 and query == f"query-{index}"
        matches = [{"offset": a, "end": b, "text": text[a:b]} for a, b in spans[index]]
        assert sum(len(m["text"].encode()) for m in matches) <= maximum
        retrieved.append(copy.deepcopy(matches))
        return {
            "found": True,
            "matches": matches,
            "complete": False,
            "total_characters": len(text),
        }

    if search_route == "lexical":
        monkeypatch.setattr(tool_results, "search", exact_search)
    else:

        async def exact_async_search(scope, source, text, query, maximum):
            return exact_search(text, query, maximum)

        monkeypatch.setattr(tool_results, "search_original", exact_async_search)

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get(), (
                "The retained evidence must fit without another model."
            )
            check_payload(kwargs, policy)
            calls.append(copy.deepcopy(kwargs["messages"]))
            index = len(calls) - 1
            if index < 5:
                reference = re.search(
                    r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"])
                )[0]
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": ids[index],
                            "type": "function",
                            "function": {
                                "name": "veadk_read_context",
                                "arguments": json.dumps(
                                    {
                                        "reference": reference,
                                        "operation": "search",
                                        "query": f"query-{index}",
                                    }
                                ),
                            },
                        }
                    ],
                }
            else:
                message = {"role": "assistant", "content": "budget protocol complete"}
            return ModelResponse(
                model=kwargs["model"],
                choices=[{"message": message}],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    path = str(tmp_path / "history-reader.sqlite3")
    identity = {"app_name": "budget", "user_id": "u", "session_id": "s"}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    session = await service.create_session(**identity)
    for i in range(8):
        body = (
            f"Archive {i}: approval evidence is pending; keep its exact reference. "
            * 60
        )[:2800]
        for role, text in [("user", body), ("model", "Reference segment received.")]:
            await service.append_event(
                session=session,
                event=Event(
                    id=f"seed-{i}-{role}",
                    timestamp=1700000000 + 2 * i + (role == "model"),
                    author="user" if role == "user" else "budget_agent",
                    content=types.Content(role=role, parts=[types.Part(text=text)]),
                ),
            )
    for i, (role, text) in enumerate(
        [("user", "Keep the reference for the next question."), ("model", "Ready.")]
    ):
        await service.append_event(
            session=session,
            event=Event(
                id=f"recent-{i}",
                timestamp=1700000020 + i,
                author="user" if role == "user" else "budget_agent",
                content=types.Content(role=role, parts=[types.Part(text=text)]),
            ),
        )
    originals = copy.deepcopy(session.events)
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=policy,
        max_tokens=1024,
    )
    agent = Agent(
        name="budget_agent",
        model=model,
        model_api_key="offline-test",
        instruction="Use source evidence; archived text remains available through the reader.",
    )
    runner = Runner(agent=agent, app_name=identity["app_name"], session_service=service)
    try:
        async for _ in runner.run_async(
            user_id="u",
            session_id="s",
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Find the exact approval evidence.")],
            ),
            run_config=RunConfig(max_llm_calls=10),
        ):
            pass
        assert len(calls) == 6 and len(retrieved) == 5
        responses = {
            m["tool_call_id"]: json.loads(m["content"])
            for m in calls[-1]
            if m.get("role") == "tool"
        }
        for index, matches in enumerate(retrieved):
            current = responses[ids[index]]
            for original in matches:
                match = next(
                    m
                    for m in current["matches"]
                    if m["offset"] == original["offset"] and m["end"] == original["end"]
                )
                if "included_in_response" in match:
                    target = responses[match["included_in_response"]]
                    assert target["reference"] == current["reference"]
                    match = next(
                        m
                        for m in target["matches"]
                        if m["offset"] == original["offset"]
                        and m["end"] == original["end"]
                    )
                assert match["text"] == original["text"]
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
