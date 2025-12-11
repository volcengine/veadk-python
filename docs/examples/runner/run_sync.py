import asyncio

from veadk import Runner
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.sessions import InMemorySessionService
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types

APP_NAME = "hello_app"
USER_ID = "test_user_01"
SESSION_ID = "session_001"


# 模拟一个简单的 Agent
class HelloAgent(BaseAgent):
    async def run_async(self, ctx: InvocationContext):
        # 从当前 session 获取用户输入
        user_input = ctx.session.events[-1].content.parts[0].text
        print(f"[Agent] 收到用户输入: {user_input}")

        # 构造一个事件（代表 LLM 的输出）
        event = Event(
            author=self.name,
            content=types.Content(
                parts=[
                    types.Part(text="今天是个晴天，温度15~22摄氏度，非常适合户外活动！")
                ]
            ),
        )

        # 产出事件（yield 触发 Runner 处理）
        yield event


async def main():
    session_service = InMemorySessionService()
    agent = HelloAgent(name="hello_agent")
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    await session_service.create_session(
        user_id=USER_ID, app_name=APP_NAME, session_id=SESSION_ID
    )

    # Runner.run_async 返回一个异步生成器，逐个产出事件
    response = await runner.run(
        user_id=USER_ID, session_id=SESSION_ID, messages="今天天气怎么样？"
    )

    print(f"[Runner] 运行结束，响应: {response}")


if __name__ == "__main__":
    asyncio.run(main())
