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

import pytest

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.content_safety.state import DEFUSE_PREFIX, DEFUSE_SUFFIX
from veadk.routing.state import (
    QueryStateBuilder,
    IncompleteRoutingState,
    request_has_media,
)

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
)


def make_request(*messages):
    contents = [
        types.Content(role=role, parts=[types.Part(text=text)])
        for role, text in messages
    ]
    return LlmRequest(model="provider/model", contents=contents)


def text_of(state):
    return "\n".join(part.get("text", "") for part in state)


def test_recent_turns_are_labelled_and_included():
    request = make_request(("user", "first"), ("model", "answer"), ("user", "second"))
    state = QueryStateBuilder(defuse=False).build_for_routing(request)
    assert text_of(state) == "[user]\nfirst\n[model]\nanswer\n[user]\nsecond"


def test_turn_window_reports_incomplete_history():
    request = make_request(
        ("user", "one"),
        ("model", "two"),
        ("user", "three"),
        ("model", "four"),
    )
    with pytest.raises(IncompleteRoutingState, match="history"):
        QueryStateBuilder(defuse=False, max_turns=2).build_for_routing(request)


def test_empty_request_returns_empty_state():
    request = LlmRequest(model="provider/model", contents=[])
    assert QueryStateBuilder().build_for_routing(request) == []


def test_content_without_parts_is_skipped():
    request = LlmRequest(
        model="provider/model",
        contents=[
            types.Content(role="user", parts=[]),
            types.Content(role="user", parts=[types.Part(text="kept")]),
        ],
    )
    state = QueryStateBuilder(defuse=False).build_for_routing(request)
    assert text_of(state) == "[user]\nkept"


def test_thought_parts_are_skipped():
    request = LlmRequest(
        model="provider/model",
        contents=[
            types.Content(
                role="model",
                parts=[types.Part(text="hidden", thought=True), types.Part(text="ok")],
            )
        ],
    )
    state = QueryStateBuilder(defuse=False).build_for_routing(request)
    assert "hidden" not in text_of(state)
    assert "ok" in text_of(state)


def test_defuse_wrapper_is_added_by_default():
    state = QueryStateBuilder().build_for_routing(make_request(("user", "hello")))
    assert state[0]["text"] == DEFUSE_PREFIX
    assert state[-1]["text"] == DEFUSE_SUFFIX


def test_text_budget_reports_incomplete_state():
    request = make_request(("user", "x" * 500))
    with pytest.raises(IncompleteRoutingState, match="character budget"):
        QueryStateBuilder(max_chars=100, defuse=False).build_for_routing(request)


def test_media_part_is_converted_to_image_url():
    request = LlmRequest(
        model="provider/model",
        contents=[
            types.Content(
                role="user",
                parts=[
                    types.Part(
                        inline_data=types.Blob(mime_type="image/png", data=PNG_BYTES)
                    )
                ],
            )
        ],
    )
    state = QueryStateBuilder(defuse=False).build_for_routing(request)
    assert request_has_media(request) is True
    media = [part for part in state if part.get("type") == "image"]
    assert len(media) == 1
    assert media[0]["image_url"].startswith("data:image/png;base64,")


def test_text_only_request_has_no_media():
    assert request_has_media(make_request(("user", "hello"))) is False
