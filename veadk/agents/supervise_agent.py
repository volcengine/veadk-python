from google.adk.models.llm_request import LlmRequest
from jinja2 import Template

from veadk import Agent, Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

instruction = Template("""You are a supervisor of an agent system. The system prompt of worker agent is:

```system prompt
{{ system_prompt }}
```
                       
You should guide the agent to finish task. If you think the history execution is not correct, you should give your advice to the worker agent. If you think the history execution is correct, you should output an empty string.
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
        f"Tools of agent is {llm_request.tools_dict}. History trajectory is: "
        + messages
    )

    logger.debug(f"Prompt for supervisor: {prompt}")

    return await runner.run(messages=prompt)
