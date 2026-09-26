"""Previously retrieved evidence must remain exact across subsequent reads."""

import copy
import json
import re

import pytest
from google.adk.agents.run_config import RunConfig
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse
from test_recoverable_context import mcp_source, read

from veadk import Agent, Runner
from veadk.context.budget import check_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import is_summary
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    compact_read_results,
    compact_tool_results,
)
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


async def scenario(offsets):
    text = "".join(f"Record {i}: ordinary archival detail.\n" for i in range(3000))
    request, scope = mcp_source(text)
    config = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, config)
    ref = next(iter(refs))
    for index, offset in enumerate(offsets):
        value = await read(request, scope, ref, offset=offset)
        event = Event(
            id=f"page-{index}",
            author="agent",
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=READ_CONTEXT_TOOL, id=f"read-{index}", response=value
                        )
                    )
                ],
            ),
        )
        scope.session.events.append(event)
    request.contents = [copy.deepcopy(e.content) for e in scope.session.events]
    return request, scope, refs, config


def retained_text(response, responses):
    def literal(target, start, end):
        if "text" in target:
            return target["text"][start - target["offset"] : end - target["offset"]]
        # Do not follow aliases recursively: every target must have literal text.
        segments = [
            s
            for s in target.get("segments", [])
            if "text" in s and s["offset"] <= start and end <= s["end"]
        ]
        assert len(segments) == 1
        segment = segments[0]
        return segment["text"][start - segment["offset"] : end - segment["offset"]]

    def part(segment):
        if "text" in segment:
            return segment["text"]
        target = responses[segment["included_in_response"]]
        assert target["reference"] == response["reference"]
        assert target["source_sha256"] == response["source_sha256"]
        return literal(target, segment["offset"], segment["end"])

    segments = response.get("segments", [response])
    cursor = response["offset"]
    for segment in segments:
        assert segment["offset"] == cursor and segment["end"] > cursor
        cursor = segment["end"]
    assert cursor == response["end"]
    result = "".join(part(s) for s in segments)
    assert len(result) == response["end"] - response["offset"]
    return result


@pytest.mark.asyncio
async def test_distinct_read_pages_keep_every_character_and_exact_offsets():
    request, scope, refs, config = await scenario([0, 12000, 24000])
    originals = copy.deepcopy(scope.session.events)
    newest = copy.deepcopy(request.contents[-1])
    compact_read_results(request.contents, scope, refs, config)
    responses = {
        c.parts[0].function_response.id: c.parts[0].function_response.response
        for c in request.contents[1:]
    }
    for event in originals[1:]:
        original = event.content.parts[0].function_response
        assert (
            retained_text(responses[original.id], responses)
            == original.response["text"]
        )
        assert responses[original.id]["end"] - responses[original.id]["offset"] == len(
            original.response["text"]
        )
    assert request.contents[-1] == newest and scope.session.events == originals


@pytest.mark.asyncio
async def test_duplicate_pages_alias_exact_text_in_same_input_without_another_read():
    request, scope, refs, config = await scenario([0, 12000, 0])
    originals = copy.deepcopy(scope.session.events)
    before = len(json.dumps([c.model_dump() for c in request.contents]))
    compact_read_results(request.contents, scope, refs, config)
    responses = {
        c.parts[0].function_response.id: c.parts[0].function_response.response
        for c in request.contents[1:]
    }
    assert responses["read-0"].get("included_in_response") == "read-2"
    for event in originals[1:]:
        original = event.content.parts[0].function_response
        assert (
            retained_text(responses[original.id], responses)
            == original.response["text"]
        )
    assert len(json.dumps([c.model_dump() for c in request.contents])) < before - 6000
    assert scope.session.events == originals


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation", ["unknown_field", "wrong_hash", "wrong_text", "duplicate_id"]
)
async def test_unverified_or_ambiguous_pages_are_not_rewritten(mutation):
    request, scope, refs, config = await scenario([0, 12000, 0])
    response = scope.session.events[1].content.parts[0].function_response
    if mutation == "unknown_field":
        response.response["new_evidence"] = "Approval remains pending."
    elif mutation == "wrong_hash":
        response.response["source_sha256"] = "0" * 64
    elif mutation == "wrong_text":
        response.response["text"] = "X" * len(response.response["text"])
    else:
        response.id = scope.session.events[-1].content.parts[0].function_response.id
    request.contents = [copy.deepcopy(e.content) for e in scope.session.events]
    original = copy.deepcopy(request.contents[1])
    compact_read_results(request.contents, scope, refs, config)
    assert request.contents[1] == original


@pytest.mark.asyncio
async def test_page_alias_cannot_cross_user_turn_or_replace_protected_evidence():
    request, scope, refs, config = await scenario([0, 12000, 0])
    request.contents.insert(
        -1, types.Content(role="user", parts=[types.Part(text="A new task.")])
    )
    compact_read_results(request.contents, scope, refs, config)
    first = request.contents[1].parts[0].function_response.response
    assert (
        first["text"]
        == scope.session.events[1].content.parts[0].function_response.response["text"]
    )
    request.contents = [copy.deepcopy(e.content) for e in scope.session.events]
    protected = config.model_copy(
        update={"protected_context": (first["text"][500:600],)}
    )
    before = copy.deepcopy(request.contents[1])
    compact_read_results(request.contents, scope, refs, protected)
    assert request.contents[1] == before


@pytest.mark.asyncio
async def test_native_sqlite_two_reads_keep_earlier_evidence_at_model_boundary(
    tmp_path,
):
    text = "".join(
        f"Archive line {i}: preserved facts and supporting details.\n"
        for i in range(2200)
    )
    source, _ = mcp_source(text)
    offsets = (10000, 30000)
    calls = []
    policy = ContextCompressionConfig(
        context_window=256000,
        input_limit=48000,
        max_model_attempts=1,
        request_timeout_seconds=120,
    )

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get()
            check_payload(kwargs, policy)
            calls.append(copy.deepcopy(kwargs["messages"]))
            index = len(calls) - 1
            if index < 2:
                ref = re.search(r"ctx_[a-f0-9]{24}", json.dumps(kwargs["messages"]))[0]
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": f"read-{index}",
                            "type": "function",
                            "function": {
                                "name": READ_CONTEXT_TOOL,
                                "arguments": json.dumps(
                                    {"reference": ref, "offset": offsets[index]}
                                ),
                            },
                        }
                    ],
                }
            else:
                responses = {
                    m["tool_call_id"]: json.loads(m["content"])
                    for m in kwargs["messages"]
                    if m.get("role") == "tool"
                    and m.get("tool_call_id", "").startswith("read-")
                }
                for i, offset in enumerate(offsets):
                    assert (
                        retained_text(responses[f"read-{i}"], responses)
                        == text[offset : offset + 8000]
                    )
                message = {
                    "role": "assistant",
                    "content": "All retrieved evidence is still present.",
                }
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    database = str(tmp_path / "read-evidence.sqlite3")
    identity = {"app_name": "read_evidence", "user_id": "u", "session_id": "s"}
    service = ShortTermMemory(
        backend="sqlite", local_database_path=database
    ).session_service
    session = await service.create_session(**identity)
    contents = [
        types.Content(
            role="user", parts=[types.Part(text="Load the archived material.")]
        ),
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
        instruction="Read the needed archived evidence. Never fetch the source again.",
    )
    runner = Runner(agent=agent, app_name=identity["app_name"], session_service=service)
    try:
        async for _ in runner.run_async(
            user_id="u",
            session_id="s",
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Compare the two archived sections.")],
            ),
            run_config=RunConfig(max_llm_calls=4),
        ):
            pass
        assert len(calls) == 3
        saved = await service.get_session(**identity)
        assert saved.events[: len(originals)] == originals
        pages = [
            p.function_response.response
            for e in saved.events
            if e.content
            for p in e.content.parts or []
            if p.function_response and p.function_response.name == READ_CONTEXT_TOOL
        ]
        assert len(pages) == 2 and all(len(p["text"]) == 8000 for p in pages)
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


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "offsets",
    [[0, 1000, 2000, 3000, 4000, 5000, 6000, 7000], [0, 16000, 4000, 14000, 0]],
)
async def test_overlapping_pages_reconstruct_all_evidence_without_alias_chains(offsets):
    request, scope, refs, config = await scenario(offsets)
    originals = copy.deepcopy(scope.session.events)
    newest = copy.deepcopy(request.contents[-1])
    before = len(json.dumps([c.model_dump() for c in request.contents]))
    compact_read_results(request.contents, scope, refs, config)
    responses = {
        c.parts[0].function_response.id: c.parts[0].function_response.response
        for c in request.contents[1:]
    }
    for event in originals[1:]:
        original = event.content.parts[0].function_response
        assert (
            retained_text(responses[original.id], responses)
            == original.response["text"]
        )
    assert len(json.dumps([c.model_dump() for c in request.contents])) < before - 6000
    assert request.contents[-1] == newest and scope.session.events == originals


@pytest.mark.asyncio
async def test_read_budget_accounts_for_escaped_control_characters_before_storage():
    text = "\x01" * 40000
    request, scope = mcp_source(text)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 4000
    value = await read(request, scope, next(iter(refs)))
    encoded = (
        len(
            json.dumps(
                json.dumps(value, ensure_ascii=False), ensure_ascii=False
            ).encode()
        )
        + 128
    )
    assert encoded <= 4000
    assert value["text"] and value["text"] == text[value["offset"] : value["end"]]
    assert value["next_offset"] == value["end"]


@pytest.mark.asyncio
async def test_read_with_small_page_budget_keeps_literal_query_in_result():
    text = "Archive notes. " * 3000 + "EXACT_FACT=7319" + " archive continuation" * 1000
    request, scope = mcp_source(text)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_page_bytes = 128
    value = await read(request, scope, next(iter(refs)), query="EXACT_FACT=7319")
    assert "EXACT_FACT=7319" in value["text"]
    assert value["text"] == text[value["offset"] : value["end"]]


@pytest.mark.asyncio
async def test_finished_previous_turn_can_archive_but_current_evidence_stays_exact():
    request, scope, refs, config = await scenario([0, 12000, 24000])
    request.contents.insert(
        -1,
        types.Content(
            role="model", parts=[types.Part(text="Previous task completed.")]
        ),
    )
    request.contents.insert(
        -1,
        types.Content(role="user", parts=[types.Part(text="Check the next section.")]),
    )
    newest = copy.deepcopy(request.contents[-1])
    originals = copy.deepcopy(scope.session.events)
    compact_read_results(request.contents, scope, refs, config)
    for content in request.contents[1:3]:
        value = content.parts[0].function_response.response
        assert value["archived"] and not value["complete"]
        assert "included_in_response" not in value
        restored = await read(
            request, scope, value["reference"], offset=value["offset"]
        )
        original = next(
            e.content.parts[0].function_response.response
            for e in originals[1:]
            if e.content.parts[0].function_response.response["offset"]
            == value["offset"]
        )
        assert restored["text"] == original["text"]
    assert request.contents[-1] == newest and scope.session.events == originals


@pytest.mark.asyncio
async def test_parallel_read_calls_share_input_allowance_and_cannot_return_empty_pages():
    import asyncio

    text = "Concurrent read evidence. " * 4000
    request, scope = mcp_source(text)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    scope.retrieval_headroom = 5000
    ref = next(iter(refs))
    values = await asyncio.gather(
        *(read(request, scope, ref, offset=i * 10000) for i in range(4))
    )
    admitted = [v for v in values if "text" in v]
    assert admitted and any(
        v.get("error") == "context_retrieval_input_budget_exhausted" for v in values
    )
    charge = sum(
        len(json.dumps(json.dumps(v, ensure_ascii=False), ensure_ascii=False).encode())
        + 128
        for v in admitted
    )
    assert charge <= 5000 and scope.retrieval_headroom >= 0
    assert all(
        v["text"] and v["text"] == text[v["offset"] : v["end"]] for v in admitted
    )
    assert scope.retrieval_input_exhausted
    compact_tool_results(request, scope, ContextCompressionConfig())
    assert READ_CONTEXT_TOOL not in {
        f.name for t in request.config.tools for f in t.function_declarations or []
    }
    again = await read(request, scope, ref)
    assert again["remaining_calls"] == 0 and "text" not in again
