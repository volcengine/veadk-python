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

from fastapi import FastAPI
from google.adk.agents import RunConfig

from veadk import Agent
from veadk.cloud.harness_app.agent import agent, short_term_memory
from veadk.cloud.harness_app.types import (
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
        self.runner = Runner(
            agent=agent,
            short_term_memory=short_term_memory,
            app_name=harness_name,
        )

        self.mount()

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
