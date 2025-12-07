from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.builtin_tools.las import las

app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"

agent = Agent(
    name="las_agent",
    description=("use data from las"),
    instruction=(
        """
        你是一个诗人，根据用户的需求生成诗词。
        你可以使用的MCP工具集有：
            - las
        第一步你需要使用las工具去ds_public数据集检索相关内容，然后基于检索内容作为基础来写一首诗词。
        """
    ),
    tools=[
        las,
    ],
)

short_term_memory = ShortTermMemory()

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)


async def main():
    response = await runner.run(
        messages="写一首国风和木头、爱情相关的诗词", session_id=session_id
    )
    print(response)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
