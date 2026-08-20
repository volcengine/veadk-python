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

import httpx
import pytest

from frontend.service.studio_scheduler.models import (
    ExecutionRequest,
    RuntimeInvocationError,
    RuntimeTarget,
)
from frontend.service.studio_scheduler.runtime_provider import (
    AgentKitRuntimeConnectionResolver,
    AgentKitRuntimeProvider,
    RuntimeConnection,
    ServiceCredentials,
)


def _request() -> ExecutionRequest:
    return ExecutionRequest(
        run_id="run-1",
        session_id="run-1",
        user_id="user@example.com",
        job_id="job-1",
        prompt="hello",
        runtime=RuntimeTarget(
            provider="volcengine",
            runtime_id="runtime-1",
            agent_name="agent one",
            region="cn-beijing",
        ),
        timeout_seconds=60,
    )


class _Resolver:
    async def resolve(self, target: RuntimeTarget) -> RuntimeConnection:
        return RuntimeConnection("https://runtime.example", "secret-key", "17")


class _Control:
    def __init__(self, *, cancel_after: int = 10_000) -> None:
        self.calls = 0
        self.cancel_after = cancel_after

    async def is_cancel_requested(self) -> bool:
        self.calls += 1
        return self.calls >= self.cancel_after


@pytest.mark.asyncio
async def test_provider_creates_an_independent_session_and_reads_final_sse_text() -> (
    None
):
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == "Bearer secret-key"
        if request.url.path.endswith("/sessions"):
            assert request.url.raw_path == (
                b"/apps/agent%20one/users/user%40example.com/sessions"
            )
            return httpx.Response(200, json={"id": "remote-session"})
        payload = json.loads(request.content)
        assert payload["session_id"] == "remote-session"
        assert payload["new_message"]["parts"] == [{"text": "hello"}]
        return httpx.Response(
            200,
            text=(
                'data: {"partial":true,"content":{"parts":[{"text":"hel"}]}}\n\n'
                'data: {"content":{"parts":[{"text":"hello world"}]}}\n\n'
                "data: [DONE]\n\n"
            ),
            headers={"content-type": "text/event-stream"},
        )

    provider = AgentKitRuntimeProvider(
        "volcengine",
        _Resolver(),
        transport=httpx.MockTransport(handler),
        cancel_poll_seconds=0.01,
    )

    result = await provider.execute(_request(), _Control())

    assert result.output == "hello world"
    assert result.session_id == "remote-session"
    assert result.runtime_version == "17"
    assert [request.url.path for request in requests][-1] == "/run_sse"


@pytest.mark.asyncio
async def test_gateway_failure_before_runtime_ack_is_retryable() -> None:
    provider = AgentKitRuntimeProvider(
        "volcengine",
        _Resolver(),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(503, text="unavailable")
        ),
    )

    with pytest.raises(RuntimeInvocationError) as caught:
        await provider.execute(_request(), _Control())

    assert caught.value.acknowledged is False
    assert caught.value.retryable is True
    assert "HTTP 503" in str(caught.value)
    assert "unavailable" in str(caught.value)


@pytest.mark.asyncio
async def test_runtime_json_error_is_diagnostic_and_redacted() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/sessions")
        return httpx.Response(
            500,
            json={
                "detail": (
                    "model boot failed; api_key=runtime-secret; "
                    "Authorization: Bearer remote-token"
                )
            },
        )

    provider = AgentKitRuntimeProvider(
        "volcengine",
        _Resolver(),
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(RuntimeInvocationError) as caught:
        await provider.execute(_request(), _Control())

    message = str(caught.value)
    assert "Runtime create session returned HTTP 500" in message
    assert "model boot failed" in message
    assert "runtime-secret" not in message
    assert "remote-token" not in message
    assert "[REDACTED]" in message
    assert "Runtime logs" in message
    assert caught.value.acknowledged is False
    assert caught.value.retryable is False


@pytest.mark.asyncio
async def test_runtime_non_json_error_reports_content_type_and_limits_body() -> None:
    provider = AgentKitRuntimeProvider(
        "volcengine",
        _Resolver(),
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                502,
                text="gateway failure " + ("x" * 10_000),
                headers={"content-type": "text/plain; charset=utf-8"},
            )
        ),
    )

    with pytest.raises(RuntimeInvocationError) as caught:
        await provider.execute(_request(), _Control())

    message = str(caught.value)
    assert "Content-Type: text/plain" in message
    assert "gateway failure" in message
    assert len(message) < 5_000


class _SlowStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.closed = False

    async def __aiter__(self):
        await asyncio.sleep(60)
        yield b"data: [DONE]\n\n"

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_cancel_is_polled_while_waiting_for_sse_and_closes_the_stream() -> None:
    stream = _SlowStream()

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/sessions"):
            return httpx.Response(200, json={"id": "remote-session"})
        return httpx.Response(
            200,
            stream=stream,
            headers={"content-type": "text/event-stream"},
        )

    provider = AgentKitRuntimeProvider(
        "volcengine",
        _Resolver(),
        transport=httpx.MockTransport(handler),
        cancel_poll_seconds=0.01,
    )

    with pytest.raises(RuntimeInvocationError) as caught:
        await provider.execute(_request(), _Control(cancel_after=2))

    assert caught.value.acknowledged is True
    assert caught.value.retryable is False
    assert stream.closed is True


@pytest.mark.asyncio
async def test_control_plane_resolver_uses_service_identity_and_current_version() -> (
    None
):
    seen: list[tuple[RuntimeTarget, ServiceCredentials]] = []
    runtime = SimpleNamespace(
        network_configurations=[
            SimpleNamespace(endpoint="https://private.example", network_type="private"),
            SimpleNamespace(endpoint="https://public.example", network_type="public"),
        ],
        authorizer_configuration=SimpleNamespace(
            key_auth=SimpleNamespace(api_key="runtime-key")
        ),
        current_version_number=23,
    )

    def load(target: RuntimeTarget, credentials: ServiceCredentials):
        seen.append((target, credentials))
        return runtime

    credentials = ServiceCredentials("ak", "sk", "token")
    resolver = AgentKitRuntimeConnectionResolver(
        credentials_resolver=lambda _provider: credentials,
        runtime_loader=load,
    )

    result = await resolver.resolve(_request().runtime)

    assert result == RuntimeConnection(
        endpoint="https://public.example",
        api_key="runtime-key",
        runtime_version="23",
    )
    assert seen == [(_request().runtime, credentials)]
