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

from typing import Optional

from google.adk.agents import LlmAgent, RunConfig
from google.adk.agents.llm_agent import ToolUnion
from google.adk.agents.run_config import StreamingMode
from google.adk.models.lite_llm import LiteLlm
from google.adk.runners import Runner
from google.genai import types
from pydantic import ConfigDict, Field
from typing_extensions import Any

from veadk.config import getenv
from veadk.consts import (
    DEFALUT_MODEL_AGENT_PROVIDER,
    DEFAULT_MODEL_AGENT_API_BASE,
    DEFAULT_MODEL_AGENT_NAME,
)
from veadk.evaluation import EvalSetRecorder
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.prompts.agent_default_prompt import DEFAULT_DESCRIPTION, DEFAULT_INSTRUCTION
from veadk.tracing.base_tracer import BaseTracer
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_asyncio
from google.adk.agents.base_agent import BaseAgent

patch_asyncio()
logger = get_logger(__name__)


class Agent(LlmAgent):
    """LLM-based Agent with Volcengine capabilities."""

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")
    """The model config"""

    name: str = "veAgent"
    """The name of the agent."""

    description: str = DEFAULT_DESCRIPTION
    """The description of the agent. This will be helpful in A2A scenario."""

    instruction: str = DEFAULT_INSTRUCTION
    """The instruction for the agent, such as principles of function calling."""

    # factory
    model_name: str = getenv("MODEL_AGENT_NAME", DEFAULT_MODEL_AGENT_NAME)
    """The name of the model for agent running."""

    model_provider: str = getenv("MODEL_AGENT_PROVIDER", DEFALUT_MODEL_AGENT_PROVIDER)
    """The provider of the model for agent running."""

    model_api_base: str = getenv("MODEL_AGENT_API_BASE", DEFAULT_MODEL_AGENT_API_BASE)
    """The api base of the model for agent running."""

    model_api_key: str = Field(
        ..., default_factory=lambda: getenv("MODEL_AGENT_API_KEY")
    )
    """The api key of the model for agent running."""

    tools: list[ToolUnion] = []
    """The tools provided to agent."""

    sub_agents: list[BaseAgent] = Field(default_factory=list, exclude=True)
    """The sub agents provided to agent."""

    knowledgebase: Optional[KnowledgeBase] = None
    """The knowledgebase provided to agent."""

    long_term_memory: Optional[LongTermMemory] = None
    """The long term memory provided to agent.

    In VeADK, the `long_term_memory` refers to cross-session memory under the same user.
    """

    tracers: list[BaseTracer] = []
    """The tracers provided to agent."""

    serve_url: str = ""
    """The url of agent serving host. Show in agent card."""

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(None)  # for sub_agents init
        self.model = LiteLlm(
            model=f"{self.model_provider}/{self.model_name}",
            api_key=self.model_api_key,
            api_base=self.model_api_base,
        )

        if self.knowledgebase:
            from veadk.tools import load_knowledgebase_tool

            load_knowledgebase_tool.knowledgebase = self.knowledgebase
            self.tools.append(load_knowledgebase_tool.load_knowledgebase_tool)

        if self.long_term_memory is not None:
            from google.adk.tools import load_memory

            self.tools.append(load_memory)

        if self.tracers:
            self.before_model_callback = []
            self.after_model_callback = []
            self.after_tool_callback = []
            for tracer in self.tracers:
                self.before_model_callback.append(tracer.tracer_hook_before_model)
                self.after_model_callback.append(tracer.tracer_hook_after_model)
                self.after_tool_callback.append(tracer.tracer_hook_after_tool)

        logger.info(f"Agent `{self.name}` init done.")
        logger.debug(
            f"Agent: {self.model_dump(include={'name', 'model_name', 'model_api_base', 'tools', 'serve_url'})}"
        )

    async def _run(
        self,
        runner,
        user_id: str,
        session_id: str,
        message: types.Content,
        stream: bool,
    ):
        stream_mode = StreamingMode.SSE if stream else StreamingMode.NONE

        async def event_generator():
            async for event in runner.run_async(
                user_id=user_id,
                session_id=session_id,
                new_message=message,
                run_config=RunConfig(streaming_mode=stream_mode),
            ):
                if event.get_function_calls():
                    for function_call in event.get_function_calls():
                        logger.debug(f"Function call: {function_call}")
                elif (
                    event.content is not None
                    and event.content.parts[0].text is not None
                    and len(event.content.parts[0].text.strip()) > 0
                ):
                    yield event.content.parts[0].text

        final_output = ""
        async for chunk in event_generator():
            if stream:
                print(chunk, end="", flush=True)
            final_output += chunk
        if stream:
            print()  # end with a new line

        return final_output

    async def run(
        self,
        prompt: str | list[str],
        stream: bool = False,
        app_name: str = "veadk_app",
        user_id: str = "veadk_user",
        session_id="veadk_session",
        load_history_sessions_from_db: bool = False,
        db_url: str = "",
        collect_runtime_data: bool = False,
        eval_set_id: str = "",
        save_session_to_memory: bool = False,
        enable_memory_optimization: bool = False,
    ):
        """Running the agent. The runner and session service will be created automatically.

        For production, consider using Google-ADK runner to run agent, rather than invoking this method.

        Args:
            prompt (str | list[str]): The prompt to run the agent.
            stream (bool, optional): Whether to stream the output. Defaults to False.
            app_name (str, optional): The name of the application. Defaults to "veadk_app".
            user_id (str, optional): The id of the user. Defaults to "veadk_user".
            session_id (str, optional): The id of the session. Defaults to "veadk_session".
            load_history_sessions_from_db (bool, optional): Whether to load history sessions from database. Defaults to False.
            db_url (str, optional): The url of the database. Defaults to "".
            collect_runtime_data (bool, optional): Whether to collect runtime data. Defaults to False.
            eval_set_id (str, optional): The id of the eval set. Defaults to "".
            save_session_to_memory (bool, optional): Whether to save this turn session to memory. Defaults to False.
        """

        logger.warning(
            "Running agent in this function is only for development and testing, do not use this function in production. For production, consider using `Google ADK Runner` to run agent, rather than invoking this method."
        )
        logger.info(
            f"Run agent {self.name}: app_name: {app_name}, user_id: {user_id}, session_id: {session_id}."
        )
        prompt = [prompt] if isinstance(prompt, str) else prompt

        # memory service
        short_term_memory = ShortTermMemory(
            backend="database" if load_history_sessions_from_db else "local",
            enable_memory_optimization=enable_memory_optimization,
            db_url=db_url,
        )
        session_service = short_term_memory.session_service
        await short_term_memory.create_session(
            app_name=app_name, user_id=user_id, session_id=session_id
        )

        # runner
        runner = Runner(
            agent=self,
            app_name=app_name,
            session_service=session_service,
            memory_service=self.long_term_memory,
        )
        if getattr(self, "tracers", None):
            for tracer in self.tracers:
                tracer.set_app_name(app_name)

        logger.info(f"Begin to process prompt {prompt}")
        # run
        final_output = ""
        for _prompt in prompt:
            message = types.Content(role="user", parts=[types.Part(text=_prompt)])
            final_output = await self._run(runner, user_id, session_id, message, stream)

        # VeADK features
        if save_session_to_memory:
            assert self.long_term_memory is not None, (
                "Long-term memory is not initialized in agent"
            )
            session = await session_service.get_session(
                app_name=app_name,
                user_id=user_id,
                session_id=session_id,
            )
            await self.long_term_memory.add_session_to_memory(session)
            logger.info(f"Add session `{session.id}` to your long-term memory.")

        if collect_runtime_data:
            eval_set_recorder = EvalSetRecorder(session_service, eval_set_id)
            dump_path = await eval_set_recorder.dump(app_name, user_id, session_id)
            self._dump_path = dump_path  # just for test/debug/instrumentation

        if self.tracers:
            for tracer in self.tracers:
                tracer.dump(user_id, session_id)

        return final_output
