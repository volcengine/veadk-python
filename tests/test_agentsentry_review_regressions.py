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

from types import SimpleNamespace as NS
from unittest.mock import Mock

from google.genai import types
from google.adk.models import LlmResponse


def shield(monkeypatch):
    for key, value in {
        "AGENTSENTRY_URL": "http://sentry/OpenTOP/V3/Lumen/Moderate",
        "AGENTSENTRY_ACCOUNT_ID": "account",
        "AGENTSENTRY_INSTANCE_ID": "instance",
        "AGENTSENTRY_AK": "ak",
        "AGENTSENTRY_SK": "sk",
    }.items():
        monkeypatch.setenv(key, value)
    from veadk.tools.builtin_tools.llm_shield import LLMShieldPlugin

    plugin = LLMShieldPlugin()
    plugin._sentry_v3.moderate = Mock(return_value=None)
    return plugin


def test_hidden_thought_is_never_a_plan(monkeypatch):
    plugin = shield(monkeypatch)
    ctx = NS(agent_states={})
    plugin.after_model_callback(
        ctx,
        LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(text="SECRET", thought=True),
                    types.Part(text="visible"),
                    types.Part(
                        function_call=types.FunctionCall(name="record", args={})
                    ),
                ],
            )
        ),
    )
    plugin.before_tool_callback(NS(name="record"), {}, ctx)
    assert plugin._sentry_v3.moderate.call_args.args[0] == "visible"


def test_dispatch_once_per_invocation_and_no_old_text_for_image(monkeypatch):
    plugin = shield(monkeypatch)
    user = types.Content(role="user", parts=[types.Part(text="hello")])
    ctx = NS(agent_states={}, user_content=user)
    req = NS(contents=[user])
    plugin.before_model_callback(ctx, req)
    plugin.before_model_callback(ctx, req)
    assert plugin._sentry_v3.moderate.call_count == 1
    image = types.Content(
        role="user",
        parts=[
            types.Part(inline_data=types.Blob(data=b"image", mime_type="image/png"))
        ],
    )
    ctx = NS(agent_states={}, user_content=image)
    response = plugin.before_model_callback(ctx, NS(contents=[user, image]))
    assert response is not None
    assert "unsupported" in response.content.parts[0].text.lower()
    assert plugin._sentry_v3.moderate.call_count == 1


def test_private_disable_requires_no_credentials(monkeypatch):
    plugin = shield(monkeypatch)
    monkeypatch.setenv("AGENTSENTRY_ENABLED", "false")
    monkeypatch.delenv("AGENTSENTRY_SK")
    disabled = type(plugin)()
    assert disabled.before_model_callback(NS(), NS()) is None
