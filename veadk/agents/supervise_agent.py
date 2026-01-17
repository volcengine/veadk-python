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
from jinja2 import Template

from veadk import Agent, Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

instruction = Template("""You are a supervisor of an agent system. The system prompt of worker agent is:

```system prompt
{{ system_prompt }}
```



You should guide the agent to finish task and must output a JSON-format string with specific advice and reason:
                       
- If you think the history execution is not correct, you should give your advice to the worker agent: {"advice": "Your advice here", "reason": "Your reason here"}.
- If you think the history execution is correct, you should output an empty string: {"advice": "", "reason": "Your reason here"}.
""")


def build_supervisor(supervised_agent: Agent) -> Agent:
    custom_instruction = instruction.render(system_prompt=supervised_agent.instruction)
    agent = Agent(
        name="supervisor",
        description="A supervisor for agent execution",
        instruction=custom_instruction,
    )

    return agent


async def generate_advice(agent: Agent, llm_request: LlmRequest) -> str:
    runner = Runner(agent=agent)

    messages = ""
    for content in llm_request.contents:
        if content and content.parts:
            for part in content.parts:
                if part.text:
                    messages += f"{content.role}: {part.text}"
                if part.function_call:
                    messages += f"{content.role}: {part.function_call}"
                if part.function_response:
                    messages += f"{content.role}: {part.function_response}"

    prompt = (
        f"Agent has the following tools: {llm_request.tools_dict}. History trajectory is: "
        + messages
    )

    logger.debug(f"Prompt for supervisor: {prompt}")

    return await runner.run(messages=prompt)
