# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The first forced lookup may shorten only a bound, verified tool response."""

import copy
import json

import pytest
from test_recoverable_context import mcp_source
from veadk.context.client import BudgetedLiteLLMClient
from veadk.context.config import ContextCompressionConfig
from veadk.context.runtime import current_scope
from veadk.context.tool_results import compact_tool_results


def prepared(case=None):
    text = "\n".join(
        f'Entry {i} contains distinct evidence {i}; keep quotes "Ω" and slash \\n.'
        for i in range(500)
    )
    request, scope = mcp_source(text)
    scope.projection_bytes = 12000
    scope.source_verification_allowed = True
    policy = ContextCompressionConfig(
        context_window=256000, output_reserve=1024, verify_sources=True
    )
    if case == "default":
        policy = policy.model_copy(update={"verify_sources": False})
    elif case == "protected":
        policy = policy.model_copy(update={"protected_context": ("distinct evidence",)})
    elif case == "duplicate_native_id":
        request.contents *= 2
    elif case in {"multiple_fields", "mixed_blocks"}:
        extra = {"type": "text", "text": text.replace("Entry", "Second")}
        if case == "mixed_blocks":
            extra = {
                "type": "image",
                "data": "synthetic-image",
                "mimeType": "image/png",
            }
        for target in (request.contents[0], scope.session.events[0].content):
            target.parts[0].function_response.response["content"].append(
                copy.deepcopy(extra)
            )
    if case == "parallel_calls":
        event = copy.deepcopy(scope.session.events[0])
        event.id = "second-source"
        event.content.parts[0].function_response.id = "fetch-2"
        event.content.parts[0].function_response.response["content"][0]["text"] = (
            text.replace("Entry", "Second")
        )
        scope.session.events.append(event)
        request.contents.append(copy.deepcopy(event.content))
    originals = copy.deepcopy(scope.session.events)
    refs = compact_tool_results(request, scope, policy)
    response = request.contents[0].parts[0].function_response
    payload = dict(
        model="openai/deepseek-v4-1-flash-260910",
        api_base="https://ark.cn-beijing.volces.com/api/v3",
        extra_body={"thinking": {"type": "disabled"}},
        max_tokens=1024,
        messages=[
            {"role": "system", "content": "Inspect original evidence."},
            {
                "role": "assistant",
                "tool_calls": [
                    {
                        "id": "fetch-1",
                        "type": "function",
                        "function": {"name": "fetch", "arguments": "{}"},
                    }
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "fetch-1",
                "content": json.dumps(response.response),
            },
            {"role": "user", "content": "What do the records establish?"},
        ],
        tools=[
            {
                "type": "function",
                "function": {
                    "name": "veadk_read_context",
                    "parameters": {"type": "object"},
                },
            }
        ],
    )
    if case == "parallel_calls":
        call = copy.deepcopy(payload["messages"][1]["tool_calls"][0])
        call["id"] = "fetch-2"
        payload["messages"][1]["tool_calls"].append(call)
        payload["messages"].insert(
            3,
            {
                "role": "tool",
                "tool_call_id": "fetch-2",
                "content": json.dumps(
                    request.contents[1].parts[0].function_response.response
                ),
            },
        )
    return scope, policy, payload, originals, refs


async def send(scope, policy, payload):
    calls = []

    class Delegate:
        async def acompletion(self, **kwargs):
            calls.append(copy.deepcopy(kwargs))
            return "synthetic-response"

    token = current_scope.set(scope)
    try:
        await BudgetedLiteLLMClient(Delegate(), policy).acompletion(**payload)
    finally:
        current_scope.reset(token)
    assert len(calls) == 1
    return calls[0]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case", [None, "multiple_fields", "mixed_blocks", "same_text_in_user"]
)
async def test_first_tool_lookup_changes_only_bound_text_then_restores_normal(case):
    scope, policy, payload, originals, refs = prepared(case)
    if case == "same_text_in_user":
        payload["messages"][-1]["content"] = payload["messages"][2]["content"]
    original_payload = copy.deepcopy(payload)
    scope.retrieval_headroom, scope.retrieval_read_bytes = 1000, 256
    first = await send(scope, policy, payload)
    before = json.loads(payload["messages"][2]["content"])
    after = json.loads(first["messages"][2]["content"])
    assert after != before, (
        "The forced source lookup must not carry the full normal preview."
    )
    assert len(json.dumps(after).encode()) < len(json.dumps(before).encode())
    assert first["messages"][:2] == payload["messages"][:2]
    assert first["messages"][3:] == payload["messages"][3:]
    assert first["tools"] == payload["tools"]
    assert after["isError"] == before["isError"]
    assert len(after["content"]) == len(before["content"])
    for old, new, source in zip(
        before["content"],
        after["content"],
        originals[0].content.parts[0].function_response.response["content"],
    ):
        if old["type"] != "text":
            assert new == old
            continue
        assert set(new) == set(old)
        opening = new["text"].split("\n", 1)[1]
        assert len(opening.encode()) <= 256 and source["text"].startswith(opening)
        assert any(reference in new["text"] for reference in refs)
    assert scope.retrieval_headroom == 1000 and scope.retrieval_read_bytes == 256
    assert scope.session.events == originals and payload == original_payload
    second = await send(scope, policy, payload)
    assert second["messages"] == payload["messages"]
    assert "tool_choice" not in second


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "case",
    [
        "default",
        "protected",
        "duplicate_native_id",
        "attempted",
        "already_read",
        "other_session",
        "other_user",
        "other_app",
        "other_agent",
        "other_branch",
        "changed_original",
        "missing_reference",
        "unknown_wire_field",
        "multipart_wire",
        "wrong_tool_name",
        "wrong_message_name",
        "wrong_call_id",
        "duplicate_wire_id",
        "duplicate_assistant_id",
        "missing_call",
        "response_before_call",
        "changed_sibling",
        "changed_text",
        "duplicate_json_key",
        "invalid_json",
        "nonfinite_json",
        "numeric_tool_calls",
        "string_tool_calls",
        "mapping_tool_calls",
        "invalid_call_item",
        "stream",
        "explicit_choice",
        "schema",
        "unsupported_model",
        "thinking_enabled",
    ],
)
async def test_unknown_or_unbound_tool_wire_is_not_shortened(case):
    scope, policy, payload, originals, refs = prepared(case)
    message = payload["messages"][2]
    call = payload["messages"][1]["tool_calls"][0]
    if case == "attempted":
        scope.source_verification_attempted = True
    elif case == "already_read":
        scope.retrieval_calls = 1
    elif case in {"other_session", "other_user", "other_app"}:
        setattr(
            scope.session,
            {"other_session": "id", "other_user": "user_id", "other_app": "app_name"}[
                case
            ],
            "other",
        )
    elif case in {"other_agent", "other_branch"}:
        setattr(scope, "agent_name" if case == "other_agent" else "branch", "other")
    elif case == "changed_original":
        scope.session.events[0].content.parts[0].function_response.response["content"][
            0
        ]["text"] += "changed"
    elif case == "missing_reference":
        scope.pending_state.clear()
    elif case == "unknown_wire_field":
        message["unknown"] = True
    elif case == "multipart_wire":
        message["content"] = [{"type": "text", "text": message["content"]}]
    elif case == "wrong_tool_name":
        call["function"]["name"] = "other"
    elif case == "wrong_message_name":
        message["name"] = "other"
    elif case == "wrong_call_id":
        message["tool_call_id"] = "other"
    elif case == "duplicate_wire_id":
        payload["messages"].insert(3, copy.deepcopy(message))
    elif case == "duplicate_assistant_id":
        payload["messages"][1]["tool_calls"].append(copy.deepcopy(call))
    elif case in {
        "numeric_tool_calls",
        "string_tool_calls",
        "mapping_tool_calls",
        "invalid_call_item",
    }:
        payload["messages"][1]["tool_calls"] = {
            "numeric_tool_calls": 7,
            "string_tool_calls": "unknown",
            "mapping_tool_calls": {"call": call},
            "invalid_call_item": [call, 7],
        }[case]
    elif case == "missing_call":
        payload["messages"].pop(1)
    elif case == "response_before_call":
        payload["messages"][1], payload["messages"][2] = message, payload["messages"][1]
    elif case in {"changed_sibling", "changed_text"}:
        value = json.loads(message["content"])
        if case == "changed_sibling":
            value["isError"] = True
        else:
            value["content"][0]["text"] += " changed"
        message["content"] = json.dumps(value)
    elif case == "duplicate_json_key":
        message["content"] = '{"isError": true, ' + message["content"][1:]
    elif case == "invalid_json":
        message["content"] += "invalid"
    elif case == "nonfinite_json":
        message["content"] = message["content"].replace(
            '"isError": false', '"isError": NaN'
        )
    elif case == "stream":
        payload["stream"] = True
    elif case == "explicit_choice":
        payload["tool_choice"] = "auto"
    elif case == "schema":
        payload["response_format"] = {"type": "json_object"}
    elif case == "unsupported_model":
        payload["model"] = "openai/unsupported-model"
    elif case == "thinking_enabled":
        payload["extra_body"] = {"thinking": {"type": "enabled"}}
    original_payload = copy.deepcopy(payload)
    result = await send(scope, policy, payload)
    assert result["messages"] == payload["messages"]
    assert payload == original_payload


@pytest.mark.asyncio
async def test_parallel_tool_responses_preserve_distinct_source_bindings():
    scope, policy, payload, originals, refs = prepared("parallel_calls")
    first = await send(scope, policy, payload)
    assert len(refs) == 2
    assert len(first["messages"]) == len(payload["messages"])
    changed = 0
    for before, after in zip(payload["messages"], first["messages"]):
        if before["role"] != "tool":
            assert after == before
            continue
        assert before["tool_call_id"] == after["tool_call_id"]
        text = json.loads(after["content"])["content"][0]["text"]
        reference, source = next(
            (r, s) for r, s in refs.items() if s["call_id"] == before["tool_call_id"]
        )
        assert reference in text
        assert all(other not in text for other in refs if other != reference)
        original = next(e for e in originals if e.id == source["event_id"])
        raw = original.content.parts[0].function_response.response["content"][0]["text"]
        assert raw.startswith(text.split("\n", 1)[1])
        assert len(after["content"].encode()) < len(before["content"].encode())
        changed += 1
    assert changed == 2 and scope.session.events == originals
    assert (await send(scope, policy, payload))["messages"] == payload["messages"]
