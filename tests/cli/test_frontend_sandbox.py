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

"""Tests for Studio's reusable AgentKit Sandbox Sessions."""

from __future__ import annotations

import asyncio
import json
import time

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.frontend_sandbox import (
    AgentkitSandboxGateway,
    SandboxCloudSession,
    SandboxConfigurationError,
    SandboxConversationService,
    SandboxInvocationError,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    SandboxStreamEvent,
    STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH,
    mount_sandbox_routes,
)


class _FakeGateway:
    def __init__(self) -> None:
        self.created = 0
        self.tool_ids: list[str] = []
        self.display_names: list[str] = []
        self.deleted: list[SandboxCloudSession] = []
        self.thread_ids: list[str | None] = []
        self.sessions: dict[str, SandboxCloudSession] = {
            "remote-existing": SandboxCloudSession(
                tool_id="tool-studio",
                instance_id="remote-existing",
                user_session_id="existing-agent",
                endpoint="https://sandbox.example/existing?Authorization=secret",
                region="cn-beijing",
                status="Ready",
                created_at="2026-07-30T08:00:00Z",
                expire_at="2026-07-30T16:00:00Z",
                tool_type="CodeEnv",
            )
        }

    async def list_sessions(self, tool_id: str) -> list[SandboxCloudSession]:
        self.tool_ids.append(tool_id)
        return [
            session for session in self.sessions.values() if session.tool_id == tool_id
        ]

    async def get_session(self, tool_id: str, session_id: str) -> SandboxCloudSession:
        self.tool_ids.append(tool_id)
        session = self.sessions.get(session_id)
        if session is None or session.tool_id != tool_id:
            raise SandboxSessionNotFoundError("AgentKit Session 不存在或已过期。")
        return session

    async def create_session(
        self, tool_id: str, display_name: str = ""
    ) -> SandboxCloudSession:
        self.created += 1
        self.tool_ids.append(tool_id)
        self.display_names.append(display_name)
        session = SandboxCloudSession(
            tool_id=tool_id,
            instance_id=f"remote-{self.created}",
            user_session_id=f"user-{self.created}",
            endpoint="https://sandbox.example/path?Authorization=secret",
            region="cn-beijing",
            status="Ready",
            created_at="2026-07-30T09:00:00Z",
            expire_at="2026-07-30T17:00:00Z",
            tool_type="CodeEnv",
            display_name=display_name,
        )
        self.sessions[session.instance_id] = session
        return session

    async def delete_session(self, session: SandboxCloudSession) -> None:
        self.deleted.append(session)

    async def stream_codex(
        self,
        session: SandboxCloudSession,
        prompt: str,
        thread_id: str | None,
    ) -> AsyncIterator[SandboxStreamEvent]:
        del session
        self.thread_ids.append(thread_id)
        if thread_id is None:
            yield SandboxStreamEvent(thread_id="thread-1")
        yield SandboxStreamEvent(
            kind="thinking",
            item_id="reasoning-1",
            status="done",
            text="分析请求",
        )
        yield SandboxStreamEvent(
            kind="tool",
            item_id="command-1",
            status="done",
            name="运行命令",
            arguments={"command": "pwd"},
            response={"exitCode": 0, "output": "/home/gem"},
        )
        yield SandboxStreamEvent(kind="text", text=f"reply:{prompt}")

    async def drain(self) -> None:
        return None


def _app(gateway: _FakeGateway, tool_id: str | None = "tool-studio") -> FastAPI:
    app = FastAPI()
    service = SandboxConversationService(gateway, tool_id=tool_id)

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    mount_sandbox_routes(app, service, _owner)
    return app


def test_sandbox_routes_list_create_connect_and_disconnect() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        listed = client.get("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        create = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "  我的智能体  "},
        )

        assert create.status_code == 200
        assert create.json()["status"] == "Ready"
        assert "endpoint" not in create.json()
        assert "secret" not in create.text
        session_id = create.json()["sessionId"]
        not_connected = client.post(
            f"/web/sandbox/sessions/{session_id}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "not connected yet"},
        )
        connected = client.post(
            "/web/sandbox/sessions/remote-existing/connect",
            headers={"X-Test-User": "alice"},
        )

        first = client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "hello"},
        )
        second = client.post(
            "/web/sandbox/sessions/remote-existing/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "again"},
        )
        disconnected = client.delete(
            "/web/sandbox/sessions/remote-existing",
            headers={"X-Test-User": "alice"},
        )

    assert listed.status_code == 200
    assert listed.json() == {
        "sessions": [
            {
                "sessionId": "remote-existing",
                "userSessionId": "existing-agent",
                "status": "Ready",
                "createdAt": "2026-07-30T08:00:00Z",
                "expireAt": "2026-07-30T16:00:00Z",
                "toolType": "CodeEnv",
                "region": "cn-beijing",
                "displayName": "",
            }
        ]
    }
    assert create.json()["displayName"] == "我的智能体"
    assert gateway.display_names == ["我的智能体"]
    assert connected.status_code == 200
    assert connected.json()["sessionId"] == "remote-existing"
    assert "endpoint" not in connected.json()
    assert "secret" not in connected.text
    assert not_connected.status_code == 404
    assert first.status_code == 200
    assert "event: activity" in first.text
    assert '"kind": "thinking"' in first.text
    assert '"kind": "tool"' in first.text
    assert "event: delta" in first.text
    assert 'data: {"text": "reply:hello"}' in first.text
    assert "event: done" in first.text
    assert second.status_code == 200
    assert gateway.thread_ids == [None, "thread-1"]
    assert disconnected.json() == {"disconnected": True}
    assert gateway.deleted == []
    assert session_id == "remote-1"


def test_sandbox_create_rejects_invalid_display_names() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        too_long = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": "名" * (STUDIO_SANDBOX_DISPLAY_NAME_MAX_LENGTH + 1)},
        )
        wrong_type = client.post(
            "/web/sandbox/sessions",
            headers={"X-Test-User": "alice"},
            json={"displayName": 42},
        )

    assert too_long.status_code == 422
    assert "40" in too_long.text
    assert wrong_type.status_code == 422
    assert gateway.display_names == []


def test_sandbox_capabilities_report_configured_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SANDBOX_CHAT_CODEX", "configured-tool")
    with TestClient(_app(_FakeGateway(), tool_id=None)) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {"enabled": True, "reason": ""}


def test_sandbox_capabilities_report_admin_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    with TestClient(_app(_FakeGateway(), tool_id=None)) as client:
        response = client.get(
            "/web/sandbox/capabilities", headers={"X-Test-User": "alice"}
        )

    assert response.status_code == 200
    assert response.json() == {"enabled": False, "reason": "管理员未配置"}


@pytest.mark.asyncio
async def test_sandbox_start_requires_preconfigured_chat_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("SANDBOX_CHAT_CODEX", raising=False)
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway)

    with pytest.raises(SandboxConfigurationError, match="管理员未配置"):
        await service.create("alice")

    assert gateway.created == 0


def test_codex_parser_preserves_reasoning_and_tool_lifecycle() -> None:
    reasoning = AgentkitSandboxGateway._parse_codex_event(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "reasoning-1",
                    "type": "reasoning",
                    "text": "检查工作区",
                },
            }
        )
    )
    command_started = AgentkitSandboxGateway._parse_codex_event(
        json.dumps(
            {
                "type": "item.started",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": "pwd",
                },
            }
        )
    )
    command_completed = AgentkitSandboxGateway._parse_codex_event(
        json.dumps(
            {
                "type": "item.completed",
                "item": {
                    "id": "command-1",
                    "type": "command_execution",
                    "command": "pwd",
                    "status": "completed",
                    "exit_code": 0,
                    "aggregated_output": "/home/gem",
                },
            }
        )
    )

    assert reasoning == SandboxStreamEvent(
        kind="thinking",
        item_id="reasoning-1",
        status="done",
        text="检查工作区",
    )
    assert command_started == SandboxStreamEvent(
        kind="tool",
        item_id="command-1",
        status="running",
        name="运行命令",
        arguments={"command": "pwd"},
    )
    assert command_completed == SandboxStreamEvent(
        kind="tool",
        item_id="command-1",
        status="done",
        name="运行命令",
        arguments={"command": "pwd"},
        response={"status": "completed", "exitCode": 0, "output": "/home/gem"},
    )


def test_sandbox_route_hides_sessions_owned_by_another_user() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        session_id = created.json()["sessionId"]
        connected = client.post(
            f"/web/sandbox/sessions/{session_id}/connect",
            headers={"X-Test-User": "alice"},
        )
        response = client.delete(
            f"/web/sandbox/sessions/{session_id}",
            headers={"X-Test-User": "bob"},
        )

    assert connected.status_code == 200
    assert response.status_code == 404
    assert gateway.deleted == []


def test_sandbox_route_rejects_empty_message() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        response = client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "  "},
        )

    assert response.status_code == 422


def test_sandbox_route_requires_an_identity() -> None:
    with TestClient(_app(_FakeGateway())) as client:
        response = client.post("/web/sandbox/sessions")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_service_owner_check_does_not_reveal_session() -> None:
    service = SandboxConversationService(_FakeGateway(), tool_id="tool-studio")
    cloud = await service.create("alice")
    session = await service.connect(cloud.instance_id, "alice")

    with pytest.raises(SandboxSessionNotFoundError):
        await service.close(session.session_id, "bob")


@pytest.mark.asyncio
async def test_service_allows_multiple_sessions_for_the_same_owner() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")

    first, second = await asyncio.gather(
        service.create("alice"),
        service.create("alice"),
    )

    assert first.instance_id != second.instance_id
    assert gateway.created == 2


def test_terminal_completion_ignores_echoed_command_and_prompt_is_not_in_command() -> (
    None
):
    marker = "__VEADK_DONE_test__"
    command = AgentkitSandboxGateway._command(None, "__VEADK_INPUT_test__", marker)

    assert "private prompt" not in command
    assert AgentkitSandboxGateway._completion_status(command, marker) is None
    assert AgentkitSandboxGateway._completion_status(f"{marker}0\r", marker) == 0


@pytest.mark.asyncio
async def test_gateway_accepts_a_lazy_client_factory() -> None:
    class _Client:
        def list_tools(self, request: object) -> str:
            del request
            return "ok"

    calls = 0

    def _factory() -> _Client:
        nonlocal calls
        calls += 1
        return _Client()

    gateway = AgentkitSandboxGateway(_factory)

    assert await gateway._call("list_tools", object()) == "ok"
    assert calls == 1


@pytest.mark.asyncio
async def test_gateway_accepts_an_already_expired_session_as_deleted() -> None:
    class _Client:
        def delete_session(self, request: object) -> None:
            del request
            raise RuntimeError("InvalidResource.NotFound")

    gateway = AgentkitSandboxGateway(_Client())
    await gateway.delete_session(
        SandboxCloudSession(
            tool_id="tool-1",
            instance_id="expired-session",
            user_session_id="user-1",
            endpoint="https://sandbox.example",
        )
    )


@pytest.mark.asyncio
async def test_gateway_lists_all_sessions_from_the_configured_tool_region() -> None:
    calls: list[tuple[str, str | None]] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def list_sessions(self, request: object) -> SimpleNamespace:
            next_token = getattr(request, "next_token")
            calls.append((self.region, next_token))
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            if next_token is None:
                return SimpleNamespace(
                    session_infos=[
                        SimpleNamespace(
                            session_id="remote-old",
                            user_session_id="old-agent",
                            endpoint="https://sandbox.example/old?Authorization=secret",
                            status="Ready",
                            created_at="2026-07-29T08:00:00Z",
                            expire_at="2026-07-30T08:00:00Z",
                            tool_type="CodeEnv",
                        )
                    ],
                    next_token="page-2",
                )
            return SimpleNamespace(
                session_infos=[
                    SimpleNamespace(
                        session_id="remote-new",
                        user_session_id="new-agent",
                        endpoint="https://sandbox.example/new?Authorization=secret",
                        status="Ready",
                        created_at="2026-07-30T08:00:00Z",
                        expire_at="2026-07-31T08:00:00Z",
                        tool_type="CodeEnv",
                    )
                ],
                next_token=None,
            )

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    sessions = await gateway.list_sessions("tool-1")

    assert [session.instance_id for session in sessions] == [
        "remote-new",
        "remote-old",
    ]
    assert all(session.region == "cn-shanghai" for session in sessions)
    assert calls == [
        ("cn-beijing", None),
        ("cn-shanghai", None),
        ("cn-shanghai", "page-2"),
    ]


@pytest.mark.asyncio
async def test_gateway_uses_the_installed_agentkit_list_sessions_contract() -> None:
    from agentkit.sdk.tools import types as tools_types

    requests: list[dict[str, object]] = []

    class _Client:
        def list_sessions(
            self, request: tools_types.ListSessionsRequest
        ) -> tools_types.ListSessionsResponse:
            requests.append(request.model_dump(by_alias=True, exclude_none=True))
            return tools_types.ListSessionsResponse(
                SessionInfos=[
                    tools_types.SessionInfosForListSessions(
                        SessionId="remote-sdk",
                        UserSessionId="sdk-agent",
                        Status="Ready",
                        Endpoint=("https://sandbox.example/path?Authorization=secret"),
                        CreatedAt="2026-07-30T08:00:00Z",
                        ExpireAt="2026-07-30T16:00:00Z",
                        ToolType="CodeEnv",
                    )
                ]
            )

    sessions = await AgentkitSandboxGateway(_Client()).list_sessions("tool-sdk")

    assert requests == [{"MaxResults": 100, "ToolId": "tool-sdk"}]
    assert len(sessions) == 1
    assert sessions[0].instance_id == "remote-sdk"
    assert sessions[0].user_session_id == "sdk-agent"
    assert sessions[0].status == "Ready"
    assert sessions[0].created_at == "2026-07-30T08:00:00Z"
    assert sessions[0].expire_at == "2026-07-30T16:00:00Z"
    assert sessions[0].tool_type == "CodeEnv"


@pytest.mark.asyncio
async def test_gateway_gets_an_existing_session_without_exposing_its_region() -> None:
    calls: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def get_session(self, request: object) -> SimpleNamespace:
            del request
            calls.append(self.region)
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="agent-1",
                endpoint="https://sandbox.example/path?Authorization=secret",
                status="Ready",
                created_at="2026-07-30T08:00:00Z",
                expire_at="2026-07-31T08:00:00Z",
                tool_type="CodeEnv",
            )

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    session = await gateway.get_session("tool-1", "remote-1")

    assert session.instance_id == "remote-1"
    assert session.region == "cn-shanghai"
    assert calls == ["cn-beijing", "cn-shanghai"]


@pytest.mark.asyncio
async def test_gateway_retries_session_creation_in_shanghai_and_deletes_there() -> None:
    created_regions: list[str] = []
    deleted_regions: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def create_session(self, request: object) -> SimpleNamespace:
            del request
            created_regions.append(self.region)
            if self.region == "cn-beijing":
                raise RuntimeError("InvalidResource.NotFound")
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="user-1",
                endpoint="https://sandbox.example",
            )

        def delete_session(self, request: object) -> None:
            del request
            deleted_regions.append(self.region)

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    session = await gateway.create_session("tool-1")
    await gateway.delete_session(session)

    assert created_regions == ["cn-beijing", "cn-shanghai"]
    assert session.region == "cn-shanghai"
    assert deleted_regions == ["cn-shanghai"]


@pytest.mark.asyncio
async def test_gateway_accepts_create_response_while_session_is_starting() -> None:
    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                session_id="remote-creating",
                user_session_id="user-creating",
                endpoint=None,
            )

    session = await AgentkitSandboxGateway(_Client()).create_session("tool-1")

    assert session.instance_id == "remote-creating"
    assert session.status == "Creating"
    assert session.endpoint == ""


@pytest.mark.asyncio
async def test_gateway_does_not_retry_non_not_found_creation_errors() -> None:
    regions: list[str] = []

    class _Client:
        def __init__(self, region: str) -> None:
            self.region = region

        def create_session(self, request: object) -> None:
            del request
            regions.append(self.region)
            raise RuntimeError("AccessDenied")

    gateway = AgentkitSandboxGateway(
        _Client,
        region_candidates=("cn-beijing", "cn-shanghai"),
    )

    with pytest.raises(SandboxProvisioningError, match="AccessDenied"):
        await gateway.create_session("tool-1")

    assert regions == ["cn-beijing"]


@pytest.mark.asyncio
async def test_disconnect_never_deletes_the_cloud_session() -> None:
    class _FailDeleteGateway(_FakeGateway):
        async def delete_session(self, session: SandboxCloudSession) -> None:
            del session
            raise SandboxProvisioningError("delete failed")

    service = SandboxConversationService(_FailDeleteGateway(), tool_id="tool-studio")
    cloud = await service.create("alice")
    session = await service.connect(cloud.instance_id, "alice")

    await service.close(session.session_id, "alice")

    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(session.session_id, "alice")


@pytest.mark.asyncio
async def test_expiry_and_close_all_only_drop_local_connections() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway, tool_id="tool-studio")
    expired = await service.connect("remote-existing", "alice")
    expired.expires_at = time.monotonic() - 1

    await service.cleanup_expired()
    active = await service.connect("remote-existing", "bob")
    await service.close_all()

    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(expired.session_id, "alice")
    with pytest.raises(SandboxSessionNotFoundError):
        service.require_owned(active.session_id, "bob")
    assert gateway.deleted == []


def test_sse_error_has_an_explicit_done_frame() -> None:
    class _FailStreamGateway(_FakeGateway):
        async def stream_codex(
            self,
            session: SandboxCloudSession,
            prompt: str,
            thread_id: str | None,
        ) -> AsyncIterator[SandboxStreamEvent]:
            del session, prompt, thread_id
            raise SandboxInvocationError("failed")
            yield SandboxStreamEvent()

    with TestClient(_app(_FailStreamGateway())) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/connect",
            headers={"X-Test-User": "alice"},
        )
        response = client.post(
            f"/web/sandbox/sessions/{created.json()['sessionId']}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "hello"},
        )

    assert "event: error" in response.text
    assert 'event: done\ndata: {"reason": "failed"}' in response.text


@pytest.mark.asyncio
async def test_cancelled_create_is_deleted_after_sdk_call_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    deleted: list[str] = []
    created: list[object] = []

    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            created.append(request)
            time.sleep(0.05)
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="user-1",
                endpoint="https://sandbox.example?Authorization=secret",
            )

        def delete_session(self, request: object) -> None:
            deleted.append(str(getattr(request, "session_id")))

    gateway = AgentkitSandboxGateway(_Client())
    task = asyncio.create_task(gateway.create_session("tool-1"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await gateway.drain()

    assert deleted == ["remote-1"]
    assert len(created) == 1
    assert getattr(created[0], "tool_id") == "tool-1"
    assert getattr(created[0], "envs") is None
