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

"""Unit tests for veadk.runtime.codex.proxy (the Responses shim).

All backend calls (``litellm.aresponses``) are mocked; no network is used.
"""

import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from litellm.exceptions import APIError

from veadk.runtime.codex import proxy
from veadk.runtime.codex.proxy import (
    ResponsesShim,
    _error_type,
    _sse,
    _synth_sse,
    _to_dict,
    get_shim_url,
)


def _parse_sse(raw: bytes) -> list[dict[str, Any]]:
    """Parse an SSE byte stream into the list of decoded data dicts."""
    events: list[dict[str, Any]] = []
    for frame in raw.decode().split("\n\n"):
        frame = frame.strip()
        if not frame:
            continue
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: ") :]))
    return events


class TestErrorType:
    def test_known_codes(self):
        assert _error_type(400) == "invalid_request_error"
        assert _error_type(401) == "authentication_error"
        assert _error_type(403) == "permission_error"
        assert _error_type(404) == "not_found_error"
        assert _error_type(429) == "rate_limit_error"

    def test_unknown_code_defaults_to_api_error(self):
        assert _error_type(500) == "api_error"
        assert _error_type(418) == "api_error"


class TestToDict:
    def test_dict_passthrough(self):
        d = {"a": 1}
        assert _to_dict(d) is d

    def test_model_dump_object(self):
        obj = SimpleNamespace(model_dump=lambda: {"x": 2})
        assert _to_dict(obj) == {"x": 2}

    def test_mapping_fallback(self):
        # dict(obj) works on a mapping-like sequence of pairs.
        assert _to_dict([("k", "v")]) == {"k": "v"}


class TestSse:
    def test_encodes_event_and_data_lines(self):
        frame = _sse({"type": "response.created", "n": 1})
        text = frame.decode()
        assert text.startswith("event: response.created\n")
        assert "data: " in text
        assert text.endswith("\n\n")
        data_line = [line for line in text.splitlines() if line.startswith("data: ")][0]
        assert json.loads(data_line[len("data: ") :]) == {
            "type": "response.created",
            "n": 1,
        }


class TestSynthSse:
    @pytest.mark.asyncio
    async def _collect(self, resp: dict[str, Any]) -> list[dict[str, Any]]:
        frames = [frame async for frame in _synth_sse(resp)]
        events: list[dict[str, Any]] = []
        for f in frames:
            events.extend(_parse_sse(f))
        return events

    @pytest.mark.asyncio
    async def test_wraps_with_created_and_completed(self):
        resp = {"id": "r1", "status": "completed", "output": []}
        events = await self._collect(resp)
        assert events[0]["type"] == "response.created"
        assert events[1]["type"] == "response.in_progress"
        assert events[-1]["type"] == "response.completed"
        # The created/in_progress snapshots are trimmed to in_progress + empty.
        assert events[0]["response"]["status"] == "in_progress"
        assert events[0]["response"]["output"] == []
        assert events[-1]["response"]["status"] == "completed"

    @pytest.mark.asyncio
    async def test_sequence_numbers_are_monotonic(self):
        resp = {"id": "r1", "output": []}
        events = await self._collect(resp)
        seqs = [e["sequence_number"] for e in events]
        assert seqs == list(range(len(events)))

    @pytest.mark.asyncio
    async def test_function_call_item_streams_arguments(self):
        resp = {
            "id": "r1",
            "output": [
                {
                    "id": "fc1",
                    "type": "function_call",
                    "name": "do",
                    "arguments": '{"x":1}',
                }
            ],
        }
        events = await self._collect(resp)
        types_seen = [e["type"] for e in events]
        assert "response.output_item.added" in types_seen
        assert "response.function_call_arguments.delta" in types_seen
        assert "response.function_call_arguments.done" in types_seen
        assert "response.output_item.done" in types_seen
        delta = [
            e for e in events if e["type"] == "response.function_call_arguments.delta"
        ][0]
        assert delta["delta"] == '{"x":1}'
        assert delta["item_id"] == "fc1"

    @pytest.mark.asyncio
    async def test_message_item_streams_text(self):
        resp = {
            "id": "r1",
            "output": [
                {
                    "id": "m1",
                    "type": "message",
                    "content": [{"type": "output_text", "text": "hi"}],
                }
            ],
        }
        events = await self._collect(resp)
        types_seen = [e["type"] for e in events]
        assert "response.content_part.added" in types_seen
        assert "response.output_text.delta" in types_seen
        assert "response.output_text.done" in types_seen
        delta = [e for e in events if e["type"] == "response.output_text.delta"][0]
        assert delta["delta"] == "hi"

    @pytest.mark.asyncio
    async def test_reasoning_item_streams_summary(self):
        resp = {
            "id": "r1",
            "output": [
                {
                    "id": "rs1",
                    "type": "reasoning",
                    "summary": [{"type": "summary_text", "text": "think"}],
                }
            ],
        }
        events = await self._collect(resp)
        types_seen = [e["type"] for e in events]
        assert "response.reasoning_summary_part.added" in types_seen
        assert "response.reasoning_summary_text.delta" in types_seen
        assert "response.reasoning_summary_text.done" in types_seen

    @pytest.mark.asyncio
    async def test_non_emitted_item_types_filtered_from_output(self):
        resp = {
            "id": "r1",
            "output": [
                {"id": "x", "type": "something_else"},
                {"id": "m1", "type": "message", "content": []},
            ],
        }
        events = await self._collect(resp)
        completed = events[-1]
        assert completed["type"] == "response.completed"
        # Only the message item survives into the completed output.
        kept_types = [it["type"] for it in completed["response"]["output"]]
        assert kept_types == ["message"]


def _make_app_client(shim: ResponsesShim) -> TestClient:
    # The app is built in __init__; exercise its route via TestClient.
    return TestClient(shim._app)


class TestResponsesEndpoint:
    def _shim(self) -> ResponsesShim:
        return ResponsesShim(api_base="https://backend.example/v1", api_key="sk-test")

    def test_non_streaming_returns_json_and_forwards_kwargs(self):
        shim = self._shim()
        fake = SimpleNamespace(model_dump=lambda: {"id": "r1", "output": []})
        mock = AsyncMock(return_value=fake)
        with patch.object(proxy.litellm, "aresponses", mock):
            client = _make_app_client(shim)
            resp = client.post(
                "/v1/responses",
                json={
                    "model": "my-model",
                    "input": "hi",
                    "temperature": 0.5,
                    "stream": False,
                    "unsupported_field": "drop me",
                },
            )
        assert resp.status_code == 200
        assert resp.json() == {"id": "r1", "output": []}

        _, kwargs = mock.call_args
        # Model is prefixed and backend creds/provider injected.
        assert kwargs["model"] == "openai/my-model"
        assert kwargs["api_base"] == "https://backend.example/v1"
        assert kwargs["api_key"] == "sk-test"
        assert kwargs["custom_llm_provider"] == "openai"
        assert kwargs["drop_params"] is True
        assert kwargs["stream"] is False
        # Passthrough kept; unsupported dropped.
        assert kwargs["input"] == "hi"
        assert kwargs["temperature"] == 0.5
        assert "unsupported_field" not in kwargs

    def test_streaming_returns_synthesized_sse(self):
        shim = self._shim()
        fake = SimpleNamespace(
            model_dump=lambda: {
                "id": "r1",
                "output": [
                    {"id": "m1", "type": "message", "content": [{"text": "hi"}]}
                ],
            }
        )
        with patch.object(proxy.litellm, "aresponses", AsyncMock(return_value=fake)):
            client = _make_app_client(shim)
            resp = client.post(
                "/v1/responses",
                json={"model": "m", "input": "hi", "stream": True},
            )
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("text/event-stream")
        events = _parse_sse(resp.content)
        assert events[0]["type"] == "response.created"
        assert events[-1]["type"] == "response.completed"

    def test_non_function_tools_are_filtered_out(self):
        shim = self._shim()
        mock = AsyncMock(
            return_value=SimpleNamespace(model_dump=lambda: {"id": "r", "output": []})
        )
        with patch.object(proxy.litellm, "aresponses", mock):
            client = _make_app_client(shim)
            client.post(
                "/v1/responses",
                json={
                    "model": "m",
                    "tools": [
                        {"type": "function", "name": "f"},
                        {"type": "web_search", "external_web_access": True},
                    ],
                },
            )
        _, kwargs = mock.call_args
        assert kwargs["tools"] == [{"type": "function", "name": "f"}]

    def test_assistant_messages_get_status_backfilled(self):
        shim = self._shim()
        mock = AsyncMock(
            return_value=SimpleNamespace(model_dump=lambda: {"id": "r", "output": []})
        )
        with patch.object(proxy.litellm, "aresponses", mock):
            client = _make_app_client(shim)
            client.post(
                "/v1/responses",
                json={
                    "model": "m",
                    "input": [
                        {"type": "message", "role": "assistant", "content": []},
                        {"type": "message", "role": "user", "content": []},
                        {
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [],
                        },
                    ],
                },
            )
        _, kwargs = mock.call_args
        sent = kwargs["input"]
        assert sent[0]["status"] == "completed"  # backfilled
        assert "status" not in sent[1]  # user untouched
        assert sent[2]["status"] == "completed"  # already present, untouched

    def test_api_error_is_translated_to_error_envelope(self):
        shim = self._shim()
        err = APIError(
            status_code=429,
            message="rate limited",
            llm_provider="openai",
            model="m",
        )
        with patch.object(proxy.litellm, "aresponses", AsyncMock(side_effect=err)):
            # TestClient re-raises by default; disable so the handler runs.
            client = TestClient(shim._app, raise_server_exceptions=False)
            resp = client.post("/v1/responses", json={"model": "m"})
        assert resp.status_code == 429
        body = resp.json()
        assert body["error"]["type"] == "rate_limit_error"
        assert "rate limited" in body["error"]["message"]


class TestStartStop:
    @pytest.mark.asyncio
    async def test_start_returns_url_and_is_idempotent(self):
        shim = ResponsesShim(api_base="https://b/v1", api_key="k")
        try:
            url = await shim.start()
            assert url.startswith("http://127.0.0.1:")
            assert shim.url == url
            # Second call returns the same URL without restarting.
            assert await shim.start() == url
        finally:
            await shim.stop()
        assert shim.url is None


class TestGetShimUrl:
    @pytest.mark.asyncio
    async def test_caches_one_shim_per_backend(self):
        proxy._SHIMS.clear()
        started: list[ResponsesShim] = []

        async def fake_start(self: ResponsesShim) -> str:
            started.append(self)
            self.url = "http://127.0.0.1:9999"
            return self.url

        with patch.object(ResponsesShim, "start", fake_start):
            url1 = await get_shim_url("https://b/v1", "k1")
            url2 = await get_shim_url("https://b/v1", "k1")
            url3 = await get_shim_url("https://other/v1", "k1")

        assert url1 == url2 == "http://127.0.0.1:9999"
        # Same (base, key) reuses one shim; a different base makes a new one.
        assert len(proxy._SHIMS) == 2
        assert url3 == "http://127.0.0.1:9999"
        proxy._SHIMS.clear()
