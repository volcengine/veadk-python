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
    CodexPermissionSettings,
    approval_decision_from_payload,
    permission_settings_from_payload,
    sandbox_service_url,
)


class _FakeWebSocket:
    def __init__(self) -> None:
        self.messages: list[dict[str, object]] = []
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
        elif method == "turn/start":
            prompt = message["params"]["input"][0]["text"]
            turn_id = "turn-approval" if prompt == "approve" else "turn-1"
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
                await self._notification(
                    "item/agentMessage/delta",
                    {"itemId": "message-1", "delta": "完成"},
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
                    {"turn": {"id": "turn-1", "status": "completed"}},
                )

    async def _notification(self, method: str, params: dict[str, object]) -> None:
        await self.queue.put(json.dumps({"method": method, "params": params}))

    async def close(self) -> None:
        self.closed = True
        await self.queue.put(None)


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
