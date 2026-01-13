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

import os
from typing import Dict, Optional, Union

# If user didn't set LITELLM_LOCAL_MODEL_COST_MAP, set it to True
# to enable local model cost map.
# This value is `false` by default, which brings heavy performance burden,
# for instance, importing `Litellm` needs about 10s latency.
if not os.getenv("LITELLM_LOCAL_MODEL_COST_MAP"):
    os.environ["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"

import uuid

from google.adk.agents import LlmAgent
from google.adk.agents.base_agent import BaseAgent
from google.adk.agents.context_cache_config import ContextCacheConfig
from google.adk.agents.llm_agent import InstructionProvider, ToolUnion
from google.adk.examples.base_example_provider import BaseExampleProvider
from google.adk.models.lite_llm import LiteLlm
from pydantic import ConfigDict, Field
from typing_extensions import Any

from veadk.config import settings
from veadk.consts import (
    DEFAULT_AGENT_NAME,
    DEFAULT_MODEL_EXTRA_CONFIG,
)
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.processors import BaseRunProcessor, NoOpRunProcessor
from veadk.prompts.agent_default_prompt import (
    DEFAULT_DESCRIPTION,
    DEFAULT_INSTRUCTION,
)
from veadk.prompts.prompt_manager import BasePromptManager
from veadk.tracing.base_tracer import BaseTracer
from veadk.utils.logger import get_logger
from veadk.utils.patches import patch_asyncio, patch_tracer
from veadk.version import VERSION

patch_tracer()
patch_asyncio()
logger = get_logger(__name__)


class Agent(LlmAgent):
    """LLM-based Agent with Volcengine capabilities.

    This class represents an intelligent agent powered by LLMs (Large Language Models),
    integrated with Volcengine's AI framework. It supports memory modules, sub-agents,
    tracers, knowledge bases, and other advanced features for A2A (Agent-to-Agent)
    or user-facing scenarios.

    Attributes:
        name (str): The name of the agent.
        description (str): A description of the agent, useful in A2A scenarios.
        instruction (Union[str, InstructionProvider]): The instruction or instruction provider.
        model_name (Union[str, List[str]]): Name of the model used by the agent.
        model_provider (str): Provider of the model (e.g., openai).
        model_api_base (str): The base URL of the model API.
        model_api_key (str): The API key for accessing the model.
        model_extra_config (dict): Extra configurations to include in model requests.
        tools (list[ToolUnion]): Tools available to the agent.
        sub_agents (list[BaseAgent]): Sub-agents managed by this agent.
        knowledgebase (Optional[KnowledgeBase]): Knowledge base attached to the agent.
        short_term_memory (Optional[ShortTermMemory]): Session-based memory for temporary context.
        long_term_memory (Optional[LongTermMemory]): Cross-session memory for persistent user context.
        tracers (list[BaseTracer]): List of tracers used for telemetry and monitoring.
        enable_authz (bool): Whether to enable agent authorization checks.
        auto_save_session (bool): Whether to automatically save sessions to long-term memory.
        skills (list[str]): List of skills that equip the agent with specific capabilities.
        example_store (Optional[BaseExampleProvider]): Example store for providing example Q/A.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True, extra="allow")

    id: str = Field(default_factory=lambda: str(uuid.uuid4()).split("-")[0])
    name: str = DEFAULT_AGENT_NAME
    description: str = DEFAULT_DESCRIPTION
    instruction: Union[str, InstructionProvider] = DEFAULT_INSTRUCTION

    model_name: Union[str, list[str]] = Field(
        default_factory=lambda: settings.model.name
    )
    model_provider: str = Field(default_factory=lambda: settings.model.provider)
    model_api_base: str = Field(default_factory=lambda: settings.model.api_base)
    model_api_key: str = Field(default_factory=lambda: settings.model.api_key)
    model_extra_config: dict = Field(default_factory=dict)

    tools: list[ToolUnion] = []

    sub_agents: list[BaseAgent] = Field(default_factory=list, exclude=True)

    prompt_manager: Optional[BasePromptManager] = None

    knowledgebase: Optional[KnowledgeBase] = None

    short_term_memory: Optional[ShortTermMemory] = None
    long_term_memory: Optional[LongTermMemory] = None

    tracers: list[BaseTracer] = []

    enable_responses: bool = False

    context_cache_config: Optional[ContextCacheConfig] = None

    run_processor: Optional[BaseRunProcessor] = Field(default=None, exclude=True)
    """Optional run processor for intercepting and processing agent execution flows.

    The run processor can be used to implement cross-cutting concerns such as:
    - Authentication flows (e.g., OAuth2 via VeIdentity)
    - Request/response logging
    - Error handling and retry logic
    - Performance monitoring

    If not provided, a NoOpRunProcessor will be used by default.

    Example:
        from veadk.integrations.ve_identity import AuthRequestProcessor

        agent = Agent(
            name="my-agent",
            run_processor=AuthRequestProcessor()
        )
    """

    enable_authz: bool = False

    auto_save_session: bool = False

    skills: list[str] = Field(default_factory=list)

    example_store: Optional[BaseExampleProvider] = None

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(None)  # for sub_agents init

        # Initialize run_processor if not provided
        if self.run_processor is None:
            self.run_processor = NoOpRunProcessor()

        # combine user model config with VeADK defaults
        headers = DEFAULT_MODEL_EXTRA_CONFIG["extra_headers"].copy()
        body = DEFAULT_MODEL_EXTRA_CONFIG["extra_body"].copy()

        if self.model_extra_config:
            user_headers = self.model_extra_config.get("extra_headers", {})
            user_body = self.model_extra_config.get("extra_body", {})

            headers |= user_headers
            body |= user_body

        self.model_extra_config |= {
            "extra_headers": headers,
            "extra_body": body,
        }

        logger.info(f"Model extra config: {self.model_extra_config}")

        if not self.model:
            if self.enable_responses:
                from veadk.models.ark_llm import ArkLlm

                self.model = ArkLlm(
                    model=f"{self.model_provider}/{self.model_name}",
                    api_key=self.model_api_key,
                    api_base=self.model_api_base,
                    **self.model_extra_config,
                )
            else:
                fallbacks = None
                if isinstance(self.model_name, list):
                    if self.model_name:
                        model_name = self.model_name[0]
                        fallbacks = [
                            f"{self.model_provider}/{m}" for m in self.model_name[1:]
                        ]
                        logger.info(
                            f"Using primary model: {model_name}, with fallbacks: {self.model_name[1:]}"
                        )
                    else:
                        model_name = settings.model.name
                        logger.warning(
                            f"Empty model_name list provided, using default model from settings: {model_name}"
                        )
                else:
                    model_name = self.model_name

                self.model = LiteLlm(
                    model=f"{self.model_provider}/{model_name}",
                    api_key=self.model_api_key,
                    api_base=self.model_api_base,
                    fallbacks=fallbacks,
                    **self.model_extra_config,
                )
            logger.debug(
                f"LiteLLM client created with config: {self.model_extra_config}"
            )
        else:
            logger.warning(
                "You are trying to use your own LiteLLM client, some default request headers may be missing."
            )

        self._prepare_tracers()

        if self.knowledgebase:
            from veadk.tools.builtin_tools.load_knowledgebase import (
                LoadKnowledgebaseTool,
            )

            load_knowledgebase_tool = LoadKnowledgebaseTool(
                knowledgebase=self.knowledgebase
            )
            self.tools.append(load_knowledgebase_tool)

        if self.long_term_memory is not None:
            from google.adk.tools import load_memory

            if hasattr(load_memory, "custom_metadata"):
                if not load_memory.custom_metadata:
                    load_memory.custom_metadata = {}
                load_memory.custom_metadata["backend"] = self.long_term_memory.backend
            self.tools.append(load_memory)

        if self.enable_authz:
            from veadk.tools.builtin_tools.agent_authorization import (
                check_agent_authorization,
            )

            if self.before_agent_callback:
                if isinstance(self.before_agent_callback, list):
                    self.before_agent_callback.append(check_agent_authorization)
                else:
                    self.before_agent_callback = [
                        self.before_agent_callback,
                        check_agent_authorization,
                    ]
            else:
                self.before_agent_callback = check_agent_authorization

        if self.prompt_manager:
            self.instruction = self.prompt_manager.get_prompt

        if self.auto_save_session:
            if self.long_term_memory is None:
                logger.warning(
                    "auto_save_session is enabled, but long_term_memory is not initialized."
                )
            else:
                from veadk.memory.save_session_callback import (
                    save_session_to_long_term_memory,
                )

                if self.after_agent_callback:
                    if isinstance(self.after_agent_callback, list):
                        self.after_agent_callback.append(
                            save_session_to_long_term_memory
                        )
                    else:
                        self.after_agent_callback = [
                            self.after_agent_callback,
                            save_session_to_long_term_memory,
                        ]
                else:
                    self.after_agent_callback = save_session_to_long_term_memory

        if self.skills:
            self.load_skills()

        if self.example_store:
            from google.adk.tools.example_tool import ExampleTool

            self.tools.append(ExampleTool(examples=self.example_store))

        logger.info(f"VeADK version: {VERSION}")

        logger.info(f"{self.__class__.__name__} `{self.name}` init done.")
        logger.debug(
            f"Agent: {self.model_dump(include={'id', 'name', 'model_name', 'model_api_base', 'tools', 'skills'})}"
        )

    def update_model(self, model_name: str):
        logger.info(f"Updating model to {model_name}")
        self.model = self.model.model_copy(
            update={"model": f"{self.model_provider}/{model_name}"}
        )

    def load_skills(self):
        from pathlib import Path

        from veadk.skills.skill import Skill
        from veadk.skills.utils import (
            load_skills_from_cloud,
            load_skills_from_directory,
        )
        from veadk.tools.skills_tools import (
            SkillsTool,
            bash_tool,
            edit_file_tool,
            read_file_tool,
            write_file_tool,
            register_skills_tool,
        )

        skills: Dict[str, Skill] = {}

        for item in self.skills:
            if not item or str(item).strip() == "":
                continue
            path = Path(item)
            if path.exists() and path.is_dir():
                for skill in load_skills_from_directory(path):
                    skills[skill.name] = skill
            else:
                for skill in load_skills_from_cloud(item):
                    skills[skill.name] = skill
        if skills:
            self.instruction += "\nYou have the following skills:\n"

            for skill in skills.values():
                self.instruction += (
                    f"- name: {skill.name}\n- description: {skill.description}\n\n"
                )

            self.tools.append(SkillsTool(skills))
            self.tools.append(read_file_tool)
            self.tools.append(write_file_tool)
            self.tools.append(edit_file_tool)
            self.tools.append(bash_tool)
            self.tools.append(register_skills_tool)

    def _prepare_tracers(self):
        enable_apmplus_tracer = os.getenv("ENABLE_APMPLUS", "false").lower() == "true"
        enable_cozeloop_tracer = os.getenv("ENABLE_COZELOOP", "false").lower() == "true"
        enable_tls_tracer = os.getenv("ENABLE_TLS", "false").lower() == "true"

        if not (enable_apmplus_tracer or enable_cozeloop_tracer or enable_tls_tracer):
            logger.info("No exporter enabled by env, skip prepare tracers.")
            return

        if not self.tracers:
            from veadk.tracing.telemetry.opentelemetry_tracer import (
                OpentelemetryTracer,
            )

            self.tracers.append(OpentelemetryTracer())

        exporters = self.tracers[0].exporters  # type: ignore

        from veadk.tracing.telemetry.exporters.apmplus_exporter import (
            APMPlusExporter,
        )
        from veadk.tracing.telemetry.exporters.cozeloop_exporter import (
            CozeloopExporter,
        )
        from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

        if enable_apmplus_tracer and not any(
            isinstance(e, APMPlusExporter) for e in exporters
        ):
            self.tracers[0].exporters.append(APMPlusExporter())  # type: ignore
            logger.info("Enable APMPlus exporter by env.")

        if enable_cozeloop_tracer and not any(
            isinstance(e, CozeloopExporter) for e in exporters
        ):
            self.tracers[0].exporters.append(CozeloopExporter())  # type: ignore
            logger.info("Enable CozeLoop exporter by env.")

        if enable_tls_tracer and not any(isinstance(e, TLSExporter) for e in exporters):
            self.tracers[0].exporters.append(TLSExporter())  # type: ignore
            logger.info("Enable TLS exporter by env.")

        logger.debug(
            f"Opentelemetry Tracer init {len(self.tracers[0].exporters)} exporters"  # type: ignore
        )

    async def run(self, **kwargs):
        raise NotImplementedError(
            "Run method in VeADK agent is deprecated since version 0.5.6. Please use runner.run_async instead. Ref: https://agentkit.gitbook.io/docs/runner/overview"
        )
