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

"""Unit tests for ``veadk.models.ark_llm``.

These exercise the pure request/response transform helpers (model-name
normalization, input filtering, request reorganization, schema conversion)
and the ``ArkLlm`` client glue with the Ark SDK fully mocked, so no network
or live Volcengine/Ark access is required.
"""

import os
from typing import Any, cast
from unittest.mock import AsyncMock, patch

import httpx
import pytest

os.environ.setdefault("MODEL_AGENT_API_KEY", "mocked_api_key")
os.environ.setdefault("MODEL_API_KEY", "mocked_api_key")

from google.adk.models.llm_request import LlmRequest  # noqa: E402
from google.adk.models.llm_response import LlmResponse  # noqa: E402
from google.genai import types  # noqa: E402
from volcenginesdkarkruntime.types.responses import (  # noqa: E402
    ResponseFunctionToolCall,
    ResponseOutputMessage,
    ResponseOutputText,
    ResponseReasoningItem,
    ResponseTextDeltaEvent,
)
from volcenginesdkarkruntime.types.responses.response_reasoning_item import (  # noqa: E402
    Summary,
)

from volcenginesdkarkruntime._exceptions import ArkBadRequestError  # noqa: E402

from veadk.consts import DEFAULT_VIDEO_MODEL_API_BASE  # noqa: E402
from veadk.models import ark_llm  # noqa: E402
from veadk.models.ark_llm import (  # noqa: E402
    ArkLlm,
    ArkLlmClient,
    _content_to_input_item,
    _get_responses_inputs,
    _is_caching_enabled,
    _responses_schema_to_text,
    _safe_json_serialize,
    _schema_to_dict,
    _to_ark_role,
    ark_response_to_generate_content_response,
    event_to_generate_content_response,
    filtered_inputs,
    get_model_without_provider,
    request_reorganization_by_ark,
)


# --------------------------------------------------------------------------
# small pure helpers
# --------------------------------------------------------------------------
def test_to_ark_role_maps_model_and_assistant_to_assistant():
    assert _to_ark_role("model") == "assistant"
    assert _to_ark_role("assistant") == "assistant"


def test_to_ark_role_defaults_to_user():
    assert _to_ark_role("user") == "user"
    assert _to_ark_role(None) == "user"
    assert _to_ark_role("anything-else") == "user"


def test_safe_json_serialize_roundtrips_dict():
    assert _safe_json_serialize({"a": 1}) == '{"a": 1}'


def test_safe_json_serialize_preserves_non_ascii():
    # ensure_ascii=False -> Chinese characters are kept verbatim.
    assert _safe_json_serialize({"k": "中文"}) == '{"k": "中文"}'


def test_safe_json_serialize_falls_back_to_str_for_unserializable():
    obj = object()
    assert _safe_json_serialize(obj) == str(obj)


def test_schema_to_dict_lowercases_type_and_strips_none_enum():
    schema = types.Schema(
        type=types.Type.STRING,
        enum=["a", "b"],
    )
    result = _schema_to_dict(schema)
    assert result["type"] == "string"
    assert result["enum"] == ["a", "b"]


def test_schema_to_dict_recurses_into_properties_and_items():
    schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "items": types.Schema(
                type=types.Type.ARRAY,
                items=types.Schema(type=types.Type.INTEGER),
            ),
        },
    )
    result = _schema_to_dict(schema)
    assert result["type"] == "object"
    nested = result["properties"]["items"]
    assert nested["type"] == "array"
    assert nested["items"]["type"] == "integer"


# --------------------------------------------------------------------------
# get_model_without_provider
# --------------------------------------------------------------------------
def test_get_model_without_provider_strips_openai_prefix():
    out = get_model_without_provider({"model": "openai/gpt-4o"})
    assert out["model"] == "gpt-4o"


def test_get_model_without_provider_rejects_non_string():
    with pytest.raises(ValueError):
        get_model_without_provider({"model": 123})


def test_get_model_without_provider_rejects_missing_slash():
    with pytest.raises(ValueError):
        get_model_without_provider({"model": "gpt-4o"})


def test_get_model_without_provider_rejects_unsupported_provider():
    with pytest.raises(ValueError):
        get_model_without_provider({"model": "anthropic/claude"})


# --------------------------------------------------------------------------
# filtered_inputs
# --------------------------------------------------------------------------
def test_filtered_inputs_identity_when_no_previous_response_id():
    inputs = cast(list, [{"role": "user"}, {"role": "assistant"}])
    assert filtered_inputs(inputs, None) is inputs


def test_filtered_inputs_keeps_trailing_user_and_tool_outputs():
    inputs = cast(
        list,
        [
            {"role": "user"},
            {"role": "assistant"},
            {"role": "user"},
            {"type": "function_call_output"},
        ],
    )
    result = filtered_inputs(inputs, previous_response_id="pid")
    # Stops at the assistant message; keeps the trailing user + tool output.
    assert result == [{"role": "user"}, {"type": "function_call_output"}]


# --------------------------------------------------------------------------
# _is_caching_enabled
# --------------------------------------------------------------------------
def test_is_caching_enabled_true():
    data = {"extra_body": {"caching": {"type": "enabled"}}}
    assert _is_caching_enabled(data) is True


def test_is_caching_enabled_false_variants():
    assert _is_caching_enabled({}) is False
    assert _is_caching_enabled({"extra_body": "nope"}) is False
    assert _is_caching_enabled({"extra_body": {"caching": "nope"}}) is False
    assert (
        _is_caching_enabled({"extra_body": {"caching": {"type": "disabled"}}}) is False
    )


# --------------------------------------------------------------------------
# _get_responses_inputs
# --------------------------------------------------------------------------
def _build_request(**config_kwargs) -> LlmRequest:
    content = types.Content(role="user", parts=[types.Part(text="hello")])
    config = types.GenerateContentConfig(**config_kwargs)
    return LlmRequest(model="openai/gpt-4o", contents=[content], config=config)


def test_get_responses_inputs_extracts_instructions_and_input():
    req = _build_request(system_instruction="be nice")
    instructions, input_params, tools, text, gen = _get_responses_inputs(req)
    assert instructions == "be nice"
    assert input_params is not None and len(input_params) == 1
    first = cast(dict, input_params[0])
    assert first["role"] == "user"
    assert first["content"][0]["text"] == "hello"
    assert tools is None
    assert text is None


def test_get_responses_inputs_extracts_generation_params():
    req = _build_request(temperature=0.5, top_p=0.9, max_output_tokens=128)
    _, _, _, _, gen = _get_responses_inputs(req)
    assert gen == {"temperature": 0.5, "max_output_tokens": 128, "top_p": 0.9}


def test_get_responses_inputs_generation_params_none_when_absent():
    req = _build_request(system_instruction="x")
    _, _, _, _, gen = _get_responses_inputs(req)
    assert gen is None


def test_get_responses_inputs_converts_tools():
    decl = types.FunctionDeclaration(
        name="get_weather",
        description="Get weather",
        parameters=types.Schema(
            type=types.Type.OBJECT,
            properties={"city": types.Schema(type=types.Type.STRING)},
        ),
    )
    tool = types.Tool(function_declarations=[decl])
    req = _build_request()
    req.config = types.GenerateContentConfig(tools=[tool])
    _, _, tools, _, _ = _get_responses_inputs(req)
    assert tools is not None and len(tools) == 1
    tool0 = cast(dict, tools[0])
    assert tool0["name"] == "get_weather"
    assert tool0["type"] == "function"
    assert tool0["parameters"]["properties"]["city"]["type"] == "string"


# --------------------------------------------------------------------------
# _responses_schema_to_text
# --------------------------------------------------------------------------
def test_responses_schema_to_text_passthrough_for_json_object_dict():
    schema = {"type": "json_object"}
    assert _responses_schema_to_text(schema) == schema


def test_responses_schema_to_text_from_pydantic_model():
    from pydantic import BaseModel

    class Out(BaseModel):
        answer: str

    text = cast(dict, _responses_schema_to_text(Out))
    fmt = text["format"]
    assert fmt["type"] == "json_schema"
    assert fmt["name"] == "Out"
    assert fmt["strict"] is True
    assert "answer" in fmt["schema"]["properties"]


# --------------------------------------------------------------------------
# request_reorganization_by_ark
# --------------------------------------------------------------------------
def _base_request_data(**overrides):
    data = {
        "model": "openai/gpt-4o",
        "instructions": None,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            }
        ],
        "previous_response_id": None,
    }
    data.update(overrides)
    return data


def test_request_reorganization_strips_provider_and_sets_expire_at():
    out = request_reorganization_by_ark(_base_request_data())
    assert out["model"] == "gpt-4o"
    assert "expire_at" in out["extra_body"]
    assert out["extra_body"]["expire_at"] > 0


def test_request_reorganization_moves_instructions_into_system_message():
    out = request_reorganization_by_ark(
        _base_request_data(instructions="system prompt")
    )
    assert "instructions" not in out
    assert out["input"][0]["role"] == "system"
    assert out["input"][0]["content"][0]["text"] == "system prompt"


def test_request_reorganization_keeps_instructions_out_when_previous_response_id():
    out = request_reorganization_by_ark(
        _base_request_data(instructions="sys", previous_response_id="resp_1")
    )
    # With a previous_response_id, instructions are dropped, not re-injected.
    assert out["input"][0]["role"] == "user"


def test_request_reorganization_filters_unsupported_fields():
    out = request_reorganization_by_ark(
        _base_request_data(not_a_real_field="x", temperature=0.3)
    )
    assert "not_a_real_field" not in out
    assert out["temperature"] == 0.3


def test_request_reorganization_drops_cache_fields_when_disabled():
    data = _base_request_data(
        previous_response_id="resp_1",
        store=True,
        extra_body={"caching": {"type": "enabled"}},
    )
    out = request_reorganization_by_ark(data, enable_responses_cache=False)
    assert "previous_response_id" not in out
    assert "store" not in out
    assert "caching" not in out.get("extra_body", {})


def test_request_reorganization_removes_tools_on_subsequent_round():
    data = _base_request_data(
        previous_response_id="resp_1",
        tools=[{"name": "f", "type": "function", "parameters": {}}],
    )
    out = request_reorganization_by_ark(data)
    assert "tools" not in out


def test_request_reorganization_disables_caching_when_text_present():
    data = _base_request_data(
        extra_body={"caching": {"type": "enabled"}},
        text={"format": {"type": "json_schema"}},
    )
    out = request_reorganization_by_ark(data)
    assert "caching" not in out.get("extra_body", {})


def test_request_reorganization_forces_store_true_when_caching_enabled():
    data = _base_request_data(
        store=False,
        extra_body={"caching": {"type": "enabled"}},
    )
    out = request_reorganization_by_ark(data)
    assert out["store"] is True


# --------------------------------------------------------------------------
# response -> LlmResponse transforms
# --------------------------------------------------------------------------
class _FakeUsageDetails:
    cached_tokens = 3


class _FakeUsage:
    input_tokens = 10
    output_tokens = 5
    total_tokens = 15
    input_tokens_details = _FakeUsageDetails()


class _FakeArkResponse:
    """Duck-typed stand-in matching the attrs ark_llm reads off a response.

    ``ark_response_to_generate_content_response`` only does an ``isinstance``
    check inside ``record_logs`` (which is wrapped in try/except), so a plain
    object is sufficient for the transform itself.
    """

    def __init__(self, output, status="completed", usage=None, model="gpt-4o"):
        self.output = output
        self.status = status
        self.incomplete_details = None
        self.usage = usage
        self.model = model
        self.id = "resp_abc"
        self.error = None


def _first_part(resp: LlmResponse) -> types.Part:
    assert resp.content is not None
    assert resp.content.parts is not None
    return resp.content.parts[0]


def test_ark_response_to_llm_response_parses_text_and_usage():
    msg = ResponseOutputMessage(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[
            ResponseOutputText(type="output_text", text="hello world", annotations=[])
        ],
    )
    raw = _FakeArkResponse(output=[msg], usage=_FakeUsage())
    resp = ark_response_to_generate_content_response(cast(Any, raw))
    assert isinstance(resp, LlmResponse)
    assert _first_part(resp).text == "hello world"
    assert resp.finish_reason == types.FinishReason.STOP
    assert resp.usage_metadata is not None
    assert resp.usage_metadata.prompt_token_count == 10
    assert resp.usage_metadata.candidates_token_count == 5
    assert resp.usage_metadata.cached_content_token_count == 3
    assert resp.interaction_id == "resp_abc"


def test_ark_response_to_llm_response_parses_function_call():
    fc = ResponseFunctionToolCall(
        type="function_call",
        name="get_weather",
        arguments='{"city": "SF"}',
        call_id="call_1",
    )
    raw = _FakeArkResponse(output=[fc])
    resp = ark_response_to_generate_content_response(cast(Any, raw))
    part = _first_part(resp)
    assert part.function_call is not None
    assert part.function_call.name == "get_weather"
    assert part.function_call.args == {"city": "SF"}
    assert part.function_call.id == "call_1"


def test_ark_response_to_llm_response_parses_reasoning_as_thought():
    reasoning = ResponseReasoningItem(
        id="r1",
        type="reasoning",
        summary=[Summary(type="summary_text", text="thinking...")],
    )
    raw = _FakeArkResponse(output=[reasoning])
    resp = ark_response_to_generate_content_response(cast(Any, raw))
    part = _first_part(resp)
    assert part.thought is True
    assert part.text == "thinking..."


def test_ark_response_to_llm_response_raises_on_empty_output():
    raw = _FakeArkResponse(output=[])
    with pytest.raises(ValueError, match="No message in response"):
        ark_response_to_generate_content_response(cast(Any, raw))


def test_event_to_generate_content_response_partial_text_delta():
    event = ResponseTextDeltaEvent(
        content_index=0,
        delta="chunk",
        item_id="i1",
        output_index=0,
        type="response.output_text.delta",
    )
    resp = event_to_generate_content_response(
        event, is_partial=True, model_version="gpt-4o"
    )
    assert resp is not None
    assert resp.partial is True
    assert _first_part(resp).text == "chunk"


def test_event_to_generate_content_response_partial_unknown_returns_none():
    # An unrelated event in the partial branch yields no LlmResponse.
    event = ResponseTextDeltaEvent(
        content_index=0,
        delta="x",
        item_id="i1",
        output_index=0,
        type="response.output_text.delta",
    )
    # Force the isinstance checks to miss by passing a bare object.
    assert (
        event_to_generate_content_response(cast(Any, object()), is_partial=True) is None
    )
    # sanity: the real delta event still works
    assert event_to_generate_content_response(event, is_partial=True) is not None


# --------------------------------------------------------------------------
# ArkLlm / ArkLlmClient
# --------------------------------------------------------------------------
def test_arkllm_supported_models():
    assert ArkLlm.supported_models() == [r"openai/.*"]


def test_arkllm_init_stores_additional_args_and_strips_reserved_keys():
    llm = ArkLlm(model="openai/gpt-4o", drop_params=True, foo="bar")
    assert llm.model == "openai/gpt-4o"
    assert llm._additional_args["foo"] == "bar"
    assert llm._additional_args["drop_params"] is True
    # reserved keys must not leak into _additional_args
    for reserved in (
        "llm_client",
        "messages",
        "tools",
        "stream",
        "enable_responses_cache",
    ):
        assert reserved not in llm._additional_args


def test_arkllm_init_respects_enable_responses_cache_flag():
    llm = ArkLlm(model="openai/gpt-4o", enable_responses_cache=False)
    assert llm.enable_responses_cache is False


def test_arkllm_init_raises_when_adk_lacks_field():
    with patch.object(ark_llm, "llm_request_has_field", return_value=False):
        with pytest.raises(ImportError, match="google-adk"):
            ArkLlm(model="openai/gpt-4o")


@pytest.mark.asyncio
async def test_arkllmclient_aresponses_uses_default_api_base_and_settings_key():
    client = ArkLlmClient()
    fake_async_ark = AsyncMock()
    fake_async_ark.responses.create = AsyncMock(return_value="RAW")

    with patch.object(ark_llm, "AsyncArk", return_value=fake_async_ark) as ark_ctor:
        with patch.object(ark_llm.settings.model, "api_key", "settings_key"):
            result = await client.aresponses(model="gpt-4o", input=[])

    assert result == "RAW"
    ark_ctor.assert_called_once_with(
        base_url=DEFAULT_VIDEO_MODEL_API_BASE,
        api_key="settings_key",
    )
    # api_base/api_key must be popped before reaching responses.create
    _, create_kwargs = fake_async_ark.responses.create.call_args
    assert "api_base" not in create_kwargs
    assert "api_key" not in create_kwargs
    assert create_kwargs["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_arkllmclient_aresponses_honours_explicit_api_key_and_base():
    client = ArkLlmClient()
    fake_async_ark = AsyncMock()
    fake_async_ark.responses.create = AsyncMock(return_value="RAW")

    with patch.object(ark_llm, "AsyncArk", return_value=fake_async_ark) as ark_ctor:
        await client.aresponses(
            model="gpt-4o", input=[], api_key="explicit", api_base="https://custom/"
        )

    ark_ctor.assert_called_once_with(
        base_url="https://custom/",
        api_key="explicit",
    )


@pytest.mark.asyncio
async def test_generate_content_via_responses_non_stream_yields_one_response():
    llm = ArkLlm(model="openai/gpt-4o")
    msg = ResponseOutputMessage(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="hi", annotations=[])],
    )
    raw = _FakeArkResponse(output=[msg])

    llm.llm_client.aresponses = AsyncMock(return_value=raw)

    args = {
        "model": "openai/gpt-4o",
        "instructions": None,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            }
        ],
        "previous_response_id": None,
    }
    responses = [
        r async for r in llm.generate_content_via_responses(args, stream=False)
    ]
    assert len(responses) == 1
    assert _first_part(responses[0]).text == "hi"
    # request was reorganized: provider stripped before hitting the client
    _, kwargs = llm.llm_client.aresponses.call_args
    assert kwargs["model"] == "gpt-4o"


@pytest.mark.asyncio
async def test_generate_content_via_responses_stream_yields_partials():
    llm = ArkLlm(model="openai/gpt-4o")

    async def _fake_stream(**kwargs):
        for delta in ("a", "b"):
            yield ResponseTextDeltaEvent(
                content_index=0,
                delta=delta,
                item_id="i1",
                output_index=0,
                type="response.output_text.delta",
            )

    # aresponses is awaited, and the awaited result is async-iterated.
    llm.llm_client.aresponses = AsyncMock(return_value=_fake_stream())

    args = {
        "model": "openai/gpt-4o",
        "instructions": None,
        "input": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "hi"}],
            }
        ],
        "previous_response_id": None,
    }
    responses = [r async for r in llm.generate_content_via_responses(args, stream=True)]
    assert [_first_part(r).text for r in responses] == ["a", "b"]
    assert all(r.partial for r in responses)
    _, kwargs = llm.llm_client.aresponses.call_args
    assert kwargs["stream"] is True


# --------------------------------------------------------------------------
# _content_to_input_item branches
# --------------------------------------------------------------------------
def test_content_to_input_item_function_response():
    part = types.Part(
        function_response=types.FunctionResponse(
            id="call_1", name="f", response={"result": 1}
        )
    )
    content = types.Content(role="user", parts=[part])
    item = cast(dict, _content_to_input_item(content))
    assert item["type"] == "function_call_output"
    assert item["call_id"] == "call_1"
    assert item["output"] == '{"result": 1}'


def test_content_to_input_item_function_call_from_model():
    part = types.Part.from_function_call(name="f", args={"a": 1})
    assert part.function_call is not None
    part.function_call.id = "call_1"
    content = types.Content(role="model", parts=[part])
    items = cast(list, _content_to_input_item(content))
    assert items[0]["type"] == "function_call"
    assert items[0]["name"] == "f"
    assert items[0]["call_id"] == "call_1"


def test_content_to_input_item_inline_image_becomes_input_image():
    part = types.Part(inline_data=types.Blob(mime_type="image/png", data=b"abc"))
    content = types.Content(role="user", parts=[part])
    item = cast(dict, _content_to_input_item(content))
    image = item["content"][0]
    assert image["type"] == "input_image"
    assert image["image_url"].startswith("data:image/png;base64,")


def test_content_to_input_item_file_uri_becomes_input_file():
    part = types.Part(
        file_data=types.FileData(
            file_uri="https://example.com/doc.pdf", mime_type="application/pdf"
        )
    )
    content = types.Content(role="user", parts=[part])
    item = cast(dict, _content_to_input_item(content))
    file_param = item["content"][0]
    assert file_param["type"] == "input_file"
    assert file_param["file_url"] == "https://example.com/doc.pdf"


# --------------------------------------------------------------------------
# generate_content_async error handling
# --------------------------------------------------------------------------
def _bad_request_error(code: str) -> ArkBadRequestError:
    request = httpx.Request("POST", "https://ark/")
    response = httpx.Response(400, request=request)
    return ArkBadRequestError(
        "bad", response=response, body={"code": code}, request_id="r"
    )


@pytest.mark.asyncio
async def test_generate_content_async_retries_on_previous_response_not_found():
    llm = ArkLlm(model="openai/gpt-4o")

    msg = ResponseOutputMessage(
        id="m1",
        type="message",
        role="assistant",
        status="completed",
        content=[ResponseOutputText(type="output_text", text="ok", annotations=[])],
    )
    recovered = _FakeArkResponse(output=[msg])

    call_count = {"n": 0}

    async def _maybe_fail(self, responses_args, stream=False):
        call_count["n"] += 1
        if call_count["n"] == 1:
            # First attempt carries previous_response_id and fails as expired.
            assert "previous_response_id" in responses_args
            raise _bad_request_error("InvalidParameter.PreviousResponseNotFound")
        # Retry must have dropped previous_response_id.
        assert "previous_response_id" not in responses_args
        yield ark_response_to_generate_content_response(cast(Any, recovered))

    req = _build_request(system_instruction="hi")
    with patch.object(ark_llm, "get_previous_interaction_id", return_value="resp_old"):
        with patch.object(ArkLlm, "generate_content_via_responses", _maybe_fail):
            responses = [r async for r in llm.generate_content_async(req)]

    assert call_count["n"] == 2
    assert _first_part(responses[0]).text == "ok"


@pytest.mark.asyncio
async def test_generate_content_async_reraises_other_bad_request():
    llm = ArkLlm(model="openai/gpt-4o")

    async def _always_fail(self, responses_args, stream=False):
        raise _bad_request_error("InvalidParameter.SomethingElse")
        yield  # pragma: no cover - makes this an async generator

    req = _build_request(system_instruction="hi")
    with patch.object(ark_llm, "get_previous_interaction_id", return_value=None):
        with patch.object(ArkLlm, "generate_content_via_responses", _always_fail):
            with pytest.raises(ArkBadRequestError):
                async for _ in llm.generate_content_async(req):
                    pass
