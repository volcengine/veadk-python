import asyncio

from veadk import Agent, Runner
from veadk.agents.sequential_agent import SequentialAgent

greeting_agent = Agent(
    name="greeting_agent",
    description="A friendly agent that greets the user.",
    instruction="Greet the user warmly.",
)

goodbye_agent = Agent(
    name="goodbye_agent",
    description="A polite agent that says goodbye to the user.",
    instruction="Say goodbye to the user politely.",
)

root_agent = SequentialAgent(sub_agents=[greeting_agent, goodbye_agent])

if __name__ == "__main__":
    runner = Runner(root_agent)
    response = asyncio.run(runner.run("你好"))
    print(response)
