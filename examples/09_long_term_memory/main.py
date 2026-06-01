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

"""Remember things *across* conversations with long-term memory.

Short-term memory (example 03) lives inside one conversation. Long-term memory
persists facts across *different* sessions and users:

- `long_term_memory=...` gives the agent a `load_memory` tool to search past
  sessions.
- `auto_save_session=True` writes each finished session into long-term memory
  automatically.

So we talk in session #1, then start a brand-new session #2 and the agent can
still recall what was said — by searching its memory, not its context window.

Uses the `local` backend, which embeds memories and needs:

    pip install "veadk-python[extensions]"
"""

import asyncio

from veadk import Agent, Runner
from veadk.memory.long_term_memory import LongTermMemory

APP_NAME = "ltm_demo"
USER_ID = "user-42"


def build_runner() -> Runner:
    long_term_memory = LongTermMemory(backend="local", app_name=APP_NAME)
    agent = Agent(
        name="ltm_agent",
        instruction=(
            "You are a personal assistant. When the user asks about something "
            "they told you before, use the `load_memory` tool to recall it."
        ),
        long_term_memory=long_term_memory,
        auto_save_session=True,  # persist each session to long-term memory
    )
    return Runner(agent=agent, app_name=APP_NAME, user_id=USER_ID)


async def main() -> None:
    runner = build_runner()

    # Session #1: share a fact. auto_save_session stores it afterwards.
    print(
        "Session 1 ->",
        await runner.run(
            messages="记一下：我对花生过敏，而且我是素食者。",
            session_id="session-1",
        ),
    )

    # Session #2: a *different* session. The agent must recall via memory search.
    print(
        "Session 2 ->",
        await runner.run(
            messages="帮我推荐一道适合我的菜，要考虑我的饮食限制。",
            session_id="session-2",
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
