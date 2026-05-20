import asyncio

from veadk import Agent, Runner
from veadk.extensions import FeishuChannelExtension
from veadk.memory.short_term_memory import ShortTermMemory

agent = Agent(
    name="feishu_agent",
    instruction="你是一个通过飞书机器人与用户沟通的助手。",
)

runner = Runner(
    agent=agent,
    app_name="veadk_feishu_demo",
    user_id="veadk_feishu_default_user",
    short_term_memory=ShortTermMemory(),
)

channel = FeishuChannelExtension(
    runner=runner,
    channel_kwargs={
        "transport": "ws",
    },
)


async def main():
    await channel.connect()


if __name__ == "__main__":
    asyncio.run(main())
