import random

from veadk import Agent, Runner
from veadk.tools.builtin_tools.vesearch import vesearch
from veadk.memory.short_term_memory import ShortTermMemory


app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"
API_KEY = "vesearch_api_key"

agent = Agent(
    name="ve_search_agent",
    model_name="doubao-seed-1-6-250615",
    api_key=API_KEY,
    description="An agent that can get result from veSearch",
    instruction="You are a helpful assistant that can provide information use vesearch tool.",
    tools=[vesearch]
)
short_term_memory = ShortTermMemory()  

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)

async def main():
    response = await runner.run(
        messages="杭州今天的天气怎么样？", session_id=session_id
    )
    print(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())