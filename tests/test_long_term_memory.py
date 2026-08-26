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

import json
import os
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.events import Event
from google.adk.sessions import Session
from google.adk.tools import load_memory
from google.genai import types
from pydantic import Field

from veadk.agent import Agent
from veadk.memory import MemoryAutoSavePolicy, save_session_callback
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)


class _RecordingBackend(BaseLongTermMemoryBackend):
    saved_call: dict[str, Any] = Field(default_factory=dict)

    def precheck_index_naming(self):
        pass

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        self.saved_call = {
            "user_id": user_id,
            "event_strings": event_strings,
            "kwargs": kwargs,
        }
        return True

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        return []


class OpenVikingLTMBackend(_RecordingBackend):
    pass


def _session_with_events(events: list[Event]) -> Session:
    return Session(
        id="session_001",
        app_name="support_app",
        user_id="alice",
        state={},
        events=events,
    )


def _saved_messages(backend: _RecordingBackend) -> list[dict[str, Any]]:
    return [json.loads(item) for item in backend.saved_call["event_strings"]]


def test_memory_auto_save_policy_is_exported():
    assert MemoryAutoSavePolicy(preset="all").preset == "all"


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


@pytest.mark.asyncio
async def test_default_auto_save_memory_policy_keeps_user_text_only():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part(text="记住我喜欢短回答")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="好的，我会记住")],
                ),
            ),
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call_1",
                                name="search",
                                args={"query": "preference"},
                            )
                        ),
                        types.Part(text="后续文本也应该保存"),
                    ],
                ),
            ),
        ]
    )

    await memory.add_session_to_memory(session)

    messages = _saved_messages(backend)
    assert [message["role"] for message in messages] == ["user", "user"]
    assert [message["parts"][0]["text"] for message in messages] == [
        "记住我喜欢短回答",
        "后续文本也应该保存",
    ]
    assert all("author" not in message for message in messages)
    assert all(
        "function_call" not in part for message in messages for part in message["parts"]
    )


@pytest.mark.asyncio
async def test_default_openviking_auto_save_memory_policy_keeps_assistant_text():
    backend = OpenVikingLTMBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part(text="我喜欢短回答")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="已记住")],
                ),
            ),
        ]
    )

    await memory.add_session_to_memory(session)

    messages = _saved_messages(backend)
    assert [message["role"] for message in messages] == ["user", "assistant"]
    assert [message["parts"][0]["text"] for message in messages] == [
        "我喜欢短回答",
        "已记住",
    ]


@pytest.mark.asyncio
async def test_all_auto_save_memory_policy_keeps_structured_events_and_sanitizes_media():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="planner",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="需要查用户偏好")],
                ),
            ),
            Event(
                author="planner",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call_1",
                                name="load_memory",
                                args={"query": "偏好"},
                            )
                        )
                    ],
                ),
            ),
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id="call_1",
                                name="load_memory",
                                response={"result": "短回答"},
                            )
                        )
                    ],
                ),
            ),
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            inline_data=types.Blob(
                                mime_type="text/plain",
                                data=b"abc",
                            )
                        )
                    ],
                ),
            ),
        ]
    )

    await memory.add_session_to_memory(session, auto_save_memory_policy="all")

    messages = _saved_messages(backend)
    assert [message["role"] for message in messages] == [
        "assistant",
        "assistant",
        "user",
        "user",
    ]
    assert messages[0]["author"] == "planner"
    assert messages[1]["parts"][0]["function_call"]["name"] == "load_memory"
    assert messages[2]["parts"][0]["function_response"]["response"] == {
        "result": "短回答"
    }
    inline_data = messages[3]["parts"][0]["inline_data"]
    assert inline_data == {
        "mime_type": "text/plain",
        "data_size": 4,
        "data_omitted": True,
    }


@pytest.mark.asyncio
async def test_custom_auto_save_memory_policy_filters_roles_and_non_text_parts():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[types.Part(text="用户文本")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="助手文本")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call_1",
                                name="search",
                                args={},
                            )
                        )
                    ],
                ),
            ),
        ]
    )

    await memory.add_session_to_memory(
        session,
        auto_save_memory_policy={
            "preset": "custom",
            "include_roles": ["assistant"],
        },
    )

    messages = _saved_messages(backend)
    assert len(messages) == 1
    assert messages[0]["role"] == "assistant"
    assert messages[0]["parts"][0]["text"] == "助手文本"


@pytest.mark.asyncio
async def test_custom_auto_save_memory_policy_explicit_event_types_keep_function_call():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(text="不会保存这段普通文本"),
                        types.Part(
                            function_call=types.FunctionCall(
                                id="call_1",
                                name="search",
                                args={"query": "偏好"},
                            )
                        ),
                    ],
                ),
            )
        ]
    )

    await memory.add_session_to_memory(
        session,
        auto_save_memory_policy={
            "preset": "custom",
            "include_roles": ["assistant"],
            "include_event_types": ["function_call"],
        },
    )

    messages = _saved_messages(backend)
    assert len(messages) == 1
    assert messages[0]["parts"] == [
        {
            "function_call": {
                "id": "call_1",
                "args": {"query": "偏好"},
                "name": "search",
            }
        }
    ]


@pytest.mark.asyncio
async def test_auto_save_memory_policy_excludes_author_and_event_type():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="助手文本")],
                ),
            ),
            Event(
                author="memory_optimizer",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="内部优化结果")],
                ),
            ),
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id="call_1",
                                name="search",
                                response={"result": "忽略工具结果"},
                            )
                        )
                    ],
                ),
            ),
        ]
    )

    await memory.add_session_to_memory(
        session,
        auto_save_memory_policy={
            "preset": "all",
            "exclude_authors": ["memory_optimizer"],
            "exclude_event_types": ["function_response"],
        },
    )

    messages = _saved_messages(backend)
    assert len(messages) == 1
    assert messages[0]["author"] == "assistant"
    assert messages[0]["parts"] == [{"text": "助手文本"}]


@pytest.mark.asyncio
async def test_auto_save_memory_policy_kwarg_is_not_forwarded_to_backend():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="assistant",
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="助手文本")],
                ),
            )
        ]
    )

    await memory.add_session_to_memory(
        session,
        source="manual",
        auto_save_memory_policy="all",
    )

    assert backend.saved_call["kwargs"] == {
        "session_id": "session_001",
        "app_name": "support_app",
        "source": "manual",
    }


@pytest.mark.asyncio
async def test_all_auto_save_memory_policy_keeps_error_event_without_content():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="assistant",
                error_code="500",
                error_message="tool failed",
            )
        ]
    )

    await memory.add_session_to_memory(session, auto_save_memory_policy="all")

    messages = _saved_messages(backend)
    assert messages == [
        {
            "parts": [
                {
                    "text": "500: tool failed",
                    "part_metadata": {"event_type": "error"},
                }
            ],
            "role": "assistant",
            "author": "assistant",
        }
    ]


@pytest.mark.asyncio
async def test_auto_save_memory_policy_strips_thought_but_keeps_final_text():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = _session_with_events(
        [
            Event(
                author="user",
                content=types.Content(
                    role="user",
                    parts=[
                        types.Part(text="内部推理", thought=True),
                        types.Part(text="最终偏好"),
                    ],
                ),
            )
        ]
    )

    await memory.add_session_to_memory(session)

    messages = _saved_messages(backend)
    assert len(messages) == 1
    assert messages[0]["parts"] == [{"text": "最终偏好"}]


@pytest.mark.asyncio
async def test_auto_save_callback_passes_agent_memory_policy():
    save_session_callback._session_save_cache.clear()
    save_session_callback._active_sessions.clear()
    session = _session_with_events([])

    class Memory:
        def __init__(self):
            self.calls = []

        async def add_session_to_memory(self, session: Session, **kwargs):
            self.calls.append({"session": session, "kwargs": kwargs})

    class SessionService:
        async def get_session(self, **kwargs):
            return session

    memory = Memory()
    callback_context = SimpleNamespace(
        _invocation_context=SimpleNamespace(
            agent=SimpleNamespace(
                long_term_memory=memory,
                auto_save_memory_policy="all",
            ),
            app_name="support_app",
            user_id="alice",
            session=session,
            session_service=SessionService(),
        )
    )

    await save_session_callback.save_session_to_long_term_memory(callback_context)

    assert memory.calls == [
        {
            "session": session,
            "kwargs": {"auto_save_memory_policy": "all"},
        }
    ]


@pytest.mark.asyncio
async def test_auto_save_callback_passes_policy_when_session_switches():
    save_session_callback._session_save_cache.clear()
    save_session_callback._active_sessions.clear()
    old_session = _session_with_events([])
    old_session.id = "old_session"
    new_session = _session_with_events([])
    new_session.id = "new_session"
    save_session_callback._active_sessions[
        (new_session.app_name, new_session.user_id)
    ] = old_session.id

    class Memory:
        def __init__(self):
            self.calls = []

        async def add_session_to_memory(self, session: Session, **kwargs):
            self.calls.append({"session_id": session.id, "kwargs": kwargs})

    class SessionService:
        async def get_session(self, *, session_id: str, **kwargs):
            return old_session if session_id == old_session.id else new_session

    memory = Memory()
    callback_context = SimpleNamespace(
        _invocation_context=SimpleNamespace(
            agent=SimpleNamespace(
                long_term_memory=memory,
                auto_save_memory_policy={"preset": "all"},
            ),
            app_name=new_session.app_name,
            user_id=new_session.user_id,
            session=new_session,
            session_service=SessionService(),
        )
    )

    await save_session_callback.save_session_to_long_term_memory(callback_context)

    assert memory.calls == [
        {
            "session_id": "old_session",
            "kwargs": {"auto_save_memory_policy": {"preset": "all"}},
        },
        {
            "session_id": "new_session",
            "kwargs": {"auto_save_memory_policy": {"preset": "all"}},
        },
    ]
