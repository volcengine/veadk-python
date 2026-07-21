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

"""Build an AgentKit application around a VeADK agent."""

from __future__ import annotations

import asyncio
import inspect
import os
import threading
import traceback
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agentkit.apps import AgentkitAgentServerApp
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import LoopAgent, ParallelAgent, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent

from veadk.agent_metadata import (
    agent_component_summaries,
    agent_skill_summaries,
)
from veadk.memory.short_term_memory import ShortTermMemory

if TYPE_CHECKING:
    from veadk.runner import Runner

_MAX_AGENT_GRAPH_DEPTH = 8
_SERVER_STATE_KEY = "_veadk_agentkit_server"


def _agent_type(agent: object) -> str:
    if isinstance(agent, LoopAgent):
        return "loop"
    if isinstance(agent, SequentialAgent):
        return "sequential"
    if isinstance(agent, ParallelAgent):
        return "parallel"
    if isinstance(agent, RemoteA2aAgent):
        return "a2a"
    return "llm"


def _model_name(model: object) -> str:
    if isinstance(model, str):
        return model
    return str(getattr(model, "model", None) or type(model).__name__)


def _tool_label(tool: object) -> str:
    name = getattr(tool, "name", None) or getattr(tool, "__name__", None)
    return str(name or type(tool).__name__)


def _display_name(
    agent_id: str,
    display_names: Mapping[str, str],
) -> str:
    return display_names.get(agent_id, agent_id)


def _agent_node(
    agent: object,
    display_names: Mapping[str, str],
    depth: int = 0,
    parent_path: tuple[str, ...] = (),
) -> dict[str, Any]:
    agent_id = str(getattr(agent, "name", "") or "")
    path = (*parent_path, agent_id) if agent_id else parent_path
    children: list[dict[str, Any]] = []
    if depth < _MAX_AGENT_GRAPH_DEPTH:
        children = [
            _agent_node(child, display_names, depth + 1, path)
            for child in getattr(agent, "sub_agents", []) or []
        ]
    mode = getattr(agent, "mode", None)
    return {
        "id": agent_id,
        "name": _display_name(agent_id, display_names),
        "description": getattr(agent, "description", "") or "",
        "type": _agent_type(agent),
        "model": _model_name(getattr(agent, "model", "")),
        "tools": [_tool_label(tool) for tool in getattr(agent, "tools", []) or []],
        "skills": agent_skill_summaries(agent),
        "components": agent_component_summaries(agent),
        "path": list(path),
        "mentionable": mode not in ("task", "single_turn"),
        "children": children,
    }


def _get_feishu_channel_method(
    channel: object,
    names: tuple[str, ...],
) -> Callable[[], Any] | None:
    raw_channel = getattr(channel, "channel", None)
    for target in (raw_channel, channel):
        if target is None:
            continue
        for name in names:
            method = getattr(target, name, None)
            if callable(method):
                return method
    return None


def _call_feishu_channel_method(
    loop: asyncio.AbstractEventLoop,
    method: Callable[[], Any],
) -> Any:
    result = method()
    if inspect.isawaitable(result):
        return loop.run_until_complete(result)
    return result


def _connect_feishu_channel(
    loop: asyncio.AbstractEventLoop,
    channel: object,
) -> Any:
    connect = _get_feishu_channel_method(channel, ("start", "connect"))
    if connect is None:
        raise AttributeError("Feishu channel has no start/connect method")
    return _call_feishu_channel_method(loop, connect)


def _disconnect_feishu_channel(
    loop: asyncio.AbstractEventLoop,
    channel: object,
) -> Any:
    disconnect = _get_feishu_channel_method(channel, ("stop", "disconnect"))
    if disconnect is None:
        return None
    return _call_feishu_channel_method(loop, disconnect)


def _stop_feishu_channel_from_lifespan(channel: object) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        _disconnect_feishu_channel(loop, channel)
    finally:
        asyncio.set_event_loop(None)
        loop.close()


def _build_feishu_channel(runner: Runner, app_id: str, app_secret: str) -> object:
    from veadk.extensions import FeishuChannelExtension

    return FeishuChannelExtension(
        runner=runner,
        app_id=app_id,
        app_secret=app_secret,
        channel_kwargs={"transport": "ws"},
        streaming=False,
        reactions=False,
    )


def _run_feishu_channel(
    runner: Runner,
    app_id: str,
    app_secret: str,
    stop_event: threading.Event,
    state: dict[str, Any],
) -> None:
    loop = asyncio.new_event_loop()
    state["loop"] = loop
    asyncio.set_event_loop(loop)
    try:
        while not stop_event.is_set():
            channel = None
            try:
                channel = _build_feishu_channel(runner, app_id, app_secret)
                state["channel"] = channel
                print("feishu channel connecting in dedicated thread", flush=True)
                _connect_feishu_channel(loop, channel)
                print("feishu channel disconnected; reconnecting in 5s", flush=True)
            except Exception as exc:  # The channel reconnects after transport errors.
                stage = "initialization" if channel is None else "connect"
                print(
                    f"feishu channel {stage} failed: "
                    f"{type(exc).__name__}: {exc}; reconnecting in 5s",
                    flush=True,
                )
                if channel is None:
                    print(traceback.format_exc(), flush=True)
            finally:
                if channel is not None:
                    try:
                        _disconnect_feishu_channel(loop, channel)
                    except Exception as exc:  # Cleanup must not stop reconnection.
                        print(
                            "feishu channel disconnect failed: "
                            f"{type(exc).__name__}: {exc}",
                            flush=True,
                        )
                    finally:
                        if state.get("channel") is channel:
                            state["channel"] = None
            stop_event.wait(5)
    finally:
        asyncio.set_event_loop(None)
        state["loop"] = None
        loop.close()


async def _start_feishu_channel(app: FastAPI, runner: Runner) -> None:
    app_id = os.getenv("FEISHU_APP_ID")
    app_secret = os.getenv("FEISHU_APP_SECRET")
    if not app_id or not app_secret:
        print(
            "feishu channel disabled: FEISHU_APP_ID or FEISHU_APP_SECRET is missing",
            flush=True,
        )
        return

    app.state.feishu_channel_state = {"channel": None, "loop": None}
    app.state.feishu_channel_stop_event = threading.Event()
    app.state.feishu_channel_thread = threading.Thread(
        target=_run_feishu_channel,
        args=(
            runner,
            app_id,
            app_secret,
            app.state.feishu_channel_stop_event,
            app.state.feishu_channel_state,
        ),
        name="feishu-channel",
        daemon=True,
    )
    app.state.feishu_channel_thread.start()
    print("feishu channel background thread started", flush=True)


async def _stop_feishu_channel(app: FastAPI) -> None:
    stop_event = getattr(app.state, "feishu_channel_stop_event", None)
    if stop_event is not None:
        stop_event.set()
    state = getattr(app.state, "feishu_channel_state", None) or {}
    channel = state.get("channel")
    if channel is not None:
        await asyncio.to_thread(_stop_feishu_channel_from_lifespan, channel)
    thread = getattr(app.state, "feishu_channel_thread", None)
    if thread is not None:
        await asyncio.to_thread(thread.join, 2)
        if thread.is_alive():
            print(
                "feishu channel background thread did not stop within 2s",
                flush=True,
            )


def _configure_feishu_lifecycle(
    app: FastAPI,
    root_agent: BaseAgent,
    short_term_memory: ShortTermMemory,
) -> None:
    from veadk import Runner

    runner = Runner(
        agent=root_agent,
        app_name=getattr(root_agent, "name", "") or "agent",
        short_term_memory=short_term_memory,
    )
    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        async with original_lifespan(fastapi_app):
            await _start_feishu_channel(fastapi_app, runner)
            try:
                yield
            finally:
                await _stop_feishu_channel(fastapi_app)

    app.router.lifespan_context = lifespan


def _add_introspection_routes(
    app: FastAPI,
    root_agent: BaseAgent,
    display_names: Mapping[str, str],
) -> None:
    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/web/agent-info/{app_name}")
    def agent_info(app_name: str) -> dict[str, Any]:
        expected_name = str(getattr(root_agent, "name", "") or "")
        if app_name != expected_name:
            raise HTTPException(status_code=404, detail="unknown agent: " + app_name)
        node = _agent_node(root_agent, display_names)
        return {
            **{key: node[key] for key in ("id", "name", "description", "type")},
            "model": node["model"],
            "tools": node["tools"],
            "skills": node["skills"],
            "components": node["components"],
            "subAgents": [
                _display_name(
                    str(getattr(child, "name", "") or ""),
                    display_names,
                )
                for child in getattr(root_agent, "sub_agents", []) or []
            ],
            "graph": node,
        }

    @app.get("/web/agent-graph")
    def agent_graph() -> dict[str, Any]:
        node = _agent_node(root_agent, display_names)
        return {
            **{key: node[key] for key in ("id", "name", "description", "type")},
            "model": node["model"],
            "tools": node["tools"],
            "skills": node["skills"],
            "components": node["components"],
            "graph": node,
        }


def _mount_webui(app: FastAPI) -> None:
    import veadk

    webui_dir = Path(veadk.__file__).resolve().parent / "webui"
    if not (webui_dir / "index.html").is_file():
        return

    if (webui_dir / "assets").is_dir():
        app.mount(
            "/assets",
            StaticFiles(directory=str(webui_dir / "assets")),
            name="webui-assets",
        )

    @app.get("/")
    @app.get("/webui")
    @app.get("/webui/{path:path}")
    def webui(path: str = "") -> FileResponse:
        del path
        return FileResponse(webui_dir / "index.html")


def _prioritize_platform_routes(app: FastAPI) -> None:
    priority_paths = {
        "/",
        "/ping",
        "/web/agent-info/{app_name}",
        "/web/agent-graph",
        "/assets",
        "/webui",
        "/webui/{path:path}",
    }
    priority_routes = [
        route
        for route in app.router.routes
        if getattr(route, "path", None) in priority_paths
    ]
    if priority_routes:
        app.router.routes[:] = priority_routes + [
            route for route in app.router.routes if route not in priority_routes
        ]


def create_agentkit_app(
    root_agent: BaseAgent,
    display_names: Mapping[str, str] | None = None,
    *,
    enable_feishu: bool = False,
) -> FastAPI:
    """Create an AgentKit-compatible FastAPI app for ``root_agent``.

    The app includes AgentKit's conversation APIs, VeADK health and topology
    endpoints, the bundled Web UI, local short-term memory fallback, and the
    optional Feishu channel lifecycle.

    Args:
        root_agent: Root ADK agent served by AgentKit.
        display_names: User-facing names keyed by technical agent name.
        enable_feishu: Whether to start the Feishu channel with credentials from
            ``FEISHU_APP_ID`` and ``FEISHU_APP_SECRET``.

    Returns:
        The configured FastAPI application.
    """
    names = dict(display_names or {})
    short_term_memory = getattr(root_agent, "short_term_memory", None)
    if short_term_memory is None:
        short_term_memory = ShortTermMemory(backend="local")

    agent_server = AgentkitAgentServerApp(
        agent=root_agent,
        short_term_memory=short_term_memory,
    )
    app = cast(FastAPI, agent_server.app)
    setattr(app.state, _SERVER_STATE_KEY, agent_server)

    if enable_feishu:
        _configure_feishu_lifecycle(app, root_agent, short_term_memory)
    _add_introspection_routes(app, root_agent, names)
    _mount_webui(app)
    _prioritize_platform_routes(app)
    return app


def run_agentkit_app(
    app: FastAPI,
    *,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Run an app returned by :func:`create_agentkit_app`."""
    agent_server = getattr(app.state, _SERVER_STATE_KEY, None)
    if agent_server is None:
        raise ValueError("app was not created by create_agentkit_app")
    resolved_host = host or os.getenv("HOST", "0.0.0.0")
    resolved_port = port if port is not None else int(os.getenv("PORT", "8000"))
    agent_server.run(host=resolved_host, port=resolved_port)
