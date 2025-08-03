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

from a2a.server.agent_execution.agent_executor import AgentExecutor
from a2a.server.agent_execution.context import RequestContext
from a2a.server.events.event_queue import EventQueue
from a2a.utils import new_agent_text_message
from typing_extensions import override

from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class VeAgentExecutor(AgentExecutor):
    def __init__(self, app_name: str, agent: Agent, short_term_memory: ShortTermMemory):
        super().__init__()
        self.app_name = app_name
        self.agent = agent
        self.short_term_memory = short_term_memory

        self.runner = Runner(
            agent=self.agent,
            short_term_memory=self.short_term_memory,
            app_name=app_name,
            user_id="",  # waiting for `execute` change
        )

    @override
    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        # extract metadata
        user_id = (
            context.metadata["user_id"]
            if "user_id" in context.metadata
            else "unkonwn_user"
        )
        self.runner.user_id = user_id

        session_id = (
            context.metadata["session_id"]
            if "session_id" in context.metadata
            else "unkonwn_session"
        )

        # process user input
        user_input = context.get_user_input()

        logger.debug(
            f"Request: user_id: {user_id}, session_id: {session_id}, user_input: {user_input}"
        )

        # running
        final_output = await self.runner.run(
            messages=user_input,
            session_id=session_id,
        )

        logger.debug(f"Final output: {final_output}")

        await event_queue.enqueue_event(new_agent_text_message(final_output))

    @override
    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        return None
