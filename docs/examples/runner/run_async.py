import asyncio

from veadk import Runner
from google.adk.agents import BaseAgent
from google.adk.events import Event, EventActions
from google.adk.sessions import InMemorySessionService
from google.adk.agents.invocation_context import InvocationContext
from google.genai import types

APP_NAME = "interactive_app"
USER_ID = "test_user_01"
SESSION_ID = "session_001"


# 模拟指令执行的Agent
class AsyncInteractiveAgent(BaseAgent):
    async def run_async(self, ctx: InvocationContext):
        user_input = ctx.session.events[-1].content.parts[0].text
        state = ctx.session.state

        print(f"[Agent] 收到输入: {user_input}")

        # 初始状态：如果会话没有暂停，说明是第一轮，需要请求用户确认
        if "pending_input" not in state:
            yield Event(
                author=self.name,
                content=types.Content(
                    parts=[types.Part(text=f"你说: {user_input}，是否确认执行？")]
                ),
                actions=EventActions(state_delta={"pending_input": user_input}),
            )
            return
        else:
            # 第二阶段：会话已暂停，等待用户确认结果
            # 检查用户输入是否为确认
            if user_input.lower() in ["是", "yes", "y"]:
                # 用户已确认，执行操作
                pending_action = state.get("pending_input", "")
                yield Event(
                    author=self.name,
                    content=types.Content(
                        parts=[types.Part(text=f"操作 '{pending_action}' 完成 ✅")]
                    ),
                    actions=EventActions(state_delta={"pending_input": None}),
                )
                return
            # 用户已取消
            else:
                pending_action = state.get("pending_input", "")
                yield Event(
                    author=self.name,
                    content=types.Content(
                        parts=[types.Part(text=f"操作 '{pending_action}' 已取消 ❌")]
                    ),
                    actions=EventActions(state_delta={"pending_input": None}),
                )
                return


# 模拟多轮异步会话
async def main():
    session_service = InMemorySessionService()
    agent = AsyncInteractiveAgent(name="async_agent")
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=session_service)
    await session_service.create_session(
        user_id=USER_ID, app_name=APP_NAME, session_id=SESSION_ID
    )

    # 第 1 轮：输入指令
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=types.Content(parts=[types.Part(text="删除我的账号")]),
    ):
        print(f"[Runner] 接收到事件: {event.content.parts[0].text}")

    # 第 2 轮：确认操作
    async for event in runner.run_async(
        user_id=USER_ID,
        session_id=SESSION_ID,
        new_message=types.Content(parts=[types.Part(text="是")]),
    ):
        print(f"[Runner] 接收到事件: {event.content.parts[0].text}")


if __name__ == "__main__":
    asyncio.run(main())
