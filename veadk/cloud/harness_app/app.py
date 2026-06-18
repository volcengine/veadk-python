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

The agent is built once from the environment (see ``agent.py``) and served at
``POST /harness/invoke``. A request may carry a once-time ``harness`` override:
the base agent is cloned, the override applied, and a throwaway runner drives
that clone for the single call.

Run with either:
    python app.py
    uvicorn app:app --host 0.0.0.0 --port 8000
"""

import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, Request
from google.adk.agents import RunConfig
from google.adk.plugins import BasePlugin

from veadk import Agent
from veadk.cloud.harness_app.agent import agent, short_term_memory
from veadk.cloud.harness_app.harness_plugins import (
    build_harness_plugins_from_enhance,
    build_harness_plugins_from_headers,
    build_harness_plugins_from_runtime_env,
)
from veadk.cloud.harness_app.metrics import HarnessLlmUsagePlugin
from veadk.cloud.harness_app.types import (
    HarnessCompactionMetric,
    HarnessPluginMetrics,
    HarnessResponseMetrics,
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
RETURN_LLM_USAGE = os.getenv("HARNESS_APP_RETURN_LLM_USAGE", "").lower() in {
    "1",
    "true",
    "yes",
    "on",
}


class HarnessApp:
    def __init__(
        self,
        agent: Agent,
        short_term_memory: ShortTermMemory,
        harness_name: str = "default",
        max_llm_calls: int | None = None,
    ):
        self.app = FastAPI()
        self.agent = agent
        self.short_term_memory = short_term_memory
        self.harness_name = harness_name
        self.max_llm_calls = max_llm_calls
        self.return_llm_usage = RETURN_LLM_USAGE
        self.plugins = build_harness_plugins_from_runtime_env()
        self.runner = Runner(
            agent=agent,
            short_term_memory=short_term_memory,
            app_name=harness_name,
            plugins=self.plugins,
        )

        self.mount()

    def mount(self):
        @self.app.post("/harness/invoke")
        async def invoke_harness(
            request: InvokeHarnessRequest,
            http_request: Request,
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
                            plugins=plugins,
                        )
                        output = await runner.run(
                            messages=[request.prompt],
                            user_id=request.run_agent_request.user_id,
                            session_id=request.run_agent_request.session_id,
                            run_config=run_config,
                        )
                elif header_plugins:
                    runner = Runner(
                        agent=self.agent,
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
                elif usage_plugin:
                    runner = Runner(
                        agent=self.agent,
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
