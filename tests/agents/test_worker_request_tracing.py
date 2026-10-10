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


"""验证真实 HTTPX 请求携带当前 Span，并保留重试及异常边界。"""

import asyncio

import httpx
import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from veadk.agents._remote_sandbox.codex_worker_client import (
    CodexWorkerClient,
    CodexWorkerError,
)


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "retry", "failure", "cancel"])
async def test_worker_request_propagation_and_redaction(monkeypatch, outcome):
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(trace, "get_tracer", provider.get_tracer)
    requests = []

    async def respond(request):
        requests.append(request)
        if outcome == "cancel":
            raise asyncio.CancelledError("secret")
        if outcome == "retry" and len(requests) == 1:
            return httpx.Response(503)
        if outcome == "failure":
            return httpx.Response(400)
        return httpx.Response(200, json={"status": "running"})

    client = CodexWorkerClient(
        "https://worker.invalid?signature=secret", api_key="secret"
    )
    client._http = httpx.AsyncClient(
        transport=httpx.MockTransport(respond), headers=client._headers
    )
    try:
        with provider.get_tracer("test").start_as_current_span("agent") as parent:
            if outcome == "cancel":
                with pytest.raises(asyncio.CancelledError):
                    await client.start_turn(
                        "private-session", "secret task", "same-key"
                    )
            elif outcome == "failure":
                with pytest.raises(CodexWorkerError):
                    await client.start_turn(
                        "private-session", "secret task", "same-key"
                    )
            else:
                assert (
                    await client.start_turn(
                        "private-session", "secret task", "same-key"
                    )
                )["status"] == "running"
        span = next(
            s for s in exporter.get_finished_spans() if s.name == "worker.turn.start"
        )
        assert span.parent.span_id == parent.get_span_context().span_id
        for request in requests:
            parts = request.headers["traceparent"].split("-")
            assert parts[1] == f"{span.context.trace_id:032x}"
            assert parts[2] == f"{span.context.span_id:016x}"
            assert request.headers["idempotency-key"] == "same-key"
            assert request.headers["x-api-key"] == "secret"
            assert "baggage" not in request.headers
        assert "secret" not in span.to_json()
        assert "private-session" not in span.to_json()
        if outcome in {"failure", "cancel"}:
            assert span.status.status_code.name == "ERROR"
            assert "error.type" in span.attributes
        if outcome == "retry":
            assert len(requests) == 2
            assert len(span.events) == 2
            assert span.attributes["http.response.status_code"] == 200
    finally:
        await client._http.aclose()
        provider.shutdown()


@pytest.mark.asyncio
async def test_worker_request_without_observation(monkeypatch):
    from veadk.agents._remote_sandbox import request_tracing

    monkeypatch.setattr(request_tracing, "trace", None)

    async def respond(request):
        assert "traceparent" not in request.headers
        return httpx.Response(200, json={"status": "ready"})

    client = CodexWorkerClient("https://worker.invalid")
    client._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert (await client.request("GET", "/readyz"))["status"] == "ready"
    finally:
        await client._http.aclose()
