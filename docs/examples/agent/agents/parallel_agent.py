import asyncio

from veadk import Agent, Runner
from veadk.agents.parallel_agent import ParallelAgent

pros_agent = Agent(
    name="pros_agent",
    description="An expert that identifies the advantages of a topic.",
    instruction="List and explain the positive aspects or advantages of the given topic.",
)

cons_agent = Agent(
    name="cons_agent",
    description="An expert that identifies the disadvantages of a topic.",
    instruction="List and explain the negative aspects or disadvantages of the given topic.",
)

root_agent = ParallelAgent(sub_agents=[pros_agent, cons_agent])

if __name__ == "__main__":
    runner = Runner(root_agent)
    response = asyncio.run(runner.run("请分析 LLM-as-a-Judge 这种评测模式的优劣"))
    print(response)
