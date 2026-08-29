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

"""Single toolset exposing resource collection and dynamic agent execution."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Sequence

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools import BaseTool, FunctionTool, ToolContext
from google.adk.tools.base_toolset import BaseToolset
from typing_extensions import override

from veadk.tools.builtin_tools.create_agent.capabilities import (
    detect_agent_capabilities,
)
from veadk.tools.builtin_tools.create_agent.collect_resources import ResourceCollector
from veadk.tools.builtin_tools.create_agent.create_agents import CreateAgentsTool
from veadk.tools.builtin_tools.create_agent.models import (
    AgentBlueprint,
    AgentCapabilities,
    CreateAgentsInput,
    CreateAgentsResponse,
    LegacyCreateAgentsInput,
)
from veadk.tools.builtin_tools.create_agent.orchestrator import AgentOrchestrator
from veadk.tools.builtin_tools.create_agent.resource_store import ResourceStore
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgeSource,
    ResourceSource,
    SkillResourceSource,
)


class CreateAgentToolset(BaseToolset):
    """Discover resources, then create and execute selected sub-agents."""

    def __init__(
        self,
        *,
        skill_source_ids: str | Sequence[str] | None = None,
        resource_sources: Sequence[ResourceSource] | None = None,
        capabilities: AgentCapabilities | None = None,
        resource_store: ResourceStore | None = None,
        skill_cache_dir: Path | None = None,
        leaf_factory=None,
        knowledge_factory=None,
        executor=None,
    ) -> None:
        super().__init__()
        self.capabilities = capabilities or detect_agent_capabilities()
        self._store = resource_store or ResourceStore()
        sources = (
            list(resource_sources)
            if resource_sources is not None
            else _default_sources(skill_source_ids)
        )
        self._collector = ResourceCollector(
            sources=sources,
            store=self._store,
            capabilities=self.capabilities,
        )
        self._orchestrator = AgentOrchestrator(
            supports_workflow="workflow" in self.capabilities.agent_types,
            max_orchestration_depth=self.capabilities.max_orchestration_depth,
            leaf_factory=leaf_factory,
            knowledge_factory=knowledge_factory,
            executor=executor,
            skill_cache_dir=skill_cache_dir,
        )
        input_model = (
            CreateAgentsInput
            if "workflow" in self.capabilities.agent_types
            else LegacyCreateAgentsInput
        )
        self._tools = [
            FunctionTool(self.collect_resources),
            CreateAgentsTool(self.create_agents, input_model=input_model),
        ]

    async def collect_resources(
        self, tool_context: ToolContext | None = None
    ) -> dict[str, Any]:
        """List all configured resources concurrently; no query or filtering is applied."""
        result = await self._collector.collect(
            owner=_context_owner(tool_context),
            tool_context=tool_context,
        )
        return result.model_dump(mode="json")

    async def create_agents(
        self,
        collection_id: str,
        agents: list[AgentBlueprint],
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Create and run multiple agent blueprints after collecting resources."""
        parsed_agents = [
            agent
            if isinstance(agent, AgentBlueprint)
            else AgentBlueprint.model_validate(agent)
            for agent in agents
        ]
        owner = _context_owner(tool_context)
        snapshot = self._store.consume(collection_id=collection_id, owner=owner)
        results = await self._orchestrator.create_and_run(
            snapshot=snapshot,
            agents=parsed_agents,
            tool_context=tool_context,
        )
        return CreateAgentsResponse(
            collection_id=collection_id,
            results=results,
        ).model_dump(mode="json")

    @override
    async def get_tools(
        self, readonly_context: ReadonlyContext | None = None
    ) -> list[BaseTool]:
        del readonly_context
        return list(self._tools)

    async def close(self) -> None:
        return None


def _default_sources(
    skill_source_ids: str | Sequence[str] | None,
) -> list[ResourceSource]:
    if skill_source_ids is None:
        skill_source_ids = ",".join(
            value
            for value in (
                os.getenv("SKILL_HUB_SPACE_ID", ""),
                os.getenv("SKILL_SPACE_ID", ""),
            )
            if value
        )
    if isinstance(skill_source_ids, str):
        source_ids = [
            value.strip() for value in skill_source_ids.split(",") if value.strip()
        ]
    else:
        source_ids = [
            str(value).strip() for value in skill_source_ids if str(value).strip()
        ]
    unique_source_ids = list(dict.fromkeys(source_ids))
    return [
        *(SkillResourceSource(source_id) for source_id in unique_source_ids),
        AgentKitKnowledgeSource(),
    ]


def _context_owner(tool_context: ToolContext | None) -> str:
    if tool_context is None:
        return "local"
    invocation = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation, "session", None)
    return ":".join(
        str(value or "")
        for value in (
            getattr(session, "app_name", None) or getattr(session, "appName", None),
            getattr(invocation, "user_id", None) or getattr(session, "user_id", None),
            getattr(session, "id", None),
            getattr(invocation, "invocation_id", None),
        )
    )
