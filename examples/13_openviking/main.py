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

"""Use OpenViking for both knowledge base RAG and long-term memory.

This example imports local Markdown docs into an OpenViking resource directory
and stores cross-session memories in OpenViking. OpenViking handles indexing and
memory extraction remotely, so no embedding model configuration is required.
"""

import asyncio
from pathlib import Path

from veadk import Agent, Runner
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory

APP_NAME = "openviking_demo"
USER_ID = "user-42"
DOCS_DIR = Path(__file__).parent / "docs"


def build_knowledgebase() -> KnowledgeBase:
    # Recommended: keep OpenViking connection settings in .env or config.yaml.
    # This reads DATABASE_OPENVIKING_URL/API_KEY/USER_ID automatically.
    knowledgebase = KnowledgeBase(
        backend="openviking",
        index="company_faq",
    )
    # Equivalent explicit override when one process needs multiple contexts:
    #
    # knowledgebase = KnowledgeBase(
    #     backend="openviking",
    #     backend_config={
    #         "index": "company_faq",
    #         "openviking_user_id": "openviking_demo",
    #     },
    # )
    knowledgebase.add_from_directory(str(DOCS_DIR))
    return knowledgebase


def build_runner(knowledgebase: KnowledgeBase) -> Runner:
    # LongTermMemory also reads DATABASE_OPENVIKING_URL/API_KEY/USER_ID.
    long_term_memory = LongTermMemory(
        backend="openviking",
        app_name=APP_NAME,
    )
    agent = Agent(
        name="openviking_agent",
        description="Answers with OpenViking knowledge and memory.",
        instruction=(
            "Use the knowledge base for company policy questions. Use the "
            "`load_memory` tool when the user asks about preferences or facts "
            "shared in previous sessions."
        ),
        knowledgebase=knowledgebase,
        long_term_memory=long_term_memory,
        auto_save_session=True,
    )
    # Runner.user_id is the end-user id. OpenViking receives it as peer_id for
    # memory isolation; it is different from DATABASE_OPENVIKING_USER_ID.
    return Runner(agent=agent, app_name=APP_NAME, user_id=USER_ID)


async def main() -> None:
    knowledgebase = build_knowledgebase()
    try:
        runner = build_runner(knowledgebase)

        print(
            "Session 1 ->",
            await runner.run(
                messages=(
                    "请先记住：我喜欢简短直接的回答。然后告诉我公司的远程办公政策。"
                ),
                session_id="session-1",
            ),
        )

        print(
            "Session 2 ->",
            await runner.run(
                messages="我之前说过我偏好什么回答风格？顺便说一下报销时限。",
                session_id="session-2",
            ),
        )
    finally:
        knowledgebase.close()


if __name__ == "__main__":
    asyncio.run(main())
