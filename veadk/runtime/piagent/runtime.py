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

"""Pi coding agent runtime for VeADK."""

from __future__ import annotations

from typing import TYPE_CHECKING, AsyncGenerator

from veadk.runtime.base_runtime import BaseRuntime, build_system_append
from veadk.runtime.piagent.client import PiAgentRpcClient
from veadk.runtime.piagent.config import PiAgentConfig, prepare_piagent_home
from veadk.runtime.piagent.installer import resolve_or_install_piagent_binary
from veadk.runtime.piagent.translate import PiEventTranslator, build_prompt
from veadk.utils.logger import get_logger

if TYPE_CHECKING:
    from google.adk.agents.invocation_context import InvocationContext
    from google.adk.events.event import Event

    from veadk.agent import Agent

logger = get_logger(__name__)


class PiAgentRuntime(BaseRuntime):
    """Run an agent invocation through a local Pi RPC process."""

    name = "piagent"

    async def run_async(
        self, agent: "Agent", ctx: "InvocationContext"
    ) -> AsyncGenerator["Event", None]:
        binary_path = resolve_or_install_piagent_binary()
        config = PiAgentConfig.from_agent(agent, binary_path)
        prepare_piagent_home(config)

        prompt = build_prompt(ctx)
        append_text = build_system_append(agent)
        if append_text:
            prompt = (
                f"# System instructions\n\n{append_text}\n\n# Conversation\n\n{prompt}"
            )

        logger.info(
            "piagent runtime: "
            f"model={config.model.model} provider={config.model.provider_id}"
        )
        translator = PiEventTranslator(
            author=agent.name,
            invocation_id=ctx.invocation_id,
        )
        async with PiAgentRpcClient(config) as client:
            async for pi_event in client.prompt(prompt):
                for event in translator.event_to_adk_events(pi_event):
                    yield event
