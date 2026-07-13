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

import json
import stat
from types import SimpleNamespace

import pytest
from google.adk.events.event import Event
from google.genai import types

from veadk import Agent
from veadk.runtime import get_runtime
from veadk.runtime.piagent.client import PiAgentRpcClient
from veadk.runtime.piagent.config import PiAgentConfig, PiAgentModelConfig
from veadk.runtime.piagent.installer import resolve_platform_archive
from veadk.runtime.piagent.runtime import PiAgentRuntime
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
        session=SimpleNamespace(events=list(events)),
    )


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
