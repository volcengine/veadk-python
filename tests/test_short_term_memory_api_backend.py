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

import asyncio
import json

from google.adk.events.event import Event
from google.genai.types import Content, Part

from veadk.memory.short_term_memory import ShortTermMemory


def test_api_short_term_memory_backend(monkeypatch):
    calls = []

    def fake_ve_request(**kwargs):
        calls.append(kwargs)
        action = kwargs["action"]
        if action == "CreateSession":
            return {"Result": {"SessionId": kwargs["request_body"]["SessionId"]}}
        if action == "GetSession":
            get_session_calls = [
                call for call in calls if call["action"] == "GetSession"
            ]
            if len(get_session_calls) == 1:
                return {"Result": None}
            return {
                "Result": {
                    "Session": {
                        "SessionId": kwargs["request_body"]["SessionId"],
                        "AppName": "default_app",
                        "UserId": "user",
                        "Events": [
                            {
                                "id": "evt_1",
                                "invocation_id": "inv_1",
                                "timestamp": "2026-01-01T00:00:01Z",
                                "content": {
                                    "role": "user",
                                    "parts": [{"text": "hello"}],
                                },
                                "event_data": {
                                    "author": "user",
                                    "partial": False,
                                },
                            }
                        ],
                    }
                }
            }
        if action == "ListSessionIds":
            return {"Result": {"SessionIds": ["session"]}}
        return {"Result": {}}

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(
        backend="api",
        backend_configs={
            "api_session_config": {
                "account_id": "account",
                "service": "arkclaw_stg",
                "region": "cn-beijing",
                "version": "2026-03-01",
            }
        },
    )

    session = asyncio.run(
        memory.create_session(
            app_name="default_app", user_id="user", session_id="session"
        )
    )
    assert session
    assert session.id == "session"

    event = Event(
        id="evt_1",
        invocation_id="inv_1",
        author="user",
        content=Content(role="user", parts=[Part(text="hello")]),
    )
    asyncio.run(memory.session_service.append_event(session=session, event=event))

    loaded = asyncio.run(
        memory.session_service.get_session(
            app_name="default_app", user_id="user", session_id="session"
        )
    )
    assert loaded
    assert loaded.events[0].content.parts[0].text == "hello"  # type: ignore[union-attr]

    listed = asyncio.run(
        memory.session_service.list_sessions(app_name="default_app", user_id="user")
    )
    assert [item.id for item in listed.sessions] == ["session"]

    asyncio.run(
        memory.session_service.delete_session(
            app_name="default_app", user_id="user", session_id="session"
        )
    )

    actions = [call["action"] for call in calls]
    assert actions == [
        "GetSession",
        "CreateSession",
        "AppendEvent",
        "GetSession",
        "ListSessionIds",
        "DeleteSession",
    ]

    append_call = calls[2]
    assert append_call["host"] == "open.volcengineapi.com"
    assert append_call["scheme"] == "https"
    assert append_call["request_body"]["AccountId"] == "account"
    raw_event = json.loads(append_call["request_body"]["Event"])
    assert raw_event["id"] == "evt_1"
    assert raw_event["content"]["parts"][0]["text"] == "hello"
    assert raw_event["event_data"]["author"] == "user"


def test_api_short_term_memory_backend_defaults(monkeypatch):
    captured = {}

    def fake_ve_request(**kwargs):
        captured.update(kwargs)
        return {"Result": {"SessionIds": []}}

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    listed = asyncio.run(
        memory.session_service.list_sessions(app_name="default_app", user_id="user")
    )

    assert listed.sessions == []
    assert captured["service"] == "arkclaw"
    assert captured["region"] == "cn-beijing"
    assert captured["version"] == "2026-03-01"
    assert captured["host"] == "open.volcengineapi.com"
    assert captured["scheme"] == "https"
    assert "AccountId" not in captured["request_body"]


def test_api_get_session_empty_list_returns_none(monkeypatch):
    def fake_ve_request(**kwargs):
        return {"Result": {"Session": []}}

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="default_app", user_id="user", session_id="missing"
        )
    )

    assert session is None


def test_api_get_session_parses_remote_session_shape(monkeypatch):
    state = {
        "accountId": "2107625663",
        "sessionId": "session",
        "intent_plan_dispatched:32dbe438798044dea1e8e2c6c8112527": True,
    }

    def fake_ve_request(**kwargs):
        return {
            "Result": {
                "Session": {
                    "SessionId": "session",
                    "State": state,
                    "Events": [
                        {
                            "id": "evt_1",
                            "author": "planning_agent",
                            "actions": {
                                "state_delta": {},
                                "artifact_delta": {},
                                "requested_auth_configs": {},
                                "requested_tool_confirmations": {},
                            },
                            "content": {
                                "role": "model",
                                "parts": [
                                    {"text": "thinking", "thought": True},
                                    {"text": '{"task_list": []}'},
                                ],
                            },
                            "partial": False,
                            "timestamp": 1778742679.785006,
                            "finish_reason": "STOP",
                            "invocation_id": "inv_1",
                            "model_version": "doubao-seed-1-8-251228",
                            "usage_metadata": {
                                "total_token_count": 10,
                                "prompt_token_count": 5,
                                "candidates_token_count": 5,
                            },
                        }
                    ],
                }
            }
        }

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="default_app", user_id="user", session_id="session"
        )
    )

    assert session is not None
    assert session.state == state
    assert session.events[0].author == "planning_agent"
    assert session.events[0].content.parts[0].thought is True  # type: ignore[union-attr]
    assert session.events[0].content.parts[1].text == '{"task_list": []}'  # type: ignore[union-attr]


def test_api_parses_direct_session_api_responses(monkeypatch):
    calls = []

    def fake_ve_request(**kwargs):
        calls.append(kwargs)
        action = kwargs["action"]
        if action == "ListSessionIds":
            return [
                {
                    "id": "session",
                    "appName": "agent",
                    "userId": "user",
                    "state": {},
                    "events": [],
                    "lastUpdateTime": 1779795224.84444,
                }
            ]
        if action == "CreateSession":
            return {
                "id": "created",
                "appName": "superagent",
                "userId": "123456",
                "state": {},
                "events": [],
                "lastUpdateTime": 1779795370.47742,
            }
        if action == "GetSession":
            return {
                "id": "session",
                "appName": "agent",
                "userId": "user",
                "state": {},
                "events": [
                    {
                        "content": {
                            "parts": [{"text": "hello"}],
                            "role": "user",
                        },
                        "invocationId": "inv_1",
                        "author": "user",
                        "actions": {
                            "stateDelta": {},
                            "artifactDelta": {},
                            "requestedAuthConfigs": {},
                            "requestedToolConfirmations": {},
                        },
                        "id": "evt_1",
                        "timestamp": 1779795224.784519,
                    },
                    {
                        "modelVersion": "deepseek-v3-2-251201",
                        "content": {
                            "parts": [{"text": "hi"}],
                            "role": "model",
                        },
                        "partial": False,
                        "finishReason": "STOP",
                        "usageMetadata": {
                            "cachedContentTokenCount": 0,
                            "candidatesTokenCount": 12,
                            "promptTokenCount": 42,
                            "totalTokenCount": 54,
                        },
                        "invocationId": "inv_1",
                        "author": "hello_world",
                        "actions": {
                            "stateDelta": {},
                            "artifactDelta": {},
                            "requestedAuthConfigs": {},
                            "requestedToolConfirmations": {},
                        },
                        "id": "evt_2",
                        "timestamp": 1779795224.84444,
                    },
                ],
                "lastUpdateTime": 1779795224.84444,
            }
        return {}

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    listed = asyncio.run(
        memory.session_service.list_sessions(app_name="agent", user_id="user")
    )
    created = asyncio.run(
        memory.session_service.create_session(
            app_name="superagent", user_id="123456", session_id="created"
        )
    )
    loaded = asyncio.run(
        memory.session_service.get_session(
            app_name="agent", user_id="user", session_id="session"
        )
    )

    assert [session.id for session in listed.sessions] == ["session"]
    assert listed.sessions[0].app_name == "agent"
    assert listed.sessions[0].user_id == "user"
    assert listed.sessions[0].last_update_time == 1779795224.84444
    assert created.id == "created"
    assert created.app_name == "superagent"
    assert loaded is not None
    assert loaded.events[0].invocation_id == "inv_1"
    assert loaded.events[1].model_version == "deepseek-v3-2-251201"
    assert loaded.events[1].usage_metadata.total_token_count == 54  # type: ignore[union-attr]


def test_api_get_session_detail_not_found_returns_none(monkeypatch):
    def fake_ve_request(**kwargs):
        return {"detail": "Session not found"}

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="agent", user_id="user", session_id="missing"
        )
    )

    assert session is None


def test_api_get_session_response_metadata_not_found_returns_none(monkeypatch):
    def fake_ve_request(**kwargs):
        return {
            "ResponseMetadata": {
                "RequestId": "request",
                "Action": "GetSession",
                "Version": "2026-03-01",
                "Service": "arkclaw_stg",
                "Error": {
                    "HTTPCode": 404,
                    "Code": "ResourceNotFound.session",
                    "Message": "Session not found",
                    "Data": None,
                },
            }
        }

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="agent", user_id="user", session_id="missing"
        )
    )

    assert session is None


def test_api_get_session_normalizes_null_action_maps(monkeypatch):
    def fake_ve_request(**kwargs):
        return {
            "ResponseMetadata": {
                "RequestId": "request",
                "Action": "GetSession",
                "Version": "2026-03-01",
                "Service": "arkclaw_stg",
            },
            "Result": {
                "id": "session",
                "appName": "agent",
                "userId": "user",
                "state": {},
                "events": [
                    {
                        "content": {
                            "parts": [{"text": "hello"}],
                            "role": "user",
                        },
                        "invocationId": "inv_1",
                        "author": "user",
                        "actions": {
                            "stateDelta": None,
                            "artifactDelta": None,
                            "requestedAuthConfigs": None,
                            "requestedToolConfirmations": None,
                        },
                        "id": "evt_1",
                        "timestamp": 1779795224.784519,
                    }
                ],
                "lastUpdateTime": 1779795224.84444,
            },
        }

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")
    monkeypatch.setattr(
        "veadk.memory.short_term_memory_backends.api_backend.ve_request",
        fake_ve_request,
    )

    memory = ShortTermMemory(backend="api")
    session = asyncio.run(
        memory.session_service.get_session(
            app_name="agent", user_id="user", session_id="session"
        )
    )

    assert session is not None
    assert session.events[0].actions.state_delta == {}
    assert session.events[0].actions.artifact_delta == {}
    assert session.events[0].actions.requested_auth_configs == {}
    assert session.events[0].actions.requested_tool_confirmations == {}
