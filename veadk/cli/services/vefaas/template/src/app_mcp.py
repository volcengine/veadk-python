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

import os
import argparse
from agent import agent, app_name, short_term_memory
from veadk.tracing.base_tracer import BaseTracer
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer
from veadk import Agent
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.runner import Runner
from fastmcp import FastMCP


# ==============================================================================
# Tracer Config ================================================================

TRACERS: list[BaseTracer] = []

exporters = []
if os.getenv("VEADK_TRACER_APMPLUS", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter

    exporters.append(APMPlusExporter())

if os.getenv("VEADK_TRACER_COZELOOP", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter

    exporters.append(CozeloopExporter())

if os.getenv("VEADK_TRACER_TLS", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

    exporters.append(TLSExporter())

TRACERS.append(OpentelemetryTracer(exporters=exporters))


agent.tracers.extend(TRACERS)
if not getattr(agent, "before_model_callback", None):
    agent.before_model_callback = []
if not getattr(agent, "after_model_callback", None):
    agent.after_model_callback = []
if not getattr(agent, "after_tool_callback", None):
    agent.after_tool_callback = []
for tracer in TRACERS:
    if tracer.tracer_hook_before_model not in agent.before_model_callback:
        agent.before_model_callback.append(tracer.tracer_hook_before_model)
    if tracer.tracer_hook_after_model not in agent.after_model_callback:
        agent.after_model_callback.append(tracer.tracer_hook_after_model)
    if tracer.tracer_hook_after_tool not in agent.after_tool_callback:
        agent.after_tool_callback.append(tracer.tracer_hook_after_tool)

# Tracer Config ================================================================
# ==============================================================================


class VeMCPServer:
    def __init__(self, agent: Agent, app_name: str, short_term_memory: ShortTermMemory):
        self.agent = agent
        self.app_name = app_name
        self.short_term_memory = short_term_memory

        self.runner = Runner(
            agent=self.agent,
            short_term_memory=self.short_term_memory,
            app_name=app_name,
            user_id="",  # waiting for tool call to provide user_id
        )

    def build(self) -> FastMCP:
        # Create MCP server
        mcp = FastMCP(name=self.app_name)

        @mcp.tool
        async def run_agent(
            user_input: str,
            user_id: str = "unknown_user",
            session_id: str = "unknown_session",
        ) -> str:
            """
            Execute agent with user input and return final output
            Args:
                user_input: str, user_id: str = "unknown_user", session_id: str = "unknown_session"
            Returns:
                final_output: str
            """
            # Set user_id for runner
            self.runner.user_id = user_id

            # Running agent and get final output
            final_output = await self.runner.run(
                messages=user_input,
                session_id=session_id,
            )

            return final_output

        return mcp


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="MCP Server")
    parser.add_argument(
        "--transport", default="http", help="Transport type (default: http)"
    )
    parser.add_argument(
        "--host", default="0.0.0.0", help="Host address (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="Port number (default: 8000)"
    )
    parser.add_argument("--log-level", default="INFO", help="Log level (default: INFO)")

    args = parser.parse_args()

    server = VeMCPServer(
        agent=agent,
        app_name=app_name,
        short_term_memory=short_term_memory,
    )
    mcp = server.build()
    mcp.run(transport=args.transport, host=args.host, port=args.port)
