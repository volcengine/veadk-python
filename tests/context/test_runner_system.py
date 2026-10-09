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

"""Run real VeADK/ADK tool and session loops with an offline model transport."""

import copy
import json

import httpx
import pytest
from google.adk.models.lite_llm import LiteLLMClient
from google.adk.sessions import InMemorySessionService
from google.genai import types
from litellm import ModelResponse

from veadk import Agent, Runner
from veadk.context.tool_results import READ_CONTEXT_TOOL
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.models.retrying_lite_llm import RetryingLiteLlm


class ToolLoopClient(LiteLLMClient):
    def __init__(self):
        self.requests = []

    async def acompletion(self, **kwargs):
        self.requests.append(copy.deepcopy(kwargs))
        tools = [message for message in kwargs["messages"] if message["role"] == "tool"]
        if not tools:
            message = self._call("fetch_report", {}, "fetch-1")
        elif tools[-1]["tool_call_id"] == "fetch-1":
            preview = json.loads(tools[-1]["content"])["result"]
            assert "Preview only" in preview
            ref = preview.split("reference='")[1].split("'")[0]
            assert READ_CONTEXT_TOOL in [
                tool["function"]["name"] for tool in kwargs["tools"]
            ]
            message = self._call(
                READ_CONTEXT_TOOL, {"reference": ref, "query": "INV-418"}, "read-1"
            )
        else:
            original = json.loads(tools[-1]["content"])
            assert "INV-418 = 187.25 CNY" in original["text"]
            message = {
                "role": "assistant",
                "content": "INV-418 = 187.25 CNY; payment was not submitted.",
            }
        return ModelResponse(
            model="openai/context-test", choices=[{"message": message}]
        )

    def _call(self, name, arguments, call_id):
        return {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": name, "arguments": json.dumps(arguments)},
                }
            ],
        }


@pytest.mark.asyncio
async def test_large_tool_result_is_retrievable_in_the_real_runner_without_reexecuting():
    executions = 0
    original_text = "x" * 30000 + "INV-418 = 187.25 CNY" + "y" * 30000

    def fetch_report() -> str:
        """Read the invoice report. This tool never makes a payment."""
        nonlocal executions
        executions += 1
        return original_text

    client = ToolLoopClient()
    model = RetryingLiteLlm(
        model="openai/context-test",
        llm_client=client,
        context_compression={
            "context_window": 24000,
            "output_reserve": 2000,
            "safety_margin": 256,
            "tool_result_max_bytes": 4000,
            "retrieval_max_bytes": 2000,
        },
    )
    agent = Agent(
        name="accountant",
        model=model,
        model_api_key="offline-test",
        tools=[fetch_report],
    )
    service = InMemorySessionService()
    await service.create_session(
        app_name="context_test", user_id="user", session_id="session"
    )
    runner = Runner(agent=agent, app_name="context_test", session_service=service)
    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id="session",
            new_message=types.Content(
                role="user",
                parts=[types.Part(text="Read the invoice; do not submit payment.")],
            ),
        )
    ]
    assert executions == 1
    assert len(client.requests) == 3
    assert any(
        "187.25 CNY" in (part.text or "")
        for event in events
        if event.content
        for part in event.content.parts
    )
    session = await service.get_session(
        app_name="context_test", user_id="user", session_id="session"
    )
    saved_results = [
        part.function_response
        for event in session.events
        if event.content
        for part in event.content.parts
        if part.function_response and part.function_response.name == "fetch_report"
    ]
    assert saved_results[0].response["result"] == original_text
    assert (
        max(len(json.dumps(request["messages"])) for request in client.requests) < 24000
    )


@pytest.mark.asyncio
async def test_sqlite_runner_compresses_tool_input_and_persists_originals(
    monkeypatch, tmp_path
):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_EMBEDDING_API_KEY", raising=False)
    wire, runners = [], []
    original_run = Runner.run

    def get_inventory_report() -> str:
        """Return the complete synthetic inventory report for all 430 records."""
        return "".join(
            f"Record {i}: warehouse {i * 17}, audited balance {i * 23} units.\n"
            for i in range(430)
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

    monkeypatch.setattr(Runner, "run", observe_run)
    monkeypatch.setattr(httpx.AsyncClient, "send", send)
    data = tmp_path / ".adk"
    data.mkdir()
    memory = ShortTermMemory(
        backend="sqlite",
        local_database_path=str(data / "compression-demo.db"),
    )
    agent = Agent(
        name="inventory_assistant",
        model_name="doubao-seed-2-1-pro-260628",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3",
        model_api_key="synthetic-offline",
        instruction=(
            "Use get_inventory_report for the first inventory question. "
            "Answer from the report with record ID, balance and unit. "
            "For follow-up questions use retained evidence; read the original "
            "context only if the needed details are missing."
        ),
        tools=[get_inventory_report],
        context_compression={"input_limit": 16000},
    )
    runner = Runner(
        agent=agent,
        short_term_memory=memory,
        app_name="compression_demo",
        user_id="demo_user",
    )
    for question in (
        "Fetch the inventory report. What is the audited balance for Record 113?",
        "From the same report, what is the audited balance for Record 227?",
    ):
        await runner.run(messages=question, session_id="inventory_session")
    assert len(wire) == 3 and len(runners) == 2
    original = get_inventory_report()
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
