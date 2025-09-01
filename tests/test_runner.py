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

from google.genai import types

from veadk.agent import Agent
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner


def _test_convert_messages(runner):
    message = "test message"
    expected_message = [
        types.Content(
            parts=[types.Part(text=message)],
            role="user",
        )
    ]
    actual_message = runner._convert_messages(
        message, session_id="test_session_id", upload_inline_data_to_tos=True
    )
    assert actual_message == expected_message

    message = ["test message 1", "test message 2"]
    expected_message = [
        types.Content(
            parts=[types.Part(text="test message 1")],
            role="user",
        ),
        types.Content(
            parts=[types.Part(text="test message 2")],
            role="user",
        ),
    ]
    actual_message = runner._convert_messages(
        message, session_id="test_session_id", upload_inline_data_to_tos=True
    )
    assert actual_message == expected_message


def test_runner():
    short_term_memory = ShortTermMemory()
    long_term_memory = LongTermMemory(backend="local")
    agent = Agent(
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        long_term_memory=long_term_memory,
    )

    runner = Runner(agent=agent, short_term_memory=short_term_memory)
    assert runner.long_term_memory == agent.long_term_memory

    adk_runner = runner.runner
    assert adk_runner.memory_service == agent.long_term_memory
    assert adk_runner.session_service == runner.short_term_memory.session_service

    _test_convert_messages(runner)
    _test_convert_messages(runner)
    _test_convert_messages(runner)
