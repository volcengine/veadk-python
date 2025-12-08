from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.builtin_tools.generate_image import image_generate

app_name = "veadk_app"
user_id = "veadk_user"
session_id = "veadk_session"

agent = Agent(
    name="image_generate_agent",
    description=("根据需求生成图片."),
    instruction=(
        """
        你是一个图片生成专家，根据用户的需求生成图片。
        你可以使用的工具有：
            - image_generate
        你只能依靠自己和绘图工具来完成任务。
        """
    ),
    tools=[
        image_generate,
    ],
)

short_term_memory = ShortTermMemory()

runner = Runner(
    agent=agent, short_term_memory=short_term_memory, app_name=app_name, user_id=user_id
)


async def main():
    response = await runner.run(messages="生成一个可爱的小猫", session_id=session_id)
    print(response)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
