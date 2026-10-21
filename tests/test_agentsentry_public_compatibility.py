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

import builtins

import json

from types import SimpleNamespace

from unittest.mock import Mock

import pytest

from google.genai import types

from google.adk.models import LlmResponse


@pytest.fixture
def public_env(monkeypatch):
    for key in (
        "AGENTSENTRY_URL",
        "ENABLE_LLM_SHIELD",
        "TOOL_LLM_SHIELD_REGION",
        "TOOL_LLM_SHIELD_ACCOUNT_ID",
        "AGENTSENTRY_AK",
        "AGENTSENTRY_SK",
        "AGENTSENTRY_ACCOUNT_ID",
        "AGENTSENTRY_INSTANCE_ID",
        "AGENTSENTRY_REGION",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TOOL_LLM_SHIELD_APP_ID", "public-app")
    monkeypatch.setenv("TOOL_LLM_SHIELD_API_KEY", "public-api-key")
    monkeypatch.setenv("TOOL_LLM_SHIELD_URL", "https://public-custom.example")
    # Public construction/calls must not even import the private adapter.
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name.endswith("agentsentry_v3"):
            raise AssertionError("Private adapter imported by public mode")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_veadk_public_request_and_callbacks_unchanged(public_env, monkeypatch):
    import veadk.tools.builtin_tools.llm_shield as module

    p = module.LLMShieldPlugin()
    assert p._sentry_v3 is None
    post = Mock(
        return_value=SimpleNamespace(
            status_code=200, json=lambda: {"Result": {"Decision": {"DecisionType": 1}}}
        )
    )
    monkeypatch.setattr(module.requests, "post", post)
    assert p._request_llm_shield("text", "user") is None
    args = post.call_args
    assert args.args[0] == "https://public-custom.example/v2/moderate"
    assert args.kwargs["headers"]["x-api-key"] == "public-api-key"
    assert args.kwargs["params"] == {"Action": "Moderate", "Version": "2025-08-31"}
    assert json.loads(args.kwargs["data"]) == {
        "Message": {"Role": "user", "Content": "text", "ContentType": 1},
        "Scene": "public-app",
    }
    p._request_llm_shield = Mock(return_value=None)
    ctx = SimpleNamespace()
    p.before_model_callback(
        ctx,
        SimpleNamespace(
            contents=[
                types.Content(
                    role="user",
                    parts=[types.Part(text="first"), types.Part(text="second")],
                )
            ]
        ),
    )
    assert p._request_llm_shield.call_args.kwargs == {
        "message": "first",
        "role": "user",
        "hook_name": "before_model",
    }
    p.after_model_callback(
        ctx,
        LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text="reply")])
        ),
    )
    assert p._request_llm_shield.call_args.kwargs["hook_name"] == "after_model"
    p.before_tool_callback(SimpleNamespace(name="tool"), {"x": "arg"}, ctx)
    assert p._request_llm_shield.call_args.kwargs["role"] == "user"
    p.after_tool_callback(None, {}, ctx, "result")
    assert p._request_llm_shield.call_args.kwargs["hook_name"] == "after_tool_call"
