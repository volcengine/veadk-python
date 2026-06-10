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

from fastapi import FastAPI
from pydantic import BaseModel, Field, field_validator

from veadk import Agent
from veadk.consts import DEFAULT_MODEL_AGENT_NAME
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class Harness(BaseModel):
    model_name: str = Field(default=DEFAULT_MODEL_AGENT_NAME)
    tools: list[str] = Field(default_factory=list)
    system_prompt: str = Field(default="You are a helpful assistant.")

    @field_validator("tools", mode="before")
    @classmethod
    def _split_tools(cls, value: object) -> object:
        """Accept a list[str] or a comma-separated string for ``tools``.

        ``"web_search,web_fetch"`` becomes ``["web_search", "web_fetch"]``; a
        bare name becomes a single-item list. Non-string inputs pass through so
        Pydantic validates them normally.
        """
        if isinstance(value, str):
            return [name.strip() for name in value.split(",") if name.strip()]
        return value


class AddHarnessRequest(BaseModel):
    harness_name: str
    harness: Harness


class AddHarnessResponse(BaseModel):
    code: int = Field(default=200)
    msg: str = Field(default="Harness added successfully.")
    harness_name: str


class RunAgentRequest(BaseModel):
    user_id: str
    session_id: str


class InvokeHarnessRequest(BaseModel):
    prompt: str
    harness_name: str
    harness: Harness | None = None
    run_agent_request: RunAgentRequest


class InvokeHarnessResponse(BaseModel):
    harness_name: str
    overwrite: bool = Field(
        default=False
    )  # Whether the agent is created with once-time harness or not.
    output: str


class HarnessApp:
    def __init__(self):
        self.app = FastAPI()
        self.agents = {}

        self.short_term_memory = ShortTermMemory(backend="local")

        self.mount()

    def mount(self):
        @self.app.post("/harness/add")
        def add_harness(request: AddHarnessRequest) -> AddHarnessResponse:
            if request.harness_name in self.agents:
                logger.warning(
                    f"Harness with name {request.harness_name} already exists."
                )
                return AddHarnessResponse(
                    code=400,
                    msg=f"Harness with name {request.harness_name} already exists.",
                    harness_name=request.harness_name,
                )

            agent = self._create_agent(request.harness)
            self.agents[request.harness_name] = agent
            return AddHarnessResponse(harness_name=request.harness_name)

        @self.app.post("/harness/invoke")
        async def invoke_harness(
            request: InvokeHarnessRequest,
        ) -> InvokeHarnessResponse:
            if request.harness_name not in self.agents:
                logger.error(
                    f"Harness with name {request.harness_name} does not exist."
                )
                return InvokeHarnessResponse(
                    harness_name=request.harness_name,
                    output=f"Harness with name {request.harness_name} does not exist. Please add it first.",
                )

            if request.harness:
                logger.info(
                    f"Temporarily create agent with once-time harness {request.harness}."
                )
                agent = self._create_agent(request.harness)
            else:
                agent = self.agents[request.harness_name]

            agent_runner = Runner(
                agent=agent,
                short_term_memory=self.short_term_memory,
                app_name=request.harness_name,
            )
            output = await agent_runner.run(
                messages=[request.prompt],
                user_id=request.run_agent_request.user_id,
                session_id=request.run_agent_request.session_id,
            )

            return InvokeHarnessResponse(
                harness_name=request.harness_name,
                overwrite=request.harness is not None,
                output=output,
            )

    def _create_agent(self, harness: Harness) -> Agent:
        from veadk.tools import get_builtin_tool

        tools = [get_builtin_tool(name) for name in harness.tools]
        agent = Agent(
            name="temp_agent",
            model_name=harness.model_name,
            instruction=harness.system_prompt,
            tools=tools,
        )
        return agent

    def serve(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        import uvicorn

        uvicorn.run(self.app, host=host, port=port)


if __name__ == "__main__":
    # Entry for `python -m veadk.cloud.harness_app` (e.g. the AgentKit runtime),
    # serving the API on 0.0.0.0:8000.
    HarnessApp().serve()
