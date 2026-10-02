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

"""Run the public teaching example through Runner using synthetic HTTP replies."""

import json
from pathlib import Path
import runpy

import httpx
import pytest

from veadk import Agent, Runner


@pytest.mark.asyncio
async def test_teaching_example_compresses_tool_input_and_persists_originals(
    monkeypatch, tmp_path
):
    path = (
        Path(__file__).resolve().parents[2] / "examples/18_context_compression/main.py"
    )
    namespace = runpy.run_path(str(path))
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    wire, runners = [], []
    original_run = Runner.run

    def configured_agent(**kwargs):
        return Agent(
            model_name="doubao-seed-2-1-pro-260628",
            model_api_base="https://ark.cn-beijing.volces.com/api/v3",
            model_api_key="synthetic-offline",
            **kwargs,
        )

    async def observe_run(self, *args, **kwargs):
        runners.append(self)
        return await original_run(self, *args, **kwargs)

    async def send(self, request, **kwargs):
        assert request.url.host == "ark.cn-beijing.volces.com"
        body = json.loads(request.content)
        wire.append(body)
        message = {"role": "assistant", "content": "Record 113: 2599 units."}
        finish = "stop"
        if len(wire) == 1:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "inventory-call",
                        "type": "function",
                        "function": {"name": "get_inventory_report", "arguments": "{}"},
                    }
                ],
            }
            finish = "tool_calls"
        elif "Record 227" in json.dumps(body["messages"][-1]):
            message["content"] = "Record 227: 5221 units."
        return httpx.Response(
            200,
            request=request,
            json={
                "id": "synthetic",
                "created": 0,
                "object": "chat.completion",
                "model": body["model"],
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": finish,
                        "message": message,
                    }
                ],
                "usage": {
                    "prompt_tokens": 1,
                    "completion_tokens": 1,
                    "total_tokens": 2,
                },
            },
        )

    monkeypatch.setitem(namespace["main"].__globals__, "Agent", configured_agent)
    monkeypatch.setattr(Runner, "run", observe_run)
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    await namespace["main"]()
    assert len(wire) == 3 and len(runners) == 2
    original = namespace["get_inventory_report"]()
    tool_messages = [m for m in wire[1]["messages"] if m["role"] == "tool"]
    assert len(tool_messages) == 1
    preview = tool_messages[0]["content"]
    assert len(preview.encode()) < len(original.encode())
    assert "ctx_" in preview and "Record 113:" in preview
    assert "2599 units" in preview
    assert any(t["function"]["name"] == "veadk_read_context" for t in wire[1]["tools"])
    service = runners[0].session_service
    saved = await service.get_session(
        app_name="compression_demo",
        user_id="demo_user",
        session_id="inventory_session",
    )
    responses = [
        p.function_response
        for e in saved.events
        if e.content
        for p in e.content.parts or []
        if p.function_response
    ]
    assert any(
        r.name == "get_inventory_report" and r.response.get("result") == original
        for r in responses
    )
    assert (tmp_path / ".adk/compression-demo.db").is_file()
    assert not (tmp_path / ".adk/context-index.sqlite3").exists()
