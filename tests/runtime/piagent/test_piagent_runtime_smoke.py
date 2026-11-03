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

"""Manual smoke test for a real local Pi binary.

This file is intentionally skipped by default because it calls a real model. Run
it explicitly after setting model credentials. Set PIAGENT_BINARY to use an
existing Pi executable inside a fully extracted Pi release directory; otherwise
the runtime uses PIAGENT_INSTALL_DIR/pi/pi and downloads Pi there when it is
missing:

    PIAGENT_BINARY=/path/to/pi \
    PIAGENT_AGENT_DIR=/private/tmp/veadk-piagent-test-home \
    MODEL_AGENT_API_KEY=<key> \
    PIAGENT_SMOKE_MODEL=<model> \
    PIAGENT_RUN_SMOKE=1 \
    .venv/bin/python -m pytest tests/runtime/piagent/test_piagent_runtime_smoke.py -s
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from fastapi import FastAPI, Request

from veadk import Agent, Runner


# NOTE: `pytest_configure` is only collected from `conftest.py` and plugins, so
# defining it here would be dead code. The `piagent_smoke` marker is registered
# in `pytest.ini` instead. (It previously appeared to work only because
# `filterwarnings = ignore::UserWarning` swallowed the resulting
# `PytestUnknownMarkWarning`.)


@pytest.mark.piagent_smoke
@pytest.mark.asyncio
async def test_real_piagent_runtime_smoke():
    if os.getenv("PIAGENT_RUN_SMOKE") != "1":
        pytest.skip("set PIAGENT_RUN_SMOKE=1 to call a real Pi binary and model")

    api_key = os.getenv("PIAGENT_SMOKE_API_KEY") or os.getenv("MODEL_AGENT_API_KEY")
    if not api_key:
        pytest.skip("set PIAGENT_SMOKE_API_KEY or MODEL_AGENT_API_KEY")

    model_name = os.getenv("PIAGENT_SMOKE_MODEL")
    if not model_name:
        pytest.skip("PIAGENT_SMOKE_MODEL is required")

    agent = Agent(
        name="assistant",
        instruction="Answer briefly.",
        runtime="piagent",
        model_name=model_name,
        model_api_base=os.getenv(
            "PIAGENT_SMOKE_API_BASE",
            "https://ark.cn-beijing.volces.com/api/v3/",
        ),
        model_api_key=api_key,
        model_api_key_name="",
    )
    runner = Runner(agent=agent, app_name="piagent_smoke")

    result = await runner.run("hello", user_id="u1", session_id="s1")

    assert isinstance(result, str)
    assert result.strip()


@pytest.mark.piagent_smoke
@pytest.mark.asyncio
async def test_real_piagent_resumes_native_tool_results(monkeypatch):
    """A real Pi process must receive tool results as protocol messages."""
    if os.getenv("PIAGENT_RUN_SMOKE") != "1":
        pytest.skip("set PIAGENT_RUN_SMOKE=1 to spawn the real Pi binary")
    binary = Path(
        os.getenv("PIAGENT_BINARY", "~/.cache/veadk/piagent/pi/pi")
    ).expanduser()
    if not binary.is_file():
        pytest.skip("set PIAGENT_BINARY to a locally installed Pi binary")

    import uvicorn
    from fastapi.responses import StreamingResponse
    from google.adk.tools.long_running_tool import LongRunningFunctionTool
    from google.genai import types
    from veadk.runtime.piagent.client import PiAgentRpcClient

    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_DISABLE_BUILTIN_TOOLS", "1")
    requests = []
    tool_metadata = {"__proto__": {"value": "must remain"}, "ordinary": "ok"}
    pi_events = []
    original_prompt = PiAgentRpcClient.prompt

    async def capture_prompt(client, message):
        async for event in original_prompt(client, message):
            pi_events.append(event)
            yield event

    monkeypatch.setattr(PiAgentRpcClient, "prompt", capture_prompt)
    executions = []
    app = FastAPI()

    @app.post("/v1/chat/completions")
    async def complete(request: Request):
        body = await request.json()
        requests.append(body)
        latest = body["messages"][-1]
        if latest["role"] == "tool":
            delta = {"role": "assistant", "content": latest["content"]}
            finish = "stop"
        else:
            delta = {
                "role": "assistant",
                "tool_calls": [
                    {
                        "index": 0,
                        "id": f"call-{len(requests)}",
                        "type": "function",
                        "function": {
                            "name": "external_job",
                            "arguments": json.dumps(
                                {"city": "Beijing", "metadata": tool_metadata}
                            ),
                        },
                    }
                ],
            }
            finish = "tool_calls"

        def stream():
            for update, reason in ((delta, None), ({}, finish)):
                payload = {
                    "id": "stub-response",
                    "object": "chat.completion.chunk",
                    "created": 1,
                    "model": body["model"],
                    "choices": [{"index": 0, "delta": update, "finish_reason": reason}],
                }
                yield f"data: {json.dumps(payload)}\n\n"
            yield "data: [DONE]\n\n"

        return StreamingResponse(stream(), media_type="text/event-stream")

    server = uvicorn.Server(
        uvicorn.Config(
            app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
        )
    )
    server.install_signal_handlers = lambda: None
    serving = asyncio.create_task(server.serve())
    while not server.started:
        if serving.done():
            serving.result()
        await asyncio.sleep(0.01)
    port = server.servers[0].sockets[0].getsockname()[1]

    async def external_job(city: str, metadata: dict) -> None:
        """Start a job completed by the caller."""
        await asyncio.sleep(0)
        assert metadata == tool_metadata
        executions.append(city)

    agent = Agent(
        name="assistant",
        instruction="Wait for the external result before answering.",
        runtime="piagent",
        model_name="pi-native-history-smoke",
        model_api_base=f"http://127.0.0.1:{port}/v1",
        model_api_key="local-smoke-key",
        model_api_key_name="",
        tools=[LongRunningFunctionTool(external_job)],
    )
    runner = Runner(agent=agent, app_name="pi_native_history_smoke")
    await runner.short_term_memory.create_session(
        app_name="pi_native_history_smoke", user_id="user", session_id="session"
    )

    async def send(content):
        async with asyncio.timeout(40):
            return [
                event
                async for event in runner.run_async(
                    user_id="user", session_id="session", new_message=content
                )
            ]

    try:
        for index in range(2):
            pending = await send(
                types.Content(
                    role="user", parts=[types.Part(text="Start the Beijing job.")]
                )
            )
            calls = [call for event in pending for call in event.get_function_calls()]
            assert len(calls) == 1, [
                event.get("message", {}).get("errorMessage")
                for event in pi_events
                if isinstance(event.get("message"), dict)
                and event["message"].get("errorMessage")
            ]
            result = f"external-result-{index}"
            resumed = await send(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                id=calls[0].id,
                                name="external_job",
                                response={"value": result},
                            )
                        )
                    ],
                )
            )
            assert not any(e.get_function_calls() for e in resumed)
            assert any(
                e.is_final_response()
                and e.content
                and any(result in (p.text or "") for p in e.content.parts or [])
                for e in resumed
            )
            latest = requests[-1]["messages"][-1]
            assert latest["role"] == "tool"
            assert latest["tool_call_id"] == calls[0].id
            restored_calls = [
                call
                for message in requests[-1]["messages"]
                for call in message.get("tool_calls", [])
                if call["id"] == calls[0].id
            ]
            assert len(restored_calls) == 1
            assert (
                json.loads(restored_calls[0]["function"]["arguments"])["metadata"]
                == tool_metadata
            )
            # Identical arguments are legitimate in the next user turn.
            assert executions == ["Beijing"] * (index + 1)
        resumed_requests = [
            body
            for body in requests
            if body["messages"][-1]["role"] == "tool"
            and "external-result-" in body["messages"][-1]["content"]
        ]
        assert len(resumed_requests) == 2
        assert (
            "Wait for the external result before answering."
            in requests[0]["messages"][0]["content"]
        )
    finally:
        server.should_exit = True
        await serving
