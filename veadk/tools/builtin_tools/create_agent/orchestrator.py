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

"""Build and execute dynamic agent blueprints."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable, Sequence
from typing import Any

from google.adk.agents import BaseAgent
from google.adk.tools import FunctionTool

from veadk.skills.materializer import materialize_remote_skill
from veadk.tools.builtin_tools.create_agent.executor import default_executor
from veadk.tools.builtin_tools.create_agent.knowledge_tools import (
    build_knowledge_tool,
    default_knowledge_factory,
)
from veadk.tools.builtin_tools.create_agent.models import (
    AgentBlueprint,
    CreatedAgentResult,
    LlmAgentNode,
    WorkflowAgentNode,
)
from veadk.tools.builtin_tools.create_agent.python_tools import compile_python_tool
from veadk.tools.builtin_tools.create_agent.resource_store import ResourceSnapshot
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgePayload,
    CloudCredentials,
)
from veadk.tools.builtin_tools.create_agent.sources.agentkit_knowledge import (
    _resolve_credentials,
)


LeafFactory = Callable[[LlmAgentNode, list[Any], bool, Any], BaseAgent]
KnowledgeFactory = Callable[[AgentKitKnowledgePayload, CloudCredentials], Any]
AgentExecutor = Callable[[Any, str, str], Any]


class AgentOrchestrator:
    """Validate, materialize, compose, and execute requested agents."""

    def __init__(
        self,
        *,
        supports_workflow: bool,
        max_orchestration_depth: int = 2,
        leaf_factory: LeafFactory | None = None,
        knowledge_factory: KnowledgeFactory | None = None,
        executor: AgentExecutor | None = None,
        skill_cache_dir=None,
    ) -> None:
        self._supports_workflow = supports_workflow
        self._max_depth = max_orchestration_depth
        self._leaf_factory = leaf_factory or _default_leaf_factory
        self._knowledge_factory = knowledge_factory or default_knowledge_factory
        self._executor = executor or default_executor
        self._skill_cache_dir = skill_cache_dir
        self._skill_locks: dict[str, threading.Lock] = {}

    async def create_and_run(
        self,
        *,
        snapshot: ResourceSnapshot,
        agents: Sequence[AgentBlueprint],
        tool_context: Any = None,
    ) -> list[CreatedAgentResult]:
        skill_tasks: dict[str, asyncio.Task[Any]] = {}
        return list(
            await asyncio.gather(
                *(
                    self._create_and_run_one(
                        snapshot,
                        blueprint,
                        tool_context,
                        skill_tasks,
                    )
                    for blueprint in agents
                )
            )
        )

    async def _create_and_run_one(
        self,
        snapshot: ResourceSnapshot,
        blueprint: AgentBlueprint,
        tool_context: Any,
        skill_tasks: dict[str, asyncio.Task[Any]],
    ) -> CreatedAgentResult:
        root_type = None
        knowledgebases: list[Any] = []
        try:
            nodes = {node.id: node for node in blueprint.nodes}
            root_type = nodes[blueprint.root_node].type
            workflow_members = self._validate_blueprint(blueprint, nodes)
            built: dict[str, Any] = {}
            building: set[str] = set()

            async def build(node_id: str) -> Any:
                if node_id in built:
                    return built[node_id]
                if node_id in building:
                    raise ValueError(f"Cyclic agent nesting detected at '{node_id}'.")
                building.add(node_id)
                node = nodes[node_id]

                if node.type == "llm":
                    tools, mounted = await self._build_leaf_tools(
                        node,
                        snapshot,
                        tool_context,
                        skill_tasks,
                    )
                    knowledgebases.extend(mounted)
                    value = self._leaf_factory(
                        node,
                        tools,
                        node_id in workflow_members,
                        _parent_agent(tool_context),
                    )
                elif node.type in {"sequential", "parallel", "loop"}:
                    children = [await build(child) for child in node.children]
                    value = _build_classic_orchestrator(node, children)
                elif node.type == "workflow":
                    dependencies = _workflow_dependencies(node)
                    resolved = {
                        dependency: await build(dependency)
                        for dependency in dependencies
                    }
                    value = _build_workflow(node, resolved)
                else:  # pragma: no cover - Pydantic prevents this.
                    raise ValueError(f"Unsupported node type: {node.type}")

                building.remove(node_id)
                built[node_id] = value
                return value

            root = await build(blueprint.root_node)
            output = self._executor(root, blueprint.task, blueprint.name)
            if inspect.isawaitable(output):
                output = await output
            return CreatedAgentResult(
                name=blueprint.name,
                root_type=root_type,
                status="completed",
                output=str(output or ""),
            )
        except Exception as exc:
            return CreatedAgentResult(
                name=blueprint.name,
                root_type=root_type,
                status="failed",
                error=str(exc),
            )
        finally:
            await _close_knowledgebases(knowledgebases)

    def _validate_blueprint(
        self, blueprint: AgentBlueprint, nodes: dict[str, Any]
    ) -> set[str]:
        if not self._supports_workflow and any(
            node.type == "workflow" for node in nodes.values()
        ):
            raise ValueError(
                "The installed Google ADK does not support workflow nodes."
            )

        ownership: dict[str, set[str]] = {}
        workflow_members: set[str] = set()
        for node in nodes.values():
            if node.type in {"sequential", "parallel", "loop"}:
                references = list(node.children)
                if any(
                    nodes.get(ref) and nodes[ref].type == "workflow"
                    for ref in references
                ):
                    raise ValueError(
                        f"'{node.id}' cannot contain a workflow node; Google ADK "
                        "workflow is a BaseNode, not a classic BaseAgent child."
                    )
            elif node.type == "workflow":
                references = _workflow_dependencies(node)
                workflow_members.update(references)
                if any(edge.to_node == "START" for edge in node.edges):
                    raise ValueError(
                        "START can only be used as a workflow edge source."
                    )
                if node.id in references:
                    raise ValueError(f"Workflow '{node.id}' cannot contain itself.")
            else:
                references = []

            missing = sorted(set(references) - nodes.keys())
            if missing:
                raise ValueError(
                    f"Node '{node.id}' references undefined nodes: {missing}."
                )
            for reference in set(references):
                ownership.setdefault(reference, set()).add(node.id)

        multiply_owned = {
            node_id: sorted(owners)
            for node_id, owners in ownership.items()
            if len(owners) > 1
        }
        if multiply_owned:
            raise ValueError(
                f"Nodes cannot belong to multiple orchestrators: {multiply_owned}."
            )

        reachable: set[str] = set()

        def walk(node_id: str, depth: int, path: list[str]) -> None:
            if node_id in path:
                raise ValueError(
                    "Cyclic agent nesting detected: " + " -> ".join([*path, node_id])
                )
            node = nodes[node_id]
            next_depth = depth + (node.type != "llm")
            if next_depth > self._max_depth:
                raise ValueError(
                    "Maximum orchestration depth exceeded: "
                    + " -> ".join([*path, node_id])
                    + f" (max={self._max_depth})."
                )
            reachable.add(node_id)
            if node.type in {"sequential", "parallel", "loop"}:
                refs = node.children
            elif node.type == "workflow":
                refs = _workflow_dependencies(node)
            else:
                refs = []
            for reference in refs:
                walk(reference, next_depth, [*path, node_id])

        walk(blueprint.root_node, 0, [])
        orphaned = sorted(nodes.keys() - reachable)
        if orphaned:
            raise ValueError(f"Blueprint contains unreachable nodes: {orphaned}.")
        return workflow_members

    async def _build_leaf_tools(
        self,
        node: LlmAgentNode,
        snapshot: ResourceSnapshot,
        tool_context: Any,
        skill_tasks: dict[str, asyncio.Task[Any]],
    ) -> tuple[list[Any], list[Any]]:
        selected = []
        for ref in node.resources:
            resource = snapshot.resources.get(ref)
            if resource is None:
                raise ValueError(
                    f"Resource '{ref}' is not part of collection "
                    f"'{snapshot.collection_id}'."
                )
            selected.append(resource)

        tools: list[Any] = [
            FunctionTool(compile_python_tool(spec)) for spec in node.python_tools
        ]
        skill_resources = [
            resource for resource in selected if resource.descriptor.kind == "skill"
        ]
        if skill_resources:
            from google.adk.skills import load_skill_from_dir
            from google.adk.tools.skill_toolset import SkillToolset

            skills = await asyncio.gather(
                *(
                    self._load_skill(resource, skill_tasks)
                    for resource in skill_resources
                )
            )
            loaded = [
                await asyncio.to_thread(load_skill_from_dir, path) for path in skills
            ]
            tools.append(SkillToolset(skills=loaded))

        knowledge_resources = [
            resource
            for resource in selected
            if resource.descriptor.kind == "knowledge_base"
        ]
        mounted: list[Any] = []
        if knowledge_resources:
            credentials = await asyncio.to_thread(_resolve_credentials, tool_context)
            if credentials is None:
                raise ValueError(
                    "Selected AgentKit knowledge bases require AK/SK or STS credentials."
                )
            created = await asyncio.gather(
                *(
                    asyncio.to_thread(
                        self._knowledge_factory, resource.payload, credentials
                    )
                    for resource in knowledge_resources
                ),
                return_exceptions=True,
            )
            mounted = [
                value for value in created if not isinstance(value, BaseException)
            ]
            failures = [value for value in created if isinstance(value, BaseException)]
            if failures:
                await _close_knowledgebases(mounted)
                raise failures[0]
            tools.append(build_knowledge_tool(knowledge_resources, mounted))

        return tools, mounted

    async def _load_skill(
        self,
        resource,
        skill_tasks: dict[str, asyncio.Task[Any]],
    ) -> Any:
        task = skill_tasks.get(resource.descriptor.ref)
        if task is None:
            lock = self._skill_locks.setdefault(
                resource.descriptor.ref,
                threading.Lock(),
            )
            task = asyncio.create_task(
                asyncio.to_thread(
                    _materialize_skill,
                    lock,
                    resource.payload,
                    self._skill_cache_dir,
                )
            )
            skill_tasks[resource.descriptor.ref] = task
        return await task


def _materialize_skill(lock: threading.Lock, skill: Any, cache_dir: Any) -> Any:
    with lock:
        return materialize_remote_skill(skill, cache_dir=cache_dir)


async def _close_knowledgebases(knowledgebases: Sequence[Any]) -> None:
    for knowledgebase in knowledgebases:
        close = getattr(knowledgebase, "close", None)
        if not callable(close):
            continue
        try:
            result = close()
            if inspect.isawaitable(result):
                await result
        except Exception:
            pass


def _workflow_dependencies(node: WorkflowAgentNode) -> list[str]:
    result: list[str] = []
    for edge in node.edges:
        for candidate in (edge.from_node, edge.to_node):
            if candidate != "START" and candidate not in result:
                result.append(candidate)
    return result


def _build_classic_orchestrator(node: Any, children: list[BaseAgent]) -> BaseAgent:
    common = {
        "name": node.id,
        "description": node.description,
        "sub_agents": children,
    }
    if node.type == "sequential":
        from veadk.agents.sequential_agent import SequentialAgent

        return SequentialAgent(**common)
    if node.type == "parallel":
        from veadk.agents.parallel_agent import ParallelAgent

        return ParallelAgent(**common)
    from veadk.agents.loop_agent import LoopAgent

    return LoopAgent(max_iterations=node.max_iterations, **common)


def _build_workflow(node: WorkflowAgentNode, resolved: dict[str, Any]) -> Any:
    from google.adk.workflow import Edge, START, Workflow

    edges = []
    for edge in node.edges:
        edges.append(
            Edge(
                from_node=START
                if edge.from_node == "START"
                else resolved[edge.from_node],
                to_node=resolved[edge.to_node],
                route=edge.route,
            )
        )
    return Workflow(
        name=node.id,
        description=node.description,
        edges=edges,
        max_concurrency=node.max_concurrency,
    )


def _default_leaf_factory(
    node: LlmAgentNode,
    tools: list[Any],
    workflow_member: bool,
    parent_agent: Any,
) -> BaseAgent:
    kwargs: dict[str, Any] = {
        "name": node.id,
        "description": node.description,
        "instruction": node.instruction,
        "tools": tools,
    }
    if node.model_name is not None:
        kwargs["model_name"] = node.model_name
    if node.model_provider is not None:
        kwargs["model_provider"] = node.model_provider
    if node.model_api_base is not None:
        kwargs["model_api_base"] = node.model_api_base
    inherit_parent_model = (
        node.model_name is None
        and node.model_provider is None
        and node.model_api_base is None
        and parent_agent is not None
        and getattr(parent_agent, "model", None) is not None
    )
    if inherit_parent_model:
        kwargs["model"] = parent_agent.model
        inherited_api_key = getattr(parent_agent, "model_api_key", "")
        if inherited_api_key:
            kwargs["model_api_key"] = inherited_api_key
    if workflow_member:
        kwargs["mode"] = "single_turn"

    if inherit_parent_model and not hasattr(parent_agent, "model_api_key"):
        from google.adk.agents import LlmAgent

        return LlmAgent(**kwargs)

    from veadk.agent import Agent

    return Agent(**kwargs)


def _parent_agent(tool_context: Any) -> Any:
    invocation = getattr(tool_context, "_invocation_context", None)
    return getattr(invocation, "agent", None)
