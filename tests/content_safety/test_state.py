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


def test_build_after_model_ignores_hidden_thought_parts():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(text="hidden reasoning", thought=True),
                types.Part(text="visible answer"),
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    assert "visible answer" in state
    assert "hidden reasoning" not in state


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


def inline_media_part(mime_type, data=b"abc", display_name=None):
    return types.Part(
        inline_data=types.Blob(
            mime_type=mime_type, data=data, display_name=display_name
        )
    )


def test_build_after_model_maps_text_and_image_to_state_parts():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[types.Part(text="look"), inline_media_part("image/png")],
        )
    )
    state = StateBuilder().build_after_model(response)
    assert isinstance(state, list)
    assert state[0] == {"type": "text", "text": DEFUSE_PREFIX}
    assert state[-1] == {"type": "text", "text": DEFUSE_SUFFIX}
    assert any(part.get("type") == "text" and "look" in part["text"] for part in state)
    image = next(part for part in state if part.get("type") == "image")
    assert image["image_url"].startswith("data:image/png;base64,")


def test_inline_media_prefers_display_name_url():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                inline_media_part(
                    "image/jpeg", display_name="https://tos.example/image.jpg"
                )
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    image = next(part for part in state if part.get("type") == "image")
    assert image["image_url"] == "https://tos.example/image.jpg"


def test_build_after_model_maps_audio_and_video():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                inline_media_part("audio/wav", data=b"aud"),
                inline_media_part("video/mp4", data=b"vid"),
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    audio = next(part for part in state if part.get("type") == "audio")
    video = next(part for part in state if part.get("type") == "video")
    assert audio["audio_url"].startswith("data:audio/wav;base64,")
    assert video["video_url"].startswith("data:video/mp4;base64,")
    assert video["fps"] == 1


def test_file_data_mapping_and_unsupported_scheme(caplog):
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri="https://files.example/a.png",
                        mime_type="image/png",
                    )
                ),
                types.Part(
                    file_data=types.FileData(
                        file_uri="gs://bucket/a.png", mime_type="image/png"
                    )
                ),
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    images = [part for part in state if part.get("type") == "image"]
    assert len(images) == 1
    assert images[0]["image_url"] == "https://files.example/a.png"
    assert "unsupported_scheme" in caplog.text


def test_inline_media_without_data_or_url_is_skipped(caplog):
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[types.Part(inline_data=types.Blob(mime_type="image/png"))],
        )
    )
    assert StateBuilder().build_after_model(response) == ""
    assert "no_url_or_data" in caplog.text


def test_thought_media_is_skipped():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    inline_data=types.Blob(mime_type="image/png", data=b"abc"),
                    thought=True,
                )
            ],
        )
    )
    assert StateBuilder().build_after_model(response) == ""


def test_file_data_edge_cases_are_skipped(caplog):
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri="https://files.example/a.pdf",
                        mime_type="application/pdf",
                    )
                ),
                types.Part(
                    file_data=types.FileData(file_uri="", mime_type="image/png")
                ),
            ],
        )
    )
    assert StateBuilder().build_after_model(response) == ""
    assert "reason=unsupported" in caplog.text
    assert "reason=no_file_uri" in caplog.text


def test_file_data_video_gets_fps():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(
                    file_data=types.FileData(
                        file_uri="https://files.example/clip.mp4",
                        mime_type="video/mp4",
                    )
                )
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    video = next(part for part in state if part.get("type") == "video")
    assert video["video_url"] == "https://files.example/clip.mp4"
    assert video["fps"] == 1


def test_media_state_text_budget_is_bounded():
    parts = [
        types.Part(text="abcdefghij"),
        inline_media_part("image/png"),
    ]
    truncated = StateBuilder(max_chars=5).build_parts(parts, label="model_output")
    assert any(
        part.get("type") == "text" and part["text"] == "[mode" for part in truncated
    )
    assert any(part.get("type") == "image" for part in truncated)

    exhausted = StateBuilder(max_chars=0).build_parts(parts, label="model_output")
    assert [part["type"] for part in exhausted] == ["text", "image", "text"]
    assert exhausted[0]["text"] == DEFUSE_PREFIX
    assert exhausted[-1]["text"] == DEFUSE_SUFFIX


def test_unsupported_inline_mime_is_skipped(caplog):
    response = SimpleNamespace(
        content=types.Content(
            role="model", parts=[inline_media_part("application/pdf")]
        )
    )
    assert StateBuilder().build_after_model(response) == ""
    assert "unsupported" in caplog.text


def test_mixed_text_media_preserves_order():
    response = SimpleNamespace(
        content=types.Content(
            role="model",
            parts=[
                types.Part(text="before"),
                inline_media_part("image/png"),
                types.Part(text="after"),
            ],
        )
    )
    state = StateBuilder().build_after_model(response)
    assert isinstance(state, list)
    text = "\n".join(part["text"] for part in state if part.get("type") == "text")
    assert text.index("before") < text.index("after")
    image_index = next(
        index for index, part in enumerate(state) if part.get("type") == "image"
    )
    assert any(
        part.get("type") == "text" and "before" in part["text"]
        for part in state[:image_index]
    )
    assert any(
        part.get("type") == "text" and "after" in part["text"]
        for part in state[image_index + 1 :]
    )


def test_text_only_after_model_stays_a_string():
    response = SimpleNamespace(
        content=types.Content(role="model", parts=[types.Part(text="hello")])
    )
    assert isinstance(StateBuilder().build_after_model(response), str)


def test_redact_text_covers_common_secret_shapes():
    from veadk.content_safety.state import _redact_text

    raw = (
        "Authorization: Bearer abcdefgh12345678 "
        "api_key=supersecretvalue "
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature12345 "
        "sk-abcdefghijklmnop"
    )
    redacted = _redact_text(raw)
    assert "abcdefgh12345678" not in redacted
    assert "supersecretvalue" not in redacted
    assert "eyJhbGciOiJIUzI1NiJ9" not in redacted
    assert "sk-abcdefghijklmnop" not in redacted
    assert redacted.count("[REDACTED]") >= 4


def test_redact_string_scalar_and_function_response():
    from veadk.content_safety.state import _redact_text

    assert "abcdefgh12345678" not in _redact("token=abcdefgh12345678")
    text = _function_response_text(
        tool_response_content({"output": "token=abcdefgh12345678"})
    )
    assert "abcdefgh12345678" not in text
    assert "[REDACTED]" in text
    assert _redact_text("normal text without credentials") == (
        "normal text without credentials"
    )
