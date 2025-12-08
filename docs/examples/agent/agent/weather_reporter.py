import asyncio

from veadk import Runner
from veadk.agent_builder import AgentBuilder

agent_builder = AgentBuilder()

agent = agent_builder.build(path="weather_reporter_agent.yaml")

runner = Runner(agent)
response = asyncio.run(runner.run("今天北京天气如何？"))

print(response)
