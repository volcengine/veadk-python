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

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
import requests
from a2a.types import Message, Task, TaskState, TaskStatus
from google.adk.events import Event

from veadk.a2a.agentkit_remote_skill_agent import (
    _AGENTKIT_SESSION_ID_METADATA_KEY,
    _SessionBoundRemoteSkillAgent,
    AgentkitRemoteSkillAgent,
)
from veadk.tools.builtin_tools._agentkit import AgentKitSessionLease


def _lease(session_id: str, endpoint: str) -> AgentKitSessionLease:
    return AgentKitSessionLease(
        tool_id="tool-1",
        logical_user_session_id="skills_user_session",
        user_session_id="skills_user_session",
        session_id=session_id,
        status="Ready",
        endpoint=endpoint,
        internal_endpoint="",
        created_at="2026-08-24T01:00:00+00:00",
        expire_at="2026-08-24T02:00:00+00:00",
    )


def _agent_card() -> dict:
    return {
        "name": "skill-sandbox",
        "description": "Skill sandbox",
        "url": "http://127.0.0.1:8000/a2a",
        "version": "1.0.0",
        "capabilities": {},
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": [],
    }


def _response(
    status_code: int,
    *,
    json_body: object | None = None,
    body: bytes = b"",
    content_type: str = "application/json",
) -> requests.Response:
    response = requests.Response()
    response.status_code = status_code
    response.headers["Content-Type"] = content_type
    response._content = (
        json.dumps(json_body).encode("utf-8") if json_body is not None else body
    )
    return response


def test_constructor_does_not_resolve_agentkit_session() -> None:
    with patch(
        "veadk.a2a.agentkit_remote_skill_agent.ensure_agentkit_session_lease"
    ) as ensure:
        AgentkitRemoteSkillAgent(name="skills", tool_id="tool-1")

    ensure.assert_not_called()


def test_resolve_lease_uses_adk_session_as_logical_key() -> None:
    captured = {}
    expected = _lease("session-1", "https://sandbox.test")

    def fake_ensure(**kwargs):
        captured.update(kwargs)
        return expected

    ctx = SimpleNamespace(
        user_id="user-1",
        session=SimpleNamespace(id="adk-session-1", state={"key": "value"}),
    )
    agent = AgentkitRemoteSkillAgent(
        name="skills",
        tool_id="tool-1",
        request_timeout=900,
        expiry_buffer=90,
    )

    with patch(
        "veadk.a2a.agentkit_remote_skill_agent.ensure_agentkit_session_lease",
        side_effect=fake_ensure,
    ):
        result = asyncio.run(agent._resolve_lease(ctx))  # type: ignore[arg-type]

    assert result is expected
    assert captured["tool_user_session_id"] == "skills_user-1_adk-session-1"
    assert captured["min_remaining_seconds"] == 990
    assert captured["tool_state"] == {"key": "value"}


def test_delegate_is_rebuilt_when_physical_session_changes() -> None:
    created = []

    class FakeDelegate:
        def __init__(self, **kwargs):
            created.append(kwargs)
            self._httpx_client = SimpleNamespace(headers={})

        async def cleanup(self):
            return None

    ctx = SimpleNamespace(credential_service=None)
    agent = AgentkitRemoteSkillAgent(name="skills", tool_id="tool-1")
    first = _lease(
        "session-1",
        "https://sandbox.test/?faasInstanceName=first",
    )
    second = _lease(
        "session-2",
        "https://sandbox.test/?faasInstanceName=second",
    )

    async def run():
        with (
            patch(
                "veadk.a2a.agentkit_remote_skill_agent._SessionBoundRemoteSkillAgent",
                FakeDelegate,
            ),
            patch.object(
                agent,
                "_wait_for_agent_card",
                new=AsyncMock(),
            ) as wait_for_agent_card,
        ):
            first_delegate = await agent._delegate_for(first, ctx)  # type: ignore[arg-type]
            reused_delegate = await agent._delegate_for(first, ctx)  # type: ignore[arg-type]
            second_delegate = await agent._delegate_for(second, ctx)  # type: ignore[arg-type]
        return first_delegate, reused_delegate, second_delegate, wait_for_agent_card

    first_delegate, reused_delegate, second_delegate, wait_for_agent_card = asyncio.run(
        run()
    )

    assert first_delegate is reused_delegate
    assert second_delegate is not first_delegate
    assert len(created) == 2
    assert created[0]["rpc_url"] == ("https://sandbox.test/a2a?faasInstanceName=first")
    assert created[1]["rpc_url"] == ("https://sandbox.test/a2a?faasInstanceName=second")
    assert wait_for_agent_card.await_count == 2


def test_wait_for_agent_card_retries_502_and_preserves_endpoint_query() -> None:
    agent = AgentkitRemoteSkillAgent(
        name="skills",
        tool_id="tool-1",
        a2a_ready_timeout=10,
        a2a_ready_poll_interval=0.01,
    )
    responses = [
        _response(502, body=b"bad gateway", content_type="text/html"),
        _response(200, json_body=_agent_card()),
    ]

    async def run() -> None:
        with (
            patch(
                "veadk.a2a.agentkit_remote_skill_agent.requests.get",
                side_effect=responses,
            ) as get,
            patch(
                "veadk.a2a.agentkit_remote_skill_agent.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await agent._wait_for_agent_card(
                endpoint="https://sandbox.test/?faasInstanceName=instance-1",
                headers={"inbound_auth": "token"},
            )

        assert get.call_count == 2
        assert get.call_args_list[0].args[0] == (
            "https://sandbox.test/.well-known/agent-card.json"
            "?faasInstanceName=instance-1"
        )
        assert get.call_args_list[0].kwargs["headers"] == {"inbound_auth": "token"}
        sleep.assert_awaited_once()

    asyncio.run(run())


def test_wait_for_agent_card_retries_non_json_response() -> None:
    agent = AgentkitRemoteSkillAgent(
        name="skills",
        tool_id="tool-1",
        a2a_ready_timeout=10,
        a2a_ready_poll_interval=0.01,
    )

    async def run() -> None:
        with (
            patch(
                "veadk.a2a.agentkit_remote_skill_agent.requests.get",
                side_effect=[
                    _response(200, body=b"starting", content_type="text/plain"),
                    _response(200, json_body=_agent_card()),
                ],
            ),
            patch(
                "veadk.a2a.agentkit_remote_skill_agent.asyncio.sleep",
                new=AsyncMock(),
            ) as sleep,
        ):
            await agent._wait_for_agent_card(
                endpoint="https://sandbox.test",
                headers={},
            )

        sleep.assert_awaited_once()

    asyncio.run(run())


def test_wait_for_agent_card_fails_fast_for_404() -> None:
    agent = AgentkitRemoteSkillAgent(
        name="skills",
        tool_id="tool-1",
        a2a_ready_timeout=10,
    )

    async def run() -> None:
        with patch(
            "veadk.a2a.agentkit_remote_skill_agent.requests.get",
            return_value=_response(404, body=b"not found", content_type="text/plain"),
        ) as get:
            with pytest.raises(RuntimeError, match=r"HTTP 404"):
                await agent._wait_for_agent_card(
                    endpoint="https://sandbox.test",
                    headers={},
                )
        get.assert_called_once()

    asyncio.run(run())


def test_wait_for_agent_card_timeout_reports_redacted_response_summary() -> None:
    agent = AgentkitRemoteSkillAgent(
        name="skills",
        tool_id="tool-1",
        a2a_ready_timeout=5,
    )

    async def run() -> None:
        with (
            patch(
                "veadk.a2a.agentkit_remote_skill_agent.requests.get",
                return_value=_response(
                    503,
                    body=b"temporarily unavailable",
                    content_type="text/plain",
                ),
            ),
            patch(
                "veadk.a2a.agentkit_remote_skill_agent._monotonic",
                side_effect=[0, 0, 6],
            ),
        ):
            with pytest.raises(
                TimeoutError,
                match=(
                    r"HTTP 503, content-type=text/plain, "
                    r"body-bytes=23"
                ),
            ):
                await agent._wait_for_agent_card(
                    endpoint="https://sandbox.test/?Authorization=secret",
                    headers={},
                )

    asyncio.run(run())


def test_session_bound_delegate_rejects_stale_a2a_context() -> None:
    response = SimpleNamespace(json=lambda: _agent_card())
    with patch("veadk.a2a.remote_ve_agent.requests.get", return_value=response):
        delegate = _SessionBoundRemoteSkillAgent(
            agentkit_session_id="session-current",
            poll_interval=2,
            max_poll_interval=16,
            name="skills",
            url="https://sandbox.test",
            rpc_url="https://sandbox.test/a2a",
        )

    current = Event(
        author="skills",
        custom_metadata={
            "a2a:response": True,
            _AGENTKIT_SESSION_ID_METADATA_KEY: "session-current",
        },
    )
    stale = Event(
        author="skills",
        custom_metadata={
            "a2a:response": True,
            _AGENTKIT_SESSION_ID_METADATA_KEY: "session-old",
        },
    )

    assert delegate._is_remote_response(current)
    assert not delegate._is_remote_response(stale)
    asyncio.run(delegate.cleanup())


def test_session_bound_delegate_polls_non_blocking_task_to_completion() -> None:
    response = SimpleNamespace(json=lambda: _agent_card())
    working = Task(
        id="task-1",
        contextId="context-1",
        status=TaskStatus(state=TaskState.working),
    )
    completed = Task(
        id="task-1",
        contextId="context-1",
        status=TaskStatus(state=TaskState.completed),
    )

    async def run():
        with patch("veadk.a2a.remote_ve_agent.requests.get", return_value=response):
            delegate = _SessionBoundRemoteSkillAgent(
                agentkit_session_id="session-current",
                poll_interval=2,
                max_poll_interval=16,
                name="skills",
                url="https://sandbox.test",
                rpc_url="https://sandbox.test/a2a",
            )
        await delegate._ensure_resolved()
        client = delegate._a2a_client
        client._transport.send_message = AsyncMock(return_value=working)
        client.get_task = AsyncMock(return_value=completed)
        delegate._configure_polling_client()

        with patch(
            "veadk.a2a.agentkit_remote_skill_agent.asyncio.sleep",
            new=AsyncMock(),
        ):
            results = [
                item
                async for item in client.send_message(
                    request=Message(
                        messageId="message-1",
                        role="user",
                        parts=[{"kind": "text", "text": "run skill"}],
                    ),
                    request_metadata={"user_id": "user-1"},
                )
            ]
        await delegate.cleanup()
        return client, results

    client, results = asyncio.run(run())

    assert client._config.polling is True
    assert results == [(completed, None)]
    send_params = client._transport.send_message.await_args.args[0]
    assert send_params.configuration.blocking is False
    assert send_params.metadata == {"user_id": "user-1"}
    client.get_task.assert_awaited_once()
    query = client.get_task.await_args.args[0]
    assert query.id == "task-1"
    assert query.history_length == 20


def test_run_tags_events_with_physical_agentkit_session() -> None:
    lease = _lease("session-1", "https://sandbox.test")

    class FakeDelegate:
        async def _run_async_impl(self, _ctx):
            yield Event(author="skills")

    async def fake_resolve(self, _ctx):
        return lease

    async def fake_delegate(self, _lease, _ctx):
        return FakeDelegate()

    agent = AgentkitRemoteSkillAgent(name="skills", tool_id="tool-1")
    ctx = SimpleNamespace(invocation_id="invocation-1", branch=None)

    async def run():
        with (
            patch.object(AgentkitRemoteSkillAgent, "_resolve_lease", fake_resolve),
            patch.object(AgentkitRemoteSkillAgent, "_delegate_for", fake_delegate),
        ):
            return [
                event
                async for event in agent._run_async_impl(ctx)  # type: ignore[arg-type]
            ]

    events = asyncio.run(run())

    assert events[0].custom_metadata == {_AGENTKIT_SESSION_ID_METADATA_KEY: "session-1"}
