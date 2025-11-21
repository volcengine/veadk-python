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
from typing import Literal, Optional, Union

from a2a.types import AgentCard
from google.adk.agents import BaseAgent
from starlette.applications import Starlette
from google.adk.artifacts.in_memory_artifact_service import InMemoryArtifactService
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.memory.in_memory_memory_service import InMemoryMemoryService
from google.adk.a2a.utils.agent_to_a2a import to_a2a as google_adk_to_a2a
from veadk import Runner
from veadk.a2a.ve_middlewares import build_a2a_auth_middleware
from veadk.auth.ve_credential_service import VeCredentialService
from veadk.consts import DEFAULT_AGENT_NAME


def to_a2a(
    agent: BaseAgent,
    *,
    host: str = "localhost",
    port: int = 8000,
    protocol: str = "http",
    agent_card: Optional[Union[AgentCard, str]] = None,
    runner: Optional[Runner] = None,
    enable_auth: bool = False,
    auth_method: Literal["header", "querystring"] = "header",
) -> Starlette:
    """Convert an ADK agent to a A2A Starlette application with optional VeADK enhancements.

    This function wraps Google ADK's to_a2a utility and optionally adds:
    - VeCredentialService for authentication management
    - A2A authentication middleware for token validation

    Args:
        agent: The ADK agent to convert to A2A server
        host: The host for the A2A RPC URL (default: "localhost")
        port: The port for the A2A RPC URL (default: 8000)
        protocol: The protocol for the A2A RPC URL (default: "http")
        agent_card: Optional pre-built AgentCard object or path to agent card
                    JSON. If not provided, will be built automatically from the
                    agent.
        runner: Optional pre-built Runner object. If not provided, a default
                runner will be created using in-memory services.
                When enable_auth=True:
                - If runner is provided and has a credential_service, it must be
                  a VeCredentialService instance (raises TypeError otherwise)
                - If runner is provided without credential_service, a new
                  VeCredentialService will be created and set
                - If runner is not provided, a new runner with VeCredentialService
                  will be created
        auth_method: Authentication method for A2A requests (only used when
                    enable_auth=True). Options:
                    - "header": Extract token from Authorization header (default)
                    - "querystring": Extract token from query parameter
        enable_auth: Whether to enable VeADK authentication features.
                          When True, enables credential service and auth middleware.
                          When False, uses standard Google ADK behavior.
                          Default: False

    Returns:
        A Starlette application that can be run with uvicorn

    Raises:
        TypeError: If enable_auth=True and runner has a credential_service
                  that is not a VeCredentialService instance

    Example:
        Basic usage (without VeADK auth):
        ```python
        from veadk import Agent
        from veadk.a2a.utils.agent_to_a2a import to_a2a

        agent = Agent(name="my_agent", tools=[...])
        app = to_a2a(agent, host="localhost", port=8000)
        # Run with: uvicorn module:app --host localhost --port 8000
        ```

        With VeADK authentication enabled:
        ```python
        app = to_a2a(agent, enable_auth=True)
        ```

        With custom runner and VeADK auth:
        ```python
        from veadk import Agent, Runner
        from veadk.memory.short_term_memory import ShortTermMemory
        from veadk.auth.ve_credential_service import VeCredentialService

        agent = Agent(name="my_agent")
        runner = Runner(
            agent=agent,
            short_term_memory=ShortTermMemory(),
            app_name="my_app",
            credential_service=VeCredentialService()  # Optional
        )
        app = to_a2a(agent, runner=runner, enable_auth=True)
        ```

        With querystring authentication:
        ```python
        app = to_a2a(agent, enable_auth=True, auth_method="querystring")
        ```
    """
    app_name = agent.name or DEFAULT_AGENT_NAME
    middleware = None  # May need support multiple middlewares in the future

    # Handle VeADK authentication setup
    if enable_auth:
        # Create credential service if not provided
        credential_service = VeCredentialService()
        if runner is not None:
            # Check if runner has credential_service
            if runner.credential_service is not None:
                # Validate that it's a VeCredentialService
                if not isinstance(runner.credential_service, VeCredentialService):
                    raise TypeError(
                        f"When enable_auth=True, runner.credential_service must be "
                        f"a VeCredentialService instance, got {type(runner.credential_service).__name__}"
                    )
                # Use existing credential service
                credential_service = runner.credential_service
            else:
                # Add credential_service to runner
                runner.credential_service = credential_service
        else:
            # Create runner with credential_service
            runner = Runner(
                app_name=app_name,
                agent=agent,
                artifact_service=InMemoryArtifactService(),
                session_service=InMemorySessionService(),
                memory_service=InMemoryMemoryService(),
                credential_service=credential_service,
            )

        middleware = build_a2a_auth_middleware(
            app_name=app_name,
            credential_service=credential_service,
            auth_method=auth_method,
        )

    # Convert agent to A2A Starlette app using Google ADK utility
    app: Starlette = google_adk_to_a2a(
        agent=agent,
        host=host,
        port=port,
        protocol=protocol,
        agent_card=agent_card,
        runner=runner,
    )

    # Add VeADK authentication middleware only if enabled
    if middleware:
        app.add_middleware(middleware)

    return app
