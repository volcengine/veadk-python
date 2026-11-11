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

from google.adk.models.llm_request import LlmRequest
from google.genai import types

from veadk.configs.routing_configs import SimpleModelConfig
from veadk.routing.capability import CapabilityGuard
from veadk.routing.registry import ModelRegistry, SimpleModelRuntime
from veadk.routing.state import request_has_media, request_text_chars

PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x00IEND\xaeB`\x82"
)


def request_with(parts, *, config=None):
    kwargs = {"config": config} if config is not None else {}
    return LlmRequest(
        model="provider/model",
        contents=[types.Content(role="user", parts=parts)],
        **kwargs,
    )


def text_request(text="hello"):
    return request_with([types.Part(text=text)])


def test_text_only_is_allowed_by_default():
    check = CapabilityGuard().check(text_request(), SimpleModelConfig(name="cheap"))
    assert check.allowed is True
    assert check.reason == ""


def test_registry_check_matches_the_guard():
    runtime = SimpleModelRuntime(config=SimpleModelConfig(name="cheap"), llm=object())
    registry = ModelRegistry(runtimes=[runtime])
    check = registry.check(text_request(), runtime)
    assert check.allowed is True


def test_media_is_rejected_by_default():
    request = request_with(
        [types.Part(inline_data=types.Blob(mime_type="image/png", data=PNG_BYTES))]
    )
    assert request_has_media(request) is True
    check = CapabilityGuard().check(request, SimpleModelConfig(name="cheap"))
    assert check.allowed is False
    assert check.reason == "media_not_supported"


def test_media_is_allowed_when_declared():
    request = request_with(
        [types.Part(inline_data=types.Blob(mime_type="image/png", data=PNG_BYTES))]
    )
    model = SimpleModelConfig(name="cheap", supports_media=True)
    assert CapabilityGuard().check(request, model).allowed is True


def test_tools_are_rejected_by_default():
    request = text_request()
    request.tools_dict = {"lookup": object()}
    check = CapabilityGuard().check(request, SimpleModelConfig(name="cheap"))
    assert check.allowed is False
    assert check.reason == "tools_not_supported"


def test_tools_are_allowed_when_declared():
    request = text_request()
    request.tools_dict = {"lookup": object()}
    model = SimpleModelConfig(name="cheap", supports_tools=True)
    assert CapabilityGuard().check(request, model).allowed is True


def test_structured_output_is_rejected_by_default():
    config = types.GenerateContentConfig(response_schema={"type": "object"})
    request = request_with([types.Part(text="hello")], config=config)
    check = CapabilityGuard().check(request, SimpleModelConfig(name="cheap"))
    assert check.allowed is False
    assert check.reason == "structured_output_not_supported"


def test_structured_output_is_allowed_when_declared():
    config = types.GenerateContentConfig(response_schema={"type": "object"})
    request = request_with([types.Part(text="hello")], config=config)
    model = SimpleModelConfig(name="cheap", supports_structured_output=True)
    assert CapabilityGuard().check(request, model).allowed is True


def test_context_limit_uses_request_characters():
    request = text_request("x" * 120)
    assert request_text_chars(request) == 120
    model = SimpleModelConfig(name="cheap", max_context_chars=100)
    check = CapabilityGuard().check(request, model)
    assert check.allowed is False
    assert check.reason == "context_too_large"


def test_media_counts_towards_context_budget():
    request = request_with(
        [types.Part(inline_data=types.Blob(mime_type="image/png", data=PNG_BYTES))]
    )
    assert request_text_chars(request) == 4_000
