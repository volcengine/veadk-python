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
import threading
from typing import Any

import pytest
from google.adk.events import Event
from google.adk.sessions import Session
from google.genai import types
from pydantic import Field

from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.long_term_memory_backends.base_backend import (
    BaseLongTermMemoryBackend,
)
from veadk.memory.long_term_memory_backends.openviking_backend import (
    OpenVikingLTMBackend,
)


def _install_fake_openviking_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    responses: dict[str, dict[str, Any]] | None = None,
):
    calls = []
    responses = responses or {}

    class FakeSyncHTTPClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def initialize(self):
            pass

        def close(self):
            pass

        def create_session(self, *, session_id=None, memory_policy=None, **kwargs):
            calls.append(
                {
                    "method": "create_session",
                    "actor_peer_id": self.kwargs.get("actor_peer_id"),
                    "payload": {
                        "session_id": session_id,
                        "memory_policy": memory_policy,
                        **kwargs,
                    },
                }
            )
            return responses.get("create_session", {})

        def add_message(
            self, session_id, *, role, content=None, peer_id=None, **kwargs
        ):
            calls.append(
                {
                    "method": "add_message",
                    "actor_peer_id": self.kwargs.get("actor_peer_id"),
                    "payload": {
                        "session_id": session_id,
                        "role": role,
                        "content": content,
                        "peer_id": peer_id,
                        **kwargs,
                    },
                }
            )
            return responses.get("add_message", {})

        def commit_session(self, *, session_id, keep_recent_count=0, **kwargs):
            calls.append(
                {
                    "method": "commit_session",
                    "actor_peer_id": self.kwargs.get("actor_peer_id"),
                    "payload": {
                        "session_id": session_id,
                        "keep_recent_count": keep_recent_count,
                        **kwargs,
                    },
                }
            )
            return responses.get("commit_session", {})

        def find(self, *, query, target_uri="", limit=10, context_type=None, **kwargs):
            calls.append(
                {
                    "method": "find",
                    "actor_peer_id": self.kwargs.get("actor_peer_id"),
                    "payload": {
                        "query": query,
                        "target_uri": target_uri,
                        "context_type": context_type,
                        "limit": limit,
                        **kwargs,
                    },
                }
            )
            return responses.get("find", {})

    monkeypatch.setattr(
        "veadk.memory.long_term_memory_backends.openviking_backend.SyncHTTPClient",
        FakeSyncHTTPClient,
    )
    return calls


def _install_loop_sensitive_openviking_sdk(
    monkeypatch: pytest.MonkeyPatch,
    *,
    event_loop_thread_id: int,
    responses: dict[str, dict[str, Any]] | None = None,
):
    calls = []
    responses = responses or {}

    class LoopSensitiveSyncHTTPClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def _record(self, method: str, payload: dict[str, Any] | None = None):
            thread_id = threading.get_ident()
            if thread_id == event_loop_thread_id:
                raise RuntimeError(f"{method} ran on the event loop thread")
            calls.append(
                {
                    "method": method,
                    "thread_id": thread_id,
                    "actor_peer_id": self.kwargs.get("actor_peer_id"),
                    "payload": payload or {},
                }
            )

        def initialize(self):
            self._record("initialize")

        def close(self):
            self._record("close")

        def create_session(self, *, session_id=None, memory_policy=None, **kwargs):
            self._record(
                "create_session",
                {
                    "session_id": session_id,
                    "memory_policy": memory_policy,
                    **kwargs,
                },
            )
            return responses.get("create_session", {})

        def add_message(
            self, session_id, *, role, content=None, peer_id=None, **kwargs
        ):
            self._record(
                "add_message",
                {
                    "session_id": session_id,
                    "role": role,
                    "content": content,
                    "peer_id": peer_id,
                    **kwargs,
                },
            )
            return responses.get("add_message", {})

        def commit_session(self, *, session_id, keep_recent_count=0, **kwargs):
            self._record(
                "commit_session",
                {
                    "session_id": session_id,
                    "keep_recent_count": keep_recent_count,
                    **kwargs,
                },
            )
            return responses.get("commit_session", {})

        def find(self, *, query, target_uri="", limit=10, context_type=None, **kwargs):
            self._record(
                "find",
                {
                    "query": query,
                    "target_uri": target_uri,
                    "context_type": context_type,
                    "limit": limit,
                    **kwargs,
                },
            )
            return responses.get("find", {})

    monkeypatch.setattr(
        "veadk.memory.long_term_memory_backends.openviking_backend.SyncHTTPClient",
        LoopSensitiveSyncHTTPClient,
    )
    return calls


def test_openviking_backend_writes_peer_messages_and_commits(monkeypatch):
    calls = _install_fake_openviking_sdk(monkeypatch)
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    assert backend.save_memory(
        user_id="alice",
        event_strings=[
            json.dumps(
                {"role": "user", "parts": [{"text": "我喜欢简短直接的回答"}]},
                ensure_ascii=False,
            )
        ],
        app_name="support_app",
        session_id="session_001",
    )

    assert [call["method"] for call in calls] == [
        "create_session",
        "add_message",
        "commit_session",
    ]
    openviking_session_id = calls[0]["payload"]["session_id"]
    assert openviking_session_id != "session_001"
    assert openviking_session_id.startswith("veadk__")
    assert "support_app" in openviking_session_id
    assert "alice" in openviking_session_id
    assert calls[0] == {
        "method": "create_session",
        "actor_peer_id": None,
        "payload": {
            "session_id": openviking_session_id,
            "memory_policy": {
                "self": {"enabled": False},
                "peer": {"enabled": True},
                "memory_types": ["entities", "events", "preferences"],
            },
        },
    }
    assert calls[1] == {
        "method": "add_message",
        "actor_peer_id": None,
        "payload": {
            "session_id": openviking_session_id,
            "role": "user",
            "content": "我喜欢简短直接的回答",
            "peer_id": "alice",
        },
    }
    assert calls[2] == {
        "method": "commit_session",
        "actor_peer_id": None,
        "payload": {"session_id": openviking_session_id, "keep_recent_count": 0},
    }


def test_openviking_backend_sdk_create_payload(monkeypatch):
    calls = _install_fake_openviking_sdk(monkeypatch)
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )
    client = backend._new_client()

    backend._create_session(client=client, session_id="sa1")

    assert calls == [
        {
            "method": "create_session",
            "actor_peer_id": None,
            "payload": {
                "session_id": "sa1",
                "memory_policy": {
                    "self": {"enabled": False},
                    "peer": {"enabled": True},
                    "memory_types": ["entities", "events", "preferences"],
                },
            },
        }
    ]


def test_openviking_backend_sdk_message_payload(monkeypatch):
    calls = _install_fake_openviking_sdk(monkeypatch)
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )
    client = backend._new_client()

    backend._add_message(
        client=client,
        session_id="sa1",
        role="user",
        content="请记住：我的专属暗号是紫竹A1。",
        peer_id="a1",
    )

    assert calls == [
        {
            "method": "add_message",
            "actor_peer_id": None,
            "payload": {
                "session_id": "sa1",
                "role": "user",
                "content": "请记住：我的专属暗号是紫竹A1。",
                "peer_id": "a1",
            },
        }
    ]


def test_openviking_backend_search_uses_find_with_actor_peer(monkeypatch):
    calls = _install_fake_openviking_sdk(
        monkeypatch,
        responses={"find": {"memories": [{"abstract": "用户喜欢简短直接的回答"}]}},
    )
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    memories = backend.search_memory(
        user_id="alice",
        query="用户偏好",
        top_k=3,
        app_name="support_app",
        session_id="session_002",
    )

    assert memories == [
        json.dumps({"abstract": "用户喜欢简短直接的回答"}, ensure_ascii=False)
    ]
    assert calls[0]["actor_peer_id"] == "alice"
    assert [call["method"] for call in calls] == ["find"]
    assert "session_id" not in calls[0]["payload"]
    assert calls[0] == {
        "method": "find",
        "actor_peer_id": "alice",
        "payload": {
            "query": "用户偏好",
            "target_uri": "viking://user/peers/alice/memories",
            "context_type": "memory",
            "limit": 3,
        },
    }


def test_openviking_backend_search_falls_back_to_find_without_session(monkeypatch):
    calls = _install_fake_openviking_sdk(
        monkeypatch,
        responses={"find": {"memories": []}},
    )
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    assert (
        backend.search_memory(
            user_id="alice",
            query="用户偏好",
            top_k=3,
            app_name="support_app",
        )
        == []
    )

    assert calls == [
        {
            "method": "find",
            "actor_peer_id": "alice",
            "payload": {
                "query": "用户偏好",
                "target_uri": "viking://user/peers/alice/memories",
                "context_type": "memory",
                "limit": 3,
            },
        }
    ]


def test_openviking_backend_sdk_find_payload(monkeypatch):
    calls = _install_fake_openviking_sdk(
        monkeypatch,
        responses={"find": {"memories": []}},
    )
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    backend._search_with_actor_client(
        peer_id="a1",
        query="我的专属暗号和回答风格偏好是什么？",
        top_k=10,
    )

    assert calls == [
        {
            "method": "find",
            "actor_peer_id": "a1",
            "payload": {
                "query": "我的专属暗号和回答风格偏好是什么？",
                "target_uri": "viking://user/peers/a1/memories",
                "context_type": "memory",
                "limit": 10,
            },
        }
    ]


def test_openviking_backend_sdk_commit_payload(monkeypatch):
    calls = _install_fake_openviking_sdk(monkeypatch)
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )
    client = backend._new_client()

    backend._commit_session(client=client, session_id="sa1")

    assert calls == [
        {
            "method": "commit_session",
            "actor_peer_id": None,
            "payload": {"session_id": "sa1", "keep_recent_count": 0},
        }
    ]


def test_openviking_backend_extracts_top_level_adk_memory_items(monkeypatch):
    _install_fake_openviking_sdk(
        monkeypatch,
        responses={
            "find": {
                "memories": [
                    {
                        "author": "user",
                        "content": {
                            "parts": [
                                "{'text': \"'# 用户偏好记录\\n- Result: 成功记录用户偏好'\"}"
                            ],
                            "role": "user",
                        },
                        "custom_metadata": {},
                    }
                ]
            }
        },
    )
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    memories = backend.search_memory(
        user_id="alice",
        query="用户偏好",
        top_k=3,
        app_name="support_app",
    )

    assert json.loads(memories[0]) == {
        "author": "user",
        "content": {
            "parts": ["{'text': \"'# 用户偏好记录\\n- Result: 成功记录用户偏好'\"}"],
            "role": "user",
        },
        "custom_metadata": {},
    }


def test_openviking_backend_deduplicates_memories_by_uri_and_keeps_best_score():
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    memories = [
        json.loads(memory)
        for memory in backend._extract_memories(
            {
                "memories": [
                    {
                        "uri": "viking://user/default/peers/aa01/memories/a.md",
                        "score": 0.1,
                        "abstract": "low score",
                    },
                    {
                        "uri": "viking://user/default/peers/aa01/memories/b.md",
                        "score": 0.3,
                        "abstract": "other memory",
                    },
                    {
                        "uri": "viking://user/default/peers/aa01/memories/a.md",
                        "score": 0.9,
                        "abstract": "high score",
                    },
                ]
            }
        )
    ]

    assert len(memories) == 2
    assert memories[0]["abstract"] == "high score"
    assert memories[0]["score"] == 0.9
    assert memories[1]["abstract"] == "other memory"


@pytest.mark.parametrize(
    "peer_id",
    ["app/alice", "app:alice", "alice+1", ".", "..", "alice bob"],
)
def test_openviking_backend_rejects_unsafe_peer_id(peer_id):
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
        peer_id_resolver=lambda app_name, user_id: peer_id,
    )

    with pytest.raises(ValueError, match="safe single path segment"):
        backend.search_memory(
            user_id="alice",
            query="用户偏好",
            top_k=3,
            app_name="support_app",
        )


def test_openviking_backend_namespaces_same_session_by_peer(monkeypatch):
    calls = _install_fake_openviking_sdk(monkeypatch)
    backend = OpenVikingLTMBackend(
        index="support_app",
        url="http://openviking.test",
        api_key="owner-key",
    )

    for user_id in ("alice", "bob"):
        assert backend.save_memory(
            user_id=user_id,
            event_strings=[json.dumps({"role": "user", "parts": [{"text": user_id}]})],
            app_name="support_app",
            session_id="session",
        )

    created_sessions = [
        call["payload"]["session_id"]
        for call in calls
        if call["method"] == "create_session"
    ]
    message_calls = [call for call in calls if call["method"] == "add_message"]

    assert len(created_sessions) == 2
    assert created_sessions[0] != created_sessions[1]
    assert "alice" in created_sessions[0]
    assert "bob" in created_sessions[1]
    assert message_calls[0]["payload"]["peer_id"] == "alice"
    assert message_calls[0]["payload"]["session_id"] == created_sessions[0]
    assert message_calls[1]["payload"]["peer_id"] == "bob"
    assert message_calls[1]["payload"]["session_id"] == created_sessions[1]


@pytest.mark.asyncio
async def test_long_term_memory_openviking_search_runs_sdk_off_event_loop_thread(
    monkeypatch,
):
    event_loop_thread_id = threading.get_ident()
    calls = _install_loop_sensitive_openviking_sdk(
        monkeypatch,
        event_loop_thread_id=event_loop_thread_id,
        responses={
            "find": {
                "memories": [
                    {
                        "uri": "viking://user/peers/alice/memories/preferences/a.md",
                        "abstract": "用户喜欢简短直接的回答",
                    }
                ]
            }
        },
    )
    memory = LongTermMemory(
        backend="openviking",
        backend_config={
            "index": "support_app",
            "url": "http://openviking.test",
            "api_key": "owner-key",
        },
        top_k=2,
    )

    response = await memory.search_memory(
        app_name="support_app",
        user_id="alice",
        query="用户偏好",
    )

    assert response.memories[0].content.parts[0].text == "用户喜欢简短直接的回答"
    assert [call["method"] for call in calls] == ["initialize", "find", "close"]
    assert {call["thread_id"] for call in calls} != {event_loop_thread_id}
    assert calls[1]["actor_peer_id"] == "alice"
    assert calls[1]["payload"] == {
        "query": "用户偏好",
        "target_uri": "viking://user/peers/alice/memories",
        "context_type": "memory",
        "limit": 2,
    }


@pytest.mark.asyncio
async def test_long_term_memory_openviking_save_runs_sdk_off_event_loop_thread(
    monkeypatch,
):
    event_loop_thread_id = threading.get_ident()
    calls = _install_loop_sensitive_openviking_sdk(
        monkeypatch,
        event_loop_thread_id=event_loop_thread_id,
    )
    memory = LongTermMemory(
        backend="openviking",
        backend_config={
            "index": "support_app",
            "url": "http://openviking.test",
            "api_key": "owner-key",
        },
    )
    session = Session(
        id="session_001",
        app_name="support_app",
        user_id="alice",
        state={},
        events=[
            Event(
                author="user",
                content=types.Content(
                    parts=[types.Part(text="记住我喜欢短回答")],
                    role="user",
                ),
            )
        ],
    )

    await memory.add_session_to_memory(session)

    assert [call["method"] for call in calls] == [
        "initialize",
        "create_session",
        "add_message",
        "commit_session",
        "close",
    ]
    assert {call["thread_id"] for call in calls} != {event_loop_thread_id}
    assert len({call["thread_id"] for call in calls}) == 1
    assert calls[1]["payload"]["session_id"].startswith("veadk__")
    assert calls[2]["payload"]["peer_id"] == "alice"
    assert calls[2]["payload"]["content"] == "记住我喜欢短回答"


class _RecordingBackend(BaseLongTermMemoryBackend):
    saved_call: dict[str, Any] = Field(default_factory=dict)
    search_call: dict[str, Any] = Field(default_factory=dict)

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
        self.search_call = {
            "user_id": user_id,
            "query": query,
            "top_k": top_k,
            "kwargs": kwargs,
        }
        return [
            json.dumps(
                {
                    "author": "assistant",
                    "role": "model",
                    "parts": [{"text": "remembered"}],
                }
            )
        ]


class _RawOpenVikingResponseBackend(BaseLongTermMemoryBackend):
    def precheck_index_naming(self):
        pass

    def save_memory(self, user_id: str, event_strings: list[str], **kwargs) -> bool:
        return True

    def search_memory(
        self, user_id: str, query: str, top_k: int, **kwargs
    ) -> list[str]:
        return [
            json.dumps(
                {
                    "memories": [
                        {
                            "author": "user",
                            "content": {
                                "parts": [
                                    "{'text': \"'# 用户偏好记录\\n- Result: 成功记录用户偏好'\"}"
                                ],
                                "role": "user",
                            },
                            "custom_metadata": {"source": "openviking"},
                        }
                    ]
                },
                ensure_ascii=False,
            )
        ]


@pytest.mark.asyncio
async def test_long_term_memory_passes_session_and_app_to_backend():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app")
    session = Session(
        id="session_001",
        app_name="support_app",
        user_id="alice",
        state={},
        events=[
            Event(
                author="user",
                content=types.Content(
                    parts=[types.Part(text="记住我喜欢短回答")],
                    role="user",
                ),
            )
        ],
    )

    await memory.add_session_to_memory(session, source="manual")

    assert backend.saved_call["user_id"] == "alice"
    assert backend.saved_call["kwargs"] == {
        "session_id": "session_001",
        "app_name": "support_app",
        "source": "manual",
    }


@pytest.mark.asyncio
async def test_long_term_memory_does_not_pass_session_to_search_backend():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app", top_k=2)

    response = await memory.search_memory(
        app_name="support_app",
        user_id="alice",
        query="用户偏好",
    )

    assert response.memories[0].author == "assistant"
    assert response.memories[0].content.role == "model"
    assert response.memories[0].content.parts[0].text == "remembered"
    assert backend.search_call == {
        "user_id": "alice",
        "query": "用户偏好",
        "top_k": 2,
        "kwargs": {
            "app_name": "support_app",
        },
    }


def test_long_term_memory_parses_openviking_abstract_and_metadata():
    backend = _RecordingBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app", top_k=2)

    entries = memory._convert_memory_chunk_to_entries(
        json.dumps(
            {
                "context_type": "memory",
                "uri": "viking://user/default/peers/aa01/memories/entities/人物/用户A.md",
                "level": 2,
                "score": 0.40563082695007324,
                "category": "",
                "match_reason": "",
                "relations": [],
                "abstract": "# 用户A\n- 专属暗号：紫竹A001_manual_001",
                "overview": None,
            },
            ensure_ascii=False,
        )
    )

    assert len(entries) == 1
    assert (
        entries[0].id
        == "viking://user/default/peers/aa01/memories/entities/人物/用户A.md"
    )
    assert (
        entries[0].content.parts[0].text == "# 用户A\n- 专属暗号：紫竹A001_manual_001"
    )
    assert entries[0].custom_metadata == {
        "context_type": "memory",
        "uri": "viking://user/default/peers/aa01/memories/entities/人物/用户A.md",
        "level": 2,
        "score": 0.40563082695007324,
        "category": "",
        "match_reason": "",
        "relations": [],
        "overview": None,
    }


@pytest.mark.asyncio
async def test_long_term_memory_parses_raw_openviking_memory_response():
    backend = _RawOpenVikingResponseBackend(index="support_app")
    memory = LongTermMemory(backend=backend, app_name="support_app", top_k=2)

    response = await memory.search_memory(
        app_name="support_app",
        user_id="alice",
        query="用户偏好",
    )

    assert len(response.memories) == 1
    assert response.memories[0].author == "user"
    assert response.memories[0].content.role == "user"
    assert (
        response.memories[0].content.parts[0].text
        == "# 用户偏好记录\n- Result: 成功记录用户偏好"
    )
    assert response.memories[0].custom_metadata == {"source": "openviking"}
