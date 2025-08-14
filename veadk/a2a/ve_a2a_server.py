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

from a2a.server.apps.jsonrpc.fastapi_app import A2AFastAPIApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from fastapi import FastAPI

from veadk import Agent
from veadk.a2a.agent_card import get_agent_card
from veadk.a2a.ve_agent_executor import VeAgentExecutor
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner


class VeA2AServer:
    def __init__(
        self, agent: Agent, url: str, app_name: str, short_term_memory: ShortTermMemory
    ):
        self.agent_card = get_agent_card(agent, url)

        self.agent_executor = VeAgentExecutor(
            app_name=app_name,
            agent=agent,
            short_term_memory=short_term_memory,
        )

        self.task_store = InMemoryTaskStore()

        self.request_handler = DefaultRequestHandler(
            agent_executor=self.agent_executor, task_store=self.task_store
        )

    def build(self) -> FastAPI:
        app_application = A2AFastAPIApplication(
            agent_card=self.agent_card,
            http_handler=self.request_handler,
        )
        app = app_application.build()  # build routes

        runner = Runner(
            agent=self.agent_executor.agent,
            short_term_memory=self.agent_executor.short_term_memory,
            app_name=self.agent_executor.app_name,
            user_id="",
        )

        @app.post("/run_agent", operation_id="run_agent", tags=["mcp"])
        async def run_agent(
            user_input: str,
            user_id: str = "unknown_user",
            session_id: str = "unknown_session",
        ) -> str:
            """
            Execute agent with user input and return final output
            Args:
                user_input: User's input message
                user_id: User identifier
                session_id: Session identifier
            Returns:
                Final agent response
            """
            # Set user_id for runner
            runner.user_id = user_id

            # Running agent and get final output
            final_output = await runner.run(
                messages=user_input,
                session_id=session_id,
            )

            return final_output

        return app


def init_app(
    server_url: str, app_name: str, agent: Agent, short_term_memory: ShortTermMemory
) -> FastAPI:
    """Init the fastapi application in terms of VeADK agent.

    Args:
        server_url: str, the url of the server
        app_name: str, the name of the app
        agent: Agent, the agent of the app
        short_term_memory: ShortTermMemory, the short term memory of the app

    Returns:
        FastAPI, the fastapi app
    """

    server = VeA2AServer(
        agent=agent,
        url=server_url,
        app_name=app_name,
        short_term_memory=short_term_memory,
    )
    return server.build()
