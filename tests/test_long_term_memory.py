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
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.tools import load_memory
from google.genai import types

from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory

app_name = "test_ltm"
user_id = "test_user"


@pytest.mark.asyncio
async def test_long_term_memory():
    long_term_memory = LongTermMemory(backend="local")
    agent = Agent(
        name="all_name",
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        description="a veadk test agent",
        instruction="a veadk test agent",
        long_term_memory=long_term_memory,
    )

    assert load_memory in agent.tools, "load_memory tool not found in agent tools"

    # mock session
    session = Session(
        id="test_session_id",
        app_name=app_name,
        user_id=user_id,
        events=[
            Event(
                invocation_id="test_invocation_id",
                author=agent.name,
                branch=None,
                content=types.Content(
                    parts=[types.Part(text="My name is Alice.")],
                    role="user",
                ),
            )
        ],
    )

    await long_term_memory.add_session_to_memory(session)

    memories = await long_term_memory.search_memory(
        app_name=app_name,
        user_id=user_id,
        query="Alice",
    )
    assert (
        "Alice" in memories.model_dump()["memories"][0]["content"]["parts"][0]["text"]
    )
