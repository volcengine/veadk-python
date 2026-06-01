# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Multi-turn conversation backed by short-term memory.

Short-term memory = the conversation context (everything sent to the model:
system prompt + history). VeADK keys it by `session_id`: reuse the same id and
the agent remembers earlier turns. Here we use the `sqlite` backend so the
session also survives across process restarts (stored on disk).
"""

import asyncio

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory

APP_NAME = "memory_demo"
SESSION_ID = "user-42-chat"


async def main() -> None:
    # `sqlite` persists the session to a local file. Use "local" for a purely
    # in-memory session that disappears when the process exits.
    short_term_memory = ShortTermMemory(
        backend="sqlite",
        local_database_path="./short_term_memory.db",
    )

    agent = Agent(
        name="memory_agent",
        instruction="You are a concise assistant. Remember what the user tells you.",
        short_term_memory=short_term_memory,
    )

    runner = Runner(
        agent=agent,
        short_term_memory=short_term_memory,
        app_name=APP_NAME,
    )

    # Turn 1: tell the agent something.
    print(
        "Turn 1 ->",
        await runner.run(
            messages="我叫小明，最喜欢的颜色是蓝色。",
            session_id=SESSION_ID,
        ),
    )

    # Turn 2: same session_id, so the agent recalls turn 1.
    print(
        "Turn 2 ->",
        await runner.run(
            messages="我叫什么名字？我喜欢什么颜色？",
            session_id=SESSION_ID,
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
