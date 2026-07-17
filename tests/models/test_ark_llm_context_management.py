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
