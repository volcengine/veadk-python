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

"""Harness server: serve the env-assembled agent over HTTP.

The agent is built once from the environment (see ``agent.py``) and exposed three
ways on a single FastAPI app:

* ``POST /harness/invoke`` — the harness entry point, with once-time ``harness``
  overrides (clone the base agent, apply the override, run a throwaway runner).
* The Google ADK web/api routes (``/run``, ``/run_sse``, ``/list-apps``, session
  management, …), served by an ``AdkWebServer`` over the single in-memory agent;
  ``/run_sse`` is wrapped so harness overrides and per-turn registry tools can
  be applied before the model call.
* The A2A protocol routes (agent card at ``/.well-known/agent-card.json`` plus the
  JSON-RPC endpoint), mounted at ``/`` for the base agent.

The A2A protocol surface serves the base agent only. Harness once-time overrides
are available through ``/harness/invoke`` and the wrapped ``/run_sse`` route.

Run with either:
    python app.py
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import json
import os
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from google.adk.agents import RunConfig
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.run_config import StreamingMode
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.cli.adk_web_server import AdkWebServer, RunAgentRequest
from google.adk.cli.utils.base_agent_loader import BaseAgentLoader
from google.adk.evaluation.local_eval_set_results_manager import (
    LocalEvalSetResultsManager,
)
from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
from google.adk.events import Event
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.plugins import BasePlugin
from google.adk.sessions import Session
from google.adk.utils.context_utils import Aclosing
from typing_extensions import override

from veadk import Agent
from veadk.a2a.registry_client import (
    registry_authorization_from_headers,
    registry_tip_token_from_headers,
)
from veadk.a2a.utils.agent_to_a2a import to_a2a
from veadk.cloud.harness_app.agent import agent, short_term_memory
from veadk.cloud.harness_app.harness_plugins import (
    build_harness_plugins_from_enhance,
    build_harness_plugins_from_headers,
    build_harness_plugins_from_runtime_env,
)
from veadk.cloud.harness_app.metrics import HarnessLlmUsagePlugin
from veadk.cloud.harness_app.types import (
    HarnessAgentConfigRequest,
    HarnessCompactionMetric,
    HarnessCreateSessionRequest,
    HarnessEnhanceOverrides,
    HarnessOverrides,
    HarnessPluginMetrics,
    HarnessResponseMetrics,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
)
from veadk.cloud.harness_app.utils import (
    SkillLoadError,
    ToolLoadError,
    harness_overrides_from_env,
    has_a2a_registry_config,
    merge_harness_overrides,
    spawn_harness_run_agent,
)
from veadk.integrations.agentkit.app import (
    _ADK_SERVER_STATE_KEY,
    _add_introspection_routes,
    _configure_studio_tool_routes,
)
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

HARNESS_NAME = os.getenv("HARNESS_NAME", "default")
# Harness default max LLM calls per run, from harness.yaml (overridable per
# invocation). Unset uses the documented default.
DEFAULT_MAX_LLM_CALLS = (
    int(os.environ["MAX_LLM_CALLS"]) if os.environ.get("MAX_LLM_CALLS") else 10
)
RETURN_LLM_USAGE = os.getenv("HARNESS_APP_RETURN_LLM_USAGE", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_RESOURCE_HARNESS_FIELDS = ("knowledgebase", "longterm_memory")
_RESOURCE_ID_FIELDS = ("id", "_id", "resource_id", "index", "app_name")


def _content_text(content: Any) -> str:
    parts = getattr(content, "parts", None) or []
    texts = []
    for part in parts:
        text = getattr(part, "text", None)
        if text:
            texts.append(text)
    return "\n".join(texts)


def _harness_config_delta(overrides: HarnessOverrides) -> dict[str, Any]:
    return merge_harness_overrides(overrides).model_dump(
        mode="json",
        exclude_unset=True,
        exclude_none=False,
    )


def _merge_harness_config(
    current: dict[str, Any] | HarnessOverrides | None,
    overrides: dict[str, Any] | HarnessOverrides | None,
) -> dict[str, Any]:
    return _harness_config_delta(merge_harness_overrides(current, overrides))


def _public_harness_config(config: dict[str, Any]) -> dict[str, Any]:
    public_config = dict(config)
    for field in _RESOURCE_HARNESS_FIELDS:
        value = public_config.get(field)
        if value is None:
            public_config.pop(field, None)
            continue
        if isinstance(value, dict):
            resource_id = _public_resource_id(value)
            public_config[field] = {"id": resource_id} if resource_id else {}
    return public_config


def _public_resource_id(value: dict[str, Any]) -> str:
    config = value.get("config")
    candidates = [value.get(field) for field in _RESOURCE_ID_FIELDS]
    if isinstance(config, dict):
        candidates.extend(config.get(field) for field in _RESOURCE_ID_FIELDS)
    for candidate in candidates:
        if candidate not in {None, ""}:
            return str(candidate)
    return ""


class _HarnessAgentLoader(BaseAgentLoader):
    """Serve the single env-built harness agent to the ADK web server.

    The harness builds one agent in-process from the environment, so this loader
    just returns that agent for the harness app name (ADK's web server otherwise
    expects a directory of agents).
    """

    def __init__(self, agent: BaseAgent, app_name: str) -> None:
        super().__init__()
        self._agent = agent
        self._app_name = app_name

    @override
    def load_agent(self, agent_name: str) -> BaseAgent:
        return self._agent

    @override
    def list_agents(self) -> list[str]:
        return [self._app_name]

    @override
    def list_agents_detailed(self) -> list[dict[str, Any]]:
        return [
            {
                "name": self._app_name,
                "root_agent_name": self._agent.name,
                "description": getattr(self._agent, "description", "") or "",
                "language": "python",
            }
        ]


class HarnessRunAgentRequest(RunAgentRequest):
    """ADK ``/run_sse`` request plus an optional once-time harness override.

    When ``harness`` is set, the streaming run uses a spawned agent (base agent
    cloned with the override applied). A registry-enabled base agent is also
    cloned per turn so dynamic remote A2A tools stay scoped to that turn.
    """

    harness: HarnessOverrides | None = None
    harness_merge: bool = False
    harness_enhance: HarnessEnhanceOverrides | None = None


class HarnessApp:
    def __init__(
        self,
        agent: Agent,
        short_term_memory: ShortTermMemory,
        harness_name: str = "default",
        max_llm_calls: int | None = None,
        enable_studio_tools: bool = False,
    ):
        self.agent = agent
        self.short_term_memory = short_term_memory
        self.harness_name = harness_name
        self.max_llm_calls = max_llm_calls
        self.return_llm_usage = RETURN_LLM_USAGE
        self.default_harness_config = _harness_config_delta(
            harness_overrides_from_env()
        )
        self.plugins = build_harness_plugins_from_runtime_env()
        self.runner = Runner(
            agent=agent,
            short_term_memory=short_term_memory,
            app_name=harness_name,
            plugins=self.plugins,
        )

        # ADK web/api server over the single in-memory agent (reuses the harness
        # session service so sessions are shared; long-term memory if configured).
        self._server = AdkWebServer(
            agent_loader=_HarnessAgentLoader(agent, harness_name),
            session_service=short_term_memory.session_service,
            memory_service=getattr(agent, "long_term_memory", None)
            or InMemoryMemoryService(),
            artifact_service=InMemoryArtifactService(),
            credential_service=InMemoryCredentialService(),
            eval_sets_manager=LocalEvalSetsManager(agents_dir="."),
            eval_set_results_manager=LocalEvalSetResultsManager(agents_dir="."),
            agents_dir=".",
        )

        # A2A protocol app for the base agent (agent card + JSON-RPC).
        self._a2a_app = to_a2a(agent, runner=self.runner)

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # A mounted sub-app's lifespan is not run automatically. The A2A app
            # registers its routes (agent card + RPC) inside its lifespan, so
            # enter it here or those routes never appear.
            async with self._a2a_app.router.lifespan_context(self._a2a_app):
                yield

        # Base app = ADK api routes; then add /harness/invoke; mount A2A last so
        # it catches the well-known / RPC paths the ADK routes don't claim.
        self.app = self._server.get_fast_api_app(lifespan=lifespan)
        setattr(self.app.state, _ADK_SERVER_STATE_KEY, self._server)
        _configure_studio_tool_routes(
            self.app,
            self.agent,
            enabled=enable_studio_tools,
        )
        _add_introspection_routes(
            self.app,
            self.agent,
            {},
            app_name=self.harness_name,
        )
        self.mount()
        self._mount_run_sse_override()
        self.app.mount("/", self._a2a_app)

    def _promote_route(self, endpoint: Any) -> None:
        routes = self.app.router.routes
        for i, route in enumerate(routes):
            if getattr(route, "endpoint", None) is endpoint:
                routes.insert(0, routes.pop(i))
                return

    async def _get_session_or_404(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> Session:
        session = await self.short_term_memory.session_service.get_session(
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        return session

    def _effective_harness_config(
        self,
        overrides: HarnessOverrides,
        *,
        harness_merge: bool = False,
    ) -> HarnessOverrides:
        if harness_merge:
            return HarnessOverrides.model_validate(
                _merge_harness_config(self.default_harness_config, overrides)
            )
        return HarnessOverrides.model_validate(_harness_config_delta(overrides))

    async def _agent_config_response(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> dict[str, Any]:
        return {
            "app_name": app_name,
            "user_id": user_id,
            "session_id": session_id,
            "harness": _public_harness_config(self.default_harness_config),
        }

    def mount(self):
        @self.app.post(
            "/apps/{app_name}/users/{user_id}/sessions",
            response_model_exclude_none=True,
        )
        async def create_harness_session(
            app_name: str,
            user_id: str,
            req: HarnessCreateSessionRequest | None = None,
        ) -> Session:
            session_id = None
            state = None
            events = None
            if req is not None:
                session_id = req.id or req.session_id or None
                state = req.state
                events = req.events

            session = await self._server._create_session(
                app_name=app_name,
                user_id=user_id,
                state=state,
                session_id=session_id,
            )
            for event_data in events or []:
                event = Event.model_validate(event_data)
                await self.short_term_memory.session_service.append_event(
                    session=session,
                    event=event,
                )
            return session

        self._promote_route(create_harness_session)

        @self.app.get("/get_agent_config")
        async def get_agent_config(
            user_id: str | None = Query(default="default"),
            session_id: str | None = Query(default="default"),
            app_name: str | None = Query(default=None),
            user_id_camel: str | None = Query(default=None, alias="userId"),
            session_id_camel: str | None = Query(default=None, alias="sessionId"),
            app_name_camel: str | None = Query(default=None, alias="appName"),
        ) -> dict[str, Any]:
            resolved_user_id = user_id_camel or user_id or "default"
            resolved_session_id = session_id_camel or session_id or "default"
            return await self._agent_config_response(
                app_name or app_name_camel or self.harness_name,
                resolved_user_id,
                resolved_session_id,
            )

        @self.app.post("/get_agent_config")
        async def post_get_agent_config(
            req: HarnessAgentConfigRequest,
        ) -> dict[str, Any]:
            return await self._agent_config_response(
                req.app_name or self.harness_name,
                req.user_id,
                req.session_id,
            )

        @self.app.post("/harness/invoke")
        async def invoke_harness(
            request: InvokeHarnessRequest,
            http_request: Request,
        ) -> InvokeHarnessResponse:
            effective_harness = (
                self._effective_harness_config(
                    request.harness,
                    harness_merge=request.harness_merge,
                )
                if request.harness is not None
                else None
            )
            # max LLM calls: per-call override, then request harness override,
            # then the app default from env/config.
            max_llm_calls = (
                request.run_agent_request.max_llm_calls
                or (
                    effective_harness.max_llm_calls
                    if effective_harness and effective_harness.max_llm_calls is not None
                    else None
                )
                or self.max_llm_calls
            )
            run_config = (
                RunConfig(max_llm_calls=max_llm_calls)
                if max_llm_calls is not None
                else RunConfig()
            )

            try:
                tip_token = registry_tip_token_from_headers(http_request.headers)
                auth_header = registry_authorization_from_headers(http_request.headers)
                header_plugins = build_harness_plugins_from_headers(
                    http_request.headers
                )
                body_plugins = build_harness_plugins_from_enhance(
                    request.harness_enhance
                )
                usage_plugin = (
                    HarnessLlmUsagePlugin() if self.return_llm_usage else None
                )
                harness_plugins = body_plugins or header_plugins or self.plugins
                self._reset_plugin_diagnostics(harness_plugins)
                if harness_plugins:
                    logger.info(
                        "Harness plugins enabled for invocation: "
                        + ", ".join(self._plugin_names(harness_plugins))
                    )
                plugins = self._plugins_for_run(harness_plugins, usage_plugin)
                has_registry = has_a2a_registry_config(self.agent)
                needs_scoped_runner = (
                    has_registry
                    or bool(body_plugins)
                    or bool(header_plugins)
                    or usage_plugin is not None
                )
                if effective_harness is not None:
                    logger.info(
                        f"Applying once-time harness override: {effective_harness}"
                    )
                    # The override clones the base agent and may download incremental
                    # skills into a temp dir; the skill files are read from disk while
                    # the agent runs, so the dir is removed (and the one-off agent +
                    # runner dropped) only after the run finishes.
                    with tempfile.TemporaryDirectory(
                        prefix="harness_invoke_"
                    ) as work_dir:
                        agent = spawn_harness_run_agent(
                            self.agent,
                            request.prompt,
                            effective_harness,
                            download_dir=Path(work_dir),
                            app_name=self.harness_name,
                            registry_tip_token=tip_token,
                            registry_authorization=auth_header,
                        )
                        runner = Runner(
                            agent=agent,
                            short_term_memory=self.short_term_memory,
                            app_name=self.harness_name,
                            plugins=plugins,
                        )
                        output = await runner.run(
                            messages=[request.prompt],
                            user_id=request.run_agent_request.user_id,
                            session_id=request.run_agent_request.session_id,
                            run_config=run_config,
                        )
                elif needs_scoped_runner:
                    if has_registry:
                        run_agent = spawn_harness_run_agent(
                            self.agent,
                            request.prompt,
                            app_name=self.harness_name,
                            registry_tip_token=tip_token,
                            registry_authorization=auth_header,
                        )
                    else:
                        run_agent = self.agent
                    runner = Runner(
                        agent=run_agent,
                        short_term_memory=self.short_term_memory,
                        app_name=self.harness_name,
                        plugins=plugins,
                    )
                    output = await runner.run(
                        messages=[request.prompt],
                        user_id=request.run_agent_request.user_id,
                        session_id=request.run_agent_request.session_id,
                        run_config=run_config,
                    )
                else:
                    output = await self.runner.run(
                        messages=[request.prompt],
                        user_id=request.run_agent_request.user_id,
                        session_id=request.run_agent_request.session_id,
                        run_config=run_config,
                    )
            except (SkillLoadError, ToolLoadError) as e:
                # A once-time tool/skill failed to load; return the reason to the
                # caller instead of running with a wrong tool/skill set.
                logger.error(f"Once-time override failed to load: {e}")
                return InvokeHarnessResponse(
                    harness_name=self.harness_name,
                    overwrite=request.harness is not None,
                    output="",
                    error=str(e),
                )
            except Exception as e:
                # Runtime (e.g. ADK) errors take many shapes; pass the message
                # through verbatim so the caller can surface it for debugging.
                logger.exception("Harness invocation failed")
                return InvokeHarnessResponse(
                    harness_name=self.harness_name,
                    overwrite=request.harness is not None,
                    output="",
                    error=str(e),
                )

            return InvokeHarnessResponse(
                harness_name=self.harness_name,
                overwrite=request.harness is not None,
                output=output,
                metrics=(
                    self._response_metrics(harness_plugins, usage_plugin)
                    if usage_plugin
                    else None
                ),
            )

    def _mount_run_sse_override(self):
        """Override ADK's ``/run_sse`` so it honors once-time harness overrides.

        ADK's default ``/run_sse`` always runs the served (base) agent. We wrap it:
        when the request carries a ``harness`` override or the base agent has an
        A2A registry, stream a *spawned* agent (base cloned + override and/or
        dynamic remote A2A tools applied); otherwise delegate to ADK's original
        handler unchanged.
        """
        # Capture ADK's default /run_sse handler to delegate to when there is no
        # override (keeps the base path bit-for-bit ADK behavior).
        adk_run_sse = None
        for r in self.app.router.routes:
            if getattr(r, "path", None) == "/run_sse" and "POST" in getattr(
                r, "methods", set()
            ):
                adk_run_sse = r.endpoint
                break

        @self.app.post("/run_sse")
        async def run_sse(req: HarnessRunAgentRequest, http_request: Request):
            app_name = req.app_name or self.harness_name
            req.app_name = app_name
            if req.harness is not None:
                req.harness = self._effective_harness_config(
                    req.harness,
                    harness_merge=req.harness_merge,
                )
            header_plugins = build_harness_plugins_from_headers(http_request.headers)
            body_plugins = build_harness_plugins_from_enhance(req.harness_enhance)
            harness_plugins = body_plugins or header_plugins or self.plugins
            self._reset_plugin_diagnostics(harness_plugins)
            if (
                req.harness is None
                and not harness_plugins
                and not has_a2a_registry_config(self.agent)
                and adk_run_sse is not None
            ):
                # No override -> exactly ADK's default /run_sse.
                return await adk_run_sse(req)
            tip_token = registry_tip_token_from_headers(http_request.headers)
            auth_header = registry_authorization_from_headers(http_request.headers)
            return StreamingResponse(
                self._run_sse_events(
                    req,
                    tip_token,
                    auth_header,
                    plugins=self._plugins_for_run(harness_plugins, None),
                ),
                media_type="text/event-stream",
            )

        # Move ours to the front so it wins (Starlette matches the first route),
        # without deleting the default we delegate to.
        self._promote_route(run_sse)

    async def _run_sse_events(
        self,
        req: "HarnessRunAgentRequest",
        tip_token: str = "",
        auth_header: str = "",
        plugins: list[BasePlugin] | None = None,
    ):
        """Yield SSE ``data:`` lines for a run, spawning the agent on override."""
        run_config_kwargs: dict[str, Any] = {
            "streaming_mode": StreamingMode.SSE if req.streaming else StreamingMode.NONE
        }
        if req.custom_metadata:
            run_config_kwargs["custom_metadata"] = req.custom_metadata
        max_llm_calls = (
            req.harness.max_llm_calls
            if req.harness and req.harness.max_llm_calls is not None
            else self.max_llm_calls
        )
        if max_llm_calls is not None:
            run_config_kwargs["max_llm_calls"] = max_llm_calls
        run_config = RunConfig(**run_config_kwargs)
        work_dir_ctx = None
        prompt = _content_text(req.new_message)
        try:
            if req.harness is not None:
                logger.info(f"run_sse once-time override: {req.harness}")
                # Skills may download into a temp dir read from disk during the
                # run, so keep it alive for the whole stream.
                work_dir_ctx = tempfile.TemporaryDirectory(prefix="harness_run_sse_")
                try:
                    agent = spawn_harness_run_agent(
                        self.agent,
                        prompt,
                        req.harness,
                        download_dir=Path(work_dir_ctx.name),
                        app_name=req.app_name,
                        registry_tip_token=tip_token,
                        registry_authorization=auth_header,
                    )
                except (SkillLoadError, ToolLoadError) as e:
                    logger.error(f"Once-time override failed to load: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return
            elif has_a2a_registry_config(self.agent):
                agent = spawn_harness_run_agent(
                    self.agent,
                    prompt,
                    app_name=req.app_name,
                    registry_tip_token=tip_token,
                    registry_authorization=auth_header,
                )
            else:
                agent = self.agent

            runner = Runner(
                agent=agent,
                short_term_memory=self.short_term_memory,
                app_name=req.app_name,
                plugins=plugins or None,
            )
            # Be self-sufficient: create the session if the caller did not.
            if not await runner.session_service.get_session(
                app_name=req.app_name,
                user_id=req.user_id,
                session_id=req.session_id,
            ):
                await runner.session_service.create_session(
                    app_name=req.app_name,
                    user_id=req.user_id,
                    session_id=req.session_id,
                )

            async with Aclosing(
                runner.run_async(
                    user_id=req.user_id,
                    session_id=req.session_id,
                    new_message=req.new_message,
                    state_delta=req.state_delta,
                    run_config=run_config,
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
        except Exception as e:
            logger.exception("run_sse failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if work_dir_ctx is not None:
                work_dir_ctx.cleanup()

    def _plugins_for_run(
        self,
        plugins: list[BasePlugin],
        usage_plugin: HarnessLlmUsagePlugin | None,
    ) -> list[BasePlugin]:
        if usage_plugin is None:
            return plugins
        return [*plugins, usage_plugin]

    def _response_metrics(
        self,
        plugins: list[BasePlugin],
        usage_plugin: HarnessLlmUsagePlugin,
    ) -> HarnessResponseMetrics:
        return HarnessResponseMetrics(
            llm_usage=usage_plugin.metrics,
            harness_plugins=HarnessPluginMetrics(
                names=self._plugin_names(plugins),
                compaction_reports=self._compaction_reports(plugins),
            ),
        )

    def _plugin_names(self, plugins: list[BasePlugin]) -> list[str]:
        return [
            str(getattr(plugin, "name", plugin.__class__.__name__))
            for plugin in plugins
        ]

    def _reset_plugin_diagnostics(self, plugins: list[BasePlugin]) -> None:
        for plugin in plugins:
            reset_diagnostics = getattr(plugin, "reset_diagnostics", None)
            if callable(reset_diagnostics):
                reset_diagnostics()

    def _compaction_reports(
        self, plugins: list[BasePlugin]
    ) -> list[HarnessCompactionMetric]:
        metrics: list[HarnessCompactionMetric] = []
        for plugin in plugins:
            reports = getattr(plugin, "compaction_reports", None)
            if not isinstance(reports, list):
                continue
            for report in reports:
                if hasattr(report, "model_dump"):
                    metrics.append(
                        HarnessCompactionMetric.model_validate(
                            report.model_dump(mode="json")
                        )
                    )
                elif isinstance(report, dict):
                    metrics.append(HarnessCompactionMetric.model_validate(report))
        return metrics

    def serve(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        import uvicorn

        uvicorn.run(self.app, host=host, port=port)


harness_app = HarnessApp(
    agent, short_term_memory, HARNESS_NAME, max_llm_calls=DEFAULT_MAX_LLM_CALLS
)
app = harness_app.app


if __name__ == "__main__":
    harness_app.serve(
        host=os.getenv("SERVER_HOST", "0.0.0.0"),
        port=int(os.getenv("SERVER_PORT", "8000")),
    )
