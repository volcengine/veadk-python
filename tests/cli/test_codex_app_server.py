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

"""Tests for Studio's persistent Codex app-server client."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from veadk.cli.codex_app_server import (
    CodexAppServerError,
    CodexAppServerSession,
    CodexImportedMessage,
    CodexPermissionSettings,
    approval_decision_from_payload,
    permission_settings_from_payload,
    sandbox_service_url,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
        self.files: dict[str, str] = {}
        self.queue: asyncio.Queue[str | None] = asyncio.Queue()
        self.closed = False

    def __aiter__(self) -> AsyncIterator[str]:
        return self

    async def __anext__(self) -> str:
        value = await self.queue.get()
        if value is None:
            raise StopAsyncIteration
        return value

    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        self.messages.append(message)
        method = message.get("method")
        request_id = message.get("id")
        if method is None and request_id == "server-approval":
            await self._notification(
                "turn/completed",
                {"turn": {"id": "turn-approval", "status": "completed"}},
            )
            return
        if not isinstance(request_id, int):
            return
        if method == "wait":
            return
        result: dict[str, object]
        if method == "initialize":
            result = {}
        elif method == "thread/start" and "threadId" not in message.get("params", {}):
            result = {
                "thread": {"id": "thread-1", "turns": []},
                "cwd": "/workspace",
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandbox": {
                    "type": "workspaceWrite",
                    "networkAccess": False,
                },
            }
        elif method == "config/read":
            result = {
                "layers": [
                    {
                        "name": {"type": "user", "profile": None},
                        "version": "version-7",
                    }
                ]
            }
        elif method == "fs/readDirectory":
            result = {
                "entries": [
                    {"fileName": "zeta", "isDirectory": True},
                    {"fileName": "alpha", "isDirectory": True},
                    {"fileName": "notes.txt", "isDirectory": False},
                ]
            }
        elif method == "model/list":
            result = {
                "data": [
                    {
                        "model": "gpt-test",
                        "displayName": "GPT Test",
                        "description": "Test model",
                        "isDefault": True,
                    }
                ]
            }
        elif method == "skills/list":
            result = {
                "data": [
                    {
                        "cwd": "/workspace",
                        "skills": [
                            {
                                "name": "review",
                                "description": "Review code",
                                "path": "/private/skills/review/SKILL.md",
                                "enabled": True,
                            }
                        ],
                    }
                ]
            }
        elif method == "fs/writeFile":
            params = message.get("params")
            assert isinstance(params, dict)
            path = params.get("path")
            data = params.get("dataBase64")
            assert isinstance(path, str) and isinstance(data, str)
            self.files[path] = data
            result = {}
        elif method == "fs/readFile":
            params = message.get("params")
            assert isinstance(params, dict)
            path = params.get("path")
            assert isinstance(path, str)
            result = {"dataBase64": self.files.get(path, "")}
        elif method == "thread/list":
            result = {
                "data": [
                    {
                        "id": "thread-old",
                        "name": "Older work",
                        "preview": "hello",
                        "cwd": "/workspace",
                        "modelProvider": "openai",
                        "createdAt": 10,
                        "updatedAt": 20,
                        "status": {"type": "idle"},
                    }
                ]
            }
        elif method in {"thread/resume", "thread/fork"}:
            thread_id = (
                message["params"]["threadId"]
                if method == "thread/resume"
                else "thread-fork"
            )
            result = {
                "thread": {
                    "id": thread_id,
                    "cwd": "/workspace",
                },
                "cwd": "/workspace",
                "model": "gpt-test",
            }
        elif method == "thread/read":
            result = {
                "thread": {
                    "id": message["params"]["threadId"],
                    "cwd": "/workspace",
                    "turns": [
                        {
                            "startedAt": 20,
                            "items": [
                                {
                                    "id": "user-old",
                                    "type": "userMessage",
                                    "content": [
                                        {
                                            "type": "text",
                                            "text": "$review inspect this",
                                        },
                                        {"type": "skill", "name": "review"},
                                    ],
                                },
                                {
                                    "id": "assistant-old",
                                    "type": "agentMessage",
                                    "text": "Looks good.",
                                },
                            ],
                        }
                    ],
                },
                "cwd": "/workspace",
                "model": "gpt-test",
            }
        elif method == "turn/start":
            prompt = message["params"]["input"][0]["text"]
            turn_id = (
                "turn-approval"
                if prompt == "approve"
                else ("turn-2" if prompt == "tokens-2" else "turn-1")
            )
            result = {"turn": {"id": turn_id}}
        else:
            result = {}
        await self.queue.put(json.dumps({"id": request_id, "result": result}))
        if method == "turn/start":
            prompt = message["params"]["input"][0]["text"]
            if prompt == "approve":
                await self.queue.put(
                    json.dumps(
                        {
                            "id": "server-approval",
                            "method": "item/commandExecution/requestApproval",
                            "params": {
                                "threadId": "thread-1",
                                "turnId": "turn-approval",
                                "itemId": "command-approval",
                                "command": "git status",
                                "cwd": "/workspace",
                                "reason": "需要检查工作区",
                                "startedAtMs": 1_785_428_800_000,
                            },
                        }
                    )
                )
            else:
                if prompt == "reasoning-delta":
                    await self._notification(
                        "item/reasoning/summaryTextDelta",
                        {"itemId": "reasoning-1", "delta": "分"},
                    )
                    await self._notification(
                        "item/reasoning/textDelta",
                        {"itemId": "reasoning-1", "delta": "析"},
                    )
                    await self._notification(
                        "item/completed",
                        {
                            "item": {
                                "id": "reasoning-1",
                                "type": "reasoning",
                                "summary": ["分析"],
                                "status": "completed",
                            }
                        },
                    )
                await self._notification(
                    "item/agentMessage/delta",
                    {"itemId": "message-1", "delta": "完成"},
                )
                if prompt in {"tokens-1", "tokens-2"}:
                    total = 100 if prompt == "tokens-1" else 130
                    last = 10 if prompt == "tokens-1" else 30
                    await self._notification(
                        "thread/tokenUsage/updated",
                        {
                            "threadId": "thread-1",
                            "turnId": turn_id,
                            "tokenUsage": {
                                "total": {
                                    "totalTokens": total,
                                    "inputTokens": total - 4,
                                    "cachedInputTokens": 2,
                                    "outputTokens": 4,
                                    "reasoningOutputTokens": 1,
                                },
                                "last": {
                                    "totalTokens": last,
                                    "inputTokens": last - 4,
                                    "cachedInputTokens": 1,
                                    "outputTokens": 4,
                                    "reasoningOutputTokens": 1,
                                },
                                "modelContextWindow": 200_000,
                            },
                        },
                    )
                await self._notification(
                    "item/started",
                    {
                        "item": {
                            "id": "command-1",
                            "type": "commandExecution",
                            "command": "pwd",
                            "cwd": "/workspace",
                        }
                    },
                )
                await self._notification(
                    "item/completed",
                    {
                        "item": {
                            "id": "command-1",
                            "type": "commandExecution",
                            "command": "pwd",
                            "cwd": "/workspace",
                            "status": "completed",
                            "exitCode": 0,
                            "aggregatedOutput": "/workspace",
                        }
                    },
                )
                await self._notification(
                    "turn/completed",
                    {"turn": {"id": turn_id, "status": "completed"}},
                )

    async def _notification(self, method: str, params: dict[str, object]) -> None:
        await self.queue.put(json.dumps({"method": method, "params": params}))

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(None)


class _MissingRolloutWebSocket(_FakeWebSocket):
    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        if (
            message.get("method") == "thread/resume"
            and message.get("params", {}).get("threadId") == "thread-empty"
        ):
            self.messages.append(message)
            await self.queue.put(
                json.dumps(
                    {
                        "id": message["id"],
                        "error": {
                            "message": ("no rollout found for thread id thread-empty")
                        },
                    }
                )
            )
            return
        await super().send(raw)


class _DetailedErrorWebSocket(_FakeWebSocket):
    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        if message.get("method") == "rpc/error":
            self.messages.append(message)
            await self.queue.put(
                json.dumps(
                    {
                        "id": message["id"],
                        "error": {
                            "code": -32001,
                            "message": "quota exceeded",
                            "data": {
                                "reason": "quota_exceeded",
                                "retryAfter": 30,
                            },
                        },
                    }
                )
            )
            return
        await super().send(raw)


class _SendFailureWebSocket(_FakeWebSocket):
    async def send(self, raw: str) -> None:
        message = json.loads(raw)
        if message.get("method") == "model/list":
            raise ConnectionError("socket write failed: transport reset")
        await super().send(raw)


@pytest.mark.asyncio
async def test_permissions_persist_and_apply_to_every_turn() -> None:
    websocket = _FakeWebSocket()

    async def _factory(url: str) -> _FakeWebSocket:
        assert url == (
            "wss://sandbox.example/v1/codex/app-server/?Authorization=secret"
        )
        return websocket

    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=_factory,
    )
    await session.connect()
    settings = CodexPermissionSettings(
        approval_policy="never",
        approvals_reviewer="auto_review",
        sandbox_mode="read-only",
        network_access=True,
    )

    await session.update_permissions(settings)
    events = [event async for event in session.stream_turn("hello")]

    batch_write = next(
        message
        for message in websocket.messages
        if message.get("method") == "config/batchWrite"
    )
    assert batch_write["params"]["expectedVersion"] == "version-7"
    assert batch_write["params"]["reloadUserConfig"] is True
    edits = batch_write["params"]["edits"]
    assert {edit["keyPath"]: edit["value"] for edit in edits} == {
        "sandbox_mode": "read-only",
        "approval_policy": "never",
        "approvals_reviewer": "auto_review",
        "sandbox_workspace_write.network_access": True,
    }
    turn_start = next(
        message
        for message in websocket.messages
        if message.get("method") == "turn/start"
        and "threadId" in message.get("params", {})
    )
    assert turn_start["params"]["approvalPolicy"] == "never"
    assert turn_start["params"]["approvalsReviewer"] == "auto_review"
    assert turn_start["params"]["sandboxPolicy"] == {
        "type": "readOnly",
        "networkAccess": True,
    }
    assert [event.kind for event in events] == ["text", "tool", "tool"]
    assert session.workspace_locked is True
    with pytest.raises(CodexAppServerError, match="不能再修改"):
        await session.update_workspace("/other")
    await session.close()


@pytest.mark.asyncio
async def test_reasoning_deltas_stream_as_accumulated_thinking() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    events = [event async for event in session.stream_turn("reasoning-delta")]
    thinking = [event for event in events if event.kind == "thinking"]

    assert [event.text for event in thinking] == ["分", "分析", "分析"]
    assert [event.status for event in thinking] == ["running", "running", "done"]
    await session.close()


@pytest.mark.asyncio
async def test_workspace_directory_browsing_and_user_approval() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()
    assert await session.update_workspace("/workspace/project") == (
        "/workspace/project"
    )
    listing = await session.list_directories("/workspace")
    assert [entry.name for entry in listing.directories] == ["alpha", "zeta"]

    stream = session.stream_turn("approve")
    requested = await anext(stream)
    assert requested.approval is not None
    assert requested.approval.command == "git status"
    session.resolve_approval(requested.approval.id, "acceptForSession")
    resolved = await anext(stream)
    assert resolved.approval_resolved_id == requested.approval.id
    with pytest.raises(StopAsyncIteration):
        await anext(stream)
    response = next(
        message
        for message in websocket.messages
        if message.get("id") == "server-approval"
    )
    assert response["result"] == {"decision": "acceptForSession"}
    await session.close()


@pytest.mark.asyncio
async def test_clean_socket_close_rejects_pending_requests() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()
    pending = asyncio.create_task(session.request("wait"))
    await asyncio.sleep(0)

    await websocket.queue.put(None)

    with pytest.raises(CodexAppServerError, match="连接已断开"):
        await pending
    await session.close()


@pytest.mark.asyncio
async def test_send_failure_preserves_transport_error_as_cause() -> None:
    websocket = _SendFailureWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    with pytest.raises(CodexAppServerError, match="发送请求失败") as captured:
        await session.list_models()

    assert isinstance(captured.value.__cause__, ConnectionError)
    assert str(captured.value.__cause__) == "socket write failed: transport reset"
    await session.close()


@pytest.mark.asyncio
async def test_json_rpc_error_preserves_complete_payload() -> None:
    websocket = _DetailedErrorWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    with pytest.raises(CodexAppServerError) as captured:
        await session.request("rpc/error")

    detail = str(captured.value)
    assert '"code":-32001' in detail
    assert '"message":"quota exceeded"' in detail
    assert '"data":{"reason":"quota_exceeded","retryAfter":30}' in detail
    await session.close()


@pytest.mark.asyncio
async def test_models_skills_and_structured_skill_input_keep_paths_private() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    models = await session.list_models()
    skills = await session.list_skills()
    events = [
        event
        async for event in session.stream_turn(
            "$review inspect this",
            (skills[0].id,),
        )
    ]

    assert models[0].public_dict() == {
        "id": "gpt-test",
        "displayName": "GPT Test",
        "description": "Test model",
        "isDefault": True,
    }
    assert skills[0].public_dict() == {
        "id": skills[0].id,
        "name": "review",
        "description": "Review code",
    }
    assert "/private/skills" not in json.dumps(
        skills[0].public_dict(), ensure_ascii=False
    )
    turn_start = [
        message
        for message in websocket.messages
        if message.get("method") == "turn/start"
        and "threadId" in message.get("params", {})
    ][-1]
    assert turn_start["params"]["input"] == [
        {"type": "text", "text": "$review inspect this"},
        {
            "type": "skill",
            "name": "review",
            "path": "/private/skills/review/SKILL.md",
        },
    ]
    assert events[0].text == "完成"
    await session.close()


@pytest.mark.asyncio
async def test_token_usage_is_exact_per_turn_and_thread_total_is_retained() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    first = [event async for event in session.stream_turn("tokens-1")]
    second = [event async for event in session.stream_turn("tokens-2")]
    first_usage = next(event for event in first if event.kind == "usage")
    second_usage = next(event for event in second if event.kind == "usage")

    assert first_usage.usage is not None
    assert first_usage.usage.total_tokens == 10
    assert second_usage.usage is not None
    assert second_usage.usage.total_tokens == 30
    assert second_usage.thread_total is not None
    assert second_usage.thread_total.total_tokens == 130
    assert second_usage.model_context_window == 200_000
    assert session.thread_token_total == second_usage.thread_total
    await session.close()


@pytest.mark.asyncio
async def test_thread_commands_restore_sanitized_history() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    threads, cursor = await session.list_threads(search_term="older")
    snapshot = await session.resume_thread("thread-old")
    workspace_locked_after_resume = session.workspace_locked
    deleted_inactive = await session.delete_thread("thread-other")
    replacement = await session.delete_thread("thread-old")
    fork = await session.fork_thread()
    await session.compact_thread()

    assert cursor == ""
    assert threads[0].public_dict()["status"] == "idle"
    assert snapshot.thread.id == "thread-old"
    assert snapshot.workspace_locked is True
    assert workspace_locked_after_resume is True
    assert snapshot.messages[0].content == "inspect this"
    assert snapshot.messages[0].skill_names == ("review",)
    assert snapshot.messages[1].content == "Looks good."
    assert deleted_inactive is None
    assert replacement is not None
    assert replacement.thread.id == "thread-1"
    assert fork.thread.id == "thread-fork"
    list_request = next(
        message
        for message in websocket.messages
        if message.get("method") == "thread/list"
    )
    assert list_request["params"]["sourceKinds"] == [
        "appServer",
        "cli",
        "vscode",
    ]
    read_request = next(
        message
        for message in websocket.messages
        if message.get("method") == "thread/read"
    )
    assert read_request["params"] == {
        "threadId": "thread-old",
        "includeTurns": True,
    }
    assert [
        message["params"]["threadId"]
        for message in websocket.messages
        if message.get("method") == "thread/archive"
    ] == ["thread-other", "thread-old"]
    assert [
        message["params"]["threadId"]
        for message in websocket.messages
        if message.get("method") == "thread/unsubscribe"
    ] == ["thread-other", "thread-old"]
    second_archive_index = next(
        index
        for index, message in enumerate(websocket.messages)
        if message.get("method") == "thread/archive"
        and message["params"]["threadId"] == "thread-old"
    )
    replacement_index = min(
        index
        for index, message in enumerate(
            websocket.messages[second_archive_index + 1 :],
            second_archive_index + 1,
        )
        if message.get("method") == "thread/start"
    )
    assert second_archive_index < replacement_index
    assert any(
        message.get("method") == "thread/compact/start"
        for message in websocket.messages
    )
    await session.close()


@pytest.mark.asyncio
async def test_inject_history_uses_model_visible_items_without_starting_turn() -> None:
    websocket = _FakeWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()
    await session.update_workspace("/workspace/project")

    await session.inject_history(
        (
            CodexImportedMessage(role="user", content="修复登录超时"),
            CodexImportedMessage(role="assistant", content="已定位重试逻辑。"),
        )
    )
    snapshot = await session.read_thread("thread-1")

    inject_request = next(
        message
        for message in websocket.messages
        if message.get("method") == "thread/inject_items"
    )
    assert inject_request["params"] == {
        "threadId": "thread-1",
        "items": [
            {
                "type": "message",
                "role": "user",
                "content": [{"type": "input_text", "text": "修复登录超时"}],
            },
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "已定位重试逻辑。"}],
            },
        ],
    }
    assert not any(
        message.get("method") == "turn/start" for message in websocket.messages
    )
    assert [(message.role, message.content) for message in snapshot.messages[:2]] == [
        ("user", "修复登录超时"),
        ("assistant", "已定位重试逻辑。"),
    ]
    await session.close()


@pytest.mark.asyncio
async def test_delete_inactive_thread_without_rollout_is_idempotent() -> None:
    websocket = _MissingRolloutWebSocket()
    session = CodexAppServerSession(
        "https://sandbox.example?Authorization=secret",
        websocket_factory=lambda _url: _ready(websocket),
    )
    await session.connect()

    deleted = await session.delete_thread("thread-empty")

    assert deleted is None
    assert session.thread_id == "thread-1"
    assert not any(
        message.get("method") in {"thread/unsubscribe", "thread/archive"}
        and message.get("params", {}).get("threadId") == "thread-empty"
        for message in websocket.messages
    )
    await session.close()


async def _ready(value: _FakeWebSocket) -> _FakeWebSocket:
    return value


def test_public_payload_validation_and_private_url_building() -> None:
    assert (
        permission_settings_from_payload(
            {
                "approvalPolicy": "on-request",
                "approvalsReviewer": "user",
                "sandboxMode": "workspace-write",
                "networkAccess": False,
            }
        )
        == CodexPermissionSettings()
    )
    assert approval_decision_from_payload("decline") == "decline"
    with pytest.raises(ValueError):
        approval_decision_from_payload({"decision": "accept"})
    assert (
        sandbox_service_url(
            "https://sandbox.example/root?Authorization=secret",
            "/browser-ui",
        )
        == "https://sandbox.example/root/browser-ui?Authorization=secret"
    )
    assert sandbox_service_url(
        "https://sandbox.example?Authorization=secret&session_id=stale",
        "/v1/shell/ws",
        websocket=True,
        query={"session_id": "current"},
    ) == ("wss://sandbox.example/v1/shell/ws?Authorization=secret&session_id=current")


def test_app_server_client_stays_compatible_with_python_310() -> None:
    source = (Path(__file__).parents[2] / "veadk/cli/codex_app_server.py").read_text(
        encoding="utf-8"
    )

    assert "asyncio.timeout(" not in source
