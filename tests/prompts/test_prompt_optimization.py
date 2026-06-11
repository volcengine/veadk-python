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

"""Unit tests for ``veadk.prompts.prompt_optimization``.

These verify the Jinja2 rendering helpers. The agent and its tools are mocked;
no model calls are made (the rendering functions themselves perform none).
"""

from unittest.mock import MagicMock, patch

from veadk.prompts import prompt_optimization as po


def _make_agent(*, tools=None):
    agent = MagicMock()
    agent.name = "MyAgent"
    agent.model_name = "doubao"
    agent.description = "an agent"
    agent.instruction = "ORIGINAL_INSTRUCTION"
    agent.tools = tools if tools is not None else []
    return agent


def test_render_prompt_feedback_includes_instruction_and_feedback():
    agent = _make_agent()
    rendered = po.render_prompt_feedback_with_jinja2(agent, feedback="too verbose")

    assert "ORIGINAL_INSTRUCTION" in rendered
    assert "too verbose" in rendered


def test_render_prompt_with_no_tools_embeds_agent_info():
    agent = _make_agent(tools=[])
    rendered = po.render_prompt_with_jinja2(agent)

    assert "ORIGINAL_INSTRUCTION" in rendered
    assert "MyAgent" in rendered
    assert "doubao" in rendered
    assert "an agent" in rendered
    # With no tools the tools loop produces no <tool> blocks.
    assert "<tool>" not in rendered


def test_render_prompt_with_function_tool_renders_tool_block():
    """A plain callable is treated as a function tool and wrapped in a
    ``FunctionTool`` whose declaration is rendered into the prompt."""

    def my_function(x: int) -> int:
        """double it"""
        return x * 2

    agent = _make_agent(tools=[my_function])

    declaration = MagicMock()
    declaration.model_dump.return_value = {"parameters": {"type": "object"}}

    fake_tool = MagicMock()
    fake_tool.name = "my_function"
    fake_tool.description = "double it"
    fake_tool._get_declaration.return_value = declaration

    with patch.object(po, "FunctionTool", return_value=fake_tool) as mock_ft:
        rendered = po.render_prompt_with_jinja2(agent)

    mock_ft.assert_called_once_with(my_function)
    assert "<tool>" in rendered
    assert "my_function" in rendered
    assert "function" in rendered


def test_render_prompt_skips_tool_without_declaration():
    def my_function():
        return None

    agent = _make_agent(tools=[my_function])

    fake_tool = MagicMock()
    fake_tool._get_declaration.return_value = None

    with patch.object(po, "FunctionTool", return_value=fake_tool):
        rendered = po.render_prompt_with_jinja2(agent)

    # Declaration is None -> tool is skipped, no tool block emitted.
    assert "<tool>" not in rendered
