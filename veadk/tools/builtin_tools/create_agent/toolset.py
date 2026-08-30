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

"""Single toolset exposing resource collection and dynamic agent transfer."""

from __future__ import annotations

import hashlib
import os
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from google.adk.agents import BaseAgent
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
    AgentKitSkillCenterSource,
    BuiltinToolResourceSource,
    ResourceSource,
    SkillHubSearchSource,
    SkillResourceSource,
)


class CreateAgentToolset(BaseToolset):
    """Discover resources, then create and transfer to selected sub-agents."""

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
            skill_cache_dir=skill_cache_dir,
        )
        input_model = (
            CreateAgentsInput
            if "workflow" in self.capabilities.agent_types
            else LegacyCreateAgentsInput
        )
        self._input_model = input_model
        self._registrations: dict[str, tuple[BaseAgent, Any, str]] = {}
        self._bootstrap_agents: list[tuple[BaseAgent, BaseAgent]] = []
        self._tools = [
            FunctionTool(self.collect_resources),
            CreateAgentsTool(self.create_agents, input_model=input_model),
        ]

    async def collect_resources(
        self,
        skill_hub_keywords: list[str] | None = None,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Collect resources and search public Skill Hub with task keywords.

        AgentKit Skill Center discovery automatically enumerates every Skill
        Space visible to the active AK/SK or STS credentials. Constructor-level
        ``skill_source_ids`` only narrows that account catalog when supplied.

        Args:
            skill_hub_keywords: Two to five concise keywords or short phrases
                derived from the user's task. Each value is sent to Skill Hub
                search and is returned for transparent UI display.
        """
        await self._release_session(_context_session(tool_context))
        keywords = _normalize_skill_hub_keywords(skill_hub_keywords)
        result = await self._collector.collect(
            owner=_context_owner(tool_context),
            tool_context=tool_context,
            additional_sources=(SkillHubSearchSource(keywords),) if keywords else (),
        )
        return result.model_dump(mode="json")

    async def create_agents(
        self,
        collection_id: str,
        agents: list[Any],
        handoff_to: str,
        tool_context: ToolContext | None = None,
    ) -> dict[str, Any]:
        """Create agents, register them, then transfer control to one of them."""
        request = self._input_model.model_validate(
            {
                "collection_id": collection_id,
                "agents": agents,
                "handoff_to": handoff_to,
            }
        )
        parsed_agents = [
            AgentBlueprint.model_validate(
                agent.model_dump() if hasattr(agent, "model_dump") else agent
            )
            for agent in request.agents
        ]
        parent = _parent_agent(tool_context)
        if parent is None:
            raise ValueError(
                "create_agents requires an active ADK agent invocation so the "
                "created agents can be registered and transferred to."
            )
        actions = getattr(tool_context, "actions", None)
        if actions is None:
            raise ValueError(
                "create_agents requires a ToolContext with event actions for "
                "transfer_to_agent."
            )
        owner = _context_owner(tool_context)
        snapshot = self._store.consume(collection_id=collection_id, owner=owner)
        runtime_names = [
            _runtime_name(agent.name, collection_id, index)
            for index, agent in enumerate(parsed_agents)
        ]
        built_agents = await self._orchestrator.create(
            snapshot=snapshot,
            agents=parsed_agents,
            runtime_names=runtime_names,
            tool_context=tool_context,
        )
        target_index = next(
            index
            for index, agent in enumerate(parsed_agents)
            if agent.name == handoff_to
        )
        target = built_agents[target_index]
        if target.root is None or target.result.status == "failed":
            for built in built_agents:
                await built.close()
            return CreateAgentsResponse(
                collection_id=collection_id,
                results=[built.result for built in built_agents],
            ).model_dump(mode="json")

        registered: list[str] = []
        try:
            for built in built_agents:
                if built.root is None:
                    continue
                runtime_name = built.result.runtime_name
                if not runtime_name:
                    raise ValueError("Created agent is missing its runtime name.")
                _register_sub_agent(parent, built.root)
                self._registrations[runtime_name] = (
                    parent,
                    built,
                    _context_session(tool_context),
                )
                registered.append(runtime_name)
        except Exception:
            for runtime_name in registered:
                await self._release(runtime_name)
            for built in built_agents:
                if built.result.runtime_name not in registered:
                    await built.close()
            raise

        handoff_runtime_name = target.result.runtime_name
        if not handoff_runtime_name:  # pragma: no cover - guarded by the builder.
            raise ValueError("Handoff target is missing its runtime name.")
        actions.transfer_to_agent = handoff_runtime_name
        return CreateAgentsResponse(
            collection_id=collection_id,
            handoff_to=handoff_runtime_name,
            results=[built.result for built in built_agents],
        ).model_dump(mode="json")

    @override
    async def get_tools(
        self, readonly_context: ReadonlyContext | None = None
    ) -> list[BaseTool]:
        del readonly_context
        return list(self._tools)

    async def close(self) -> None:
        for runtime_name in list(self._registrations):
            await self._release(runtime_name)
        for parent, bootstrap in self._bootstrap_agents:
            if bootstrap in parent.sub_agents:
                parent.sub_agents.remove(bootstrap)
            bootstrap.parent_agent = None
        self._bootstrap_agents.clear()

    def prepare_parent_agent(self, parent: BaseAgent) -> None:
        """Make ADK select its transfer-aware scheduler before the first turn."""
        if any(
            registered_parent is parent
            for registered_parent, _ in self._bootstrap_agents
        ):
            return
        name = "_create_agent_runtime_slot"
        suffix = 1
        while parent.root_agent.find_agent(name) is not None:
            name = f"_create_agent_runtime_slot_{suffix}"
            suffix += 1
        bootstrap = _TransferBootstrapAgent(name=name)
        bootstrap.parent_agent = parent
        parent.sub_agents.append(bootstrap)
        self._bootstrap_agents.append((parent, bootstrap))

    async def _release(self, runtime_name: str) -> None:
        registration = self._registrations.pop(runtime_name, None)
        if registration is None:
            return
        parent, built, _ = registration
        if built.root in parent.sub_agents:
            parent.sub_agents.remove(built.root)
        if built.root is not None:
            built.root.parent_agent = None
        await built.close()

    async def _release_session(self, session_key: str) -> None:
        if not session_key:
            return
        for runtime_name, (_, _, registered_session) in list(
            self._registrations.items()
        ):
            if registered_session == session_key:
                await self._release(runtime_name)


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
    skill_hub_source_ids = [
        source_id for source_id in unique_source_ids if source_id.startswith("sp-")
    ]
    agentkit_space_ids = [
        source_id for source_id in unique_source_ids if not source_id.startswith("sp-")
    ]
    return [
        *(SkillResourceSource(source_id) for source_id in skill_hub_source_ids),
        AgentKitSkillCenterSource(agentkit_space_ids),
        AgentKitKnowledgeSource(),
        BuiltinToolResourceSource(),
    ]


def _normalize_skill_hub_keywords(values: Sequence[str] | None) -> list[str]:
    keywords: list[str] = []
    for value in values or ():
        keyword = str(value).strip()
        if keyword and keyword not in keywords:
            keywords.append(keyword)
        if len(keywords) == 5:
            break
    return keywords


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


def _context_session(tool_context: ToolContext | None) -> str:
    if tool_context is None:
        return ""
    invocation = getattr(tool_context, "_invocation_context", None)
    session = getattr(invocation, "session", None)
    return ":".join(
        str(value or "")
        for value in (
            getattr(session, "app_name", None) or getattr(session, "appName", None),
            getattr(invocation, "user_id", None) or getattr(session, "user_id", None),
            getattr(session, "id", None),
        )
    )


def _parent_agent(tool_context: ToolContext | None) -> BaseAgent | None:
    invocation = getattr(tool_context, "_invocation_context", None)
    agent = getattr(invocation, "agent", None)
    return agent if isinstance(agent, BaseAgent) else None


def _runtime_name(name: str, collection_id: str, index: int) -> str:
    suffix = hashlib.sha256(f"{collection_id}:{index}".encode("utf-8")).hexdigest()[:10]
    return f"{name}__{suffix}"


def _register_sub_agent(parent: BaseAgent, child: BaseAgent) -> None:
    root = parent.root_agent
    if root.find_agent(child.name) is not None:
        raise ValueError(f"Agent runtime name '{child.name}' is already registered.")
    child.parent_agent = parent
    parent.sub_agents.append(child)


class _TransferBootstrapAgent(BaseAgent):
    """Invisible scheduler marker; dynamic agents replace it as transfer targets."""

    mode: str = "single_turn"

    async def _run_async_impl(self, ctx):
        del ctx
        if False:  # pragma: no cover - this internal marker is never dispatched.
            yield
