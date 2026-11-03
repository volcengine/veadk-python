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


"""Public SkillSandboxAgent API tests."""

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

from veadk import Agent, SkillSandboxAgent


@pytest.fixture
def anyio_backend():
    return "asyncio"


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
    root = Agent(
        name="coordinator",
        model=ParentModel(),
        model_api_key="fixture",
        sub_agents=[child],
    )
    sessions = InMemorySessionService()
    await sessions.create_session(
        app_name="probe", user_id="user", session_id="session"
    )
    return Runner(agent=root, app_name="probe", session_service=sessions)


async def collect(runner):
    result = []
    async for event in runner.run_async(
        user_id="user",
        session_id="session",
        new_message=types.Content(
            role="user",
            parts=[types.Part(text="List the available skills")],
        ),
    ):
        result.append(event)
    return result


def test_skill_sandbox_agent_is_exported_and_defaults_to_skill():
    agent = SkillSandboxAgent(name="sandbox")

    assert agent.tool_type == "Skill"
    assert agent.tool_id_env == "AGENTKIT_TOOL_ID_SKILLS"


@pytest.mark.anyio
async def test_skill_sandbox_agent_resolves_skills_tool_env_by_default():
    agent = SkillSandboxAgent(name="sandbox")
    ctx = SimpleNamespace(
        app_name="app", user_id="user", session=SimpleNamespace(state={})
    )
    lease = SimpleNamespace(
        session_id="physical", select_endpoint=lambda **kw: "https://example.test"
    )

    with (
        patch(
            "veadk.agents.agentkit_remote_sandbox_agent.resolve_agentkit_tool_id",
            return_value="skills-tool",
        ) as resolve_tool_id,
        patch(
            "veadk.agents.agentkit_remote_sandbox_agent.ensure_agentkit_session_lease",
            return_value=lease,
        ),
    ):
        kind, _, _, _ = await agent._resolve(ctx, "logical")

    assert kind == "Skill"
    resolve_tool_id.assert_called_once_with("AGENTKIT_TOOL_ID_SKILLS")


@pytest.mark.anyio
async def test_skill_sandbox_agent_sends_guarded_user_task_to_a2a():
    received_messages = []

    def task(state="working"):
        result = {
            "kind": "task",
            "id": "a2a-task",
            "contextId": "remote-context",
            "status": {"state": state},
        }
        if state == "completed":
            result["artifacts"] = [
                {
                    "artifactId": "answer",
                    "parts": [{"kind": "text", "text": "Guarded task accepted"}],
                }
            ]
        return result

    async def handle(request):
        if request.method == "GET":
            return web.json_response(
                {
                    "name": "skill",
                    "description": "fixture",
                    "version": "1",
                    "url": "http://127.0.0.1:1/a2a",
                    "capabilities": {"streaming": False},
                    "defaultInputModes": ["text/plain"],
                    "defaultOutputModes": ["text/plain"],
                    "skills": [],
                }
            )
        body = await request.json()
        if body["method"].startswith("message/"):
            received_messages.append(body["params"]["message"])

        def reply(result):
            return {"jsonrpc": "2.0", "id": body["id"], "result": result}

        if body["method"] == "tasks/get":
            return web.json_response(reply(task("completed")))
        return web.json_response(reply(task()))

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handle)
    async with TestServer(app) as server:
        runner = await make_runner(
            SkillSandboxAgent(
                name="sandbox",
                guardrails="Only use bash_tool.",
                endpoint=str(server.make_url("/?route=fixture")),
            )
        )
        events = await collect(runner)

    assert not [e.error_message for e in events if e.error_message]
    assert received_messages
    submitted_text = "\n".join(
        part["text"]
        for part in received_messages[0]["parts"]
        if part.get("kind") == "text"
    )
    assert "Only use bash_tool." in submitted_text
    assert "用户请求 / User request:" in submitted_text
    assert "List the available skills" in submitted_text
