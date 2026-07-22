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

from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from google.adk.agents.base_agent import BaseAgent

import veadk
import veadk.integrations.agentkit.app as agentkit_app


class _FakeAgentServer:
    instances: list[_FakeAgentServer] = []

    def __init__(self, agent: BaseAgent, short_term_memory: object) -> None:
        self.agent = agent
        self.short_term_memory = short_term_memory
        self.app = FastAPI()
        self.run_kwargs: dict[str, Any] | None = None
        self.instances.append(self)

    def run(self, **kwargs: Any) -> None:
        self.run_kwargs = kwargs


class _FakeShortTermMemory:
    def __init__(self, backend: str) -> None:
        self.backend = backend


@pytest.fixture(autouse=True)
def fake_agentkit_server(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeAgentServer.instances.clear()
    monkeypatch.setattr(agentkit_app, "AgentkitAgentServerApp", _FakeAgentServer)
    monkeypatch.setattr(agentkit_app, "ShortTermMemory", _FakeShortTermMemory)


def _root_agent() -> BaseAgent:
    child = SimpleNamespace(
        name="agent_sub_1",
        description="Handles orders",
        model="child-model",
        tools=[],
        sub_agents=[],
    )
    root = SimpleNamespace(
        name="agent",
        description="Customer support",
        model=SimpleNamespace(model="doubao-model"),
        tools=[SimpleNamespace(name="search_orders")],
        sub_agents=[child],
    )
    return cast(BaseAgent, root)


def test_create_agentkit_app_preserves_platform_route_contract() -> None:
    app = agentkit_app.create_agentkit_app(
        _root_agent(),
        {"agent": "客服智能体", "agent_sub_1": "订单助手"},
    )

    server = _FakeAgentServer.instances[-1]
    assert isinstance(server.short_term_memory, _FakeShortTermMemory)
    assert server.short_term_memory.backend == "local"

    client = TestClient(app)
    assert client.get("/ping").json() == {"status": "ok"}
    info = client.get("/web/agent-info/agent")
    assert info.status_code == 200
    assert info.json() == {
        "id": "agent",
        "name": "客服智能体",
        "description": "Customer support",
        "type": "llm",
        "model": "doubao-model",
        "tools": ["search_orders"],
        "skills": [],
        "components": [],
        "searchSources": [],
        "subAgents": ["订单助手"],
        "graph": {
            "id": "agent",
            "name": "客服智能体",
            "description": "Customer support",
            "type": "llm",
            "model": "doubao-model",
            "tools": ["search_orders"],
            "skills": [],
            "components": [],
            "path": ["agent"],
            "mentionable": True,
            "children": [
                {
                    "id": "agent_sub_1",
                    "name": "订单助手",
                    "description": "Handles orders",
                    "type": "llm",
                    "model": "child-model",
                    "tools": [],
                    "skills": [],
                    "components": [],
                    "path": ["agent", "agent_sub_1"],
                    "mentionable": True,
                    "children": [],
                }
            ],
        },
    }
    assert client.get("/web/agent-info/unknown").status_code == 404
    assert client.get("/web/agent-graph").json()["graph"] == info.json()["graph"]


def test_agent_info_exposes_mounted_skills_and_components() -> None:
    root_agent = _root_agent()
    setattr(
        root_agent,
        "skills_dict",
        {
            "refund-orders": SimpleNamespace(
                name="refund-orders",
                description="Handle refund requests.",
            )
        },
    )
    setattr(
        root_agent,
        "knowledgebase",
        SimpleNamespace(
            index="support-docs",
            description="Customer support documentation.",
            backend="viking",
        ),
    )
    setattr(root_agent, "long_term_memory", SimpleNamespace(backend="viking"))
    setattr(root_agent, "tracers", [SimpleNamespace(name="apm-tracer")])
    setattr(root_agent, "plugins", [SimpleNamespace(name="audit-plugin")])

    info = TestClient(agentkit_app.create_agentkit_app(root_agent)).get(
        "/web/agent-info/agent"
    )

    assert info.status_code == 200
    assert info.json()["skills"] == [
        {"name": "refund-orders", "description": "Handle refund requests."}
    ]
    assert info.json()["components"] == [
        {
            "kind": "knowledgebase",
            "name": "support-docs",
            "source": "knowledgebase",
            "backend": "viking",
            "description": "Customer support documentation.",
        },
        {
            "kind": "memory",
            "name": "SimpleNamespace",
            "source": "long_term_memory",
            "backend": "viking",
        },
        {"kind": "tracer", "name": "apm-tracer"},
        {"kind": "plugin", "name": "audit-plugin"},
    ]
    assert info.json()["graph"]["skills"] == info.json()["skills"]
    assert info.json()["graph"]["components"] == info.json()["components"]
    assert info.json()["searchSources"] == ["knowledge", "memory"]


def test_agent_search_uses_mounted_knowledgebase_and_long_term_memory() -> None:
    class Knowledgebase:
        name = "user_knowledgebase"
        index = "support-docs"
        backend = "viking"

        def search(self, query: str) -> list[SimpleNamespace]:
            assert query == "退款规则"
            return [SimpleNamespace(content="七天内可申请退款。")]

    class LongTermMemory:
        name = "customer-memory"
        backend = "viking"

        async def search_memory(
            self,
            *,
            app_name: str,
            user_id: str,
            query: str,
        ) -> SimpleNamespace:
            assert (app_name, user_id, query) == ("agent", "user-1", "偏好")
            content = SimpleNamespace(
                parts=[SimpleNamespace(text="用户偏好中文回复。")]
            )
            entry = SimpleNamespace(
                author="user",
                content=content,
                timestamp=1_700_000_000.0,
            )
            return SimpleNamespace(memories=[entry])

    root_agent = _root_agent()
    setattr(root_agent, "knowledgebase", Knowledgebase())
    setattr(root_agent, "long_term_memory", LongTermMemory())
    client = TestClient(agentkit_app.create_agentkit_app(root_agent))

    knowledge = client.get(
        "/web/search",
        params={"source": "knowledge", "app_name": "agent", "q": "退款规则"},
    )
    memory = client.get(
        "/web/search",
        params={
            "source": "memory",
            "app_name": "agent",
            "q": "偏好",
            "user_id": "user-1",
        },
    )

    assert knowledge.json() == {
        "mounted": True,
        "sourceName": "support-docs",
        "sourceType": "viking",
        "results": [{"content": "七天内可申请退款。"}],
    }
    assert memory.json() == {
        "mounted": True,
        "sourceName": "customer-memory",
        "sourceType": "viking",
        "results": [
            {
                "content": "用户偏好中文回复。",
                "author": "user",
                "timestamp": 1_700_000_000.0,
            }
        ],
    }


def test_agent_search_reports_unmounted_components() -> None:
    client = TestClient(agentkit_app.create_agentkit_app(_root_agent()))

    response = client.get(
        "/web/search",
        params={"source": "knowledge", "app_name": "agent", "q": "退款"},
    )

    assert response.json() == {"mounted": False, "results": []}


def test_create_agentkit_app_reuses_agent_memory_and_configures_feishu(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    memory = object()
    root_agent = _root_agent()
    setattr(root_agent, "short_term_memory", memory)
    configured: list[tuple[FastAPI, BaseAgent, object]] = []

    monkeypatch.setattr(
        agentkit_app,
        "_configure_feishu_lifecycle",
        lambda app, agent, short_term_memory: configured.append(
            (app, agent, short_term_memory)
        ),
    )

    app = agentkit_app.create_agentkit_app(root_agent, enable_feishu=True)

    assert _FakeAgentServer.instances[-1].short_term_memory is memory
    assert configured == [(app, root_agent, memory)]


def test_feishu_lifecycle_starts_and_stops_with_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runners: list[dict[str, Any]] = []
    events: list[str] = []

    class _FakeRunner:
        def __init__(self, **kwargs: Any) -> None:
            runners.append(kwargs)

    async def fake_start(app: FastAPI, runner: object) -> None:
        del app, runner
        events.append("start")

    async def fake_stop(app: FastAPI) -> None:
        del app
        events.append("stop")

    monkeypatch.setattr(veadk, "Runner", _FakeRunner)
    monkeypatch.setattr(agentkit_app, "_start_feishu_channel", fake_start)
    monkeypatch.setattr(agentkit_app, "_stop_feishu_channel", fake_stop)
    root_agent = _root_agent()

    app = agentkit_app.create_agentkit_app(root_agent, enable_feishu=True)
    with TestClient(app):
        assert events == ["start"]

    assert events == ["start", "stop"]
    assert runners[0]["agent"] is root_agent
    assert runners[0]["app_name"] == "agent"
    assert isinstance(runners[0]["short_term_memory"], _FakeShortTermMemory)


def test_run_agentkit_app_uses_explicit_and_environment_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = agentkit_app.create_agentkit_app(_root_agent())
    server = _FakeAgentServer.instances[-1]

    agentkit_app.run_agentkit_app(app, host="127.0.0.1", port=9000)
    assert server.run_kwargs == {"host": "127.0.0.1", "port": 9000}

    monkeypatch.setenv("HOST", "0.0.0.0")
    monkeypatch.setenv("PORT", "8080")
    agentkit_app.run_agentkit_app(app)
    assert server.run_kwargs == {"host": "0.0.0.0", "port": 8080}


def test_run_agentkit_app_rejects_unmanaged_app() -> None:
    with pytest.raises(ValueError, match="create_agentkit_app"):
        agentkit_app.run_agentkit_app(FastAPI())
