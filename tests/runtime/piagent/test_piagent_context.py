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

import asyncio
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.runtime.piagent.config import PiAgentModelConfig
from veadk.runtime.piagent.context_bridge import build_pi_messages, pi_context_extension


MODEL = PiAgentModelConfig(
    provider_id="veadk",
    model="test-model",
    base_url="https://model.invalid",
    api_key="private-model-credential",
    api="openai-completions",
    api_key_env="TEST_KEY",
)


def _request(*contents):
    return LlmRequest(
        contents=list(contents),
        config=types.GenerateContentConfig(system_instruction="Wait for tool results."),
    )


def _call(call_id="call-1"):
    return types.Content(
        role="model",
        parts=[
            types.Part(
                function_call=types.FunctionCall(
                    id=call_id, name="lookup", args={"key": "same"}
                )
            )
        ],
    )


def _response(call_id="call-1"):
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id=call_id, name="lookup", response={"value": False}
                )
            )
        ],
    )


def test_history_keeps_native_roles_and_tool_pairing():
    request = _request(
        types.Content(role="user", parts=[types.Part(text="Look it up.")]),
        _call(),
        _response(),
        types.Content(
            role="model",
            parts=[
                types.Part(text="private reasoning", thought=True),
                types.Part(text="It is false."),
            ],
        ),
        types.Content(role="user", parts=[types.Part(text="Look it up again.")]),
        _call("call-2"),
        _response("call-2"),
    )
    messages = build_pi_messages(request, MODEL)
    assert [m["role"] for m in messages] == [
        "user",
        "assistant",
        "toolResult",
        "assistant",
        "user",
        "assistant",
        "toolResult",
    ]
    assert messages[1]["content"][0]["id"] == messages[2]["toolCallId"] == "call-1"
    assert messages[5]["content"][0]["id"] == messages[6]["toolCallId"] == "call-2"
    assert json.loads(messages[6]["content"][0]["text"]) == {"value": False}
    assert "private reasoning" not in json.dumps(messages)
    assert messages[1]["provider"] == MODEL.provider_id


def test_missing_call_ids_are_paired_without_reusing_another_call():
    messages = build_pi_messages(
        _request(_call(None), _response(None), _call(None), _response(None)), MODEL
    )
    assert messages[0]["content"][0]["id"] == messages[1]["toolCallId"]
    assert messages[2]["content"][0]["id"] == messages[3]["toolCallId"]
    assert messages[1]["toolCallId"] != messages[3]["toolCallId"]


def test_generated_call_id_does_not_collide_with_explicit_parallel_id():
    messages = build_pi_messages(
        _request(
            _call("veadk-call-1"),
            _call(None),
            _response("veadk-call-1"),
            _response(None),
        ),
        MODEL,
    )
    ids = [call["id"] for call in messages[0]["content"]]
    assert len(set(ids)) == 2
    assert [m["toolCallId"] for m in messages[1:]] == ids


def test_history_uses_the_current_pi_tool_alias():
    messages = build_pi_messages(
        _request(_call(), _response()), MODEL, tool_names={"lookup": "veadk_lookup"}
    )
    assert messages[0]["content"][0]["name"] == "veadk_lookup"
    assert messages[1]["toolName"] == "veadk_lookup"


@pytest.mark.parametrize("packed_results", [False, True])
def test_parallel_calls_share_one_assistant_and_keep_reversed_results(packed_results):
    responses = [_response("call-b"), _response("call-a")]
    if packed_results:
        responses = [
            types.Content(
                role="user",
                parts=[part for result in responses for part in result.parts],
            )
        ]
    messages = build_pi_messages(
        _request(_call("call-a"), _call("call-b"), *responses), MODEL
    )
    assert [m["role"] for m in messages] == ["assistant", "toolResult", "toolResult"]
    assert [call["id"] for call in messages[0]["content"]] == ["call-a", "call-b"]
    assert [m["toolCallId"] for m in messages[1:]] == ["call-b", "call-a"]


@pytest.mark.parametrize("same_content", [False, True])
def test_tool_result_precedes_new_user_text_without_merging_the_user_turn(same_content):
    text = types.Part(text="Now ask a different question.")
    result = _response()
    following = [types.Content(role="user", parts=[text]), result]
    if same_content:
        following = [types.Content(role="user", parts=[text, *result.parts])]
    messages = build_pi_messages(_request(_call(), *following), MODEL)
    assert [m["role"] for m in messages] == ["assistant", "toolResult", "user"]
    assert messages[-1]["content"] == [{"type": "text", "text": text.text}]


def test_history_preserves_pydantic_json_values():
    call, result = _call(), _response()
    value = datetime(2026, 11, 3, tzinfo=timezone.utc)
    call.parts[0].function_call.args = {"at": value}
    result.parts[0].function_response.response = {"at": value}
    messages = build_pi_messages(_request(call, result), MODEL)
    assert messages[0]["content"][0]["arguments"] == {"at": "2026-11-03T00:00:00Z"}
    assert json.loads(messages[1]["content"][0]["text"]) == {
        "at": "2026-11-03T00:00:00Z"
    }


def test_reused_call_id_in_a_new_turn_keeps_each_result_separate():
    second = _response()
    second.parts[0].function_response.response = {"value": True}
    messages = build_pi_messages(
        _request(
            _call(),
            _response(),
            types.Content(role="user", parts=[types.Part(text="Do it again.")]),
            _call(),
            second,
        ),
        MODEL,
    )
    assert [m["role"] for m in messages] == [
        "assistant",
        "toolResult",
        "user",
        "assistant",
        "toolResult",
    ]
    assert json.loads(messages[1]["content"][0]["text"]) == {"value": False}
    assert json.loads(messages[4]["content"][0]["text"]) == {"value": True}


def test_progress_and_final_result_share_one_protocol_result():
    final = _response()
    final.parts[0].function_response.response = {"value": "completed"}
    messages = build_pi_messages(_request(_call(), _response(), final), MODEL)
    assert [m["role"] for m in messages] == ["assistant", "toolResult"]
    assert [json.loads(p["text"]) for p in messages[1]["content"]] == [
        {"value": False},
        {"value": "completed"},
    ]


@pytest.mark.parametrize("raise_error", [False, True])
def test_context_file_is_private_isolated_and_cleaned(raise_error):
    request = _request(_call(), _response())
    paths = []
    try:
        with pi_context_extension(request, MODEL, prompt="startup") as first:
            with pi_context_extension(request, MODEL, prompt="startup") as second:
                paths = [Path(first), Path(second)]
                assert paths[0].parent != paths[1].parent
                if os.name == "posix":
                    assert stat.S_IMODE(paths[0].stat().st_mode) == 0o600
                    assert stat.S_IMODE(paths[0].parent.stat().st_mode) == 0o700
                payload = json.loads(
                    json.loads(
                        paths[0]
                        .read_text()
                        .splitlines()[0]
                        .removeprefix("const context = JSON.parse(")
                        .removesuffix(");")
                    )
                )
                assert payload["messages"][-1]["role"] == "toolResult"
                assert payload["instruction"] == "Wait for tool results."
                assert MODEL.api_key not in paths[0].read_text()
                if raise_error:
                    raise ValueError("probe failure")
    except ValueError:
        assert raise_error
    assert paths and all(not path.parent.exists() for path in paths)


@pytest.mark.asyncio
async def test_context_file_is_cleaned_on_cancellation():
    ready = asyncio.Event()
    paths = []

    async def run():
        with pi_context_extension(_request(), MODEL, prompt="startup") as filename:
            paths.append(Path(filename))
            ready.set()
            await asyncio.Event().wait()

    task = asyncio.create_task(run())
    await ready.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not paths[0].parent.exists()
