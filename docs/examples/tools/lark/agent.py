
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.builtin_tools.lark import lark_tools

app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"

agent = Agent(
    name="lark_agent",
    description=("飞书机器人"),
    instruction=("""
            你是一个飞书机器人，通过lark_tools给用户发消息。
        """
    ),
    tools=[
        lark_tools,
    ],
)

short_term_memory = ShortTermMemory()  

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)

async def main():
    response = await runner.run(
        messages="给xiangya@bytedance.com发送'你好，我是lark agent'", session_id=session_id
    )
    print(response)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())