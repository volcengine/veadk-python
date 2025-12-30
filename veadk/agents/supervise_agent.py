from google.adk.models.llm_request import LlmRequest
from jinja2 import Template
from pydantic import BaseModel

from veadk import Agent, Runner


class SupervisorAgentOutput(BaseModel):
    advice: str = ""
    """
    Advices for the worker agent.
    For example, suggested function call / actions / responses.
    """


instruction = Template("""You are a supervisor of an agent system. The system prompt of worker agent is:

```system prompt
{{ system_prompt }}
```
                       
```worker agent tools
{{ agent_tools }}
```

You should guide the agent to finish task. If you think the history execution is not correct, you should give your advice to the worker agent. If you think the history execution is correct, you should output an empty string.

Your final response should be in `json` format.
""")


def build_supervisor(supervised_agent: Agent) -> Agent:
    custom_instruction = instruction.render(system_prompt=supervised_agent.instruction)
    agent = Agent(
        name="supervisor",
        description="",
        instruction=custom_instruction,
        output_schema=SupervisorAgentOutput,
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

    return await runner.run(messages="History trajectory is: " + messages)
