"""Account for the actual extra JSON string layer without modifying payloads."""

import copy
import json

import pytest
from google.genai import types
from veadk.context.search_budget import tool_serialization_overhead


@pytest.mark.parametrize("text", ["plain", "许可\n", '\x01"\\\t' * 100])
def test_tool_json_expansion_is_counted_for_arguments_and_results(text):
    args = {"query": text}
    result = {"matches": [{"text": text, "offset": 0, "end": len(text)}]}
    contents = [
        types.Content(
            role="model", parts=[types.Part.from_function_call(name="tool", args=args)]
        ),
        types.Content(
            role="user",
            parts=[types.Part.from_function_response(name="tool", response=result)],
        ),
    ]
    saved = copy.deepcopy(contents)
    expected = sum(
        len(json.dumps(json.dumps(v, ensure_ascii=False), ensure_ascii=False).encode())
        - len(json.dumps(v, ensure_ascii=False, separators=(",", ":")).encode())
        for v in [args, result]
    )
    assert tool_serialization_overhead(contents) == expected
    assert expected > 0 and contents == saved


def test_plain_messages_do_not_acquire_tool_serialization_cost():
    contents = [
        types.Content(
            role="user", parts=[types.Part(text='Text with "quotes" and 许可')]
        )
    ]
    assert tool_serialization_overhead(contents) == 0


@pytest.mark.parametrize("value", [{"bytes": b"opaque"}, {"values": {1, 2}}])
def test_adk_string_fallback_values_do_not_break_budget_planning(value):
    from types import SimpleNamespace

    contents = [
        SimpleNamespace(
            parts=[
                SimpleNamespace(
                    function_call=None,
                    function_response=SimpleNamespace(response=value),
                )
            ]
        )
    ]
    assert tool_serialization_overhead(contents) == len(
        json.dumps(str(value), ensure_ascii=False).encode()
    )
