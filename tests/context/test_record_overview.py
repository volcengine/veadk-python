"""Declared record statistics are exact, optional, bounded and recoverable."""

import copy
import hashlib
import json
import re

import pytest
from google.adk.events import Event
from google.adk.models.lite_llm import LiteLLMClient
from google.genai import types
from litellm import ModelResponse
from test_recoverable_context import mcp_source, read

from veadk import Agent, Runner
from veadk.context.budget import check_payload
from veadk.context.config import ContextCompressionConfig
from veadk.context.evidence import repeated_projection
from veadk.context.runtime import is_summary
from veadk.context.tool_results import compact_tool_results
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm

MARKER = "EXACT_RECORD_OVERVIEW="


def encode(records, record_format):
    if record_format == "json_array_strings":
        return json.dumps(records, ensure_ascii=False)
    return "\n\n".join(f"Paragraph {i}: {text}" for i, text in enumerate(records, 1))


def project(text, record_format=None, budget=16000, **metadata):
    request, scope = mcp_source(
        text, context_compression_record_format=record_format, **metadata
    )
    scope.projection_bytes = budget
    scope.lossless_projection_bytes = budget
    originals = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, ContextCompressionConfig())
    value = (
        request.contents[0].parts[0].function_response.response["content"][0]["text"]
    )
    assert scope.session.events == originals
    return value, request, scope, refs


def statistics(value):
    assert MARKER in value
    return json.JSONDecoder().raw_decode(value.split(MARKER, 1)[1])[0]


@pytest.mark.parametrize("fmt", ["numbered_paragraphs", "json_array_strings"])
@pytest.mark.asyncio
async def test_full_source_counts_and_hash_match_reader(fmt):
    records = ["Original Alpha " * 90, "Original Beta " * 90] * 12
    text = encode(records, fmt)
    value, request, scope, refs = project(text, fmt)
    data = statistics(value)
    assert data["record_count"] == len(records)
    assert data["unique_record_count"] == 2
    assert data["record_format"] == fmt and data["complete"] is True
    assert data["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert data["equality"]
    assert len(refs) == 1
    result = await read(request, scope, next(iter(refs)), operation="count_unique")
    assert result["value"] == data["unique_record_count"]
    original = await read(request, scope, next(iter(refs)), offset=10)
    assert original["text"] == text[10 : 10 + len(original["text"])]


@pytest.mark.parametrize("fmt", [None, "csv", "auto"])
def test_no_statistics_without_supported_developer_contract(fmt):
    text = encode(["Record " * 300] * 20, "numbered_paragraphs")
    assert MARKER not in project(text, fmt)[0]


@pytest.mark.parametrize(
    "text,fmt",
    [
        ("Paragraph 2: " + "a" * 18000, "numbered_paragraphs"),
        (json.dumps([1, "x" * 18000]), "json_array_strings"),
        ("[" * 18000, "json_array_strings"),
        (json.dumps(["xx"] * 10001), "json_array_strings"),
        (json.dumps(["x" * 1000001] * 2), "json_array_strings"),
    ],
    ids=["nonconsecutive", "nonstring", "invalid-json", "record-limit", "byte-limit"],
)
def test_invalid_or_excessive_sources_keep_existing_projection(text, fmt):
    value, _, _, refs = project(text, fmt)
    assert refs and MARKER not in value


@pytest.mark.parametrize("fmt", ["numbered_paragraphs", "json_array_strings"])
def test_unicode_and_near_duplicates_are_not_normalized(fmt):
    records = ["完整证据 " * 300 + ending for ending in ["A", "a", "é", "e\u0301"]]
    text = encode(records * 4, fmt)
    value = project(text, fmt, budget=30000)[0]
    assert statistics(value)["unique_record_count"] == 4


def test_json_string_whitespace_remains_significant():
    records = ["large exact record " * 200 + ending for ending in ["", " ", "\n"]]
    value = project(encode(records * 4, "json_array_strings"), "json_array_strings")[0]
    assert statistics(value)["unique_record_count"] == 3


def test_statistics_never_displace_lossless_evidence_when_budget_is_tight():
    text = encode(
        ["Alpha evidence " * 100, "Beta evidence " * 100] * 20, "numbered_paragraphs"
    )
    original = repeated_projection(text)["text"]
    size = len(original.encode())
    for budget in (size, size + 20):
        value, _, scope, _ = project(text, "numbered_paragraphs", budget=budget)
        assert value.startswith(original + "\n[Lossless projection")
        assert MARKER not in value and not scope.lossy_references
    value = project(text, "numbered_paragraphs", budget=size + 1000)[0]
    assert value.startswith(original + "\n" + MARKER)
    assert statistics(value)["unique_record_count"] == 2


def test_small_sources_and_protected_sources_are_unchanged():
    small = encode(["A", "B", "A"], "numbered_paragraphs")
    value, _, _, refs = project(small, "numbered_paragraphs")
    assert value == small and not refs
    text = encode(["PROTECTED " * 300] * 10, "numbered_paragraphs")
    request, scope = mcp_source(
        text, context_compression_record_format="numbered_paragraphs"
    )
    refs = compact_tool_results(
        request, scope, ContextCompressionConfig(protected_context=["PROTECTED"])
    )
    assert not refs
    assert (
        request.contents[0].parts[0].function_response.response["content"][0]["text"]
        == text
    )


@pytest.mark.asyncio
async def test_native_runner_sqlite_sends_statistics_and_reloads_exact_source(tmp_path):
    text = encode(
        ["Exact evidence " * 100, "Other record " * 100] * 20, "numbered_paragraphs"
    )
    request, _ = mcp_source(
        text, context_compression_record_format="numbered_paragraphs"
    )
    tool = request.tools_dict["fetch"]
    identity = {"app_name": "record_test", "user_id": "user", "session_id": "session"}
    policy = ContextCompressionConfig(
        context_window=256000, input_limit=22000, output_reserve=1024
    )
    path = str(tmp_path / "records.sqlite3")
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    session = await service.create_session(**identity)
    contents = [
        types.Content(role="user", parts=[types.Part(text="Load records")]),
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
        request.contents[0],
    ]
    for i, content in enumerate(contents):
        await service.append_event(
            session,
            Event(
                id=f"seed-{i}",
                timestamp=1700000000 + i,
                author="user" if i == 0 else "agent",
                content=content,
            ),
        )
    originals = copy.deepcopy(session.events)
    await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    calls = []

    class Client(LiteLLMClient):
        async def acompletion(self, **kwargs):
            assert not is_summary.get()
            check_payload(kwargs, policy)
            calls.append(copy.deepcopy(kwargs["messages"]))
            results = [m for m in kwargs["messages"] if m["role"] == "tool"]
            if len(calls) == 1:
                source = json.loads(results[0]["content"])["content"][0]["text"]
                assert statistics(source)["unique_record_count"] == 2
                reference = re.search(r"ctx_[a-f0-9]{24}", source)[0]
                message = {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "original-read",
                            "type": "function",
                            "function": {
                                "name": "veadk_read_context",
                                "arguments": json.dumps(
                                    {"reference": reference, "offset": 100}
                                ),
                            },
                        }
                    ],
                }
            else:
                assert len(calls) == 2
                result = json.loads(results[-1]["content"])
                assert result["text"] == text[100 : 100 + len(result["text"])]
                assert (
                    result["source_sha256"] == hashlib.sha256(text.encode()).hexdigest()
                )
                message = {"role": "assistant", "content": "2"}
            return ModelResponse(model=kwargs["model"], choices=[{"message": message}])

    model = RetryingLiteLlm(
        model="openai/context-test",
        api_key="offline-test",
        llm_client=Client(),
        context_compression=policy,
        max_tokens=1024,
    )
    agent = Agent(name="agent", model=model, model_api_key="offline-test", tools=[tool])
    runner = Runner(agent=agent, app_name=identity["app_name"], session_service=service)
    try:
        async for _ in runner.run_async(
            user_id="user",
            session_id="session",
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Count the exact distinct records.")],
            ),
        ):
            pass
        assert len(calls) == 2
        saved = await service.get_session(**identity)
        assert saved.events[: len(originals)] == originals
    finally:
        await service.close()
    service = ShortTermMemory(
        backend="sqlite", local_database_path=path
    ).session_service
    try:
        restored = await service.get_session(**identity)
        assert restored.model_dump() == saved.model_dump()
    finally:
        await service.close()
