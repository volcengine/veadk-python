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

import asyncio
import importlib
import sys
import os
from pathlib import Path
from types import SimpleNamespace


EXAMPLE_DIR = Path(__file__).parents[2] / "examples" / "16_self_host_sandbox"
if str(EXAMPLE_DIR) not in sys.path:
    sys.path.insert(0, str(EXAMPLE_DIR))

os.environ.setdefault("ANTHROPIC_BASE_URL", "https://sandbox.example.com")
os.environ.setdefault("ANTHROPIC_ENVIRONMENT_KEY", "test-token")
os.environ.setdefault("MODEL_AGENT_API_KEY", "test-model-api-key")

agent_module = importlib.import_module("agents.self_host_sandbox_agent.agent")
SandboxSessionManager = agent_module.SandboxSessionManager


class _FakeClient:
    def __init__(self, remote_session_id: str):
        self.session_id = None
        self.remote_session_id = remote_session_id
        self.created_titles = []
        self.idle_count = 0

    def create_session(self, title: str):
        self.created_titles.append(title)
        self.session_id = self.remote_session_id

    def post_status_idle(self):
        self.idle_count += 1


def test_each_veadk_session_creates_a_distinct_remote_session(monkeypatch):
    manager = SandboxSessionManager()
    clients = iter((_FakeClient("remote-1"), _FakeClient("remote-2")))
    monkeypatch.setattr(manager, "_new_client", lambda: next(clients))

    assert manager.create_remote_session("veadk-1") == "remote-1"
    assert manager.create_remote_session("veadk-1") == "remote-1"
    assert manager.create_remote_session("veadk-2") == "remote-2"

    assert manager.get("veadk-1") is not manager.get("veadk-2")
    assert manager.get("veadk-1").created_titles == [
        "VeADK Self-Hosted Sandbox Session veadk-1"
    ]
    assert manager.get("veadk-2").created_titles == [
        "VeADK Self-Hosted Sandbox Session veadk-2"
    ]


def test_web_session_service_creation_provisions_remote_session(monkeypatch):
    created = []
    monkeypatch.setattr(
        agent_module.sandbox_sessions,
        "create_remote_session",
        lambda session_id: created.append(session_id) or "remote-web",
    )

    asyncio.run(
        agent_module.short_term_memory.session_service.create_session(
            app_name="self_host_sandbox_agent",
            user_id="user",
            session_id="web-session",
        )
    )

    assert created == ["web-session"]


def test_dispatch_task_sends_only_the_model_tool_call(monkeypatch):
    dispatched = []
    client = SimpleNamespace(
        dispatch_tool=lambda name, arguments, *, dispatch_id: dispatched.append(
            (name, arguments, dispatch_id)
        )
        or {"stdout": "ok"}
    )
    monkeypatch.setattr(agent_module.sandbox_sessions, "get", lambda session_id: client)
    tool_call = SimpleNamespace(
        session_id="veadk-session",
        id="tool-call-1",
        name="bash",
        arguments={"command": "printf ok"},
    )

    result = asyncio.run(agent_module.dispatch_task(tool_call))

    assert result == {"stdout": "ok"}
    assert dispatched == [("bash", {"command": "printf ok"}, "tool-call-1")]
    assert not hasattr(agent_module.agent, "run_turn")
