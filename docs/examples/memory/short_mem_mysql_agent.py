import asyncio
from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

app_name = "veadk_playground_app_short_term_1"
user_id = "veadk_playground_user_short_term_1"
session_id = "veadk_playground_session_short_term_1"

agent = Agent()
short_term_memory = ShortTermMemory(backend="local")
runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)


async def main():
    response1 = await runner.run(
        messages="我在 7 月 15 日购买了 20 个冰激凌", session_id=session_id
    )
    print(f"response of round 1: {response1}")

    response2 = await runner.run(
        messages="我什么时候买了冰激凌？", session_id=session_id
    )
    print(f"response of round 2: {response2}")


if __name__ == "__main__":
    asyncio.run(main())
