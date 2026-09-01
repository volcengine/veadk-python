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
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from google.adk.agents.invocation_context import InvocationContext
from google.adk.agents.llm_agent import LlmAgent
from google.adk.auth.auth_credential import AuthCredential
from google.adk.auth.auth_credential import AuthCredentialTypes
from google.adk.auth.auth_tool import AuthConfig
from google.adk.events.event import Event
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.tool_context import ToolContext
from google.genai import types
from fastapi.openapi.models import APIKey
from fastapi.openapi.models import APIKeyIn

from veadk.runtime.base_runtime import resolve_system_append
from veadk.runtime.agent_transfer import build_transfer_tool
from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.config import codex_subprocess_env
from veadk.runtime.codex.config import toml_string
from veadk.runtime.codex.proxy import ResponsesShim
from veadk.runtime.codex.tools_bridge import add_tool_to_bundle
from veadk.runtime.codex.tools_bridge import build_executable_tools
from veadk.runtime.codex.tools_bridge import close_toolsets
from veadk.runtime.codex.tools_bridge import resume_authenticated_tools
from veadk.runtime.codex.tools_bridge import resume_confirmed_tools
from veadk.runtime.codex.translate import build_prompt
from veadk.runtime.codex.translate import build_input_attachments
from veadk.runtime.codex.translate import notification_to_events


class _DeferredTool(BaseTool):
    def __init__(self):
        super().__init__(name="deferred", description="A deferred tool")
        self._defers_response = True

    def _get_declaration(self):
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(type=types.Type.OBJECT),
        )

    async def run_async(self, *, args, tool_context):
        return None


class _SlowTool(BaseTool):
    def __init__(self):
        super().__init__(name="slow", description="A slow tool")

    def _get_declaration(self):
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(type=types.Type.OBJECT),
        )

    async def run_async(self, *, args, tool_context):
        await asyncio.sleep(0.1)
        return {"completed": True}


class _FailingTool(BaseTool):
    def __init__(self):
        super().__init__(name="failing", description="A failing tool")

    def _get_declaration(self):
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(type=types.Type.OBJECT),
        )

    async def run_async(self, *, args, tool_context):
        raise RuntimeError(str(args["secret"]))


def _ctx(agent, *events, user_content=None) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-1",
        agent=agent,
        user_content=user_content,
        session=Session(
            id="session-1",
            appName="app",
            userId="user",
            state={},
            events=list(events),
        ),
    )


def _event(author: str, *parts: types.Part):
    return SimpleNamespace(
        author=author,
        content=types.Content(
            role="user" if author == "user" else "model", parts=list(parts)
        ),
    )


def test_codex_runtime_defaults_are_fail_closed() -> None:
    config = CodexRuntimeConfig()
    assert config.approval_mode == "deny_all"
    assert config.sandbox == "workspace_write"
    assert config.network_access is False
    assert config.reuse_workspace is False


def test_codex_subprocess_masks_host_credentials(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "host-secret")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "host-access-key")
    monkeypatch.setenv("PATH", "/usr/bin")

    env = codex_subprocess_env(str(tmp_path), "opaque-turn-token")

    assert env["OPENAI_API_KEY"] == ""
    assert env["AWS_ACCESS_KEY_ID"] == ""
    assert "PATH" not in env
    assert env["VEADK_CODEX_API_KEY"] == "opaque-turn-token"


def test_codex_home_escapes_untrusted_toml_values() -> None:
    encoded = toml_string('model"\\nfull_access = true')

    assert encoded == '"model\\"\\\\nfull_access = true"'
    assert "\n" not in encoded


def test_structured_prompt_preserves_tool_history() -> None:
    user = types.Content(role="user", parts=[types.Part(text="what happened?")])
    ctx = SimpleNamespace(
        user_content=user,
        session=SimpleNamespace(
            events=[
                _event("user", types.Part(text="run it")),
                _event(
                    "assistant",
                    types.Part(
                        function_call=types.FunctionCall(
                            id="call-1", name="lookup", args={"q": "veadk"}
                        )
                    ),
                ),
                _event(
                    "assistant",
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="call-1",
                            name="lookup",
                            response={"result": "ok"},
                        )
                    ),
                ),
                _event("user", types.Part(text="what happened?")),
            ]
        ),
    )

    prompt = build_prompt(ctx)

    assert '"type":"function_call"' in prompt
    assert '"type":"function_response"' in prompt
    assert "what happened?" in prompt
    assert "# System instructions" not in prompt


def test_structured_prompt_hides_auth_and_confirmation_payloads() -> None:
    current = types.Content(
        role="user",
        parts=[
            types.Part(
                function_response=types.FunctionResponse(
                    id="auth-1",
                    name="adk_request_credential",
                    response={"apiKey": "do-not-send-to-model"},
                )
            )
        ],
    )
    ctx = SimpleNamespace(
        user_content=current,
        session=SimpleNamespace(
            events=[
                _event(
                    "agent",
                    types.Part(
                        function_call=types.FunctionCall(
                            id="auth-1",
                            name="adk_request_credential",
                            args={"authConfig": {"credentialKey": "key"}},
                        )
                    ),
                ),
                _event(
                    "user",
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="auth-1",
                            name="adk_request_credential",
                            response={"apiKey": "do-not-send-to-model"},
                        )
                    ),
                ),
                _event("agent", types.Part(text="credential accepted")),
            ]
        ),
    )

    prompt = build_prompt(ctx)

    assert "do-not-send-to-model" not in prompt
    assert "adk_request_credential" not in prompt
    assert "credential accepted" in prompt


def test_inline_attachment_is_materialized_only_in_workspace(tmp_path) -> None:
    content = types.Content(
        role="user",
        parts=[
            types.Part(
                inline_data=types.Blob(mime_type="image/png", data=b"image-bytes")
            )
        ],
    )
    ctx = SimpleNamespace(user_content=content)

    attachments = build_input_attachments(ctx, str(tmp_path))

    assert attachments == [
        {
            "kind": "local_image",
            "name": "attachment-0.png",
            "value": str(tmp_path / "attachment-0.png"),
        }
    ]
    assert (tmp_path / "attachment-0.png").read_bytes() == b"image-bytes"


def test_native_tool_lifecycle_emits_start_delta_and_complete_once() -> None:
    item = {
        "id": "cmd-1",
        "type": "commandExecution",
        "command": "pwd",
        "cwd": "/workspace",
        "status": "inProgress",
    }
    started = type(
        "ItemStartedNotification",
        (),
        {"model_dump": lambda self: {"item": item}},
    )()
    delta = type(
        "CommandExecutionOutputDeltaNotification",
        (),
        {"model_dump": lambda self: {"item_id": "cmd-1", "delta": "/workspace\n"}},
    )()
    completed_item = {
        **item,
        "status": "completed",
        "aggregated_output": "/workspace\n",
        "exit_code": 0,
    }
    completed = type(
        "ItemCompletedNotification",
        (),
        {"model_dump": lambda self: {"item": completed_item}},
    )()
    active: set[str] = set()

    start_events = notification_to_events(
        started, "agent", "inv", active_tool_items=active
    )
    delta_events = notification_to_events(
        delta, "agent", "inv", active_tool_items=active
    )
    complete_events = notification_to_events(
        completed, "agent", "inv", active_tool_items=active
    )

    assert start_events[0].get_function_calls()[0].id == "cmd-1"
    assert start_events[0].custom_metadata["codex_event_type"] == "item_started"
    assert delta_events[0].partial is True
    assert delta_events[0].custom_metadata["codex_event_type"] == "command_output"
    assert not complete_events[0].get_function_calls()
    assert complete_events[0].get_function_responses()[0].id == "cmd-1"
    assert complete_events[0].custom_metadata["codex_event_type"] == "item_completed"
    assert active == set()


def test_native_plan_error_and_turn_complete_are_observable() -> None:
    plan = type(
        "TurnPlanUpdatedNotification",
        (),
        {
            "model_dump": lambda self: {
                "explanation": "working",
                "plan": [{"step": "test", "status": "inProgress"}],
            }
        },
    )()
    error = type(
        "ErrorNotification",
        (),
        {
            "model_dump": lambda self: {
                "error": {"code": "backend", "message": "retrying"},
                "will_retry": True,
            }
        },
    )()
    completed = type(
        "TurnCompletedNotification",
        (),
        {
            "model_dump": lambda self: {
                "turn": {"id": "turn-1", "status": "completed", "error": None}
            }
        },
    )()

    plan_event = notification_to_events(plan, "agent", "inv")[0]
    error_event = notification_to_events(error, "agent", "inv")[0]
    complete_event = notification_to_events(completed, "agent", "inv")[0]

    assert plan_event.custom_metadata["plan"][0]["step"] == "test"
    assert error_event.error_code == "backend"
    assert error_event.custom_metadata["will_retry"] is True
    assert complete_event.turn_complete is True
    assert complete_event.custom_metadata["turn_id"] == "turn-1"


def test_native_token_usage_is_observable() -> None:
    usage = type(
        "ThreadTokenUsageUpdatedNotification",
        (),
        {
            "model_dump": lambda self: {
                "turn_id": "turn-1",
                "token_usage": {
                    "last": {"input_tokens": 10, "output_tokens": 4},
                    "total": {"input_tokens": 10, "output_tokens": 4},
                },
            }
        },
    )()

    event = notification_to_events(usage, "agent", "inv")[0]

    assert event.custom_metadata["codex_event_type"] == "token_usage"
    assert event.custom_metadata["token_usage"]["total"]["output_tokens"] == 4


@pytest.mark.asyncio
async def test_dynamic_instruction_is_resolved_outside_user_prompt() -> None:
    async def instruction(readonly_context):
        return f"Tenant is {readonly_context.state['tenant']}."

    agent = LlmAgent(
        name="agent",
        description="A test agent.",
        model="gemini-2.5-flash",
        instruction=instruction,
    )
    ctx = _ctx(agent)
    ctx.session.state["tenant"] = "acme"

    base, developer = await resolve_system_append(agent, ctx)

    assert "Your name is agent." in base
    assert "A test agent." in base
    assert developer == "Tenant is acme."


@pytest.mark.asyncio
async def test_tool_executor_runs_adk_callbacks_and_persists_state_delta() -> None:
    callback_order: list[str] = []
    emitted = []

    def update(value: int, tool_context: ToolContext):
        callback_order.append("tool")
        tool_context.state["updated"] = value
        return {"value": value}

    async def before_tool_callback(tool, args, tool_context):
        callback_order.append("before")

    async def after_tool_callback(tool, args, tool_context, tool_response):
        callback_order.append("after")

    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[update],
        before_tool_callback=before_tool_callback,
        after_tool_callback=after_tool_callback,
    )
    ctx = _ctx(agent)

    async def sink(event):
        emitted.append(event)

    bundle = await build_executable_tools(agent, ctx, event_sink=sink)
    output = await bundle.executors["update"]({"value": 7}, "call-7")

    assert json.loads(output) == {"value": 7}
    assert callback_order == ["before", "tool", "after"]
    assert len(emitted) == 2
    assert emitted[0].get_function_calls()[0].id == "call-7"
    assert emitted[1].actions.state_delta == {"updated": 7}
    assert emitted[1].get_function_responses()[0].id == "call-7"


@pytest.mark.asyncio
async def test_tool_confirmation_fails_closed_before_side_effect() -> None:
    called = False
    emitted = []

    def destructive_action(path: str):
        nonlocal called
        called = True
        return {"deleted": path}

    tool = FunctionTool(destructive_action, require_confirmation=True)
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[tool],
    )
    ctx = _ctx(agent)

    async def sink(event):
        emitted.append(event)

    bundle = await build_executable_tools(agent, ctx, event_sink=sink)
    output = json.loads(
        await bundle.executors["destructive_action"](
            {"path": "/important"}, "call-confirm"
        )
    )

    assert called is False
    assert output["status"] == "confirmation_required"
    assert emitted[-1].actions.requested_tool_confirmations
    assert any(
        call.name == "adk_request_confirmation"
        for event in emitted
        for call in event.get_function_calls()
    )


@pytest.mark.asyncio
async def test_confirmed_tool_resumes_once_on_next_invocation() -> None:
    calls: list[str] = []

    def destructive_action(path: str):
        calls.append(path)
        return {"deleted": path}

    tool = FunctionTool(destructive_action, require_confirmation=True)
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[tool],
    )
    first_ctx = _ctx(agent)
    emitted = []

    async def sink(event):
        emitted.append(event)

    first_bundle = await build_executable_tools(agent, first_ctx, event_sink=sink)
    await first_bundle.executors["destructive_action"](
        {"path": "/important"}, "call-confirm"
    )
    confirmation_call = next(
        call
        for event in emitted
        for call in event.get_function_calls()
        if call.name == "adk_request_confirmation"
    )
    confirmation_response = Event(
        invocation_id="inv-2",
        author="user",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=confirmation_call.id,
                        name="adk_request_confirmation",
                        response={"confirmed": True},
                    )
                )
            ],
        ),
    )
    history = [*emitted, confirmation_response]
    second_ctx = _ctx(agent, *history)
    second_bundle = await build_executable_tools(agent, second_ctx)

    resumed = await resume_confirmed_tools(second_bundle, second_ctx)

    assert calls == ["/important"]
    assert resumed[-1].get_function_responses()[0].id == "call-confirm"
    second_ctx.session.events.extend(resumed)
    assert await resume_confirmed_tools(second_bundle, second_ctx) == []
    assert calls == ["/important"]


@pytest.mark.asyncio
async def test_authenticated_tool_stores_credential_and_resumes() -> None:
    received_credentials = []
    auth_config = AuthConfig(
        auth_scheme=APIKey.model_validate(
            {"name": "x-api-key", "in": APIKeyIn.header, "type": "apiKey"}
        ),
        credential_key="codex-test-key",
    )

    def protected_action(tool_context: ToolContext):
        credential = tool_context.get_auth_response(auth_config)
        if credential is None:
            tool_context.request_credential(auth_config)
            return {"status": "authentication_required"}
        received_credentials.append(credential.api_key)
        return {"authenticated": True}

    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[protected_action],
    )
    first_ctx = _ctx(agent)
    emitted = []

    async def sink(event):
        emitted.append(event)

    first_bundle = await build_executable_tools(agent, first_ctx, event_sink=sink)
    output = json.loads(
        await first_bundle.executors["protected_action"]({}, "call-auth")
    )
    assert output["status"] == "authentication_required"
    auth_call = next(
        call
        for event in emitted
        for call in event.get_function_calls()
        if call.name == "adk_request_credential"
    )
    auth_response = Event(
        invocation_id="inv-2",
        author="user",
        content=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=auth_call.id,
                        name="adk_request_credential",
                        response=AuthConfig(
                            auth_scheme=auth_config.auth_scheme,
                            exchanged_auth_credential=AuthCredential(
                                auth_type=AuthCredentialTypes.API_KEY,
                                api_key="secret",
                            ),
                        ).model_dump(exclude_none=True, by_alias=True),
                    )
                )
            ],
        ),
    )
    second_ctx = _ctx(agent, *emitted, auth_response)
    second_bundle = await build_executable_tools(agent, second_ctx)

    resumed = await resume_authenticated_tools(second_bundle, second_ctx)

    assert received_credentials == ["secret"]
    assert resumed[-1].get_function_responses()[0].id == "call-auth"
    assert resumed[-1].get_function_responses()[0].response == {"authenticated": True}


@pytest.mark.asyncio
async def test_long_running_tool_returns_pending_and_marks_call() -> None:
    emitted = []
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[_DeferredTool()],
    )
    ctx = _ctx(agent)

    async def sink(event):
        emitted.append(event)

    bundle = await build_executable_tools(agent, ctx, event_sink=sink)
    output = json.loads(await bundle.executors["deferred"]({}, "call-deferred"))

    assert output == {"status": "pending", "call_id": "call-deferred"}
    assert emitted[0].long_running_tool_ids == {"call-deferred"}


@pytest.mark.asyncio
async def test_tool_timeout_is_an_event_and_structured_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[_SlowTool()],
    )
    ctx = _ctx(agent)
    emitted = []
    tool_logger = logging.getLogger("veadk.runtime.codex.tools_bridge")
    tool_logger.addHandler(caplog.handler)
    tool_logger.setLevel(logging.DEBUG)

    async def sink(event):
        emitted.append(event)

    try:
        bundle = await build_executable_tools(
            agent, ctx, event_sink=sink, timeout_seconds=0.01
        )
        output = json.loads(await bundle.executors["slow"]({}, "call-timeout"))
    finally:
        tool_logger.removeHandler(caplog.handler)

    assert output["status"] == "failed"
    assert "timed out" in output["error"].lower()
    assert emitted[-1].get_function_responses()[0].id == "call-timeout"
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "codex_tool_timeout" in messages
    assert "invocation_id=inv-1" in messages
    assert "call_id=call-timeout" in messages
    assert "status=failed" in messages


@pytest.mark.asyncio
async def test_tool_logs_do_not_include_arguments_or_error_secrets(
    caplog: pytest.LogCaptureFixture,
) -> None:
    secret = "super-secret-tool-argument"
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[_FailingTool()],
    )
    ctx = _ctx(agent)
    tool_logger = logging.getLogger("veadk.runtime.codex.tools_bridge")
    tool_logger.addHandler(caplog.handler)
    tool_logger.setLevel(logging.DEBUG)

    try:
        bundle = await build_executable_tools(agent, ctx)
        output = json.loads(
            await bundle.executors["failing"]({"secret": secret}, "call-failure")
        )
    finally:
        tool_logger.removeHandler(caplog.handler)

    assert output["status"] == "failed"
    assert secret in output["error"]
    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "codex_tool_failed" in messages
    assert "error_type=RuntimeError" in messages
    assert secret not in messages


@pytest.mark.asyncio
async def test_tool_executor_supports_stdio_mcp_toolset() -> None:
    from google.adk.tools.mcp_tool.mcp_session_manager import StdioServerParameters
    from google.adk.tools.mcp_tool.mcp_toolset import MCPToolset

    server = (
        Path(__file__).resolve().parents[3]
        / "examples"
        / "piagent_with_mcp"
        / "mcp_order_server.py"
    )
    toolset = MCPToolset(
        connection_params=StdioServerParameters(
            command=sys.executable,
            args=[str(server)],
        )
    )
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        tools=[toolset],
    )
    ctx = _ctx(agent)

    bundle = await build_executable_tools(agent, ctx)
    try:
        output = json.loads(
            await bundle.executors["get_order_status"](
                {"order_id": "A10086"}, "call-mcp"
            )
        )
        assert output["structuredContent"]["status"] == "paid"
    finally:
        await close_toolsets(bundle.opened_toolsets)


@pytest.mark.asyncio
async def test_transfer_tool_executor_emits_adk_transfer_action() -> None:
    worker = LlmAgent(name="worker", model="gemini-2.5-flash")
    agent = LlmAgent(
        name="agent",
        model="gemini-2.5-flash",
        sub_agents=[worker],
    )
    ctx = _ctx(agent)
    emitted: list[Event] = []

    async def emit(event: Event) -> None:
        emitted.append(event)

    bundle = await build_executable_tools(agent, ctx, event_sink=emit)
    try:
        add_tool_to_bundle(
            bundle,
            build_transfer_tool([worker]),
            ctx,
            event_sink=emit,
        )
        output = json.loads(
            await bundle.executors["transfer_to_agent"](
                {"agent_name": "worker"}, "call-transfer"
            )
        )
    finally:
        await close_toolsets(bundle.opened_toolsets)

    assert output["status"] == "transferred"
    assert output["agent_name"] == "worker"
    assert bundle.specs[0]["parameters"]["properties"]["agent_name"]["enum"] == [
        "worker"
    ]
    assert any(event.actions.transfer_to_agent == "worker" for event in emitted)


@pytest.mark.asyncio
async def test_shim_routes_concurrent_turns_to_their_own_executors(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    calls: list[tuple[str, str]] = []

    async def executor_a(args, call_id):
        await asyncio.sleep(0.01)
        calls.append(("a", call_id))
        return json.dumps({"owner": "a"})

    async def executor_b(args, call_id):
        calls.append(("b", call_id))
        return json.dumps({"owner": "b"})

    token_a = shim.register_turn(
        [{"type": "function", "name": "tool_a", "parameters": {}}],
        {"tool_a": executor_a},
    )
    token_b = shim.register_turn(
        [{"type": "function", "name": "tool_b", "parameters": {}}],
        {"tool_b": executor_b},
    )

    async def fake_aresponses(**kwargs):
        conversation = kwargs["input"]
        if any(item.get("type") == "function_call_output" for item in conversation):
            return {
                "id": "resp-final",
                "model": "model",
                "output": [
                    {
                        "id": "msg",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "done"}],
                    }
                ],
            }
        tool = next(
            item for item in kwargs["tools"] if item["name"] in {"tool_a", "tool_b"}
        )
        suffix = tool["name"][-1]
        return {
            "id": f"resp-{suffix}",
            "model": "model",
            "output": [
                {
                    "id": f"fc-{suffix}",
                    "call_id": f"call-{suffix}",
                    "type": "function_call",
                    "name": tool["name"],
                    "arguments": "{}",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", fake_aresponses)
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        body = {
            "model": "model",
            "stream": False,
            "input": [{"type": "message", "role": "user", "content": "go"}],
        }
        response_a, response_b = await asyncio.gather(
            client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {token_a}"},
                json=body,
            ),
            client.post(
                "/v1/responses",
                headers={"Authorization": f"Bearer {token_b}"},
                json=body,
            ),
        )

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert sorted(calls) == [("a", "call-a"), ("b", "call-b")]


@pytest.mark.asyncio
async def test_shim_rejects_unknown_invocation_token() -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": "Bearer unknown"},
            json={"model": "model", "input": []},
        )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_shim_completes_turn_after_transfer_without_second_model_call(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    backend_calls = 0

    async def executor(args, call_id):
        return json.dumps(
            {
                "status": "transferred",
                "call_id": call_id,
                "agent_name": args["agent_name"],
            }
        )

    token = shim.register_turn(
        [{"type": "function", "name": "transfer_to_agent", "parameters": {}}],
        {"transfer_to_agent": executor},
    )

    async def fake_aresponses(**kwargs):
        nonlocal backend_calls
        backend_calls += 1
        assert not any(
            item.get("type") == "function_call_output" for item in kwargs["input"]
        )
        return {
            "id": "transfer-response",
            "model": "model",
            "output": [
                {
                    "id": "fc-transfer",
                    "call_id": "call-transfer",
                    "type": "function_call",
                    "name": "transfer_to_agent",
                    "arguments": json.dumps({"agent_name": "worker"}),
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", fake_aresponses)
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "model",
                "input": [{"type": "message", "role": "user", "content": "go"}],
            },
        )

    assert response.status_code == 200
    assert backend_calls == 1
    body = response.json()
    assert body["status"] == "completed"
    assert body["output"][0]["type"] == "message"


@pytest.mark.asyncio
async def test_shim_reports_tool_iteration_budget_instead_of_dropping_call(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")

    async def executor(args, call_id):
        return "{}"

    token = shim.register_turn(
        [{"type": "function", "name": "loop", "parameters": {}}],
        {"loop": executor},
        max_tool_iterations=1,
    )

    async def always_calls_tool(**kwargs):
        return {
            "id": "resp",
            "model": "model",
            "output": [
                {
                    "id": "fc",
                    "call_id": "call-loop",
                    "type": "function_call",
                    "name": "loop",
                    "arguments": "{}",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr(
        "veadk.runtime.codex.proxy.litellm.aresponses", always_calls_tool
    )
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "model": "model",
                "input": [{"type": "message", "role": "user", "content": "go"}],
            },
        )

    assert response.status_code == 409
    assert response.json()["error"]["type"] == "tool_iteration_limit"


@pytest.mark.asyncio
async def test_shim_rejects_invalid_tool_json_without_calling_executor(
    monkeypatch,
) -> None:
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    called = False

    async def executor(args, call_id):
        nonlocal called
        called = True
        return "{}"

    token = shim.register_turn(
        [{"type": "function", "name": "parse", "parameters": {}}],
        {"parse": executor},
    )

    async def fake_aresponses(**kwargs):
        if any(item.get("type") == "function_call_output" for item in kwargs["input"]):
            return {
                "id": "final",
                "model": "model",
                "output": [
                    {
                        "id": "msg",
                        "type": "message",
                        "role": "assistant",
                        "status": "completed",
                        "content": [{"type": "output_text", "text": "handled"}],
                    }
                ],
            }
        return {
            "id": "tool",
            "model": "model",
            "output": [
                {
                    "id": "fc",
                    "call_id": "call-invalid",
                    "type": "function_call",
                    "name": "parse",
                    "arguments": "{not-json",
                    "status": "completed",
                }
            ],
        }

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", fake_aresponses)
    transport = httpx.ASGITransport(app=shim._app)
    async with httpx.AsyncClient(transport=transport, base_url="http://shim") as client:
        response = await client.post(
            "/v1/responses",
            headers={"Authorization": f"Bearer {token}"},
            json={"model": "model", "input": []},
        )

    assert response.status_code == 200
    assert called is False
