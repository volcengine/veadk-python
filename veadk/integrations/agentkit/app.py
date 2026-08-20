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
import json
import os
import threading
import traceback
from collections.abc import Callable, Iterable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, Protocol, cast

from agentkit.apps import AgentkitAgentServerApp
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import LoopAgent, ParallelAgent, RunConfig, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.agents.run_config import StreamingMode
from google.adk.apps.app import App
from google.adk.cli.api_server import RunAgentRequest
from google.adk.runners import Runner as AdkRunner
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from veadk.agent_metadata import (
    agent_component_summaries,
    agent_search_sources,
    agent_skill_summaries,
)
from veadk.agent_search import search_agent_component
from veadk.cli.frontend_invocation import FrontendInvocationPlugin
from veadk.integrations.agentkit.session_capabilities import (
    CapabilityError,
    SessionCapabilityService,
    mount_session_capability_routes,
)
from veadk.memory.short_term_memory import ShortTermMemory

if TYPE_CHECKING:
    from agentkit.identity import RuntimeIdentity  # pyright: ignore[reportMissingImports]

    from veadk.runner import Runner


class _MultiAppAdkServer(Protocol):
    """ADK services recovered from the multi-app server route closure."""

    session_service: Any
    artifact_service: Any
    memory_service: Any
    credential_service: Any
    auto_create_session: bool
    default_app_name: str | None

    async def get_runner_async(self, app_name: str) -> Any: ...


_MAX_AGENT_GRAPH_DEPTH = 8
_SERVER_STATE_KEY = "_veadk_agentkit_server"
_ADK_SERVER_STATE_KEY = "_veadk_adk_server"
_DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY = "_veadk_dynamic_a2a_routes_enabled"
_SESSION_CAPABILITY_SERVICE_STATE_KEY = "_veadk_session_capability_service"
_REGISTRY_CONFIG_ATTR = "_veadk_a2a_registry_config"
_RUNTIME_IDENTITY_REQUIREMENT = (
    "Runtime identity requires agentkit-sdk-python>=0.8.2; "
    "upgrade AgentKit SDK before passing identity."
)


def _agentkit_supports_runtime_identity() -> bool:
    """Return whether the installed AgentKit server exposes identity binding."""
    try:
        parameters = inspect.signature(AgentkitAgentServerApp).parameters
    except (TypeError, ValueError):
        return False
    return "identity" in parameters and "identity_health_routes" in parameters


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


def _tool_name(tool: object) -> str | None:
    name = getattr(tool, "__name__", None) or getattr(tool, "name", None)
    return str(name) if name else None


def _content_text(content: object) -> str:
    parts = getattr(content, "parts", None) or []
    texts: list[str] = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(str(text))
    return "\n".join(texts)


def _has_a2a_registry_config(agent: object) -> bool:
    if getattr(agent, _REGISTRY_CONFIG_ATTR, None) is not None:
        return True
    return any(
        _has_a2a_registry_config(child)
        for child in getattr(agent, "sub_agents", []) or []
    )


def _add_dynamic_a2a_agent_tools(agent: object, prompt: str) -> int:
    attached = 0
    registry_config = getattr(agent, _REGISTRY_CONFIG_ATTR, None)
    prompt = prompt.strip()
    if registry_config is not None and prompt:
        from veadk.tools.builtin_tools.a2a_registry import build_remote_a2a_agent_tools

        dynamic_tools = build_remote_a2a_agent_tools(prompt, registry_config)
        existing = {
            name
            for tool in getattr(agent, "tools", []) or []
            if (name := _tool_name(tool))
        }
        for tool in dynamic_tools:
            name = _tool_name(tool)
            if not name or name in existing:
                continue
            getattr(agent, "tools").append(tool)
            existing.add(name)
            attached += 1

    for child in getattr(agent, "sub_agents", []) or []:
        attached += _add_dynamic_a2a_agent_tools(child, prompt)
    return attached


def _spawn_dynamic_a2a_agent(base_agent: BaseAgent, prompt: str) -> BaseAgent:
    cloned = base_agent.clone(update={})
    attached = _add_dynamic_a2a_agent_tools(cloned, prompt)
    if _has_a2a_registry_config(cloned):
        print(
            f"dynamic A2A tool assembly completed for this turn: attached={attached}",
            flush=True,
        )
    return cloned


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
    instruction = getattr(agent, "instruction", "")
    return {
        "id": agent_id,
        "name": _display_name(agent_id, display_names),
        "description": getattr(agent, "description", "") or "",
        "instruction": instruction if isinstance(instruction, str) else "",
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


def _configure_harness_extension_lifecycle(
    app: FastAPI,
    harness_extension: Any,
) -> None:
    """Expose a safe status route and close the managed extension on shutdown."""

    status_payload = getattr(harness_extension, "sidecar_status_payload", None)
    close = getattr(harness_extension, "close", None)
    if not callable(status_payload) or not callable(close):
        raise TypeError(
            "harness_extension must provide sidecar_status_payload() and close()"
        )

    @app.get("/web/harness-sidecar/status")
    def harness_sidecar_status() -> dict[str, Any]:
        payload = status_payload()
        if not isinstance(payload, Mapping):
            raise RuntimeError("Harness Sidecar status must be an object")
        return {str(key): value for key, value in payload.items()}

    original_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(fastapi_app: FastAPI):
        async with original_lifespan(fastapi_app):
            try:
                yield
            finally:
                close()

    app.router.lifespan_context = lifespan


def _add_introspection_routes(
    app: FastAPI,
    root_agent: BaseAgent,
    display_names: Mapping[str, str],
    agent_draft: Mapping[str, Any] | None = None,
    *,
    app_name: str | None = None,
) -> None:
    expected_name = app_name or str(getattr(root_agent, "name", "") or "")

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/web/agent-info/{app_name}")
    def agent_info(app_name: str) -> dict[str, Any]:
        if app_name != expected_name:
            raise HTTPException(status_code=404, detail="unknown agent: " + app_name)
        node = _agent_node(root_agent, display_names)
        return {
            **{key: node[key] for key in ("id", "name", "description", "type")},
            "model": node["model"],
            "tools": node["tools"],
            "skills": node["skills"],
            "components": node["components"],
            "searchSources": agent_search_sources(root_agent),
            "subAgents": [
                _display_name(
                    str(getattr(child, "name", "") or ""),
                    display_names,
                )
                for child in getattr(root_agent, "sub_agents", []) or []
            ],
            "graph": node,
            "draft": dict(agent_draft) if agent_draft is not None else None,
        }

    @app.get("/web/search")
    async def agent_search(
        source: str,
        app_name: str,
        q: str,
        user_id: str = "",
    ) -> dict[str, Any]:
        if app_name != expected_name:
            raise HTTPException(status_code=404, detail="unknown agent: " + app_name)
        if source not in {"knowledge", "memory"}:
            raise HTTPException(
                status_code=400,
                detail="unsupported Agent search source: " + source,
            )
        if source == "memory" and not user_id:
            raise HTTPException(
                status_code=400,
                detail="user_id is required for long-term memory search",
            )
        return await search_agent_component(
            root_agent,
            source,
            q,
            app_name=expected_name,
            user_id=user_id,
        )

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
        "/web/search",
        "/web/harness-sidecar/status",
        "/harness/capabilities/tools",
        "/harness/skills/spaces",
        "/harness/skills/spaces/{space_id}/skills",
        "/harness/apps/{app_name}/users/{user_id}/sessions/{session_id}/capabilities",
        "/harness/apps/{app_name}/users/{user_id}/sessions/{session_id}/capabilities/{capability_id}",
        "/harness/run_sse",
        "/assets",
        "/webui",
        "/webui/{path:path}",
    }

    def is_priority_route(route: Any) -> bool:
        if getattr(route, "path", None) in priority_paths:
            return True
        included_router = getattr(route, "original_router", None)
        return any(
            getattr(included_route, "path", None) in priority_paths
            for included_route in getattr(included_router, "routes", ())
        )

    priority_routes = [route for route in app.router.routes if is_priority_route(route)]
    if priority_routes:
        app.router.routes[:] = priority_routes + [
            route for route in app.router.routes if route not in priority_routes
        ]


def _promote_route(app: FastAPI, endpoint: Callable[..., Any]) -> None:
    routes = app.router.routes
    for index, route in enumerate(routes):
        if getattr(route, "endpoint", None) == endpoint:
            routes.insert(0, routes.pop(index))
            return


class _RuntimeServices:
    def __init__(self, app: FastAPI):
        agent_server = getattr(app.state, _SERVER_STATE_KEY, None)
        if agent_server is not None:
            self._load_from_server(getattr(agent_server, "server", agent_server))
            return

        adk_server = getattr(app.state, _ADK_SERVER_STATE_KEY, None)
        if adk_server is not None:
            self._load_from_server(adk_server)
            return

        attrs = getattr(app, "_tmpl_attrs", {})
        self.default_app_name = attrs.get("app_name")
        self.current_app_name_ref = attrs.get("current_app_name_ref")
        self.artifact_service = attrs.get("artifact_service")
        self.session_service = attrs.get("session_service")
        self.memory_service = attrs.get("memory_service")
        self.credential_service = attrs.get("credential_service")
        self.auto_create_session = bool(attrs.get("auto_create_session", False))

    def _load_from_server(self, server: object) -> None:
        self.default_app_name = getattr(server, "default_app_name", None)
        self.current_app_name_ref = getattr(server, "current_app_name_ref", None)
        self.artifact_service = getattr(server, "artifact_service", None)
        self.session_service = getattr(server, "session_service", None)
        self.memory_service = getattr(server, "memory_service", None)
        self.credential_service = getattr(server, "credential_service", None)
        self.auto_create_session = bool(getattr(server, "auto_create_session", False))


def _dynamic_runner(
    services: _RuntimeServices,
    *,
    app_name: str,
    root_agent: BaseAgent,
    prompt: str,
    plugins: Iterable[Any] = (),
) -> AdkRunner:
    if services.session_service is None:
        raise RuntimeError("ADK session service is unavailable")
    run_agent = _spawn_dynamic_a2a_agent(root_agent, prompt)
    if plugins:
        agent_app = App(
            name=app_name,
            root_agent=run_agent,
            plugins=_runtime_plugins(plugins),
        )
    else:
        agent_app = App(
            name=app_name,
            root_agent=run_agent,
            plugins=[FrontendInvocationPlugin()],
        )
    return AdkRunner(
        app=agent_app,
        artifact_service=services.artifact_service,
        session_service=services.session_service,
        memory_service=services.memory_service,
        credential_service=services.credential_service,
        auto_create_session=services.auto_create_session,
    )


def _runtime_plugins(plugins: Iterable[Any]) -> list[Any]:
    resolved = list(plugins)
    if not any(isinstance(plugin, FrontendInvocationPlugin) for plugin in resolved):
        resolved.append(FrontendInvocationPlugin())
    return resolved


def _resolve_run_app_name(
    services: _RuntimeServices,
    root_agent: BaseAgent,
    req: RunAgentRequest,
) -> str:
    app_name = req.app_name or services.default_app_name
    if not app_name:
        app_name = getattr(root_agent, "name", "") or ""
    if not app_name:
        raise HTTPException(
            status_code=400,
            detail="app_name is required when ADK_DEFAULT_APP_NAME is not set",
        )
    req.app_name = app_name
    if services.current_app_name_ref is not None:
        services.current_app_name_ref.value = app_name
    return app_name


def _run_request_custom_metadata(req: RunAgentRequest) -> dict[str, Any] | None:
    metadata = getattr(req, "custom_metadata", None)
    return metadata if isinstance(metadata, dict) and metadata else None


def _resolve_invoke_app_name(
    services: _RuntimeServices,
    root_agent: BaseAgent,
) -> str:
    app_name = services.default_app_name or getattr(root_agent, "name", "") or ""
    if not app_name:
        raise HTTPException(
            status_code=400,
            detail="app_name is required when ADK_DEFAULT_APP_NAME is not set",
        )
    if services.current_app_name_ref is not None:
        services.current_app_name_ref.value = app_name
    return app_name


async def _invoke_text(request: Request) -> str:
    body = await request.body()
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except Exception:
        return body.decode("utf-8", errors="replace")
    if isinstance(payload, dict):
        text = payload.get("prompt")
        if text is not None:
            return str(text)
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return ""


def _configure_dynamic_a2a_routes(
    app: FastAPI,
    root_agent: BaseAgent,
    plugins: Iterable[Any] = (),
) -> None:
    if getattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, False):
        return

    services = _RuntimeServices(app)
    session_service = services.session_service
    if session_service is None:
        return

    @app.post("/run", response_model=None)
    async def run_agent_dynamic(
        req: RunAgentRequest,
        request: Request,
    ) -> list[Any] | Response:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
            plugins=plugins,
        )
        custom_metadata = _run_request_custom_metadata(req)
        run_config = (
            RunConfig(custom_metadata=custom_metadata) if custom_metadata else None
        )

        async def worker() -> list[Any]:
            async with Aclosing(
                runner.run_async(
                    user_id=req.user_id,
                    session_id=req.session_id,
                    new_message=req.new_message,
                    state_delta=req.state_delta,
                    invocation_id=req.invocation_id,
                    run_config=run_config,
                )
            ) as agen:
                return [event async for event in agen]

        worker_task = asyncio.create_task(worker())

        async def monitor() -> None:
            try:
                while True:
                    message = await request.receive()
                    if message.get("type") == "http.disconnect":
                        worker_task.cancel()
                        break
            except asyncio.CancelledError:
                pass

        monitor_task = asyncio.create_task(monitor())
        try:
            return await worker_task
        except asyncio.CancelledError:
            if await request.is_disconnected():
                return Response(status_code=499)
            raise
        finally:
            monitor_task.cancel()

    @app.post("/run_sse")
    async def run_agent_sse_dynamic(req: RunAgentRequest) -> StreamingResponse:
        app_name = _resolve_run_app_name(services, root_agent, req)
        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=_content_text(req.new_message),
            plugins=plugins,
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
        custom_metadata = _run_request_custom_metadata(req)

        if not runner.auto_create_session:
            session = await session_service.get_session(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
            if not session:
                await session_service.create_session(
                    app_name=app_name,
                    user_id=req.user_id,
                    session_id=req.session_id,
                )

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        new_message=req.new_message,
                        state_delta=req.state_delta,
                        run_config=RunConfig(
                            streaming_mode=stream_mode,
                            custom_metadata=custom_metadata,
                        ),
                        invocation_id=req.invocation_id,
                    )
                ) as agen:
                    async for event in agen:
                        events_to_stream = [event]
                        if (
                            not req.function_call_event_id
                            and event.actions.artifact_delta
                            and event.content
                            and event.content.parts
                        ):
                            content_event = event.model_copy(deep=True)
                            content_event.actions.artifact_delta = {}
                            artifact_event = event.model_copy(deep=True)
                            artifact_event.content = None
                            events_to_stream = [content_event, artifact_event]

                        for event_to_stream in events_to_stream:
                            yield (
                                "data: "
                                + event_to_stream.model_dump_json(
                                    exclude_none=True,
                                    by_alias=True,
                                )
                                + "\n\n"
                            )
            except Exception as exc:  # noqa: BLE001 - SSE surfaces errors as data.
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    @app.post("/invoke")
    async def invoke_agent_dynamic(request: Request) -> StreamingResponse:
        app_name = _resolve_invoke_app_name(services, root_agent)
        user_id = request.headers.get("user_id") or "agentkit_user"
        session_id = request.headers.get("session_id") or ""
        prompt = await _invoke_text(request)
        content = types.UserContent(parts=[types.Part(text=prompt or "")])

        session = await session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if not session:
            await session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )

        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=prompt,
            plugins=plugins,
        )

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=user_id,
                        session_id=session_id,
                        new_message=content,
                        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                    )
                ) as agen:
                    async for event in agen:
                        yield (
                            "data: "
                            + event.model_dump_json(
                                exclude_none=True,
                                by_alias=True,
                            )
                            + "\n\n"
                        )
            except Exception as exc:  # noqa: BLE001 - SSE surfaces errors as data.
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    _promote_route(app, run_agent_dynamic)
    _promote_route(app, run_agent_sse_dynamic)
    _promote_route(app, invoke_agent_dynamic)
    setattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, True)


def _configure_session_capability_routes(
    app: FastAPI,
    root_agent: BaseAgent,
    plugins: Iterable[Any] = (),
) -> None:
    services = _RuntimeServices(app)
    if services.session_service is None:
        return

    capability_service = SessionCapabilityService(
        root_agent=root_agent,
        session_service=services.session_service,
    )
    setattr(app.state, _SESSION_CAPABILITY_SERVICE_STATE_KEY, capability_service)
    mount_session_capability_routes(app=app, service=capability_service)

    @app.post("/harness/run_sse")
    async def run_agent_sse_with_session_capabilities(
        req: RunAgentRequest,
    ) -> StreamingResponse:
        app_name = _resolve_run_app_name(services, root_agent, req)
        try:
            run_agent = await capability_service.build_agent(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
        except CapabilityError as exc:
            raise HTTPException(
                status_code=exc.status_code,
                detail=str(exc),
            ) from exc

        _add_dynamic_a2a_agent_tools(run_agent, _content_text(req.new_message))
        session_service = services.session_service
        if session_service is None:
            raise HTTPException(status_code=501, detail="Session service unavailable")
        runner = AdkRunner(
            app=App(name=app_name, root_agent=run_agent, plugins=list(plugins)),
            artifact_service=services.artifact_service,
            session_service=session_service,
            memory_service=services.memory_service,
            credential_service=services.credential_service,
            auto_create_session=services.auto_create_session,
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
        custom_metadata = _run_request_custom_metadata(req)

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        new_message=req.new_message,
                        state_delta=req.state_delta,
                        run_config=RunConfig(
                            streaming_mode=stream_mode,
                            custom_metadata=custom_metadata,
                        ),
                        invocation_id=req.invocation_id,
                    )
                ) as agen:
                    async for event in agen:
                        events_to_stream = [event]
                        if (
                            not req.function_call_event_id
                            and event.actions.artifact_delta
                            and event.content
                            and event.content.parts
                        ):
                            content_event = event.model_copy(deep=True)
                            content_event.actions.artifact_delta = {}
                            artifact_event = event.model_copy(deep=True)
                            artifact_event.content = None
                            events_to_stream = [content_event, artifact_event]

                        for event_to_stream in events_to_stream:
                            yield (
                                "data: "
                                + event_to_stream.model_dump_json(
                                    exclude_none=True,
                                    by_alias=True,
                                )
                                + "\n\n"
                            )
            except Exception as exc:  # noqa: BLE001 - SSE surfaces errors as data.
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    _promote_route(app, run_agent_sse_with_session_capabilities)


def configure_multi_app_session_capability_routes(
    app: FastAPI,
    adk_server: _MultiAppAdkServer,
) -> None:
    """Enable session capability overlays on an ADK multi-app dev server."""

    async def service_for(app_name: str) -> SessionCapabilityService:
        source_runner = await adk_server.get_runner_async(app_name)
        source_app = getattr(source_runner, "app", None)
        root_agent = getattr(source_app, "root_agent", None)
        if not isinstance(root_agent, BaseAgent):
            raise HTTPException(status_code=404, detail=f"Agent not found: {app_name}")
        return SessionCapabilityService(
            root_agent=root_agent,
            session_service=adk_server.session_service,
        )

    mount_session_capability_routes(
        app=app,
        service_resolver=service_for,
    )

    @app.post("/harness/run_sse")
    async def run_multi_app_with_session_capabilities(
        req: RunAgentRequest,
    ):
        app_name = req.app_name or getattr(adk_server, "default_app_name", None)
        if not app_name:
            raise HTTPException(status_code=400, detail="app_name is required")
        req.app_name = app_name
        try:
            capability_service = await service_for(app_name)
            run_agent = await capability_service.build_agent(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
        except CapabilityError as exc:
            raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

        _add_dynamic_a2a_agent_tools(run_agent, _content_text(req.new_message))
        source_runner = await adk_server.get_runner_async(app_name)
        source_app = getattr(source_runner, "app", None)
        plugins = list(getattr(source_app, "plugins", None) or [])
        runner = AdkRunner(
            app=App(name=app_name, root_agent=run_agent, plugins=plugins),
            artifact_service=adk_server.artifact_service,
            session_service=adk_server.session_service,
            memory_service=adk_server.memory_service,
            credential_service=adk_server.credential_service,
            auto_create_session=adk_server.auto_create_session,
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
        custom_metadata = _run_request_custom_metadata(req)

        async def event_generator():
            try:
                async with Aclosing(
                    runner.run_async(
                        user_id=req.user_id,
                        session_id=req.session_id,
                        new_message=req.new_message,
                        state_delta=req.state_delta,
                        run_config=RunConfig(
                            streaming_mode=stream_mode,
                            custom_metadata=custom_metadata,
                        ),
                        invocation_id=req.invocation_id,
                    )
                ) as agen:
                    async for event in agen:
                        events_to_stream = [event]
                        if (
                            not req.function_call_event_id
                            and event.actions.artifact_delta
                            and event.content
                            and event.content.parts
                        ):
                            content_event = event.model_copy(deep=True)
                            content_event.actions.artifact_delta = {}
                            artifact_event = event.model_copy(deep=True)
                            artifact_event.content = None
                            events_to_stream = [content_event, artifact_event]

                        for event_to_stream in events_to_stream:
                            yield (
                                "data: "
                                + event_to_stream.model_dump_json(
                                    exclude_none=True,
                                    by_alias=True,
                                )
                                + "\n\n"
                            )
            except Exception as exc:  # noqa: BLE001 - SSE surfaces errors as data.
                yield f"data: {json.dumps({'error': str(exc)})}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")

    _promote_route(app, run_multi_app_with_session_capabilities)


def create_agentkit_app(
    root_agent: BaseAgent | None = None,
    display_names: Mapping[str, str] | None = None,
    *,
    app: App | None = None,
    agent_draft: Mapping[str, Any] | None = None,
    enable_feishu: bool = False,
    identity: RuntimeIdentity | None = None,
    harness_extension: Any | None = None,
) -> FastAPI:
    """Create an AgentKit-compatible FastAPI app for ``root_agent``.

    The app includes AgentKit's conversation APIs, VeADK health and topology
    endpoints, the bundled Web UI, local short-term memory fallback, and the
    optional Feishu channel lifecycle.

    Args:
        root_agent: Root ADK agent served by AgentKit. Mutually exclusive with
            ``app``.
        display_names: User-facing names keyed by technical agent name.
        app: Optional ADK App whose plugins must be preserved by every runner.
        agent_draft: Optional sanitized builder draft for read-only editing metadata.
        enable_feishu: Whether to start the Feishu channel with credentials from
            ``FEISHU_APP_ID`` and ``FEISHU_APP_SECRET``.
        identity: Optional AgentKit Runtime identity boundary. When supplied,
            AgentKit verifies and binds the inbound user identity before VeADK
            Agent or Tool code runs.
        harness_extension: Optional managed Harness Extension. Its status route
            is mounted and it is closed during application shutdown.

    Returns:
        The configured FastAPI application.
    """
    adk_app = app
    if adk_app is not None and root_agent is not None:
        raise TypeError("Only one of 'root_agent' or 'app' can be provided")
    if adk_app is not None:
        root_agent = adk_app.root_agent
    if root_agent is None:
        raise TypeError("Either 'root_agent' or 'app' must be provided")
    names = dict(display_names or {})
    app_plugins = list(getattr(adk_app, "plugins", None) or [])
    short_term_memory = getattr(root_agent, "short_term_memory", None)
    if short_term_memory is None:
        short_term_memory = ShortTermMemory(backend="local")

    agent_server_kwargs: dict[str, Any] = {"short_term_memory": short_term_memory}
    if adk_app is not None:
        agent_server_kwargs["app"] = adk_app
    else:
        agent_server_kwargs["agent"] = root_agent
    if identity is not None:
        if not _agentkit_supports_runtime_identity():
            raise RuntimeError(_RUNTIME_IDENTITY_REQUIREMENT)
        agent_server_kwargs["identity"] = identity
        # VeADK's fixed /ping route returns only {"status": "ok"}. AgentKit
        # keeps every business and introspection route identity-bound.
        agent_server_kwargs["identity_health_routes"] = ("/ping",)
    agent_server = AgentkitAgentServerApp(**agent_server_kwargs)
    fastapi_app = cast(FastAPI, agent_server.app)
    setattr(fastapi_app.state, _SERVER_STATE_KEY, agent_server)
    _configure_dynamic_a2a_routes(fastapi_app, root_agent, app_plugins)
    _configure_session_capability_routes(fastapi_app, root_agent, app_plugins)

    if enable_feishu:
        _configure_feishu_lifecycle(fastapi_app, root_agent, short_term_memory)
    if harness_extension is not None:
        _configure_harness_extension_lifecycle(fastapi_app, harness_extension)
    _add_introspection_routes(fastapi_app, root_agent, names, agent_draft)
    _mount_webui(fastapi_app)
    _prioritize_platform_routes(fastapi_app)
    return fastapi_app


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
