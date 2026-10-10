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

from veadk.models.ark_llm import request_reorganization_by_ark


def test_request_reorganization_preserves_context_management():
    context_management = {
        "edits": [
            {
                "type": "clear_thinking",
                "keep": {"type": "thinking_turns", "value": 1},
            },
            {
                "type": "clear_tool_uses",
                "trigger": {"type": "tool_uses", "value": 30},
                "keep": {"type": "tool_uses", "value": 20},
            },
        ]
    }

    request = request_reorganization_by_ark(
        {
            "model": "openai/test-model",
            "input": [],
            "context_management": context_management,
        }
    )

    assert request["context_management"] == context_management


def test_request_reorganization_preserves_tools_with_previous_response_id():
    tools = [
        {
            "type": "function",
            "name": "bash",
            "description": "Run a command",
            "parameters": {"type": "object"},
        }
    ]

    request = request_reorganization_by_ark(
        {
            "model": "openai/test-model",
            "input": [{"role": "user", "content": "next"}],
            "previous_response_id": "response-1",
            "tools": tools,
        }
    )

    assert request["previous_response_id"] == "response-1"
    assert request["tools"] == tools


def test_request_reorganization_does_not_add_tools_when_none_are_authorized():
    request = request_reorganization_by_ark(
        {
            "model": "openai/test-model",
            "input": [{"role": "user", "content": "next"}],
            "previous_response_id": "response-1",
        }
    )

    assert "tools" not in request


def test_disabling_responses_cache_removes_previous_id_but_preserves_tools():
    tools = [{"type": "function", "name": "bash", "parameters": {}}]

    request = request_reorganization_by_ark(
        {
            "model": "openai/test-model",
            "input": [],
            "previous_response_id": "response-1",
            "tools": tools,
            "store": True,
        },
        enable_responses_cache=False,
    )

    assert "previous_response_id" not in request
    assert request["tools"] == tools


# Regression: cloud conversation storage must not be shortened to one hour.
def test_response_retention_uses_server_default_or_explicit_value():
    from veadk.models.ark_llm import request_reorganization_by_ark

    default = request_reorganization_by_ark(
        {"model": "openai/test", "input": [], "store": True}
    )
    assert "expire_at" not in default["extra_body"]
    explicit = request_reorganization_by_ark(
        {"model": "openai/test", "input": [], "extra_body": {"expire_at": 123456789}}
    )
    assert explicit["extra_body"]["expire_at"] == 123456789
