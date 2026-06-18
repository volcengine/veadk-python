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
  management, …), served by an ``AdkWebServer`` over the single in-memory agent.
* The A2A protocol routes (agent card at ``/.well-known/agent-card.json`` plus the
  JSON-RPC endpoint), mounted at ``/`` for the base agent.

The ADK and A2A surfaces serve the base agent only; once-time overrides are a
``/harness/invoke`` feature.

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

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.agents.base_agent import BaseAgent
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.auth.credential_service.in_memory_credential_service import (
    InMemoryCredentialService,
)
from google.adk.cli.adk_web_server import AdkWebServer, RunAgentRequest
from google.adk.cli.utils.base_agent_loader import BaseAgentLoader
from google.adk.utils.context_utils import Aclosing
from google.adk.evaluation.local_eval_set_results_manager import (
    LocalEvalSetResultsManager,
)
from google.adk.evaluation.local_eval_sets_manager import LocalEvalSetsManager
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from typing_extensions import override

from veadk import Agent
from veadk.a2a.utils.agent_to_a2a import to_a2a
from veadk.cloud.harness_app.agent import agent, short_term_memory
from veadk.cloud.harness_app.types import (
    HarnessOverrides,
    InvokeHarnessRequest,
    InvokeHarnessResponse,
)
from veadk.cloud.harness_app.utils import (
    SkillLoadError,
    ToolLoadError,
    spawn_harness_agent,
)
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

HARNESS_NAME = os.getenv("HARNESS_NAME", "default")
# Optional harness default max LLM calls per run, from harness.yaml (overridable
# per invocation). Unset -> falls through to ADK RunConfig's own default.
DEFAULT_MAX_LLM_CALLS = (
    int(os.environ["MAX_LLM_CALLS"]) if os.environ.get("MAX_LLM_CALLS") else None
)


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
    cloned with the override applied); otherwise it uses the base agent.
    """

    harness: HarnessOverrides | None = None


class HarnessApp:
    def __init__(
        self,
        agent: Agent,
        short_term_memory: ShortTermMemory,
        harness_name: str = "default",
        max_llm_calls: int | None = None,
    ):
        self.agent = agent
        self.short_term_memory = short_term_memory
        self.harness_name = harness_name
        self.max_llm_calls = max_llm_calls
        self.runner = Runner(
            agent=agent,
            short_term_memory=short_term_memory,
            app_name=harness_name,
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
        self.mount()
        self._mount_run_sse_override()
        self.app.mount("/", self._a2a_app)

    def mount(self):
        @self.app.post("/harness/invoke")
        async def invoke_harness(
            request: InvokeHarnessRequest,
        ) -> InvokeHarnessResponse:
            # max LLM calls: per-call override, else the harness default; if
            # neither is set, fall through to ADK RunConfig's own default.
            max_llm_calls = (
                request.run_agent_request.max_llm_calls or self.max_llm_calls
            )
            run_config = (
                RunConfig(max_llm_calls=max_llm_calls)
                if max_llm_calls is not None
                else RunConfig()
            )

            try:
                if request.harness is not None:
                    logger.info(
                        f"Applying once-time harness override: {request.harness}"
                    )
                    # The override clones the base agent and may download incremental
                    # skills into a temp dir; the skill files are read from disk while
                    # the agent runs, so the dir is removed (and the one-off agent +
                    # runner dropped) only after the run finishes.
                    with tempfile.TemporaryDirectory(
                        prefix="harness_invoke_"
                    ) as work_dir:
                        agent = spawn_harness_agent(
                            self.agent, request.harness, download_dir=Path(work_dir)
                        )
                        runner = Runner(
                            agent=agent,
                            short_term_memory=self.short_term_memory,
                            app_name=self.harness_name,
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
            )

    def _mount_run_sse_override(self):
        """Override ADK's ``/run_sse`` so it honors once-time harness overrides.

        ADK's default ``/run_sse`` always runs the served (base) agent. We wrap it:
        when the request carries a ``harness`` override, stream a *spawned* agent
        (base cloned + override applied); otherwise **delegate to ADK's original
        handler unchanged** — so the no-override path is identical to stock run_sse.
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
        async def run_sse(req: HarnessRunAgentRequest):
            if req.harness is None and adk_run_sse is not None:
                # No override -> exactly ADK's default /run_sse.
                return await adk_run_sse(req)
            return StreamingResponse(
                self._run_sse_events(req), media_type="text/event-stream"
            )

        # Move ours to the front so it wins (Starlette matches the first route),
        # without deleting the default we delegate to.
        routes = self.app.router.routes
        for i, r in enumerate(routes):
            if getattr(r, "path", None) == "/run_sse" and (
                getattr(r, "endpoint", None) is run_sse
            ):
                routes.insert(0, routes.pop(i))
                break

    async def _run_sse_events(self, req: "HarnessRunAgentRequest"):
        """Yield SSE ``data:`` lines for a run, spawning the agent on override."""
        run_config = RunConfig(
            streaming_mode=StreamingMode.SSE if req.streaming else StreamingMode.NONE
        )
        work_dir_ctx = None
        try:
            if req.harness is not None:
                logger.info(f"run_sse once-time override: {req.harness}")
                # Skills may download into a temp dir read from disk during the
                # run, so keep it alive for the whole stream.
                work_dir_ctx = tempfile.TemporaryDirectory(prefix="harness_run_sse_")
                try:
                    agent = spawn_harness_agent(
                        self.agent,
                        req.harness,
                        download_dir=Path(work_dir_ctx.name),
                    )
                except (SkillLoadError, ToolLoadError) as e:
                    logger.error(f"Once-time override failed to load: {e}")
                    yield f"data: {json.dumps({'error': str(e)})}\n\n"
                    return
            else:
                agent = self.agent

            runner = Runner(
                agent=agent,
                short_term_memory=self.short_term_memory,
                app_name=req.app_name,
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
                    run_config=run_config,
                )
            ) as agen:
                async for event in agen:
                    yield (
                        "data: "
                        + event.model_dump_json(exclude_none=True, by_alias=True)
                        + "\n\n"
                    )
        except Exception as e:
            logger.exception("run_sse failed")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            if work_dir_ctx is not None:
                work_dir_ctx.cleanup()

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
