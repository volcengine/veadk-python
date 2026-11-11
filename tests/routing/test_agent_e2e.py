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
"""End-to-end routing through a real ADK Runner and a real HTTP Decision service.

The model itself is deterministic, but everything above it is the production
path: Agent construction, config.yaml auto-discovery, the ADK callback, the
routing proxy, httpx, TCP, the local System One-shaped server, and sessions.
"""

import json
import threading
from collections.abc import AsyncGenerator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from google.adk.apps import App
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from veadk import Agent
from veadk.configs.routing_configs import QueryRoutingConfig
from veadk.routing.llm import RoutingLlm
from veadk.routing.store import get_route_store


class _Handler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib naming
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length))
        state = "\n".join(
            part.get("text", "")
            for part in body.get("state", [])
            if part.get("type") == "text"
        )
        self.server.requests.append(body)

        if "FAIL" in state:
            self.send_response(500)
            self.end_headers()
            return

        values = {
            "is_complex": 0.99 if "COMPLEX" in state else 0.01,
            "needs_tools": 0.01,
            "needs_long_context": 0.01,
            "is_high_stakes": 0.01,
        }
        payload = {
            "answers": {
                name: {"type": "noul", "noul": value} for name, value in values.items()
            }
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *args):
        pass


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.requests: list[dict] = []


@contextmanager
def decision_server():
    server = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class NamedLlm(BaseLlm):
    model: str = "named"
    reply: str = ""
    calls: int = 0

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        self.calls += 1
        yield LlmResponse(
            content=types.Content(role="model", parts=[types.Part(text=self.reply)])
        )


def write_config(tmp_path, server, *, mode="enforce"):
    (tmp_path / "config.yaml").write_text(
        f"""
query_routing:
  mode: {mode}
  simple_models:
    - cheap-model
  decision:
    api_url: http://127.0.0.1:{server.server_address[1]}/api/v1/systemone
    api_key: e2e-key
    model: e2e-judge
""",
        encoding="utf-8",
    )


def make_agent():
    agent = Agent(
        name="e2e_agent",
        model_name="strong-model",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
        model_api_key="e2e-model-key",
    )
    assert isinstance(agent.model, RoutingLlm)
    agent.model.strong_model = NamedLlm(model="strong", reply="STRONG")
    agent.model.registry.runtimes[0].llm = NamedLlm(model="cheap", reply="CHEAP")
    return agent


async def run_turn(agent, *, session_id, message):
    app = App(name="e2e-app", root_agent=agent)
    service = InMemorySessionService()
    await service.create_session(
        app_name="e2e-app", user_id="user", session_id=session_id
    )
    runner = Runner(app=app, session_service=service)
    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text=message)]),
        )
    ]
    return "".join(
        part.text
        for event in events
        if event.content
        for part in event.content.parts
        if isinstance(part.text, str)
    )


@pytest.fixture(autouse=True)
def _clear_store():
    get_route_store().clear()
    yield
    get_route_store().clear()


@pytest.mark.asyncio
async def test_simple_query_uses_cheap_model_and_one_decision_call(
    tmp_path, monkeypatch
):
    with decision_server() as server:
        write_config(tmp_path, server)
        monkeypatch.chdir(tmp_path)
        agent = make_agent()
        cheap = agent.model.registry.runtimes[0].llm

        text = await run_turn(
            agent, session_id="simple", message="你好，介绍一下你自己"
        )

        assert text == "CHEAP"
        assert cheap.calls == 1
        assert len(server.requests) == 1
        assert set(server.requests[0]["questions"]) == {
            "is_complex",
            "needs_tools",
            "needs_long_context",
            "is_high_stakes",
        }
        assert "你好" in json.dumps(server.requests[0]["state"], ensure_ascii=False)


@pytest.mark.asyncio
async def test_next_invocation_is_classified_independently(tmp_path, monkeypatch):
    with decision_server() as server:
        write_config(tmp_path, server)
        monkeypatch.chdir(tmp_path)
        agent = make_agent()
        strong = agent.model.strong_model
        cheap = agent.model.registry.runtimes[0].llm

        first = await run_turn(
            agent, session_id="complex", message="COMPLEX: 设计一个系统"
        )
        second = await run_turn(agent, session_id="complex", message="再解释一下")

        assert first == "STRONG"
        assert second == "CHEAP"
        assert cheap.calls == 1
        assert strong.calls == 1
        # A new user invocation is classified again.
        assert len(server.requests) == 2


@pytest.mark.asyncio
async def test_decision_failure_falls_back_to_strong(tmp_path, monkeypatch):
    with decision_server() as server:
        write_config(tmp_path, server)
        monkeypatch.chdir(tmp_path)
        agent = make_agent()

        text = await run_turn(agent, session_id="failure", message="FAIL please")

        assert text == "STRONG"
        assert len(server.requests) == 1


@pytest.mark.asyncio
async def test_shadow_mode_never_switches(tmp_path, monkeypatch):
    with decision_server() as server:
        write_config(tmp_path, server, mode="shadow")
        monkeypatch.chdir(tmp_path)
        agent = make_agent()
        cheap = agent.model.registry.runtimes[0].llm

        text = await run_turn(agent, session_id="shadow", message="你好")

        assert text == "STRONG"
        assert cheap.calls == 0
        assert len(server.requests) == 1


@pytest.mark.asyncio
async def test_config_without_routing_block_is_untouched(tmp_path, monkeypatch):
    (tmp_path / "config.yaml").write_text("model:\n  agent:\n    name: x\n")
    monkeypatch.chdir(tmp_path)

    agent = Agent(
        name="plain_agent",
        model_name="strong-model",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
        model_api_key="e2e-model-key",
    )

    assert not isinstance(agent.model, RoutingLlm)
    assert agent.before_model_callback is None


def make_router_agent(name, **kwargs):
    return Agent(
        name=name,
        model_name="strong-model",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
        model_api_key="e2e-model-key",
        query_routing={"simple_models": ["cheap-model"]},
        **kwargs,
    )


async def noop_callback(callback_context, llm_request):
    return None


def test_existing_callable_callback_is_preserved():
    agent = make_router_agent("callback_agent", before_model_callback=noop_callback)
    assert isinstance(agent.model, RoutingLlm)
    assert agent.before_model_callback is noop_callback


def test_existing_callback_list_is_extended():
    agent = make_router_agent(
        "callback_list_agent", before_model_callback=[noop_callback]
    )
    assert agent.before_model_callback[0] is noop_callback
    assert len(agent.before_model_callback) == 1


def test_routing_on_a_non_adk_runtime_is_rejected():
    agent = Agent(
        name="runtime_agent",
        model_name="strong-model",
        model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
        model_api_key="e2e-model-key",
        query_routing=False,
    )
    agent.runtime = "codex"
    agent.query_routing = QueryRoutingConfig(simple_models=["cheap-model"])

    with pytest.raises(ValueError, match="only supported by the ADK runtime"):
        agent._setup_query_routing()


def test_update_model_is_rejected_while_routing_is_enabled():
    agent = make_router_agent("update_agent")

    with pytest.raises(ValueError, match="update_model is not supported"):
        agent.update_model("another-model")


@pytest.mark.asyncio
async def test_explicit_false_disables_yaml_routing(tmp_path, monkeypatch):
    with decision_server() as server:
        write_config(tmp_path, server)
        monkeypatch.chdir(tmp_path)

        agent = Agent(
            name="disabled_agent",
            model_name="strong-model",
            model_api_base="https://ark.cn-beijing.volces.com/api/v3/",
            model_api_key="e2e-model-key",
            query_routing=False,
        )

        assert not isinstance(agent.model, RoutingLlm)
