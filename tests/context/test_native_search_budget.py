"""Real Runner and SQLite must admit requests after distinct search results."""

import copy
import json
import re

import pytest
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse
from test_recoverable_context import mcp_source
from veadk import Agent, Runner
from veadk.context.budget import ContextBudgetError, check_payload, count_input
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import current_scope, is_summary
from veadk.context.tool_results import READ_CONTEXT_TOOL
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


@pytest.mark.asyncio
@pytest.mark.parametrize("escaped", [False, True], ids=["ascii", "escaped"])
@pytest.mark.parametrize("parallel", [False, True], ids=["sequential", "parallel"])
async def test_native_distinct_searches_stay_within_request_budget(
    tmp_path, escaped, parallel
):
    suffix = " exact source evidence remains pending. "
    if escaped:
        suffix += '\x01"\\\t\x02' * 12
    text = "".join(
        f"topic_{topic} record {line}{suffix}\n"
        for topic in range(4)
        for line in range(250)
    )
    source, _ = mcp_source(text)
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=12000,
        tool_result_max_bytes=1024,
        max_model_attempts=1,
        request_timeout_seconds=120,
    )
    calls, observations = [], []
    next_query = 0

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            nonlocal next_query
            assert not is_summary.get(), "New search results must fit without a summary"
            check_payload(kwargs, policy)
            calls.append(copy.deepcopy(kwargs["messages"]))
            scope = current_scope.get()
            observations.append(
                {
                    "input_size": count_input(kwargs, policy),
                    "headroom": scope.retrieval_headroom,
                }
            )
            if next_query < 4:
                ref = re.search(r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"]))[0]
                indices = list(range(4)) if parallel else [next_query]
                next_query += len(indices)
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"search-{i}",
                            "type": "function",
                            "function": {
                                "name": READ_CONTEXT_TOOL,
                                "arguments": json.dumps(
                                    {
                                        "reference": ref,
                                        "operation": "search",
                                        "query": f"topic_{i}",
                                    }
                                ),
                            },
                        }
                        for i in indices
                    ],
                }
            else:
                message = {
                    "role": "assistant",
                    "content": "Use the retained evidence; missing facts remain unknown.",
                }
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    database = str(tmp_path / "native-search.sqlite3")
    identity = {"app_name": "native_search", "user_id": "u", "session_id": "s"}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    session = await service.create_session(**identity)
    contents = [
        types.Content(role="user", parts=[types.Part(text="Load the archive.")]),
        types.Content(
            role="model",
            parts=[
                types.Part(
                    function_call=types.FunctionCall(
                        name="fetch", id="fetch-1", args={}
                    )
                )
            ],
        ),
        source.contents[0],
    ]
    for i, content in enumerate(contents):
        await service.append_event(
            session=session,
            event=Event(
                id=f"seed-{i}",
                invocation_id="seed",
                author="user" if i == 0 else "agent",
                timestamp=1700000000 + i,
                content=content,
            ),
        )
    originals = copy.deepcopy(session.events)
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=policy,
        max_tokens=1024,
    )
    agent = Agent(
        name="agent",
        model=model,
        model_api_key="offline-test",
        tools=[source.tools_dict["fetch"]],
        instruction="Use original archived evidence. Never refetch it.",
    )
    runner = Runner(agent=agent, app_name=identity["app_name"], session_service=service)
    failure = None
    try:
        try:
            async for _ in runner.run_async(
                user_id="u",
                session_id="s",
                new_message=types.Content(
                    role="user", parts=[types.Part(text="Compare the archived topics.")]
                ),
                run_config=RunConfig(max_llm_calls=8),
            ):
                pass
        except ContextBudgetError as exc:
            failure = {
                "code": exc.code,
                "input_size": exc.input_tokens,
                "budget": exc.budget,
            }
        saved = await service.get_session(**identity)
        assert saved.events[: len(originals)] == originals
        responses = {
            p.function_response.id: p.function_response.response
            for e in saved.events
            if e.content
            for p in e.content.parts or []
            if p.function_response and p.function_response.name == READ_CONTEXT_TOOL
        }
        ranges = []
        for value in responses.values():
            for match in value.get("matches", []):
                assert match["text"] == text[match["offset"] : match["end"]]
                ranges.append((match["offset"], match["end"]))
        (tmp_path / "observation.json").write_text(
            json.dumps(
                {
                    "parallel": parallel,
                    "escaped": escaped,
                    "calls": observations,
                    "failure": failure,
                    "result_count": len(responses),
                    "distinct_ranges": len(set(ranges)),
                },
                indent=2,
            )
        )
        assert failure is None, (
            f"Actual next model request failed: {failure}; calls={observations}"
        )
        assert len(calls) == (2 if parallel else 5)
        assert responses and ranges
        assert len(responses) == 4
        final = {
            m["tool_call_id"]: json.loads(m["content"])
            for m in calls[-1]
            if m.get("role") == "tool"
            and m.get("tool_call_id", "").startswith("search-")
        }
        for key, value in responses.items():
            for match in value.get("matches", []):
                seen = next(
                    m
                    for m in final[key]["matches"]
                    if m["offset"] == match["offset"] and m["end"] == match["end"]
                )
                assert seen["text"] == match["text"], (
                    "Distinct previously read evidence must stay literal"
                )
    finally:
        await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    try:
        assert (
            await service.get_session(**identity)
        ).model_dump() == saved.model_dump()
    finally:
        await service.close()
