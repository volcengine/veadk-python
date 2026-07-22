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
from collections.abc import Callable, Mapping
from contextlib import asynccontextmanager
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from agentkit.apps import AgentkitAgentServerApp
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.agents import LoopAgent, ParallelAgent, RunConfig, SequentialAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.run_config import StreamingMode
from google.adk.cli.api_server import RunAgentRequest
from google.adk.agents.remote_a2a_agent import RemoteA2aAgent
from google.adk.apps.app import App
from google.adk.runners import Runner as AdkRunner
from google.adk.utils.context_utils import Aclosing
from google.genai import types

from veadk.agent_metadata import (
    agent_component_summaries,
    agent_search_sources,
    agent_skill_summaries,
)
from veadk.agent_search import search_agent_component
from veadk.memory.short_term_memory import ShortTermMemory

if TYPE_CHECKING:
    from veadk.runner import Runner

_MAX_AGENT_GRAPH_DEPTH = 8
_SERVER_STATE_KEY = "_veadk_agentkit_server"
_ADK_SERVER_STATE_KEY = "_veadk_adk_server"
_DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY = "_veadk_dynamic_a2a_routes_enabled"
_REGISTRY_CONFIG_ATTR = "_veadk_a2a_registry_config"


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
            "searchSources": agent_search_sources(root_agent),
            "subAgents": [
                _display_name(
                    str(getattr(child, "name", "") or ""),
                    display_names,
                )
                for child in getattr(root_agent, "sub_agents", []) or []
            ],
            "graph": node,
        }

    @app.get("/web/search")
    async def agent_search(
        source: str,
        app_name: str,
        q: str,
        user_id: str = "",
    ) -> dict[str, Any]:
        expected_name = str(getattr(root_agent, "name", "") or "")
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
) -> AdkRunner:
    run_agent = _spawn_dynamic_a2a_agent(root_agent, prompt)
    agent_app = App(name=app_name, root_agent=run_agent, plugins=[])
    return AdkRunner(
        app=agent_app,
        artifact_service=services.artifact_service,
        session_service=services.session_service,
        memory_service=services.memory_service,
        credential_service=services.credential_service,
        auto_create_session=services.auto_create_session,
    )


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
) -> None:
    if getattr(app.state, _DYNAMIC_A2A_ROUTES_ENABLED_STATE_KEY, False):
        return

    services = _RuntimeServices(app)
    if services.session_service is None or not _has_a2a_registry_config(root_agent):
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
        )
        stream_mode = StreamingMode.SSE if req.streaming else StreamingMode.NONE
        custom_metadata = _run_request_custom_metadata(req)

        if not runner.auto_create_session:
            session = await services.session_service.get_session(
                app_name=app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            )
            if not session:
                raise HTTPException(
                    status_code=404,
                    detail=f"Session not found: {req.session_id}",
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

        session = await services.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if not session:
            await services.session_service.create_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )

        runner = _dynamic_runner(
            services,
            app_name=app_name,
            root_agent=root_agent,
            prompt=prompt,
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
    _configure_dynamic_a2a_routes(app, root_agent)

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
