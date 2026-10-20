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
import builtins
import importlib
import json
import logging
import re
import sys
import threading
import types as py_types
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, ClassVar

import pytest
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.invocation_context import InvocationContext
from google.adk.events.event import Event
from google.adk.models.llm_response import LlmResponse
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session
from google.genai import types

from veadk import Agent


@dataclass
class _FakeRunResult:
    session_id: str
    final_response: str
    finish_reason: str | None = None
    events: list[dict[str, Any]] | None = None
    notifications: list[Any] | None = None


class _FakeDeepSeekHarnessConfig:
    def __init__(self, **kwargs: Any) -> None:
        self.__dict__.update(kwargs)


class _FakeDeepSeekHarness:
    instances: ClassVar[list[_FakeDeepSeekHarness]] = []
    call_tool: ClassVar[dict[str, Any] | None] = None
    notification_events: ClassVar[list[dict[str, Any]]] = []
    result_events: ClassVar[list[dict[str, Any]]] = []
    final_response: ClassVar[str | None] = None
    run_started: ClassVar[threading.Event | None] = None
    block_until: ClassVar[threading.Event | None] = None

    def __init__(self, config: _FakeDeepSeekHarnessConfig) -> None:
        self.config = config
        self.calls: list[tuple[str, str | None]] = []
        self.closed = False
        type(self).instances.append(self)

    def run(
        self,
        prompt: str,
        *,
        session_id: str | None = None,
        on_notification=None,
    ) -> _FakeRunResult:
        self.calls.append((prompt, session_id))
        if type(self).run_started is not None:
            type(self).run_started.set()
        if type(self).block_until is not None:
            type(self).block_until.wait(timeout=5)
        if on_notification is not None:
            for event in type(self).notification_events:
                on_notification(
                    py_types.SimpleNamespace(
                        method="session.event",
                        payload={"sessionId": session_id, "event": event},
                    )
                )
        if type(self).call_tool is not None:
            tool_result = _call_generated_tool_bridge(
                self.config.patches,
                type(self).call_tool,
            )
            return _FakeRunResult(
                session_id=session_id or "generated",
                final_response=f"tool result: {tool_result}",
                events=list(type(self).result_events),
                notifications=[],
            )
        return _FakeRunResult(
            session_id=session_id or "generated",
            final_response=type(self).final_response
            or f"dsh reply for {len(self.calls)}",
            events=list(type(self).result_events),
            notifications=[],
        )

    def close(self) -> None:
        self.closed = True


@pytest.fixture()
def fake_dsh(monkeypatch: pytest.MonkeyPatch):
    module = py_types.ModuleType("deepseek_harness")
    module.DeepSeekHarness = _FakeDeepSeekHarness
    module.DeepSeekHarnessConfig = _FakeDeepSeekHarnessConfig
    module.RunResult = _FakeRunResult
    _FakeDeepSeekHarness.instances.clear()
    _FakeDeepSeekHarness.call_tool = None
    _FakeDeepSeekHarness.notification_events = []
    _FakeDeepSeekHarness.result_events = []
    _FakeDeepSeekHarness.final_response = None
    _FakeDeepSeekHarness.run_started = None
    _FakeDeepSeekHarness.block_until = None
    monkeypatch.setitem(sys.modules, "deepseek_harness", module)
    _drop_runtime_modules()
    yield _FakeDeepSeekHarness
    _cleanup_runtime_module()
    _drop_runtime_modules()


def test_get_runtime_reports_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    import veadk.runtime as runtime_module

    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "deepseek_harness":
            raise ModuleNotFoundError(
                "No module named 'deepseek_harness'",
                name="deepseek_harness",
            )
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.delitem(sys.modules, "deepseek_harness", raising=False)
    _drop_runtime_modules()
    runtime_module.get_runtime.cache_clear()

    with pytest.raises(ImportError) as exc_info:
        runtime_module.get_runtime("dsh")

    message = str(exc_info.value)
    assert "dsh" in message
    assert 'pip install "veadk-python[dsh]"' in message


def test_get_runtime_returns_deepseek_harness_runtime(fake_dsh) -> None:
    import veadk.runtime as runtime_module

    runtime_module.get_runtime.cache_clear()
    runtime = runtime_module.get_runtime("dsh")

    assert runtime.name == "dsh"
    assert fake_dsh.instances == []


@pytest.mark.asyncio
async def test_runtime_uses_explicit_generated_dsh_home_and_final_event(
    fake_dsh,
) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent()
    ctx = _ctx(agent, text="hello DSH")

    events = [event async for event in runtime.run_async(agent, ctx)]

    assert len(events) == 1
    assert events[0].is_final_response()
    assert events[0].content.parts[0].text == "dsh reply for 1"
    harness = fake_dsh.instances[0]
    assert harness.config.dsh_home
    assert harness.config.model == "deepseek-test-model"
    assert harness.config.profile == "sdk-minimal"
    assert harness.config.base_url == "https://deepseek.example/v1"
    assert harness.config.api_key == "test-api-key"
    assert "hello DSH" in harness.calls[0][0]


@pytest.mark.asyncio
async def test_runtime_reuses_manager_and_stable_session_id(fake_dsh) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent()

    first = _ctx(agent, text="first")
    second = _ctx(agent, text="second")
    other = _ctx(agent, session_id="session-2", text="other")

    assert [event async for event in runtime.run_async(agent, first)]
    assert [event async for event in runtime.run_async(agent, second)]
    assert [event async for event in runtime.run_async(agent, other)]

    assert len(fake_dsh.instances) == 1
    calls = fake_dsh.instances[0].calls
    assert calls[0][1] == calls[1][1]
    assert calls[2][1] != calls[0][1]


@pytest.mark.asyncio
async def test_before_model_callback_short_circuits_without_starting_dsh(
    fake_dsh,
) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()

    def before_model_callback(*, callback_context, llm_request):
        assert callback_context is not None
        assert llm_request.model == "deepseek-test-model"
        return LlmResponse(
            content=types.Content(
                role="model",
                parts=[types.Part(text="callback answer")],
            )
        )

    agent = _agent(before_model_callback=before_model_callback)
    ctx = _ctx(agent)

    events = [event async for event in runtime.run_async(agent, ctx)]

    assert events[0].content.parts[0].text == "callback answer"
    assert fake_dsh.instances == []


@pytest.mark.asyncio
async def test_before_model_callback_can_change_model(fake_dsh) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()

    def before_model_callback(*, callback_context, llm_request):
        assert callback_context is not None
        llm_request.model = "callback-selected-model"

    agent = _agent(before_model_callback=before_model_callback)
    ctx = _ctx(agent)

    assert [event async for event in runtime.run_async(agent, ctx)]

    harness = fake_dsh.instances[0]
    assert harness.config.model == "callback-selected-model"


@pytest.mark.asyncio
async def test_runtime_maps_provider_aliases(fake_dsh) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent(
        deepseek_harness_runtime_config={
            "provider": "volcengine",
            "model": "deepseek-v4-flash-260425",
        }
    )
    ctx = _ctx(agent)

    assert [event async for event in runtime.run_async(agent, ctx)]

    harness = fake_dsh.instances[0]
    assert harness.config.provider == "deepseek-official"
    assert harness.config.model == "deepseek-v4-flash-260425"

    assert runtime_module._dsh_provider("openai") == "deepseek-official"
    assert runtime_module._dsh_provider("OpenAI") == "deepseek-official"
    assert runtime_module._dsh_provider("third-party") == "deepseek-official"
    assert runtime_module._dsh_provider("") == "deepseek-official"
    assert runtime_module._dsh_provider("deepseek-official") == "deepseek-official"


def test_config_accepts_blank_provider() -> None:
    from veadk.runtime.deepseek_harness.config import DeepSeekHarnessRuntimeConfig

    assert DeepSeekHarnessRuntimeConfig(provider="").provider == "deepseek-official"
    assert DeepSeekHarnessRuntimeConfig(provider=None).provider == "deepseek-official"


@pytest.mark.asyncio
async def test_runtime_serializes_adk_session_history(fake_dsh) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent()
    history = [
        Event(
            invocation_id="old-1",
            author="user",
            content=types.Content(
                role="user",
                parts=[types.Part(text="remember alpha")],
            ),
        ),
        Event(
            invocation_id="old-1",
            author=agent.name,
            content=types.Content(
                role="model",
                parts=[types.Part(text="alpha remembered")],
            ),
        ),
    ]
    ctx = _ctx(agent, text="what did I ask you to remember?", events=history)

    assert [event async for event in runtime.run_async(agent, ctx)]

    prompt = fake_dsh.instances[0].calls[0][0]
    assert "<conversation_history>" in prompt
    assert "remember alpha" in prompt
    assert "alpha remembered" in prompt
    assert "<current_message>" in prompt
    assert "what did I ask you to remember?" in prompt


def test_config_env_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    from veadk.runtime.deepseek_harness.config import DeepSeekHarnessRuntimeConfig

    monkeypatch.setenv("VEADK_DEEPSEEK_HARNESS_MODEL", "env-model")
    monkeypatch.setenv("VEADK_DEEPSEEK_HARNESS_MAX_TOKENS", "123")
    monkeypatch.setenv("VEADK_DEEPSEEK_HARNESS_PROFILE", "sdk-minimal")

    config = DeepSeekHarnessRuntimeConfig.from_agent(
        py_types.SimpleNamespace(
            deepseek_harness_runtime_config={
                "model": "agent-model",
                "max_tokens": 99,
            }
        )
    )

    assert config.model == "env-model"
    assert config.max_tokens == 123
    assert config.profile == "sdk-minimal"


@pytest.mark.asyncio
async def test_runtime_bridges_adk_function_tools(fake_dsh, caplog) -> None:
    from google.adk.tools.function_tool import FunctionTool

    def sample_tool(value: str) -> dict[str, str]:
        return {"echo": value}

    caplog.set_level(logging.DEBUG, logger="veadk.runtime.piagent.tools_bridge")
    fake_dsh.call_tool = {
        "toolName": "sample_tool",
        "toolCallId": "call-1",
        "args": {"value": "from-dsh"},
    }
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent(tools=[FunctionTool(sample_tool)])
    ctx = _ctx(agent)

    events = [event async for event in runtime.run_async(agent, ctx)]

    assert events[-1].is_final_response()
    assert '"echo":"from-dsh"' in events[-1].content.parts[0].text
    harness = fake_dsh.instances[0]
    assert harness.config.patches
    plugin = _plugin_path_from_patch(harness.config.patches[-1])
    plugin_text = plugin.read_text(encoding="utf-8")
    assert "defineTool" in plugin_text
    assert "sample_tool" in plugin_text

    function_response_events = [
        event
        for event in events
        if event.content
        and event.content.parts
        and event.content.parts[0].function_response
    ]
    assert function_response_events

    messages = "\n".join(record.getMessage() for record in caplog.records)
    assert "dsh: bridging 1 agent tool(s): ['sample_tool']" in messages
    assert "dsh_tool_start invocation_id=inv-1" in messages
    assert "dsh_tool_complete invocation_id=inv-1" in messages
    assert "piagent: bridging" not in messages
    assert "piagent_tool_start" not in messages
    assert "piagent_tool_complete" not in messages


def test_schema_to_dsh_value_preserves_default_additional_properties(fake_dsh) -> None:
    tool_runtime = importlib.import_module(
        "veadk.runtime.deepseek_harness.tool_runtime"
    )

    rendered = tool_runtime._schema_to_dsh_value(
        {
            "type": "object",
            "properties": {"value": {"type": "string"}},
        }
    )
    explicit_false = tool_runtime._schema_to_dsh_value(
        {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        }
    )
    schema_additional = tool_runtime._schema_to_dsh_value(
        {
            "type": "object",
            "properties": {},
            "additionalProperties": {"type": "string"},
        }
    )

    assert "additionalProperties" not in rendered
    assert explicit_false["additionalProperties"] is False
    assert schema_additional["additionalProperties"] == {"type": "string"}


@pytest.mark.asyncio
async def test_runtime_uses_process_private_tool_plugin_with_persistent_home(
    fake_dsh,
    tmp_path,
) -> None:
    from google.adk.tools.function_tool import FunctionTool

    def sample_tool(value: str) -> dict[str, str]:
        return {"echo": value}

    persistent_home = tmp_path / "persistent-dsh-home"
    fake_dsh.call_tool = {
        "toolName": "sample_tool",
        "toolCallId": "call-1",
        "args": {"value": "from-dsh"},
    }
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent(
        tools=[FunctionTool(sample_tool)],
        deepseek_harness_runtime_config={"dsh_home": str(persistent_home)},
    )
    ctx = _ctx(agent)

    assert [event async for event in runtime.run_async(agent, ctx)]

    harness = fake_dsh.instances[0]
    plugin = _plugin_path_from_patch(harness.config.patches[-1])
    assert harness.config.dsh_home == str(persistent_home.resolve())
    assert not plugin.is_relative_to(persistent_home)
    assert "veadk-deepseek-harness-tools-" in str(plugin)


@pytest.mark.asyncio
async def test_persistent_dsh_home_manager_registers_process_cleanup(
    fake_dsh,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    registered = []

    monkeypatch.setattr(runtime_module.atexit, "register", registered.append)
    runtime_module._cleanup_registered = False
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent(
        deepseek_harness_runtime_config={"dsh_home": str(tmp_path / "persistent-home")}
    )
    ctx = _ctx(agent)

    assert [event async for event in runtime.run_async(agent, ctx)]

    assert registered == [runtime_module._cleanup_runtime_state]


@pytest.mark.asyncio
async def test_runtime_cancellation_does_not_close_shared_manager(fake_dsh) -> None:
    fake_dsh.run_started = threading.Event()
    fake_dsh.block_until = threading.Event()
    runtime = importlib.import_module(
        "veadk.runtime.deepseek_harness.runtime"
    ).DeepSeekHarnessRuntime()
    agent = _agent()
    ctx = _ctx(agent)

    async def _consume() -> list[Event]:
        return [event async for event in runtime.run_async(agent, ctx)]

    task = asyncio.create_task(_consume())
    assert await asyncio.to_thread(fake_dsh.run_started.wait, 5)
    task.cancel()
    await asyncio.sleep(0.05)

    assert not fake_dsh.instances[0].closed
    assert not task.done()

    fake_dsh.block_until.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert not fake_dsh.instances[0].closed


@pytest.mark.asyncio
async def test_runtime_runs_transferred_agent_and_suppresses_dsh_final(
    fake_dsh,
) -> None:
    worker = _TextAgent(name="worker", marker="worker handled it")
    fake_dsh.call_tool = {
        "toolName": "transfer_to_agent",
        "toolCallId": "transfer-1",
        "args": {"agent_name": "worker"},
    }
    fake_dsh.final_response = "root text should not leak"
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent(
        description="Routes specialist work.",
        instruction="Transfer implementation work to worker.",
        sub_agents=[worker],
    )
    ctx = _ctx(agent)

    events = [event async for event in runtime.run_async(agent, ctx)]
    function_calls = [
        part.function_call
        for event in events
        for part in (event.content.parts if event.content else [])
        if part.function_call
    ]
    texts = [
        part.text
        for event in events
        for part in (event.content.parts if event.content else [])
        if part.text
    ]

    assert [call.name for call in function_calls] == ["transfer_to_agent"]
    assert any(event.actions.transfer_to_agent == "worker" for event in events)
    assert any(event.author == "worker" for event in events)
    assert "worker handled it" in texts
    assert "root text should not leak" not in texts
    assert ctx._invocation_cost_manager._number_of_llm_calls == 0


@pytest.mark.asyncio
async def test_runtime_maps_dsh_partial_and_native_tool_events(fake_dsh) -> None:
    fake_dsh.notification_events = [
        {
            "seq": 1,
            "type": "agent/assistant-stream",
            "data": {
                "frame": {
                    "type": "chunk",
                    "chunk": {"type": "text-delta", "text": "streamed "},
                }
            },
        }
    ]
    fake_dsh.result_events = [
        {
            "seq": 2,
            "type": "tool/call",
            "data": {
                "callId": "native-1",
                "name": "skill",
                "arguments": '{"name":"demo-skill"}',
            },
        },
        {
            "seq": 3,
            "type": "tool/result",
            "data": {
                "message": {
                    "toolCallId": "native-1",
                    "content": [{"type": "text", "text": "loaded skill"}],
                }
            },
        },
    ]
    fake_dsh.final_response = "final answer"
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent()
    ctx = _ctx(agent)

    events = [event async for event in runtime.run_async(agent, ctx)]

    assert events[0].partial is True
    assert events[0].content.parts[0].text == "streamed "
    calls = [
        event.content.parts[0].function_call
        for event in events
        if event.content
        and event.content.parts
        and event.content.parts[0].function_call
    ]
    responses = [
        event.content.parts[0].function_response
        for event in events
        if event.content
        and event.content.parts
        and event.content.parts[0].function_response
    ]
    assert calls[0].name == "skill"
    assert calls[0].args == {"name": "demo-skill"}
    assert responses[0].name == "skill"
    assert responses[0].response == {"content": "loaded skill"}
    assert events[-1].is_final_response()
    assert events[-1].content.parts[0].text == "final answer"


@pytest.mark.asyncio
async def test_runtime_maps_assistant_message_stream_chunks(fake_dsh) -> None:
    fake_dsh.result_events = [
        {
            "seq": 1,
            "type": "assistant/message",
            "data": {
                "stream": [
                    {
                        "type": "text-chunks",
                        "texts": ["DSH", "-", "STREAM"],
                    },
                    {
                        "type": "reasoning-chunks",
                        "texts": ["thinking"],
                    },
                ]
            },
        }
    ]
    fake_dsh.final_response = "final answer"
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    agent = _agent()
    ctx = _ctx(agent)

    events = [event async for event in runtime.run_async(agent, ctx)]

    partial_texts = [
        event.content.parts[0].text
        for event in events
        if event.partial
        and event.content
        and event.content.parts
        and not getattr(event.content.parts[0], "thought", False)
    ]
    thought_texts = [
        event.content.parts[0].text
        for event in events
        if event.partial
        and event.content
        and event.content.parts
        and getattr(event.content.parts[0], "thought", False)
    ]
    assert "DSH-STREAM" in partial_texts
    assert "thinking" in thought_texts
    assert events[-1].content.parts[0].text == "final answer"


@pytest.mark.asyncio
async def test_runtime_emits_call_llm_span_for_tracing(fake_dsh) -> None:
    from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

    fake_dsh.final_response = "traced final answer"
    tracer = OpentelemetryTracer(exporters=[])
    agent = _agent(tracers=[tracer])
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    ctx = _ctx(agent, session_id="traced-session")

    events = [event async for event in runtime.run_async(agent, ctx)]

    assert events[-1].content.parts[0].text == "traced final answer"
    exporter = tracer._inmemory_exporter._exporter
    call_llm_spans = [span for span in exporter._spans if span.name == "call_llm"]
    assert call_llm_spans
    attributes = dict(call_llm_spans[-1].attributes or {})
    assert attributes.get("gen_ai.session.id") == "traced-session"
    assert attributes.get("veadk.deepseek_harness.runtime") == "dsh"
    assert attributes.get("veadk.deepseek_harness.status") == "completed"
    assert exporter.get_finished_spans("traced-session")


@pytest.mark.asyncio
async def test_runtime_generates_dsh_skill_patch(fake_dsh, tmp_path) -> None:
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools.skill_toolset import SkillToolset

    skill_dir = tmp_path / "demo-skill"
    _write_skill(skill_dir, name="demo-skill", body="Say DEMO_SKILL_LOADED.")
    agent = _agent(tools=[SkillToolset(skills=[load_skill_from_dir(skill_dir)])])
    runtime_module = importlib.import_module("veadk.runtime.deepseek_harness.runtime")
    runtime = runtime_module.DeepSeekHarnessRuntime()
    ctx = _ctx(agent)

    assert [event async for event in runtime.run_async(agent, ctx)]

    harness = fake_dsh.instances[0]
    skill_patch = _patch_containing(harness.config.patches, "veadk-skill-filesystem")
    patch_text = Path(skill_patch).read_text(encoding="utf-8")
    assert "@deepseek-ai/dsh-skill" in patch_text
    assert "@deepseek-ai/dsh-skill-filesystem" in patch_text
    assert "@deepseek-ai/dsh-tool-skill" in patch_text
    skill_root_match = re.search(r"customSkillDirs:\n\s+- (.+)", patch_text)
    assert skill_root_match is not None
    skill_root = Path(json.loads(skill_root_match.group(1)))
    assert (skill_root / "demo-skill" / "SKILL.md").exists()


def _agent(**kwargs: Any) -> Agent:
    return Agent(
        name="assistant",
        runtime="dsh",
        model_name="deepseek-test-model",
        model_api_base="https://deepseek.example/v1",
        model_api_key="test-api-key",
        **kwargs,
    )


def _ctx(
    agent: Agent,
    *,
    session_id: str = "session-1",
    text: str = "hello",
    events: list[Event] | None = None,
) -> InvocationContext:
    return InvocationContext(
        session_service=InMemorySessionService(),
        invocation_id="inv-1",
        agent=agent,
        user_content=types.Content(role="user", parts=[types.Part(text=text)]),
        session=Session(
            id=session_id,
            appName="app",
            userId="user",
            state={},
            events=events or [],
        ),
    )


class _TextAgent(BaseAgent):
    marker: str

    async def _run_async_impl(self, ctx: InvocationContext):
        yield Event(
            invocation_id=ctx.invocation_id,
            author=self.name,
            content=types.ModelContent(parts=[types.Part(text=self.marker)]),
        )


def _drop_runtime_modules() -> None:
    for name in [
        "veadk.runtime.deepseek_harness.runtime",
        "veadk.runtime.deepseek_harness",
    ]:
        sys.modules.pop(name, None)


def _cleanup_runtime_module() -> None:
    module = sys.modules.get("veadk.runtime.deepseek_harness.runtime")
    cleanup = getattr(module, "_cleanup_runtime_state", None)
    if callable(cleanup):
        cleanup()


def _call_generated_tool_bridge(
    patches: tuple[str, ...] | list[str],
    call: dict[str, Any],
) -> str:
    patch = _plugin_path_from_patch(patches[-1])
    plugin_text = patch.read_text(encoding="utf-8")
    bridge_url = re.search(r'const BRIDGE_URL = "([^"]+)"', plugin_text)
    token = re.search(r'const TOKEN = "([^"]+)"', plugin_text)
    assert bridge_url is not None
    assert token is not None

    request = urllib.request.Request(
        f"{bridge_url.group(1)}/call",
        data=json.dumps(call).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token.group(1)}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    assert payload["ok"] is True
    return payload["result"]


def _plugin_path_from_patch(patch_path: str):
    patch_text = Path(patch_path).read_text(encoding="utf-8")
    match = re.search(r"name: (.+)", patch_text)
    assert match is not None
    return Path(json.loads(match.group(1)))


def _patch_containing(patches: tuple[str, ...] | list[str], needle: str) -> str:
    for patch in patches:
        if needle in Path(patch).read_text(encoding="utf-8"):
            return patch
    raise AssertionError(f"no patch contains {needle!r}")


def _write_skill(path, *, name: str, body: str) -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Demo skill\n---\n{body}\n",
        encoding="utf-8",
    )
