"""A complete restored source must not invite repeated reads or pay reader schema cost."""

import copy
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.adk.models.llm_request import LlmRequest
from google.adk.sessions import Session
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

import veadk.context.tool_results as tr
from veadk.context.budget import count_input, request_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import ContextScope, current_scope
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    compact_tool_results,
    restore_fitting_originals,
)


@pytest.mark.asyncio
async def test_fitting_full_source_removes_reader_schema_and_refuses_redundant_reads(
    monkeypatch,
):
    text = "".join(f"Unique document line {i}: archival fact.\n" for i in range(600))

    def fetch() -> str:
        raise AssertionError("never repeat source tool")

    event = Event(
        id="source",
        author="agent",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="fetch", id="f1", response={"result": text}
                    )
                )
            ],
        ),
    )
    scope = ContextScope(
        session=Session(app_name="a", user_id="u", id="s", events=[event]),
        agent_name="agent",
        branch="",
    )
    request = LlmRequest(
        contents=[copy.deepcopy(event.content)],
        tools_dict={"fetch": FunctionTool(fetch)},
    )
    config = ContextCompressionConfig()
    raw_count = count_input(request_payload(request), config)
    refs = compact_tool_results(request, scope, config)
    ref = next(iter(refs))
    for i in range(2):
        response = Event(
            id=f"r{i}",
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=READ_CONTEXT_TOOL,
                            id=f"c{i}",
                            response={
                                "reference": ref,
                                "source_sha256": refs[ref]["text_hash"],
                                "text": text[i * 1000 : (i + 1) * 1000],
                                "offset": i * 1000,
                                "end": (i + 1) * 1000,
                                "complete": False,
                            },
                        )
                    )
                ],
            ),
        )
        scope.session.events.append(response)
        request.contents.append(copy.deepcopy(response.content))
    original = copy.deepcopy(scope.session.events)
    scope.retrieval_calls = 2
    available = raw_count + 1300
    restore_fitting_originals(request, scope, config, available)
    assert request.contents[0].parts[0].function_response.response["result"] == text
    names = [
        f.name
        for tool in request.config.tools or []
        for f in tool.function_declarations or []
    ]
    assert READ_CONTEXT_TOOL not in names
    assert count_input(request_payload(request), config) <= available

    def forbidden(*args, **kwargs):
        raise AssertionError("restored source must not be loaded again for stale calls")

    monkeypatch.setattr(tr, "resolve", forbidden)
    token = current_scope.set(scope)
    try:
        result = await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=ref,
            tool_context=SimpleNamespace(session=scope.session, agent_name="agent"),
            offset=1000,
        )
    finally:
        current_scope.reset(token)
    assert result["original_included"] and "text" not in result
    assert scope.retrieval_calls == 2 and scope.session.events == original


@pytest.mark.asyncio
async def test_full_source_keeps_declared_statistics_and_new_projection_can_read():
    import json

    text = json.dumps(["alpha " * 900, "beta " * 900] * 4)

    def fetch() -> str:
        raise AssertionError("never repeat source tool")

    tool = FunctionTool(fetch)
    tool.custom_metadata = {"context_compression_record_format": "json_array_strings"}
    event = Event(
        id="source",
        author="agent",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name="fetch", id="f1", response={"result": text}
                    )
                )
            ],
        ),
    )
    scope = ContextScope(
        session=Session(app_name="a", user_id="u", id="s", events=[event]),
        agent_name="agent",
        branch="",
    )
    request = LlmRequest(
        contents=[copy.deepcopy(event.content)], tools_dict={"fetch": tool}
    )
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    ref = next(iter(refs))
    result_event = Event(
        id="r1",
        author="agent",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        name=READ_CONTEXT_TOOL,
                        id="c1",
                        response={
                            "reference": ref,
                            "source_sha256": refs[ref]["text_hash"],
                            "text": text[:1000],
                            "offset": 0,
                            "end": 1000,
                            "complete": False,
                        },
                    )
                )
            ],
        ),
    )
    scope.session.events.append(result_event)
    request.contents.append(copy.deepcopy(result_event.content))
    scope.retrieval_calls = 2
    restore_fitting_originals(request, scope, config, 100000)
    assert request.contents[0].parts[0].function_response.response["result"] == text
    assert READ_CONTEXT_TOOL in [
        f.name
        for t in request.config.tools or []
        for f in t.function_declarations or []
    ]
    token = current_scope.set(scope)
    try:
        tool_context = SimpleNamespace(session=scope.session, agent_name="agent")
        result = await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=ref, tool_context=tool_context, operation="count_unique"
        )
        assert result["value"] == 2 and result["complete"]
        compact_tool_results(request, scope, config)
        result = await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=ref, tool_context=tool_context, offset=1000
        )
        assert result["text"] == text[result["offset"] : result["end"]]
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_runner_finishes_after_full_restore_without_exceeding_main_call_limit():
    import json
    import re

    from google.adk.agents.run_config import RunConfig
    from google.adk.models.lite_llm import LiteLLMClient
    from litellm import ModelResponse

    from veadk import Agent, Runner
    from veadk.memory.short_term_memory import ShortTermMemory
    from veadk.models.retrying_lite_llm import RetryingLiteLlm

    text = "".join(f"Unique document line {i}: archival fact.\n" for i in range(600))

    def fetch() -> str:
        raise AssertionError("no business tool replay")

    calls = []

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            names = [t["function"]["name"] for t in kwargs.get("tools", [])]
            original_visible = False
            for message in kwargs["messages"]:
                if message["role"] == "tool":
                    payload = json.loads(message["content"])
                    original_visible |= payload.get("result") == text
            calls.append((names, original_visible))
            if len(calls) > 2 and READ_CONTEXT_TOOL not in names and original_visible:
                message = {
                    "role": "assistant",
                    "content": "600 original lines verified",
                }
                finish = "stop"
            else:
                ref = re.search(
                    r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"])
                ).group()
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"r{len(calls)}",
                            "type": "function",
                            "function": {
                                "name": READ_CONTEXT_TOOL,
                                "arguments": json.dumps(
                                    {"reference": ref, "offset": 1000 * len(calls)}
                                ),
                            },
                        }
                    ],
                }
                finish = "tool_calls"
            return ModelResponse(
                model="context-test",
                choices=[{"index": 0, "finish_reason": finish, "message": message}],
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            )

    memory = ShortTermMemory()
    service = memory.session_service
    session = await service.create_session(
        app_name="restore", user_id="u", session_id="s"
    )
    seed = [
        ("user", "user", types.Part(text="Load the archive.")),
        (
            "agent",
            "model",
            types.Part(
                function_call=types.FunctionCall(id="f1", name="fetch", args={})
            ),
        ),
        (
            "agent",
            "user",
            types.Part(
                function_response=types.FunctionResponse(
                    id="f1", name="fetch", response={"result": text}
                )
            ),
        ),
    ]
    for i, (author, role, part) in enumerate(seed):
        await service.append_event(
            session=session,
            event=Event(
                id=f"seed{i}",
                timestamp=1700000000 + i,
                author=author,
                content=types.Content(role=role, parts=[part]),
            ),
        )
    original = copy.deepcopy(session.events)
    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=ContextCompressionConfig(
            context_window=32000, input_limit=29000, output_reserve=1000
        ),
    )
    agent = Agent(
        name="agent", model=model, model_api_key="offline-test", tools=[fetch]
    )
    runner = Runner(agent=agent, app_name="restore", session_service=service)
    answer = await runner.run(
        "Verify the entire document.",
        user_id="u",
        session_id="s",
        run_config=RunConfig(max_llm_calls=4),
    )
    assert answer == "600 original lines verified" and len(calls) == 3
    saved = await service.get_session(app_name="restore", user_id="u", session_id="s")
    assert saved.events[: len(original)] == original
