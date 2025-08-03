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

"""
This file is used to optimize prompt in AgentPilot.
"""

from __future__ import annotations

import asyncio
from typing import Callable

from google.adk.tools import FunctionTool
from google.adk.tools.mcp_tool import MCPToolset
from jinja2 import Template

from veadk import Agent

# prompt = """
# <role>
# An experienced prompt optimizer.
# </role>

# <task>
# Please optimize prompt to make it more efficient.
# The prompt will be used as a system prompt and instruction of an agent.
# The definition and context (i.e., tools) of the agent will be provided.
# </task>

# <agent_info>
# name: {{ agent.name }}
# model: {{ agent.model }}
# description: {{ agent.description }}
# </agent_info>

# <agent_tools_info>
# {% for tool in tools %}
# <tool>
# name: {{ tool.name }}
# type: {{ tool.type }}
# description: {{ tool.description }}
# arguments: {{ tool.arguments }}
# </tool>
# {% endfor %}
# </agent_tools_info>
# """.strip()

prompt = """
Please help me to optimize the following agent prompt:
{{ original_prompt }}


The following information is your references：
<agent_info>
name: {{ agent.name }}
model: {{ agent.model }}
description: {{ agent.description }}
</agent_info>

<agent_tools_info>
{% for tool in tools %}
<tool>
name: {{ tool.name }}
type: {{ tool.type }}
description: {{ tool.description }}
arguments: {{ tool.arguments }}
</tool>
{% endfor %}
</agent_tools_info>

Please note that in your optimized prompt:
- the above referenced information is not necessary. For example, the tools list of agent is not necessary in the optimized prompt, because it maybe too long. You should use the tool information to optimize the original prompt rather than simply add tool list in prompt.
- The max length of optimized prompt should be less 4096 tokens.
""".strip()

prompt_with_feedback = """
After you optimization, my current prompt is:
{{ prompt }}

I did some evaluations with the optimized prompt, and the feedback is: {{ feedback }}

Please continue to optimize the prompt based on the feedback.
""".strip()


def render_prompt_feedback_with_jinja2(agent: Agent, feedback: str):
    template = Template(prompt_with_feedback)

    context = {
        "prompt": agent.instruction,
        "feedback": feedback,
    }

    rendered_prompt = template.render(context)

    return rendered_prompt


def render_prompt_with_jinja2(agent: Agent):
    template = Template(prompt)

    tools = []
    for tool in agent.tools:
        if isinstance(tool, Callable):
            type = "function"

            _tool = FunctionTool(tool)
            tools.append(
                {
                    "name": _tool.name,
                    "description": _tool.description,
                    "arguments": str(
                        _tool._get_declaration().model_dump()["parameters"]
                    ),
                    "type": type,
                }
            )
        elif isinstance(tool, MCPToolset):
            type = "tool"

            _tools = asyncio.run(tool.get_tools())
            for _tool in _tools:
                tools.append(
                    {
                        "name": _tool.name,
                        "description": _tool.description,
                        "arguments": str(
                            _tool._get_declaration().model_dump()["parameters"]
                        ),
                        "type": type,
                    }
                )

    context = {
        "original_prompt": agent.instruction,
        "agent": {
            "name": agent.name,
            "model": agent.model_name,
            "description": agent.description,
            # "tools": str(agent.tools),
        },
        "tools": tools,
    }

    rendered_prompt = template.render(context)

    return rendered_prompt
