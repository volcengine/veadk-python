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


"""Offline tests of native transfer, both wire protocols and type discovery."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import PrivateAttr

from veadk import Agent
from veadk.agents.agentkit_remote_sandbox_agent import (
    AgentkitRemoteSandboxAgent,
    SandboxAgentError,
)


class ParentModel(BaseLlm):
    model: str = "offline-parent"
    _calls: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request, stream=False):
        self._calls += 1
        yield LlmResponse(
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            name="transfer_to_agent", args={"agent_name": "sandbox"}
                        )
                    )
                ],
            )
        )


async def make_runner(child):
    model = ParentModel()
    root = Agent(
        name="coordinator", model=model, model_api_key="fixture", sub_agents=[child]
    )
    sessions = InMemorySessionService()
    await sessions.create_session(
        app_name="probe", user_id="user", session_id="session"
    )
    return Runner(agent=root, app_name="probe", session_service=sessions), model


async def collect(runner, on_event=None, *, user_id="user"):
    result = []
    async for event in runner.run_async(
        user_id=user_id,
        session_id="session",
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="Compute two plus three in the sandbox")],
        ),
    ):
        result.append(event)
        if on_event:
            await on_event(event)
    return result


class CodeFixture:
    def __init__(self):
        self.release = asyncio.Event()
        self.starts = 0
        self.session_keys = []
        self.cancelled = False
        self.fail = False

    async def handle(self, request):
        path = request.path
        assert request.query.get("route") == "fixture"
        if path.endswith("/readyz"):
            return web.json_response(
                {"schemaVersion": 1, "capabilities": ["tool_events"]}
            )
        if path.endswith("/sessions"):
            self.session_keys.append(request.headers["Idempotency-Key"])
            return web.json_response({"status": "ready", "sessionId": "session-code"})
        if path.endswith("/cancel"):
            self.cancelled = True
            return web.json_response({"status": "interrupted"})
        if request.method == "POST":
            self.starts += 1
            return web.json_response({"turnId": "turn-code"})
        if not path.endswith("/events"):
            return web.json_response({"status": "running", "codexTurnId": "codex-1"})
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)

        async def send(seq, kind, payload):
            data = {
                "schemaVersion": 1,
                "eventId": seq,
                "sessionId": "session-code",
                "turnId": "turn-code",
                "type": kind,
                "payload": payload,
            }
            await response.write(("data: " + json.dumps(data) + "\n\n").encode())

        await send(
            1,
            "tool.started",
            {
                "item": {
                    "id": "exec-1",
                    "type": "commandExecution",
                    "command": "python -c 'print(2+3)'",
                }
            },
        )
        await asyncio.wait_for(self.release.wait(), 5)
        await send(2, "tool.delta", {"itemId": "exec-1", "delta": "5\n"})
        await send(
            3,
            "tool.completed",
            {
                "item": {
                    "id": "exec-1",
                    "type": "commandExecution",
                    "aggregatedOutput": "5\n",
                    "exitCode": 0,
                }
            },
        )
        await send(4, "message.delta", {"itemId": "msg", "delta": "Answer: 5"})
        await send(
            5,
            "turn.completed",
            {
                "status": "failed" if self.fail else "completed",
                "finalText": "Answer: 5",
                "error": {"message": "fixture failure"},
            },
        )
        return response


@pytest.mark.asyncio
async def test_code_child_streams_tools_before_final_and_reuses_session():
    fixture = CodeFixture()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", fixture.handle)
    async with TestServer(app) as server:
        child = AgentkitRemoteSandboxAgent(
            name="sandbox",
            tool_type="CodeEnv",
            endpoint=str(server.make_url("/?route=fixture")),
        )
        runner, model = await make_runner(child)

        async def observe(event):
            if event.author == "sandbox" and event.get_function_calls():
                assert not any(p.text == "Answer: 5" for p in event.content.parts)
                fixture.release.set()

        first = await collect(runner, observe)
        second = await collect(runner, observe)
        for events in (first, second):
            assert not [e.error_message for e in events if e.error_message]
            fc = next(
                e.get_function_calls()[0]
                for e in events
                if e.author == "sandbox" and e.get_function_calls()
            )
            fr = next(
                e.get_function_responses()[0]
                for e in events
                if e.author == "sandbox" and e.get_function_responses()
            )
            assert fc.id == fr.id and fr.response["exitCode"] == 0
            assert any(
                e.partial and e.content.parts[0].thought
                for e in events
                if e.author == "sandbox"
            )
            assert (
                sum(
                    e.author == "sandbox"
                    and not e.partial
                    and e.content.parts[0].text == "Answer: 5"
                    for e in events
                )
                == 1
            )
        assert fixture.starts == 2
        assert fixture.session_keys[0] == fixture.session_keys[1]
        assert model._calls <= 2  # no post-delegation summary


@pytest.mark.asyncio
async def test_code_failure_is_not_a_successful_final():
    fixture = CodeFixture()
    fixture.fail = True
    fixture.release.set()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", fixture.handle)
    async with TestServer(app) as server:
        runner, _ = await make_runner(
            AgentkitRemoteSandboxAgent(
                name="sandbox",
                tool_type="CodeEnv",
                endpoint=str(server.make_url("/?route=fixture")),
            )
        )
        events = await collect(runner)
        assert any("fixture failure" in (e.error_message or "") for e in events)


@pytest.mark.asyncio
async def test_explicit_type_skips_get_tool_and_is_passed_to_lease():
    agent = AgentkitRemoteSandboxAgent(
        name="sandbox", tool_id="private", tool_type="CodeEnv"
    )
    ctx = SimpleNamespace(
        app_name="app", user_id="u", session=SimpleNamespace(state={})
    )
    lease = SimpleNamespace(
        session_id="physical", select_endpoint=lambda **kw: "https://example.test"
    )
    with (
        patch.object(
            AgentkitRemoteSandboxAgent,
            "_discover_type",
            side_effect=AssertionError("must not discover"),
        ),
        patch(
            "veadk.agents.agentkit_remote_sandbox_agent.ensure_agentkit_session_lease",
            return_value=lease,
        ),
    ):
        assert (await agent._resolve(ctx, "logical"))[0] == "CodeEnv"


def test_private_discovery_errors_and_constructor_is_lazy():
    agent = AgentkitRemoteSandboxAgent(name="sandbox", tool_id="private")
    with (
        patch(
            "veadk.agents.agentkit_remote_sandbox_agent.get_agentkit_credentials",
            return_value=("fake-ak", "fake-sk", {}),
        ),
        patch("agentkit.sdk.tools.client.AgentkitToolsClient") as client,
    ):
        client.return_value.get_tool.return_value = SimpleNamespace(tool_type="Private")
        with pytest.raises(SandboxAgentError, match="specify tool_type"):
            agent._discover_type("private", {})


@pytest.mark.parametrize("kind", ["", "Private", "All-in-one"])
def test_invalid_explicit_type_rejected(kind):
    with pytest.raises(ValueError):
        AgentkitRemoteSandboxAgent(name="sandbox", tool_type=kind)


@pytest.mark.asyncio
async def test_discovery_cache_is_user_scoped():
    agent = AgentkitRemoteSandboxAgent(name="sandbox", tool_id="tool")
    lease = SimpleNamespace(
        session_id="physical", select_endpoint=lambda **kw: "https://example.test"
    )
    with (
        patch.object(
            AgentkitRemoteSandboxAgent, "_discover_type", return_value="Skill"
        ) as discover,
        patch(
            "veadk.agents.agentkit_remote_sandbox_agent.ensure_agentkit_session_lease",
            return_value=lease,
        ),
    ):
        for user in ["u1", "u1", "u2"]:
            await agent._resolve(
                SimpleNamespace(
                    app_name="app", user_id=user, session=SimpleNamespace(state={})
                ),
                user,
            )
        assert discover.call_count == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_skill_a2a_preserves_tool_parts_and_context(streaming):
    from google.adk.a2a.converters.part_converter import convert_genai_part_to_a2a_part

    release = asyncio.Event()
    contexts = []
    methods = []

    def wire(part):
        return convert_genai_part_to_a2a_part(part).model_dump(
            mode="json", by_alias=True, exclude_none=True
        )

    calls = [
        wire(
            types.Part(
                function_call=types.FunctionCall(
                    id="skill-exec", name="add_numbers", args={"a": 2, "b": 3}
                )
            )
        )
    ]
    results = [
        wire(
            types.Part(
                function_response=types.FunctionResponse(
                    id="skill-exec", name="add_numbers", response={"sum": 5}
                )
            )
        )
    ]

    def task(state="working"):
        result = {
            "kind": "task",
            "id": "a2a-task",
            "contextId": "remote-context",
            "status": {"state": state},
        }
        if state == "completed":
            result["artifacts"] = [
                {"artifactId": "tools", "parts": calls + results},
                {
                    "artifactId": "answer",
                    "parts": [{"kind": "text", "text": "Skill computed 5"}],
                },
            ]
        return result

    async def handle(request):
        assert request.query.get("route") == "fixture"
        if request.method == "GET":
            return web.json_response(
                {
                    "name": "skill",
                    "description": "fixture",
                    "version": "1",
                    "url": "http://127.0.0.1:1/a2a",
                    "capabilities": {"streaming": streaming},
                    "defaultInputModes": ["text/plain"],
                    "defaultOutputModes": ["text/plain"],
                    "skills": [],
                }
            )
        body = await request.json()
        methods.append(body["method"])
        if body["method"].startswith("message/"):
            contexts.append(body["params"]["message"].get("contextId"))

        def reply(result):
            return {"jsonrpc": "2.0", "id": body["id"], "result": result}

        if body["method"] == "tasks/get":
            return web.json_response(reply(task("completed")))
        if not streaming:
            return web.json_response(reply(task()))
        response = web.StreamResponse(headers={"Content-Type": "text/event-stream"})
        await response.prepare(request)

        async def send(result):
            await response.write(
                ("data: " + json.dumps(reply(result)) + "\n\n").encode()
            )

        await send(task())

        def artifact(identifier, parts):
            return {
                "kind": "artifact-update",
                "taskId": "a2a-task",
                "contextId": "remote-context",
                "artifact": {"artifactId": identifier, "parts": parts},
                "append": False,
                "lastChunk": True,
            }

        await send(artifact("calls", calls))
        await asyncio.wait_for(release.wait(), 5)
        await send(artifact("results", results))
        # Exercise partial artifact updates that default RemoteA2aAgent can drop.
        await send(
            {
                "kind": "artifact-update",
                "taskId": "a2a-task",
                "contextId": "remote-context",
                "artifact": {
                    "artifactId": "answer",
                    "parts": [{"kind": "text", "text": "Skill "}],
                },
                "append": False,
                "lastChunk": False,
            }
        )
        await send(
            {
                "kind": "artifact-update",
                "taskId": "a2a-task",
                "contextId": "remote-context",
                "artifact": {
                    "artifactId": "answer",
                    "parts": [{"kind": "text", "text": "computed 5"}],
                },
                "append": True,
                "lastChunk": True,
            }
        )
        await send(
            {
                "kind": "status-update",
                "taskId": "a2a-task",
                "contextId": "remote-context",
                "status": {"state": "completed"},
                "final": True,
            }
        )
        return response

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    async with TestServer(app) as server:
        runner, model = await make_runner(
            AgentkitRemoteSandboxAgent(
                name="sandbox",
                tool_type="Skill",
                endpoint=str(server.make_url("/?route=fixture")),
            )
        )

        async def observe(event):
            if event.author == "sandbox" and event.get_function_calls():
                release.set()

        for _ in range(2):
            events = await collect(runner, observe)
            assert not [e.error_message for e in events if e.error_message]
            assert any(e.author == "sandbox" and e.get_function_calls() for e in events)
            assert any(
                e.author == "sandbox" and e.get_function_responses() for e in events
            )
            assert any(
                e.author == "sandbox"
                and not e.partial
                and e.content.parts[0].text == "Skill computed 5"
                for e in events
            )
        assert contexts == [None, "remote-context"]
        assert ("message/stream" if streaming else "message/send") in methods
        assert model._calls <= 2


@pytest.mark.asyncio
async def test_cancelling_code_invocation_interrupts_remote_turn():
    fixture = CodeFixture()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", fixture.handle)
    async with TestServer(app) as server:
        runner, _ = await make_runner(
            AgentkitRemoteSandboxAgent(
                name="sandbox",
                tool_type="CodeEnv",
                endpoint=str(server.make_url("/?route=fixture")),
            )
        )
        seen = asyncio.Event()

        async def observe(event):
            if event.author == "sandbox" and event.get_function_calls():
                seen.set()

        running = asyncio.create_task(collect(runner, observe))
        await asyncio.wait_for(seen.wait(), 5)
        running.cancel()
        with pytest.raises(asyncio.CancelledError):
            await running
        assert fixture.cancelled
        fixture.release.set()


@pytest.mark.asyncio
@pytest.mark.parametrize("streaming", [True, False])
async def test_skill_against_native_adk_a2a_server(streaming):
    """Real ADK A2A serialization must expose the tool before it completes."""
    import socket
    import uvicorn
    from google.adk.agents import LlmAgent
    from google.adk.a2a.utils.agent_to_a2a import to_a2a

    release = asyncio.Event()

    async def add_numbers(a: int, b: int) -> dict:
        """Add numbers after the remote client has observed the call."""
        await asyncio.wait_for(release.wait(), 10)
        return {"sum": a + b}

    class RemoteModel(BaseLlm):
        model: str = "offline-remote"
        _step: int = PrivateAttr(default=0)

        async def generate_content_async(self, llm_request, stream=False):
            self._step += 1
            part = (
                types.Part(
                    function_call=types.FunctionCall(
                        name="add_numbers", args={"a": 2, "b": 3}
                    )
                )
                if self._step == 1
                else types.Part(text="Native Skill computed 5")
            )
            yield LlmResponse(content=types.Content(role="model", parts=[part]))

    remote = LlmAgent(name="native_skill", model=RemoteModel(), tools=[add_numbers])
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    from a2a.types import AgentCard, AgentCapabilities

    card = AgentCard(
        name="native_skill",
        description="fixture",
        version="1",
        url=f"http://127.0.0.1:{port}/",
        capabilities=AgentCapabilities(streaming=streaming),
        default_input_modes=["text/plain"],
        default_output_modes=["text/plain"],
        skills=[],
    )
    application = to_a2a(remote, host="127.0.0.1", port=port, agent_card=card)
    server = uvicorn.Server(
        uvicorn.Config(application, host="127.0.0.1", port=port, log_level="error")
    )
    serving = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(0.05)
        runner, _ = await make_runner(
            AgentkitRemoteSandboxAgent(
                name="sandbox", tool_type="Skill", endpoint=f"http://127.0.0.1:{port}"
            )
        )

        async def observe(event):
            if event.author == "sandbox" and event.get_function_calls():
                release.set()

        events = await collect(runner, observe)
        assert release.is_set()
        assert not [e.error_message for e in events if e.error_message]
        assert any(e.author == "sandbox" and e.get_function_responses() for e in events)
        assert any(
            e.author == "sandbox"
            and not e.partial
            and e.content.parts[0].text == "Native Skill computed 5"
            for e in events
        )
    finally:
        release.set()
        server.should_exit = True
        await asyncio.wait_for(serving, 10)


@pytest.mark.asyncio
async def test_concurrent_users_have_distinct_worker_binding_keys():
    fixture = CodeFixture()
    fixture.release.set()
    app = web.Application()
    app.router.add_route("*", "/{path:.*}", fixture.handle)
    async with TestServer(app) as server:
        child = AgentkitRemoteSandboxAgent(
            name="sandbox",
            tool_type="CodeEnv",
            endpoint=str(server.make_url("/?route=fixture")),
        )
        runner, _ = await make_runner(child)
        await runner.session_service.create_session(
            app_name="probe", user_id="other-user", session_id="session"
        )
        first, second = await asyncio.gather(
            collect(runner), collect(runner, user_id="other-user")
        )
        assert len(set(fixture.session_keys)) == 2
        assert not [e.error_message for e in first + second if e.error_message]
        assert {e.invocation_id for e in first}.isdisjoint(
            {e.invocation_id for e in second}
        )
