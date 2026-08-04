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
import tarfile
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
from veadk.runtime.piagent import installer
from veadk.runtime.piagent.client import PiAgentRpcClient
from veadk.runtime.piagent.config import PiAgentConfig, PiAgentModelConfig
from veadk.runtime.piagent.installer import (
    resolve_or_install_piagent_binary,
    resolve_platform_archive,
)
from veadk.runtime.piagent.runtime import PiAgentRuntime
from veadk.runtime.piagent.skills import materialize_skills_for_pi
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
    env_path = tmp_path / "env.json"
    path.write_text(
        f"""#!/usr/bin/env python3
import json
import os
import sys

open({str(argv_path)!r}, "w", encoding="utf-8").write(json.dumps(sys.argv[1:]))
open({str(env_path)!r}, "w", encoding="utf-8").write(json.dumps({{
    "PI_CODING_AGENT_DIR": os.environ.get("PI_CODING_AGENT_DIR"),
    "VEADK_PI_MODEL_API_KEY": os.environ.get("VEADK_PI_MODEL_API_KEY"),
}}))
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


def _write_skill(path: Path, *, name: str, body: str = "Skill body.") -> None:
    path.mkdir(parents=True, exist_ok=True)
    (path / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: Demo skill.\n---\n{body}\n",
        encoding="utf-8",
    )


def _clear_piagent_config_env(monkeypatch) -> None:
    for name in (
        "PIAGENT_AGENT_DIR",
        "PI_CODING_AGENT_DIR",
        "PIAGENT_ALLOW_PARENT_PI_CODING_AGENT_DIR",
        "PIAGENT_DISABLE_TOOLS",
        "PIAGENT_DISABLE_BUILTIN_TOOLS",
        "PIAGENT_DISABLE_EXTENSION_DISCOVERY",
        "PIAGENT_ENABLE_EXTENSION_DISCOVERY",
        "PIAGENT_DISABLE_SKILL_DISCOVERY",
        "PIAGENT_ENABLE_SKILL_DISCOVERY",
        "PIAGENT_TOOL_ALLOWLIST",
        "PIAGENT_EXCLUDE_TOOLS",
        "PIAGENT_PROJECT_TRUST",
    ):
        monkeypatch.delenv(name, raising=False)


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


def test_build_prompt_uses_user_content_when_session_event_is_missing():
    ctx = _fake_ctx()
    ctx.user_content = types.Content(
        role="user", parts=[types.Part(text="北京天气怎么样，用 PiAgent E2E skill")]
    )

    assert build_prompt(ctx) == "北京天气怎么样，用 PiAgent E2E skill"


def test_build_prompt_does_not_duplicate_user_content():
    ctx = _fake_ctx(_user_event("北京天气怎么样，用 PiAgent E2E skill"))
    ctx.user_content = types.Content(
        role="user", parts=[types.Part(text="北京天气怎么样，用 PiAgent E2E skill")]
    )

    assert build_prompt(ctx) == "北京天气怎么样，用 PiAgent E2E skill"


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
    flushed = translator.event_to_adk_events({"type": "agent_settled"})

    assert len(thinking) == 1
    assert thinking[0].partial is True
    assert thinking[0].content.parts[0].text == "plan"
    assert thinking[0].content.parts[0].thought is True
    assert len(text) == 1
    assert text[0].partial is True
    assert text[0].content.parts[0].text == "answer"
    assert text[0].content.parts[0].thought is False
    assert len(flushed) == 1
    assert flushed[0].partial is not True
    assert flushed[0].is_final_response() is True
    assert [part.text for part in flushed[0].content.parts] == ["plan", "answer"]
    assert flushed[0].content.parts[0].thought is True
    assert flushed[0].content.parts[1].thought is False
    dumped = flushed[0].model_dump(by_alias=True, exclude_none=True)
    assert dumped["content"]["parts"][1]["thought"] is False


def test_pi_event_translator_coalesces_text_deltas():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    for delta in ["你", "好", "，", "世界"]:
        streamed = translator.event_to_adk_events(
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "text_delta",
                    "delta": delta,
                },
            }
        )
        assert len(streamed) == 1
        assert streamed[0].partial is True
        assert streamed[0].content.parts[0].text == delta

    flushed = translator.event_to_adk_events({"type": "agent_settled"})

    assert len(flushed) == 1
    assert flushed[0].partial is not True
    assert flushed[0].content.parts[0].text == "你好，世界"
    assert flushed[0].content.parts[0].thought is False


def test_pi_event_translator_does_not_emit_thinking_only_final_event():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    for delta in ["我", "是", " PiAgent"]:
        streamed = translator.event_to_adk_events(
            {
                "type": "message_update",
                "assistantMessageEvent": {
                    "type": "thinking_delta",
                    "delta": delta,
                },
            }
        )
        assert len(streamed) == 1
        assert streamed[0].partial is True
        assert streamed[0].content.parts[0].text == delta
        assert streamed[0].content.parts[0].thought is True

    flushed = translator.event_to_adk_events({"type": "agent_settled"})

    assert flushed == []


def test_pi_event_translator_prefers_message_end_text():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    streamed = translator.event_to_adk_events(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "text_delta",
                "delta": "partial",
            },
        }
    )

    assert len(streamed) == 1
    assert streamed[0].partial is True
    assert streamed[0].content.parts[0].text == "partial"

    flushed = translator.event_to_adk_events(
        {
            "type": "message_end",
            "message": {"role": "assistant", "content": "final answer"},
        }
    )

    assert len(flushed) == 1
    assert flushed[0].partial is not True
    assert flushed[0].content.parts[0].text == "final answer"


def test_pi_event_translator_does_not_reuse_thinking_after_tool_call():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")
    thought = (
        "用户现在问今天北京的天气怎么样，我需要调用get_weather工具，参数是city为北京。"
    )

    streamed_thinking = translator.event_to_adk_events(
        {
            "type": "message_update",
            "assistantMessageEvent": {
                "type": "thinking_delta",
                "delta": thought,
            },
        }
    )
    thinking = translator.event_to_adk_events(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "type": "thinking",
                "content": thought,
            },
        }
    )
    call = translator.event_to_adk_events(
        {
            "type": "tool_execution_start",
            "toolCallId": "call-1",
            "toolName": "get_weather",
            "args": {"city": "北京"},
        }
    )
    response = translator.event_to_adk_events(
        {
            "type": "tool_execution_end",
            "toolCallId": "call-1",
            "toolName": "get_weather",
            "result": {"content": [{"type": "text", "text": "sunny, 28 C"}]},
            "isError": False,
        }
    )
    duplicate_thinking_end = translator.event_to_adk_events(
        {
            "type": "message_end",
            "message": {
                "role": "assistant",
                "type": "thinking",
                "content": thought,
            },
        }
    )
    final = translator.event_to_adk_events(
        {
            "type": "message_end",
            "message": {"role": "assistant", "content": "北京今天晴，28 C。"},
        }
    )
    settled = translator.event_to_adk_events({"type": "agent_settled"})

    assert len(streamed_thinking) == 1
    assert streamed_thinking[0].partial is True
    assert streamed_thinking[0].content.parts[0].text == thought
    assert streamed_thinking[0].content.parts[0].thought is True
    assert thinking == []
    assert call[0].is_final_response() is False
    assert call[0].partial is not True
    assert call[0].content.parts[0].text == thought
    assert call[0].content.parts[0].thought is True
    assert call[0].content.parts[1].function_call.name == "get_weather"
    assert response[0].content.parts[0].function_response.name == "get_weather"
    assert duplicate_thinking_end == []
    assert len(final) == 1
    assert final[0].partial is not True
    assert final[0].content.parts[0].text == "北京今天晴，28 C。"
    assert final[0].content.parts[0].thought is False
    assert settled == []


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


def test_pi_event_translator_native_bash_result():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    call = translator.event_to_adk_events(
        {
            "type": "tool_execution_start",
            "toolCallId": "call-bash",
            "toolName": "bash",
            "args": {"command": "printf ok"},
        }
    )[0]
    response = translator.event_to_adk_events(
        {
            "type": "tool_execution_end",
            "toolCallId": "call-bash",
            "toolName": "bash",
            "result": {"stdout": "ok", "stderr": "", "exitCode": 0},
            "isError": False,
        }
    )[0]

    assert call.content.parts[0].function_call.name == "bash"
    function_response = response.content.parts[0].function_response
    assert function_response.name == "bash"
    assert function_response.response["result"]["content"] == "ok"
    assert function_response.response["result"]["details"]["stdout"] == "ok"
    assert function_response.response["result"]["details"]["exitCode"] == 0


def test_pi_event_translator_native_tool_update():
    translator = PiEventTranslator(author="agent", invocation_id="inv-1")

    update = translator.event_to_adk_events(
        {
            "type": "tool_execution_update",
            "toolCallId": "call-bash",
            "toolName": "bash",
            "partialResult": {"stdout": "line 1"},
        }
    )
    response = translator.event_to_adk_events(
        {
            "type": "tool_execution_end",
            "toolCallId": "call-bash",
            "toolName": "bash",
            "result": {"stdout": "line 1\nline 2", "exitCode": 0},
            "isError": False,
        }
    )[0]

    assert len(update) == 1
    assert update[0].partial is True
    assert update[0].content.parts[0].thought is True
    assert update[0].content.parts[0].text == "[bash] line 1"
    function_response = response.content.parts[0].function_response
    assert function_response.name == "bash"
    assert function_response.response["result"]["content"] == "line 1\nline 2"


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


def test_piagent_config_defaults_to_temp_agent_dir(monkeypatch):
    _clear_piagent_config_env(monkeypatch)
    agent = SimpleNamespace(
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
    )

    config = PiAgentConfig.from_agent(agent, "/bin/pi")

    assert config.agent_dir.name.startswith("veadk-piagent-")
    assert config.disable_tools is False
    assert config.disable_builtin_tools is False
    assert config.disable_extension_discovery is True
    assert config.disable_skill_discovery is True
    assert config.project_trust == "deny"


def test_piagent_config_ignores_parent_pi_coding_agent_dir_by_default(
    tmp_path,
    monkeypatch,
):
    parent_home = tmp_path / "parent-pi-home"
    _clear_piagent_config_env(monkeypatch)
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(parent_home))
    agent = SimpleNamespace(
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
    )

    config = PiAgentConfig.from_agent(agent, "/bin/pi")

    assert config.agent_dir != parent_home
    assert config.agent_dir.name.startswith("veadk-piagent-")


def test_piagent_config_rejects_real_user_pi_agent_dir(monkeypatch):
    real_home = Path.home() / ".pi" / "agent"
    agent = SimpleNamespace(
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
    )

    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(real_home))
    with pytest.raises(ValueError, match="real Pi home"):
        PiAgentConfig.from_agent(agent, "/bin/pi")

    monkeypatch.delenv("PIAGENT_AGENT_DIR", raising=False)
    monkeypatch.setenv("PIAGENT_ALLOW_PARENT_PI_CODING_AGENT_DIR", "1")
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(real_home))
    with pytest.raises(ValueError, match="real Pi home"):
        PiAgentConfig.from_agent(agent, "/bin/pi")


def test_resolve_platform_archive_linux_amd64(monkeypatch):
    monkeypatch.setenv("PIAGENT_BINARY_PLATFORM", "linux/amd64")
    assert resolve_platform_archive() == ("linux/amd64", "pi-linux-x64.tar.gz")


def test_resolve_pi_binary_uses_configured_binary(tmp_path, monkeypatch):
    binary = _make_fake_pi(tmp_path)
    install_dir = tmp_path / "install"
    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_INSTALL_DIR", str(install_dir))

    assert resolve_or_install_piagent_binary() == str(binary)


def test_resolve_pi_binary_uses_install_dir_cache(tmp_path, monkeypatch):
    install_dir = tmp_path / "install"
    binary = install_dir / "pi" / "pi"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
    monkeypatch.delenv("PIAGENT_BINARY", raising=False)
    monkeypatch.setenv("PIAGENT_INSTALL_DIR", str(install_dir))

    assert resolve_or_install_piagent_binary() == str(binary)


def test_resolve_pi_binary_installs_into_install_dir(tmp_path, monkeypatch):
    install_dir = tmp_path / "install"
    archive_root = tmp_path / "archive-root"
    archive_pi = archive_root / "pi"
    archive_pi.mkdir(parents=True)
    archive_binary = archive_pi / "pi"
    archive_binary.write_text("#!/bin/sh\n", encoding="utf-8")
    archive_binary.chmod(archive_binary.stat().st_mode | stat.S_IXUSR)
    (archive_pi / "theme").mkdir()
    (archive_pi / "theme" / "dark.json").write_text("{}", encoding="utf-8")

    archive = tmp_path / "pi-linux-x64.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(archive_pi, arcname="pi")

    monkeypatch.delenv("PIAGENT_BINARY", raising=False)
    monkeypatch.setenv("PIAGENT_INSTALL_DIR", str(install_dir))
    monkeypatch.setenv("PIAGENT_BINARY_URL", "https://example.invalid/pi.tar.gz")

    def fake_download(url, archive_name):
        assert url == "https://example.invalid/pi.tar.gz"
        assert archive_name == "pi.tar.gz"
        return archive

    monkeypatch.setattr(installer, "_download", fake_download)

    assert resolve_or_install_piagent_binary() == str(install_dir / "pi" / "pi")
    assert (install_dir / "pi" / "theme" / "dark.json").read_text(
        encoding="utf-8"
    ) == "{}"


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
async def test_piagent_rpc_client_uses_isolated_boundary_and_explicit_resources(
    tmp_path,
):
    binary, argv_path = _make_fake_pi_with_argv_capture(tmp_path)
    extension = tmp_path / "tools.ts"
    extension.write_text("export default function () {}\n", encoding="utf-8")
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
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
        extensions=(str(extension),),
        skill_paths=(str(skill_dir),),
    )
    config.agent_dir.mkdir()
    config.models_path.write_text(json.dumps(model.to_models_json()), encoding="utf-8")

    async with PiAgentRpcClient(config) as client:
        _events = [event async for event in client.prompt("ping")]

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    env = json.loads((tmp_path / "env.json").read_text(encoding="utf-8"))
    assert env["PI_CODING_AGENT_DIR"] == str(config.agent_dir)
    assert env["VEADK_PI_MODEL_API_KEY"] == "test-key"
    assert "--no-tools" not in argv
    assert "--no-builtin-tools" not in argv
    assert "--tools" not in argv
    assert "--no-extensions" in argv
    assert "--no-approve" in argv
    assert argv[argv.index("--extension") + 1] == str(extension)
    assert "--no-skills" in argv
    assert argv[argv.index("--skill") + 1] == str(skill_dir)


@pytest.mark.asyncio
async def test_piagent_rpc_client_honors_explicit_allowlist_exclude_and_trust(
    tmp_path,
):
    binary, argv_path = _make_fake_pi_with_argv_capture(tmp_path)
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
        tool_allowlist=("read", "bash", "lookup"),
        exclude_tools=("write",),
        project_trust="approve",
    )
    config.agent_dir.mkdir()
    config.models_path.write_text(json.dumps(model.to_models_json()), encoding="utf-8")

    async with PiAgentRpcClient(config) as client:
        _events = [event async for event in client.prompt("ping")]

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    assert argv[argv.index("--tools") + 1] == "read,bash,lookup"
    assert argv[argv.index("--exclude-tools") + 1] == "write"
    assert "--approve" in argv
    assert "--no-approve" not in argv


def test_piagent_config_with_tools_and_skills_preserves_both(tmp_path):
    model = PiAgentModelConfig(
        provider_id="veadk",
        model="model-a",
        base_url="https://ark.example.com/api/v3/",
        api_key="test-key",
        api="openai-completions",
        api_key_env="VEADK_PI_MODEL_API_KEY",
    )
    base = PiAgentConfig(
        binary_path="/bin/pi",
        agent_dir=tmp_path / "agent",
        workdir=tmp_path,
        timeout_seconds=5,
        model=model,
    )

    config = base.with_skills(skill_paths=["/tmp/skill-a"]).with_tools(
        extensions=["/tmp/tools.ts"],
    )

    assert config.skill_paths == ("/tmp/skill-a",)
    assert config.disable_skill_discovery is True
    assert config.disable_tools is False
    assert config.disable_builtin_tools is False
    assert config.extensions == ("/tmp/tools.ts",)
    assert config.tool_allowlist == ()


def test_materialize_skills_for_pi_writes_adk_skill(tmp_path):
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools.skill_toolset import SkillToolset

    skill_dir = tmp_path / "demo-skill"
    _write_skill(skill_dir, name="demo-skill", body="Say DEMO_SKILL_LOADED.")
    toolset = SkillToolset(skills=[load_skill_from_dir(skill_dir)])
    agent = SimpleNamespace(tools=[toolset])

    bundle = materialize_skills_for_pi(agent)
    try:
        assert bundle.count == 1
        assert len(bundle.paths) == 1
        materialized = Path(bundle.paths[0])
        assert materialized.name == "demo-skill"
        assert "DEMO_SKILL_LOADED" in (materialized / "SKILL.md").read_text(
            encoding="utf-8"
        )
    finally:
        root = bundle.root
        bundle.close()

    assert root is not None
    assert not root.exists()


def test_materialize_skills_for_pi_links_legacy_local_skill(tmp_path):
    skill_dir = tmp_path / "legacy-skill"
    _write_skill(skill_dir, name="legacy-skill", body="Legacy body.")
    agent = SimpleNamespace(
        tools=[],
        skills_dict={"legacy-skill": SimpleNamespace(path=str(skill_dir))},
    )

    bundle = materialize_skills_for_pi(agent)
    try:
        assert bundle.count == 1
        materialized = Path(bundle.paths[0])
        assert materialized.name == "legacy-skill"
        assert (
            (materialized / "SKILL.md")
            .read_text(encoding="utf-8")
            .endswith("Legacy body.\n")
        )
    finally:
        bundle.close()


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


@pytest.mark.asyncio
async def test_build_executable_tools_prefixes_pi_reserved_names():
    agent = SimpleNamespace(tools=[_NamedTool("read"), _NamedTool("veadk_read")])

    bundle = await build_executable_tools(agent, _fake_ctx(_user_event("hi")))

    assert [spec.name for spec in bundle.specs] == ["veadk_read", "veadk_read_2"]
    assert [spec.original_name for spec in bundle.specs] == ["read", "veadk_read"]
    output = await bundle.executors["veadk_read"]({"path": "README.md"})
    assert output["name"] == "read"


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

    assert 'import { Type } from "typebox";' in source
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

    assert len(events) == 3
    assert events[0].partial is True
    assert events[0].content.parts[0].text == "checking"
    assert events[0].content.parts[0].thought is True
    assert events[1].partial is True
    assert events[1].content.parts[0].text == "pong"
    assert events[1].content.parts[0].thought is False
    assert events[2].partial is not True
    assert [part.text for part in events[2].content.parts] == ["checking", "pong"]
    assert events[2].content.parts[0].thought is True
    assert events[2].content.parts[1].thought is False
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

    assert len(events) == 3
    assert events[0].partial is True
    assert events[0].content.parts[0].text == "checking"
    assert events[1].partial is True
    assert events[1].content.parts[0].text == "pong"
    assert events[2].partial is not True
    assert [part.text for part in events[2].content.parts] == ["checking", "pong"]
    assert toolset.closed is True


@pytest.mark.asyncio
async def test_piagent_runtime_loads_and_cleans_materialized_skills(
    tmp_path,
    monkeypatch,
):
    from google.adk.skills import load_skill_from_dir
    from google.adk.tools.skill_toolset import SkillToolset

    binary, argv_path = _make_fake_pi_with_argv_capture(tmp_path)
    agent_dir = tmp_path / "agent-home"
    source_skill = tmp_path / "demo-skill"
    _write_skill(source_skill, name="demo-skill", body="Say DEMO_SKILL_LOADED.")
    skill_toolset = SkillToolset(skills=[load_skill_from_dir(source_skill)])

    monkeypatch.setenv("PIAGENT_BINARY", str(binary))
    monkeypatch.setenv("PIAGENT_AGENT_DIR", str(agent_dir))

    agent = Agent(
        name="assistant",
        instruction="Answer briefly.",
        model_name="model-a",
        model_api_base="https://ark.example.com/api/v3/",
        model_api_key="test-key",
        model_api_key_name="",
        runtime="piagent",
        tools=[skill_toolset],
    )
    ctx = _fake_ctx(_user_event("ping"))

    events = [event async for event in PiAgentRuntime().run_async(agent, ctx)]

    argv = json.loads(argv_path.read_text(encoding="utf-8"))
    skill_path = Path(argv[argv.index("--skill") + 1])
    assert events == []
    assert "--no-skills" in argv
    assert skill_path.name == "demo-skill"
    assert not skill_path.exists()
