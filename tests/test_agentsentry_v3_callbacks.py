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
from unittest.mock import Mock
import pytest
from google.genai import types
from google.adk.models import LlmResponse


@pytest.fixture
def config(monkeypatch):
    for k, v in {
        "AGENTSENTRY_URL": "http://sentry/OpenTOP/V3/Lumen/Moderate",
        "AGENTSENTRY_ACCOUNT_ID": "account",
        "AGENTSENTRY_INSTANCE_ID": "instance",
        "AGENTSENTRY_AK": "ak",
        "AGENTSENTRY_SK": "sk",
    }.items():
        monkeypatch.setenv(k, v)


@pytest.fixture
def veadk(config):
    from veadk.tools.builtin_tools.llm_shield import LLMShieldPlugin

    shield = LLMShieldPlugin()
    shield._sentry_v3.moderate = Mock(return_value=None)
    return shield


def test_all_input_parts_and_hook(veadk):
    context = SimpleNamespace(agent_states={})
    request = SimpleNamespace(
        contents=[
            types.Content(
                role="user", parts=[types.Part(text="first"), types.Part(text="second")]
            )
        ]
    )
    assert veadk.before_model_callback(context, request) is None
    args = veadk._sentry_v3.moderate.call_args
    assert args.args[0] == "first\nsecond"
    assert args.kwargs["hook_name"] == "before_dispatch"


def test_plan_and_tool_are_linked_and_blocked(veadk):
    ctx = SimpleNamespace(agent_states={}, function_call_id="call")
    content = types.Content(
        role="model",
        parts=[
            types.Part(text="first"),
            types.Part(text="risk in second"),
            types.Part(
                function_call=types.FunctionCall(name="record", args={"action": "test"})
            ),
        ],
    )
    veadk.after_model_callback(ctx, LlmResponse(content=content))
    veadk._sentry_v3.moderate.return_value = "blocked"
    assert veadk.before_tool_callback(
        SimpleNamespace(name="record"), {"action": "test"}, ctx
    ) == {"result": "blocked"}
    call = veadk._sentry_v3.moderate.call_args
    assert call.args[0] == "first\nrisk in second"
    assert call.kwargs["role"] == "assistant"
    assert call.kwargs["tool_calls"][0]["Function"]["Name"] == "record"
    # A different invocation may not use the first invocation's plan.
    other = SimpleNamespace(agent_states={})
    assert (
        veadk.before_tool_callback(
            SimpleNamespace(name="record"), {"action": "test"}, other
        )["reason"]
        == "missing_visible_execution_plan"
    )


def test_unsupported_outputs_not_relabelled(veadk):
    ctx = SimpleNamespace(agent_states={})
    assert (
        veadk.after_model_callback(
            ctx,
            LlmResponse(
                content=types.Content(role="model", parts=[types.Part(text="final")])
            ),
        )
        is None
    )
    assert veadk.after_tool_callback(None, {}, ctx, "result") is None
    veadk._sentry_v3.moderate.assert_not_called()
