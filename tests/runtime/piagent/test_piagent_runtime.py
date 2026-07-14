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
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from google.adk.events.event import Event
from google.adk.tools.base_tool import BaseTool
from google.adk.tools.base_toolset import BaseToolset
from google.adk.tools.function_tool import FunctionTool
from google.genai import types

from veadk import Agent
from veadk.runtime import get_runtime
from veadk.runtime.piagent.client import PiAgentRpcClient
from veadk.runtime.piagent.config import PiAgentConfig, PiAgentModelConfig
from veadk.runtime.piagent.installer import resolve_platform_archive
from veadk.runtime.piagent.runtime import PiAgentRuntime
from veadk.runtime.piagent.tool_runtime import PiToolRuntime, render_extension
from veadk.runtime.piagent.tools_bridge import (
    PiToolBundle,
    PiToolSpec,
    build_executable_tools,
    close_toolsets,
)
from veadk.runtime.piagent.translate import PiEventTranslator, build_prompt


def _user_event(text: str) -> Event:
    return Event(
        invocation_id="inv-user",
        author="user",
        content=types.Content(role="user", parts=[types.Part(text=text)]),
    )


def _assistant_event(text: str, *, thought: bool = False) -> Event:
    return Event(
        invocation_id="inv-assistant",
        author="assistant",
        content=types.Content(
            role="model", parts=[types.Part(text=text, thought=thought)]
        ),
    )


def _fake_ctx(*events: Event):
    return SimpleNamespace(
        invocation_id="inv-1",
        session=SimpleNamespace(events=list(events), state={}),
    )


class _FakeToolset(BaseToolset):
    def __init__(self, tools):
        super().__init__()
        self.tools = tools
        self.closed = False
        self.readonly_context = None

    async def get_tools(self, readonly_context=None):
        self.readonly_context = readonly_context
        return self.tools

    async def close(self):
        self.closed = True


class _FailingToolset(BaseToolset):
    def __init__(self):
        super().__init__()
        self.closed = False

    async def get_tools(self, readonly_context=None):
        raise RuntimeError("mcp unavailable")

    async def close(self):
        self.closed = True


class _NamedTool(BaseTool):
    def __init__(self, name: str):
        super().__init__(name=name, description="Named test tool.")

    def _get_declaration(self):
        return types.FunctionDeclaration(
            name=self.name,
            description=self.description,
            parameters=types.Schema(type=types.Type.OBJECT),
        )

    async def run_async(self, *, args, tool_context):
        return {"name": self.name, "args": args}


def _make_fake_pi(tmp_path):
    path = tmp_path / "pi"
    path.write_text(
        """#!/usr/bin/env python3
import json
import os
import sys

agent_dir = os.environ.get("PI_CODING_AGENT_DIR")
assert agent_dir, "PI_CODING_AGENT_DIR missing"
assert os.environ.get("VEADK_PI_MODEL_API_KEY") == "test-key"
assert os.path.exists(os.path.join(agent_dir, "models.json"))

for raw in sys.stdin:
    command = json.loads(raw)
    if command.get("type") == "prompt":
        print(json.dumps({
            "id": command.get("id"),
            "type": "response",
            "command": "prompt",
            "success": True,
        }), flush=True)
        print(json.dumps({
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": "checking",
            },
        }), flush=True)
        print(json.dumps({
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": "pong",
            },
        }), flush=True)
        print(json.dumps({"type": "agent_settled"}), flush=True)
        break
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


def _make_fake_pi_with_argv_capture(tmp_path):
    path = tmp_path / "pi"
    argv_path = tmp_path / "argv.json"
    path.write_text(
        f"""#!/usr/bin/env python3
import json
import sys

open({str(argv_path)!r}, "w", encoding="utf-8").write(json.dumps(sys.argv[1:]))
for raw in sys.stdin:
    command = json.loads(raw)
    if command.get("type") == "prompt":
        print(json.dumps({{
            "id": command.get("id"),
            "type": "response",
            "command": "prompt",
            "success": True,
        }}), flush=True)
        print(json.dumps({{"type": "agent_settled"}}), flush=True)
        break
""",
        encoding="utf-8",
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path, argv_path


async def _post_json(url: str, token: str, payload: dict):
    host_port = url.removeprefix("http://")
    host, port_text = host_port.split(":", 1)
    reader, writer = await asyncio.open_connection(host, int(port_text))
    body = json.dumps(payload).encode("utf-8")
    request = (
        f"POST /call HTTP/1.1\r\n"
        f"Host: {host_port}\r\n"
        f"Authorization: Bearer {token}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"Connection: close\r\n\r\n"
    ).encode("ascii") + body
    writer.write(request)
    await writer.drain()
    raw = await reader.read()
    writer.close()
    await writer.wait_closed()
    head, response_body = raw.split(b"\r\n\r\n", 1)
    status = int(head.split(b" ", 2)[1])
    return status, json.loads(response_body.decode("utf-8"))


def test_get_runtime_piagent_is_registered():
    runtime = get_runtime("piagent")
    assert isinstance(runtime, PiAgentRuntime)


def test_build_prompt_skips_thought_parts():
    ctx = _fake_ctx(
        _user_event("hello"),
        _assistant_event("private reasoning", thought=True),
        _assistant_event("visible answer"),
        _user_event("follow up"),
    )

    assert build_prompt(ctx) == "\n".join(
        [
            "User: hello",
            "Assistant: visible answer",
            "User: follow up",
        ]
    )


def test_pi_event_translator_streaming_text_and_thinking():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    thinking = translator.event_to_adk_events(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": "plan",
            },
        }
    )
    text = translator.event_to_adk_events(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": "answer",
            },
        }
    )

    assert thinking[0].content.parts[0].text == "plan"
    assert thinking[0].content.parts[0].thought is True
    assert text[0].content.parts[0].text == "answer"
    assert text[0].content.parts[0].thought is not True


def test_pi_event_translator_tool_events():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    call = translator.event_to_adk_events(
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "lookup",
            "args": {"query": "veadk"},
        }
    )[0]
    response = translator.event_to_adk_events(
        {
            "type": "tool_execution_end",
            "toolCallId": "call-1",
            "toolName": "lookup",
            "result": {
                "content": [{"type": "text", "text": "result text"}],
                "structuredContent": {"value": 1},
                "details": {"ok": True},
            },
            "isError": False,
        }
    )[0]

    assert call.content.parts[0].function_call.name == "lookup"
    assert call.content.parts[0].function_call.args == {"query": "veadk"}
    function_response = response.content.parts[0].function_response
    assert function_response.name == "lookup"
    assert function_response.response["result"]["content"] == "result text"
    assert function_response.response["result"]["structured_content"] == {"value": 1}


def test_model_config_uses_custom_provider():
    agent = Agent(
        name="assistant",
        model_name=["doubao-primary", "doubao-fallback"],
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
        model_api_key_name="",
        runtime="piagent",
    )

    model = PiAgentModelConfig.from_agent(agent)
    payload = model.to_models_json()

    assert model.provider_id == "veadk"
    assert model.model == "doubao-primary"
    provider = payload["providers"]["veadk"]
    assert provider["baseUrl"] == "https://ark.example.com/api/v3/"
    assert provider["api"] == "openai-completions"
    assert provider["apiKey"] == "$VEADK_PI_MODEL_API_KEY"
    assert provider["models"][0]["id"] == "doubao-primary"


def test_resolve_platform_archive_linux_amd64(monkeypatch):
    monkeypatch.setenv("PIAGENT_BINARY_PLATFORM", "linux/amd64")
    assert resolve_platform_archive() == ("linux/amd64", "pi-linux-x64.tar.gz")


@pytest.mark.asyncio
async def test_piagent_rpc_client_streams_fake_pi(tmp_path):
    binary = _make_fake_pi(tmp_path)
    agent_dir = tmp_path / "agent"
    model = PiAgentModelConfig(
        provider_id="veadk",
        model="model-a",
        base_url="https://ark.example.com/api/v3/",
        api_key="test-key",
        api="openai-completions",
        api_key_env="VEADK_PI_MODEL_API_KEY",
    )
    config = PiAgentConfig(
        binary_path=str(binary),
        agent_dir=agent_dir,
        workdir=tmp_path,
        timeout_seconds=5,
        model=model,
    )
    agent_dir.mkdir()
    config.models_path.write_text(json.dumps(model.to_models_json()), encoding="utf-8")

    async with PiAgentRpcClient(config) as client:
        events = [event async for event in client.prompt("ping")]

    assert [event["type"] for event in events] == [
        "message_update",
        "message_update",
        "agent_settled",
    ]


@pytest.mark.asyncio
async def test_piagent_rpc_client_loads_extensions_with_builtin_tools_disabled(
    tmp_path,
):
    binary, argv_path = _make_fake_pi_with_argv_capture(tmp_path)
    extension = tmp_path / "tools.ts"
    extension.write_text("export default function () {}\n", encoding="utf-8")
    model = PiAgentModelConfig(
        provider_id="veadk",
        model="model-a",
        base_url="https://ark.example.com/api/v3/",
        api_key="test-key",
        api="openai-completions",
        api_key_env="VEADK_PI_MODEL_API_KEY",
    )
    config = PiAgentConfig(
        binary_path=str(binary),
        agent_dir=tmp_path / "agent",
        workdir=tmp_path,
        timeout_seconds=5,
        model=model,
        disable_tools=False,
        disable_builtin_tools=True,
        extensions=(str(extension),),
        allowed_tools=("lookup",),
    )
    config.agent_dir.mkdir()

    async with PiAgentRpcClient(config) as client:
        _events = [event async for event in client.prompt("ping")]

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert "--no-tools" not in argv
    assert "--no-builtin-tools" in argv
    assert argv[argv.index("--extension") + 1] == str(extension)
    assert argv[argv.index("--tools") + 1] == "lookup"


@pytest.mark.asyncio
async def test_build_executable_tools_collects_function_tool():
    def get_weather(city: str) -> dict[str, str]:
        """Get weather.

        Args:
            city: City name.
        """
        return {"weather": f"sunny in {city}"}

    agent = SimpleNamespace(tools=[FunctionTool(get_weather)])
    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["get_weather"]
    assert bundle.specs[0].parameters["type"] == "object"
    output = await bundle.executors["get_weather"]({"city": "Beijing"})
    assert output == {"weather": "sunny in Beijing"}


@pytest.mark.asyncio
async def test_build_executable_tools_wraps_plain_callable():
    def get_order_status(order_id: str) -> dict[str, str]:
        """Query an order status.

        Args:
            order_id: Order id.
        """
        return {"order_id": order_id, "status": "paid"}

    agent = SimpleNamespace(tools=[get_order_status])
    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["get_order_status"]
    assert bundle.specs[0].parameters["properties"]["order_id"]["type"] == "string"
    output = await bundle.executors["get_order_status"]({"order_id": "A10086"})
    assert output == {"order_id": "A10086", "status": "paid"}


@pytest.mark.asyncio
async def test_build_executable_tools_expands_base_toolset():
    def get_weather(city: str) -> dict[str, str]:
        """Get weather.

        Args:
            city: City name.
        """
        return {"weather": f"sunny in {city}"}

    toolset = _FakeToolset([FunctionTool(get_weather)])
    agent = SimpleNamespace(tools=[toolset])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["get_weather"]
    assert bundle.specs[0].parameters["type"] == "object"
    assert bundle.opened_toolsets == [toolset]
    assert toolset.readonly_context.invocation_id == "inv-1"
    output = await bundle.executors["get_weather"]({"city": "Beijing"})
    assert output == {"weather": "sunny in Beijing"}

    await close_toolsets(bundle.opened_toolsets)
    assert toolset.closed is True


@pytest.mark.asyncio
async def test_build_executable_tools_skips_failing_toolset():
    toolset = _FailingToolset()
    agent = SimpleNamespace(tools=[toolset])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert bundle.specs == []
    assert bundle.executors == {}
    assert bundle.opened_toolsets == []
    assert len(bundle.skipped) == 1
    assert bundle.skipped[0].name == "_FailingToolset"
    assert "failed to list toolset tools" in bundle.skipped[0].reason
    assert toolset.closed is True


@pytest.mark.asyncio
async def test_build_executable_tools_aliases_duplicate_names():
    def echo(value: str) -> str:
        """Echo a value."""
        return value

    agent = SimpleNamespace(tools=[FunctionTool(echo), FunctionTool(echo)])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["echo", "echo_2"]
    assert [spec.original_name for spec in bundle.specs] == ["echo", "echo"]


@pytest.mark.asyncio
async def test_build_executable_tools_aliases_duplicate_toolset_names():
    def echo(value: str) -> str:
        """Echo a value."""
        return value

    toolset = _FakeToolset([FunctionTool(echo)])
    agent = SimpleNamespace(tools=[FunctionTool(echo), toolset])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["echo", "echo_2"]
    await close_toolsets(bundle.opened_toolsets)
    assert toolset.closed is True


@pytest.mark.asyncio
async def test_build_executable_tools_aliases_pi_incompatible_names():
    agent = SimpleNamespace(tools=[_NamedTool("mcp.server/get-order")])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["mcp_server_get_order"]
    assert bundle.specs[0].original_name == "mcp.server/get-order"
    output = await bundle.executors["mcp_server_get_order"]({"order_id": "A10086"})
    assert output["name"] == "mcp.server/get-order"


def test_render_extension_uses_pi_tool_shape():
    spec = PiToolSpec(
        name="get_weather",
        label="get_weather",
        description="Get weather.",
        parameters={
            "type": "object",
            "properties": {"city": {"type": "string", "description": "City"}},
            "required": ["city"],
        },
        original_name="get_weather",
    )

    source = render_extension([spec], "http://127.0.0.1:1234", "token")

    assert 'import { Type } from "@earendil-works/pi-ai";' in source
    assert 'name: "get_weather"' in source
    assert "parameters: Type.Object({city: Type.String" in source
    assert "async execute(toolCallId, params, signal" in source
    assert "return data.result ??" in source


@pytest.mark.asyncio
async def test_pi_tool_runtime_serves_executor_call():
    async def executor(args):
        return {"echo": args["value"]}

    bundle = PiToolBundle(
        specs=[
            PiToolSpec(
                name="echo",
                label="echo",
                description="Echo.",
                parameters={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                original_name="echo",
            )
        ],
        executors={"echo": executor},
    )

    async with PiToolRuntime(bundle) as runtime:
        status, payload = await _post_json(
            runtime.url,
            runtime._token,
            {"toolName": "echo", "toolCallId": "call-1", "args": {"value": "ok"}},
        )
        bad_status, bad_payload = await _post_json(
            runtime.url,
            "bad-token",
            {"toolName": "echo", "toolCallId": "call-1", "args": {"value": "ok"}},
        )

    assert status == 200
    assert payload["ok"] is True
    assert payload["result"]["structuredContent"] == {"echo": "ok"}
    assert json.loads(payload["result"]["content"][0]["text"]) == {"echo": "ok"}
    assert bad_status == 401
    assert bad_payload["ok"] is False


@pytest.mark.asyncio
async def test_build_executable_tools_calls_real_stdio_mcp_toolset():
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
    agent = SimpleNamespace(tools=[toolset])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))
    try:
        assert [spec.name for spec in bundle.specs] == ["get_order_status"]
        output = await bundle.executors["get_order_status"]({"order_id": "A10086"})
        assert output["structuredContent"]["status"] == "paid"
        assert output["isError"] is False
    finally:
        await close_toolsets(bundle.opened_toolsets)


@pytest.mark.asyncio
async def test_piagent_runtime_text_only_end_to_end(tmp_path, monkeypatch):
    binary = _make_fake_pi(tmp_path)
    agent_dir = tmp_path / "agent-home"
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(agent_dir))
    monkeypatch.setenv("PIAGENT_AUTO_INSTALL", "0")

    agent = Agent(
        name="assistant",
        instruction="Answer briefly.",
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
        model_api_key_name="",
        runtime="piagent",
    )
    ctx = _fake_ctx(_user_event("ping"))

    events = [event async for event in PiAgentRuntime().run_async(agent, ctx)]

    assert [event.content.parts[0].text for event in events] == ["checking", "pong"]
    assert events[0].content.parts[0].thought is True
    assert events[1].content.parts[0].thought is not True
    models = json.loads((agent_dir / "models.json").read_text(encoding="utf-8"))
    assert models["providers"]["veadk"]["models"][0]["id"] == "model-a"


@pytest.mark.asyncio
async def test_piagent_runtime_closes_opened_toolsets(tmp_path, monkeypatch):
    def get_weather(city: str) -> dict[str, str]:
        """Get weather.

        Args:
            city: City name.
        """
        return {"weather": f"sunny in {city}"}

    binary = _make_fake_pi(tmp_path)
    agent_dir = tmp_path / "agent-home"
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(agent_dir))
    monkeypatch.setenv("PIAGENT_AUTO_INSTALL", "0")

    toolset = _FakeToolset([FunctionTool(get_weather)])
    agent = Agent(
        name="assistant",
        instruction="Answer briefly.",
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
        model_api_key_name="",
        runtime="piagent",
        tools=[toolset],
    )
    ctx = _fake_ctx(_user_event("ping"))

    events = [event async for event in PiAgentRuntime().run_async(agent, ctx)]

    assert [event.content.parts[0].text for event in events] == ["checking", "pong"]
    assert toolset.closed is True
