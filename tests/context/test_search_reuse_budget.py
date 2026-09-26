"""Reuse credit must be realized by the existing exact-evidence compactor."""

import asyncio
import copy
import json
from types import SimpleNamespace

import pytest
from google.adk.events import Event
from google.genai import types
from test_recoverable_context import mcp_source, read
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import current_scope
from veadk.context.search_budget import reserve_parallel_exchanges, reuse_credit
from veadk.context.tool_results import (
    READ_CONTEXT_TOOL,
    _original_reader_response,
    _reader_result_size,
    compact_read_results,
    compact_tool_results,
)


async def setup():
    text = "".join(
        f"Record {i}: invoice approval evidence remains pending.\n" for i in range(3000)
    )
    request, scope = mcp_source(text)
    policy = ContextCompressionConfig()
    refs = compact_tool_results(request, scope, policy)
    ref = next(iter(refs))
    value = await read(
        request, scope, ref, operation="search", query="invoice approval"
    )
    response = types.FunctionResponse(
        id="old-search", name=READ_CONTEXT_TOOL, response=value
    )
    content = types.Content(role="user", parts=[types.Part(function_response=response)])
    scope.session.events.append(
        Event(id="old-event", author="agent", content=copy.deepcopy(content))
    )
    request.contents.append(copy.deepcopy(content))
    return request, scope, policy, refs, ref, text


async def invoke(request, scope, ref, call_id):
    token = current_scope.set(scope)
    try:
        return await request.tools_dict[READ_CONTEXT_TOOL].func(
            reference=ref,
            operation="search",
            query="invoice approval",
            tool_context=SimpleNamespace(
                session=scope.session, agent_name="agent", function_call_id=call_id
            ),
        )
    finally:
        current_scope.reset(token)


@pytest.mark.asyncio
async def test_repeated_search_credit_matches_actual_input_saving_and_keeps_full_evidence():
    request, scope, policy, refs, ref, text = await setup()
    scope.retrieval_headroom = 1800
    old_events = copy.deepcopy(scope.session.events)
    original = copy.deepcopy(request.contents[-1].parts[0].function_response.response)
    value = await invoke(request, scope, ref, "new-search")
    assert value["matches"] == original["matches"]
    charged = 1800 - scope.retrieval_headroom
    assert 0 < charged <= 1800
    content = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="new-search", name=READ_CONTEXT_TOOL, response=value
                )
            )
        ],
    )
    scope.session.events.append(
        Event(id="new-event", author="agent", content=copy.deepcopy(content))
    )
    request.contents.append(content)
    compact_read_results(request.contents, scope, refs, policy)
    old = request.contents[-2].parts[0].function_response.response
    new = request.contents[-1].parts[0].function_response.response
    actual_growth = (
        _reader_result_size(old)
        + _reader_result_size(new)
        - _reader_result_size(original)
    )
    assert actual_growth <= charged
    for alias, match in zip(old["matches"], new["matches"], strict=True):
        assert alias["included_in_response"] == "new-search"
        assert (alias["offset"], alias["end"]) == (match["offset"], match["end"])
        assert match["text"] == text[match["offset"] : match["end"]]
    assert scope.session.events[: len(old_events)] == old_events


@pytest.mark.asyncio
async def test_parallel_repeated_searches_cannot_spend_the_same_saving_twice():
    request, scope, _, _, ref, _ = await setup()
    scope.retrieval_headroom = 1800
    values = await asyncio.gather(
        *(invoke(request, scope, ref, f"new-{i}") for i in range(2))
    )
    assert values[0].get("matches")
    assert values[1]["error"] == "context_retrieval_input_budget_exhausted"
    assert scope.retrieval_reuse_claimed == {"old-search"}
    assert scope.retrieval_headroom >= 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    [
        "new_turn",
        "protected",
        "unknown_field",
        "wrong_hash",
        "wrong_text",
        "unpersisted",
        "duplicate_id",
        "same_call_id",
        "claimed",
        "already_projected",
    ],
)
async def test_unsafe_or_unavailable_duplicates_receive_no_credit(mutation):
    request, scope, policy, _, _, _ = await setup()
    response = request.contents[-1].parts[0].function_response
    value = copy.deepcopy(response.response)
    call_id = "new-search"
    if mutation == "new_turn":
        request.contents.append(
            types.Content(role="user", parts=[types.Part(text="A new task")])
        )
    elif mutation == "protected":
        policy = policy.model_copy(
            update={"protected_context": (value["matches"][0]["text"][100:180],)}
        )
    elif mutation in {"unknown_field", "already_projected"}:
        response.response[
            "custom_evidence" if mutation == "unknown_field" else "archived"
        ] = True
    elif mutation == "wrong_hash":
        response.response["source_sha256"] = "0" * 64
    elif mutation == "wrong_text":
        response.response["matches"][0]["text"] = "X" * len(
            response.response["matches"][0]["text"]
        )
    elif mutation == "unpersisted":
        scope.session.events.pop()
    elif mutation == "duplicate_id":
        request.contents.append(copy.deepcopy(request.contents[-1]))
    elif mutation == "same_call_id":
        call_id = response.id
    elif mutation == "claimed":
        scope.retrieval_reuse_claimed.add(response.id)
    before = copy.deepcopy(request.contents)
    assert reuse_credit(
        request.contents, scope, value, call_id, policy, _original_reader_response
    ) == (0, set())
    assert request.contents == before


@pytest.mark.asyncio
async def test_search_refusal_retires_only_reader_and_leaves_original_tools_available():
    request, scope, policy, _, ref, _ = await setup()
    scope.retrieval_headroom = 100
    originals = copy.deepcopy(scope.session.events)
    value = await invoke(request, scope, ref, "new-search")
    assert value["error"] == "context_retrieval_input_budget_exhausted"
    assert scope.retrieval_input_exhausted
    compact_tool_results(request, scope, policy)
    assert "fetch" in request.tools_dict
    names = {
        f.name
        for tool in request.config.tools or []
        for f in tool.function_declarations or []
    }
    assert READ_CONTEXT_TOOL not in names
    stale = await invoke(request, scope, ref, "stale-search")
    assert stale["remaining_calls"] == 0 and "matches" not in stale
    assert len(json.dumps(stale).encode()) < 512
    assert scope.session.events == originals


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "mutation",
    ["none", "single", "wrong_agent", "wrong_branch", "wrong_call", "newer_batch"],
)
async def test_parallel_envelope_reserve_uses_only_current_owned_batch_once(mutation):
    _, scope, _, _, ref, _ = await setup()
    count = 1 if mutation == "single" else 8
    content = types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id=f"batch-{i}",
                    name=READ_CONTEXT_TOOL,
                    args={
                        "reference": ref,
                        "operation": "search",
                        "query": f"topic_{i}",
                    },
                )
            )
            for i in range(count)
        ],
    )
    scope.session.events.append(
        Event(
            id="batch",
            author="other" if mutation == "wrong_agent" else "agent",
            branch="other" if mutation == "wrong_branch" else None,
            content=content,
        )
    )
    if mutation == "newer_batch":
        scope.session.events.append(
            Event(
                id="newer",
                author="agent",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="different", name="fetch", args={}
                            )
                        )
                    ],
                ),
            )
        )
    originals = copy.deepcopy(scope.session.events)
    scope.retrieval_headroom = 8000
    reserve_parallel_exchanges(
        scope, "unknown" if mutation == "wrong_call" else "batch-0"
    )
    remaining = scope.retrieval_headroom
    if mutation == "none":
        assert 0 < remaining < 8000
        reserve_parallel_exchanges(scope, "batch-1")
        assert scope.retrieval_headroom == remaining
    else:
        assert remaining == 8000
    assert scope.session.events == originals
