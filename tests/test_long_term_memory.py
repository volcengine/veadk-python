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


import pytest
# from google.adk.tools import load_memory


from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory
from veadk.runner import Runner
from veadk.memory.short_term_memory import ShortTermMemory

app_name = "test_ltm"
user_id = "test_user"
session_id = "test_session"


@pytest.mark.asyncio
async def test_long_term_memory():
    long_term_memory = LongTermMemory(
        backend="mem0",
        top_k=3,
        app_name=app_name,
        # app_name=app_name,
        # user_id=user_id,
    )
    agent = Agent(
        name="all_name",
        description="a veadk test agent",
        instruction="a veadk test agent",
        long_term_memory=long_term_memory,
    )
    runner = Runner(
        agent=agent,
        # app_name="financial-consultant-agent",
        app_name="data_analysis_v2",
        user_id=user_id,
        short_term_memory=ShortTermMemory(),
    )

    response = await runner.run(
        messages="adding memory, test llm with mem0",
        user_id=user_id,
        session_id=session_id,
    )
    print("mem0 response:", response)
    # await runner.run(messages=teaching_prompt, session_id=session_id)

    # save the teaching prompt and answer in long term memory
    await runner.save_session_to_long_term_memory(session_id=session_id)

    response = await runner.run(
        messages="query mem0", user_id=user_id, session_id=session_id
    )
    print("Search response:", response)

    # assert load_memory in agent.tools, "load_memory tool not found in agent tools"

    assert agent.long_term_memory._backend is not None

    # assert agent.long_term_memory._backend.index == build_long_term_memory_index(
    #     app_name, user_id
    # )


if __name__ == "__main__":
    import asyncio

    asyncio.run(test_long_term_memory())
