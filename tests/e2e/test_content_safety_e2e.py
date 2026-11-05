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
"""End-to-end tests through a real ADK Runner and a real local HTTP server.

The model is deterministic, but everything below it is the production path:
ADK's plugin manager, the content-safety plugin, httpx, TCP, a local
System One-shaped HTTP service, session persistence, and event streaming.
"""

import asyncio
import base64
import json
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from google.adk.agents import LlmAgent
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.adk.apps import App
from google.adk.models import LlmResponse
from google.adk.models.base_llm import BaseLlm
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import Field

from veadk import Agent as VeADKAgent
from veadk import Runner as VeADKRunner
from veadk.content_safety import (
    Checkpoint,
    ContentSafetyConfig,
    build_content_safety,
)

ALL_QUESTIONS = ("prompt_injection", "sensitive_data", "high_risk_operation")
BLOCK_MESSAGE = "blocked by e2e policy"
TOOL_CALLS: list[str] = []
RED_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAACAAAAAgCAIAAAD8GO2jAAAAK0lEQVR4nO3NQQEAAATAQGTQ"
    "P5kwSvC7BdjldMdn9XoHAAAAAAAAAAAAhy3gIwFE6inHLwAAAABJRU5ErkJggg=="
)


def _answers(low=0.01, **overrides):
    values = {name: low for name in ALL_QUESTIONS}
    values.update(overrides)
    return {name: {"type": "noul", "noul": value} for name, value in values.items()}


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        state = body.get("state", "")
        self.server.requests.append(
            {"state": state, "body": body, "headers": dict(self.headers)}
        )

        if "FAIL" in state:
            self.send_response(500)
            self.end_headers()
            return

        payload = {"answers": _answers()}
        if "INJECT" in state:
            payload = {"answers": _answers(prompt_injection=0.99)}
        elif "SECRET" in state:
            payload = {"answers": _answers(sensitive_data=0.99)}
        elif "TOOL_RISK" in state:
            payload = {"answers": _answers(high_risk_operation=0.99)}

        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):  # silence test output
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list[dict] = []


@contextmanager
def systemone_server():
    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class ScriptedLlm(BaseLlm):
    model: str = "scripted"
    turns: list[list[LlmResponse]] = Field(default_factory=list)
    calls: int = 0

    async def generate_content_async(self, llm_request, stream: bool = False):
        index = min(self.calls, len(self.turns) - 1)
        self.calls += 1
        for response in self.turns[index]:
            yield response


def text_response(text, *, partial=False):
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=text)]),
        partial=partial,
    )


def tool_call_response(name, args):
    return LlmResponse(
        content=types.Content(
            role="model",
            parts=[types.Part(function_call=types.FunctionCall(name=name, args=args))],
        ),
        partial=False,
    )


def dangerous_tool(query: str) -> dict:
    """Execute a dangerous operation.

    Args:
        query: The operation payload.
    """
    TOOL_CALLS.append(query)
    return {"ok": True, "query": query}


def make_config(server, *, on_error="allow"):
    return ContentSafetyConfig.from_dict(
        {
            "provider": "decision",
            "on_error": on_error,
            "block_message": BLOCK_MESSAGE,
            "use_default_questions": False,
            "questions": {
                name: {
                    "instructions": f"Detect {name}.",
                    "threshold": 0.5,
                }
                for name in ALL_QUESTIONS
            },
            "decision": {
                "api_url": f"http://127.0.0.1:{server.server_address[1]}/v1/judge",
                "api_key": "e2e-key",
                "model": "e2e-judge",
            },
        }
    )


async def run_agent(
    *, turns, message, plugin, streaming=False, tools=None, message_parts=None
):
    llm = ScriptedLlm(turns=turns)
    agent = LlmAgent(
        name="e2e_agent",
        model=llm,
        instruction="Answer the user.",
        tools=tools or [],
    )
    app = App(
        name="e2e_app",
        root_agent=agent,
        plugins=[plugin] if plugin is not None else [],
    )
    service = InMemorySessionService()
    await service.create_session(
        app_name="e2e_app", user_id="user", session_id="session"
    )
    runner = Runner(app=app, session_service=service)
    run_config = RunConfig(streaming_mode=StreamingMode.SSE) if streaming else None
    events = []
    async for event in runner.run_async(
        user_id="user",
        session_id="session",
        new_message=types.Content(
            role="user", parts=message_parts or [types.Part(text=message)]
        ),
        run_config=run_config,
    ):
        events.append(event)
    return llm, events


def event_text(event):
    if not event.content:
        return ""
    return "".join(
        part.text for part in event.content.parts if isinstance(part.text, str)
    )


def test_e2e_allow_full_adk_turn():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("hello from the model")]],
                message="hello",
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        assert event_text(events[-1]) == "hello from the model"
        assert len(server.requests) == 2  # before_model + after_model
        assert server.requests[0]["body"]["model"] == "e2e-judge"
        assert "before_model" in server.requests[0]["body"]["state"]
        assert "after_model" in server.requests[1]["body"]["state"]
        assert server.requests[0]["headers"]["Authorization"] == "Bearer e2e-key"
        assert server.requests[0]["headers"]["ark-beta-systemone-api"] == "true"

        invocation_id = events[-1].invocation_id
        assert (
            plugin.last_result(invocation_id, Checkpoint.BEFORE_MODEL).status.value
            == "passed"
        )
        assert (
            plugin.last_result(invocation_id, Checkpoint.AFTER_MODEL).status.value
            == "passed"
        )


def test_e2e_blocks_user_input_before_model_call():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("should never be called")]],
                message="INJECT this",
                plugin=plugin,
            )
        )

        assert llm.calls == 0
        assert len(server.requests) == 1
        assert BLOCK_MESSAGE in "".join(event_text(event) for event in events)
        invocation_id = events[-1].invocation_id
        assert (
            plugin.last_result(invocation_id, Checkpoint.BEFORE_MODEL).status.value
            == "risk_hit"
        )
        assert plugin.last_result(invocation_id, Checkpoint.AFTER_MODEL) is None


def test_e2e_blocks_model_output_after_model_call():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("SECRET value")]],
                message="hello",
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        final_text = event_text(events[-1])
        assert final_text == BLOCK_MESSAGE
        assert "SECRET" not in final_text
        invocation_id = events[-1].invocation_id
        assert (
            plugin.last_result(invocation_id, Checkpoint.AFTER_MODEL).status.value
            == "risk_hit"
        )


def test_e2e_blocks_streamed_output_without_leaking_partials():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[
                    [
                        text_response("SEC", partial=True),
                        text_response("RET value", partial=True),
                        text_response("SECRET value", partial=False),
                    ]
                ],
                message="hello",
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        partial_texts = [
            event_text(event)
            for event in events
            if event.content and event.partial and event.content.role == "model"
        ]
        assert partial_texts == ["", ""]
        assert event_text(events[-1]) == BLOCK_MESSAGE
        assert "SECRET" not in "".join(event_text(event) for event in events)


def test_e2e_blocks_tool_before_execution():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[
                    [tool_call_response("dangerous_tool", {"query": "TOOL_RISK"})],
                    [text_response("done")],
                ],
                message="call the tool",
                plugin=plugin,
                tools=[dangerous_tool],
            )
        )

        assert TOOL_CALLS == []
        invocation_id = events[-1].invocation_id
        before_tool = plugin.last_result(invocation_id, Checkpoint.BEFORE_TOOL)
        assert before_tool is not None
        assert before_tool.status.value == "risk_hit"
        function_responses = [
            part.function_response
            for event in events
            if event.content
            for part in event.content.parts
            if part.function_response
        ]
        assert function_responses
        assert function_responses[0].response["blocked"] is True


def test_e2e_tool_runs_when_content_is_allowed():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[
                    [tool_call_response("dangerous_tool", {"query": "safe"})],
                    [text_response("done")],
                ],
                message="call the tool",
                plugin=plugin,
                tools=[dangerous_tool],
            )
        )

        assert TOOL_CALLS == ["safe"]
        invocation_id = events[-1].invocation_id
        assert (
            plugin.last_result(invocation_id, Checkpoint.BEFORE_TOOL).status.value
            == "passed"
        )
        assert (
            plugin.last_result(invocation_id, Checkpoint.AFTER_TOOL).status.value
            == "passed"
        )


def test_e2e_on_error_allow_degrades_open():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server, on_error="allow"))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("still answered")]],
                message="FAIL please",
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        assert event_text(events[-1]) == "still answered"
        invocation_id = events[-1].invocation_id
        audit = plugin.last_result(invocation_id, Checkpoint.BEFORE_MODEL)
        assert audit.status.value == "error"
        assert audit.degraded is True
        assert audit.action.value == "allow"


def test_e2e_on_error_block_fails_closed():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server, on_error="block"))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("should not appear")]],
                message="FAIL please",
                plugin=plugin,
            )
        )

        assert llm.calls == 0
        assert BLOCK_MESSAGE in "".join(event_text(event) for event in events)


def test_e2e_none_provider_is_opt_in_and_makes_no_calls():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(ContentSafetyConfig())
        assert plugin is None
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("plain answer")]],
                message="hello",
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        assert event_text(events[-1]) == "plain answer"
        assert server.requests == []


def test_e2e_config_yaml_auto_mounts_in_veadk_runner(tmp_path, monkeypatch):
    TOOL_CALLS.clear()
    with systemone_server() as server:
        (tmp_path / "config.yaml").write_text(
            f"""
tool:
  content_safety:
    provider: decision
    use_default_questions: false
    block_message: {BLOCK_MESSAGE!r}
    decision:
      api_url: http://127.0.0.1:{server.server_address[1]}/v1/judge
      api_key: e2e-key
      model: e2e-judge
    questions:
      prompt_injection:
        instructions: Detect prompt_injection.
        threshold: 0.5
      sensitive_data:
        instructions: Detect sensitive_data.
        threshold: 0.5
      high_risk_operation:
        instructions: Detect high_risk_operation.
        threshold: 0.5
""",
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)

        llm = ScriptedLlm(turns=[[text_response("hello from veadk")]])
        agent = VeADKAgent(
            name="e2e_veadk_agent",
            model=llm,
            instruction="Answer the user.",
            model_api_key="e2e-model-key",
        )
        runner = VeADKRunner(agent=agent, app_name="e2e_veadk_app")

        assert [p.name for p in runner.plugin_manager.plugins] == [
            "content_safety_decision"
        ]

        result = asyncio.run(runner.run(messages="hello"))

        assert result == "hello from veadk"
        assert llm.calls == 1
        assert len(server.requests) == 2
        assert "before_model" in server.requests[0]["body"]["state"]
        assert "after_model" in server.requests[1]["body"]["state"]


def test_e2e_multimodal_image_reaches_decision_api():
    TOOL_CALLS.clear()
    with systemone_server() as server:
        plugin = build_content_safety(make_config(server))
        llm, events = asyncio.run(
            run_agent(
                turns=[[text_response("image noted")]],
                message="",
                message_parts=[
                    types.Part(text="what is this?"),
                    types.Part(
                        inline_data=types.Blob(mime_type="image/png", data=RED_PNG)
                    ),
                ],
                plugin=plugin,
            )
        )

        assert llm.calls == 1
        state = server.requests[0]["body"]["state"]
        assert isinstance(state, list)
        assert any(part.get("type") == "image" for part in state)
        image = next(part for part in state if part.get("type") == "image")
        assert image["image_url"].startswith("data:image/png;base64,")
        invocation_id = events[-1].invocation_id
        assert (
            plugin.last_result(invocation_id, Checkpoint.BEFORE_MODEL).status.value
            == "passed"
        )
