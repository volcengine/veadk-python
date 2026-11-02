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

from types import SimpleNamespace

from google.genai import types

from veadk.content_safety.state import (
    DEFUSE_PREFIX,
    DEFUSE_SUFFIX,
    StateBuilder,
    _function_response_text,
    _redact,
    _stringify,
)


def user_content(text):
    return types.Content(role="user", parts=[types.Part(text=text)])


def tool_response_content(payload):
    return types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    name="load_skill", response=payload
                )
            )
        ],
    )


def test_build_before_model_includes_user_and_tool_response():
    request = SimpleNamespace(
        contents=[user_content("hello"), tool_response_content({"ok": True})]
    )
    state = StateBuilder().build_before_model(request)
    assert "[user]\nhello" in state
    assert "[tool_response]" in state
    assert '"ok": true' in state
    assert state.startswith(DEFUSE_PREFIX)
    assert state.endswith(DEFUSE_SUFFIX)


def test_build_before_model_skips_empty_content():
    request = SimpleNamespace(
        contents=[
            types.Content(role="user", parts=[types.Part(text="")]),
            types.Content(role="model", parts=[types.Part(text="ignored")]),
        ]
    )
    assert StateBuilder().build_before_model(request) == ""


def test_build_before_model_handles_missing_contents():
    assert StateBuilder().build_before_model(SimpleNamespace()) == ""
    assert StateBuilder().build_before_model(SimpleNamespace(contents=None)) == ""


def test_build_after_model_extracts_text():
    response = SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(text="output")])
    )
    assert "output" in StateBuilder().build_after_model(response)


def test_build_after_model_handles_missing_content():
    assert StateBuilder().build_after_model(SimpleNamespace()) == ""


def test_build_before_tool_redacts_sensitive_arguments():
    tool = SimpleNamespace(name="http_call")
    args = {
        "url": "https://example",
        "api_key": "super-secret",
        "nested": {"token": "abc", "password": "pw", "safe": [1, 2]},
    }
    state = StateBuilder().build_before_tool(tool, args)
    assert "[tool]\nhttp_call" in state
    assert "super-secret" not in state
    assert "abc" not in state
    assert '"[REDACTED]"' in state
    assert '"safe": [' in state


def test_build_before_tool_uses_type_name_without_name():
    state = StateBuilder().build_before_tool(object(), {"x": 1})
    assert "[tool]\nobject" in state


def test_build_after_tool_handles_string_dict_list_and_none():
    tool = SimpleNamespace(name="t")
    builder = StateBuilder()
    assert "result" in builder.build_after_tool(tool, {}, "plain")
    assert '"a": 1' in builder.build_after_tool(tool, {}, {"a": 1})
    assert "item" in builder.build_after_tool(tool, {}, ["item"])
    assert builder.build_after_tool(tool, {}, None).endswith("</untrusted>")


def test_build_after_tool_redacts_result():
    tool = SimpleNamespace(name="t")
    state = StateBuilder().build_after_tool(tool, {}, {"secret": "value"})
    assert "value" not in state
    assert "[REDACTED]" in state


def test_truncation_and_defuse_can_be_disabled():
    builder = StateBuilder(max_chars=3, defuse=False)
    assert builder.prepare("abcdef") == "abc"
    assert builder.prepare("  abc  ") == "abc"
    assert builder.prepare("") == ""


def test_redact_depth_limit():
    value = "leaf"
    for _ in range(10):
        value = {"nested": value}
    redacted = _redact(value)
    assert "[TRUNCATED]" in str(redacted)


def test_redact_tuple_and_scalar():
    assert _redact(("a", {"token": "x"})) == ["a", {"token": "[REDACTED]"}]
    assert _redact(3) == 3


def test_function_response_text_handles_none():
    assert _function_response_text(None) == ""


def test_finalize_accepts_non_string():
    assert "123" in StateBuilder().prepare(123)


def test_stringify_variants():
    assert _stringify(None) == ""
    assert _stringify("x") == "x"
    assert _stringify(3) == "3"
    assert _stringify({"b": 2, "a": 1}) == '{"a": 1, "b": 2}'
    circular = []
    circular.append(circular)
    assert _stringify(circular) == "[[...]]"
