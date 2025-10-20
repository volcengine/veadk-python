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


import os

import pytest
from google.adk.tools import load_memory

from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory


@pytest.mark.asyncio
async def test_long_term_memory():
    os.environ["MODEL_EMBEDDING_API_KEY"] = "mocked_api_key"
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

    assert agent.long_term_memory
    assert agent.long_term_memory._backend

    # assert agent.long_term_memory._backend.index == build_long_term_memory_index(
    #     app_name, user_id
    # )
