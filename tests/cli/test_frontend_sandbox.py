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

"""Tests for Studio's temporary AgentKit Sandbox conversations."""

from __future__ import annotations

import asyncio
import time

from collections.abc import AsyncIterator
from types import SimpleNamespace

import pytest

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.cli.frontend_sandbox import (
    AgentkitSandboxGateway,
    SandboxCloudSession,
    SandboxConversationService,
    SandboxInvocationError,
    SandboxProvisioningError,
    SandboxSessionNotFoundError,
    SandboxStreamEvent,
    mount_sandbox_routes,
)


class _FakeGateway:
    def __init__(self) -> None:
        self.created = 0
        self.deleted: list[SandboxCloudSession] = []
        self.thread_ids: list[str | None] = []

    async def ensure_studio_tool(self) -> str:
        return "tool-studio"

    async def create_session(self, tool_id: str) -> SandboxCloudSession:
        self.created += 1
        return SandboxCloudSession(
            tool_id=tool_id,
            instance_id=f"remote-{self.created}",
            user_session_id=f"user-{self.created}",
            endpoint="https://sandbox.example/path?Authorization=secret",
        )

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
        yield SandboxStreamEvent(text=f"reply:{prompt}")

    async def drain(self) -> None:
        return None


def _app(gateway: _FakeGateway) -> FastAPI:
    app = FastAPI()
    service = SandboxConversationService(gateway)

    def _owner(request: Request) -> str:
        owner = request.headers.get("X-Test-User", "")
        if not owner:
            raise HTTPException(status_code=401, detail="identity required")
        return owner

    mount_sandbox_routes(app, service, _owner)
    return app


def test_sandbox_routes_start_stream_and_delete_without_exposing_endpoint() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        create = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})

        assert create.status_code == 200
        assert create.json()["status"] == "ready"
        assert "endpoint" not in create.json()
        assert "secret" not in create.text
        session_id = create.json()["sessionId"]

        first = client.post(
            f"/web/sandbox/sessions/{session_id}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "hello"},
        )
        second = client.post(
            f"/web/sandbox/sessions/{session_id}/messages",
            headers={"X-Test-User": "alice"},
            json={"message": "again"},
        )
        deleted = client.delete(
            f"/web/sandbox/sessions/{session_id}",
            headers={"X-Test-User": "alice"},
        )

    assert first.status_code == 200
    assert "event: delta" in first.text
    assert 'data: {"text": "reply:hello"}' in first.text
    assert "event: done" in first.text
    assert second.status_code == 200
    assert gateway.thread_ids == [None, "thread-1"]
    assert deleted.json() == {"deleted": True}
    assert [item.instance_id for item in gateway.deleted] == ["remote-1"]


def test_sandbox_route_hides_sessions_owned_by_another_user() -> None:
    gateway = _FakeGateway()
    with TestClient(_app(gateway)) as client:
        created = client.post("/web/sandbox/sessions", headers={"X-Test-User": "alice"})
        session_id = created.json()["sessionId"]
        response = client.delete(
            f"/web/sandbox/sessions/{session_id}",
            headers={"X-Test-User": "bob"},
        )

    assert response.status_code == 404
    assert [item.instance_id for item in gateway.deleted] == ["remote-1"]


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
    service = SandboxConversationService(_FakeGateway())
    session = await service.start("alice")

    with pytest.raises(SandboxSessionNotFoundError):
        await service.close(session.session_id, "bob")


@pytest.mark.asyncio
async def test_service_allows_multiple_sessions_for_the_same_owner() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway)

    first, second = await asyncio.gather(
        service.start("alice"),
        service.start("alice"),
    )

    assert first.session_id != second.session_id
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
async def test_delete_failure_keeps_session_for_cleanup_retry() -> None:
    class _FailDeleteGateway(_FakeGateway):
        async def delete_session(self, session: SandboxCloudSession) -> None:
            del session
            raise SandboxProvisioningError("delete failed")

    service = SandboxConversationService(_FailDeleteGateway())
    session = await service.start("alice")

    with pytest.raises(SandboxProvisioningError):
        await service.close(session.session_id, "alice")

    service.require_owned(session.session_id, "alice")


@pytest.mark.asyncio
async def test_expiry_and_close_all_delete_cloud_sessions() -> None:
    gateway = _FakeGateway()
    service = SandboxConversationService(gateway)
    expired = await service.start("alice")
    expired.expires_at = time.monotonic() - 1

    await service.cleanup_expired()
    active = await service.start("bob")
    await service.close_all()

    assert [item.instance_id for item in gateway.deleted] == [
        expired.cloud.instance_id,
        active.cloud.instance_id,
    ]


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

    class _Client:
        def create_session(self, request: object) -> SimpleNamespace:
            del request
            time.sleep(0.05)
            return SimpleNamespace(
                session_id="remote-1",
                user_session_id="user-1",
                endpoint="https://sandbox.example?Authorization=secret",
            )

        def delete_session(self, request: object) -> None:
            deleted.append(str(getattr(request, "session_id")))

    gateway = AgentkitSandboxGateway(_Client())
    monkeypatch.setattr(gateway, "_session_envs", lambda: [])
    task = asyncio.create_task(gateway.create_session("tool-1"))
    await asyncio.sleep(0)
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task
    await gateway.drain()

    assert deleted == ["remote-1"]
