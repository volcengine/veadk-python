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

"""Build dynamic agent blueprints for registration in the current agent tree."""

from __future__ import annotations

import asyncio
import inspect
import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

from google.adk.agents import BaseAgent
from google.adk.tools import FunctionTool

from veadk.skills.materializer import materialize_remote_skill
from veadk.tools import get_builtin_tool
from veadk.tools.builtin_tools.create_agent.knowledge_tools import (
    build_knowledge_tool,
    default_knowledge_factory,
)
from veadk.tools.builtin_tools.create_agent.models import (
    AgentBlueprint,
    CreatedAgentResult,
    LlmAgentNode,
    LoopAgentNode,
    ParallelAgentNode,
    SequentialAgentNode,
    WorkflowAgentNode,
)
from veadk.tools.builtin_tools.create_agent.python_tools import compile_python_tool
from veadk.tools.builtin_tools.create_agent.resource_store import ResourceSnapshot
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgePayload,
    CloudCredentials,
)
from veadk.tools.builtin_tools.create_agent.sources.cloud import (
    resolve_cloud_credentials,
)
from veadk.tools.builtin_tools.create_agent.sources.skills import (
    resolve_agentkit_skill,
)

LeafFactory = Callable[[LlmAgentNode, list[Any], bool, Any], BaseAgent]
KnowledgeFactory = Callable[[AgentKitKnowledgePayload, CloudCredentials], Any]


@dataclass
class BuiltAgent:
    """One blueprint build result and its runtime-owned resources."""

    result: CreatedAgentResult
    root: BaseAgent | None = None
    knowledgebases: list[Any] = field(default_factory=list)

    async def close(self) -> None:
        await _close_knowledgebases(self.knowledgebases)
        self.knowledgebases.clear()


class _WorkflowTransferAgent(BaseAgent):
    """Expose an ADK 2.x Workflow as a target accepted by agent transfer."""

    workflow: Any

    async def _run_async_impl(self, ctx):
        from google.adk.agents.context import Context
        from google.adk.workflow._node_runner import NodeRunner

        parent_ctx = Context(ctx, node=self)
        child_ctx = await NodeRunner(
            node=self.workflow,
            parent_ctx=parent_ctx,
        ).run(node_input=ctx.user_content)
        if child_ctx.error:
            raise child_ctx.error
        if False:  # pragma: no cover - keep this method an async generator.
            yield


class AgentOrchestrator:
    """Validate, materialize, and compose requested agents."""

    def __init__(
        self,
        *,
        supports_workflow: bool,
        max_orchestration_depth: int = 2,
        leaf_factory: LeafFactory | None = None,
        knowledge_factory: KnowledgeFactory | None = None,
        skill_cache_dir=None,
    ) -> None:
        self._supports_workflow = supports_workflow
        self._max_depth = max_orchestration_depth
        self._leaf_factory = leaf_factory or _default_leaf_factory
        self._knowledge_factory = knowledge_factory or default_knowledge_factory
        self._skill_cache_dir = skill_cache_dir
        self._skill_locks: dict[str, threading.Lock] = {}

    async def create(
        self,
        *,
        snapshot: ResourceSnapshot,
        agents: Sequence[AgentBlueprint],
        runtime_names: Sequence[str],
        tool_context: Any = None,
    ) -> list[BuiltAgent]:
        skill_tasks: dict[str, asyncio.Task[Any]] = {}
        return list(
            await asyncio.gather(
                *(
                    self._create_one(
                        snapshot,
                        blueprint,
                        runtime_name,
                        tool_context,
                        skill_tasks,
                    )
                    for blueprint, runtime_name in zip(agents, runtime_names)
                )
            )
        )

    async def _create_one(
        self,
        snapshot: ResourceSnapshot,
        blueprint: AgentBlueprint,
        runtime_name: str,
        tool_context: Any,
        skill_tasks: dict[str, asyncio.Task[Any]],
    ) -> BuiltAgent:
        root_type = None
        knowledgebases: list[Any] = []
        description, resources, python_tools = _blueprint_summary(
            blueprint,
            snapshot,
        )
        try:
            nodes = {node.id: node for node in blueprint.nodes}
            root_type = nodes[blueprint.root_node].type
            workflow_members = self._validate_blueprint(blueprint, nodes)
            runtime_node_names = {
                node_id: (
                    runtime_name
                    if node_id == blueprint.root_node
                    else f"{runtime_name}__{node_id}"
                )
                for node_id in nodes
            }
            built: dict[str, Any] = {}
            building: set[str] = set()

            async def build(node_id: str) -> Any:
                if node_id in built:
                    return built[node_id]
                if node_id in building:
                    raise ValueError(f"Cyclic agent nesting detected at '{node_id}'.")
                building.add(node_id)
                node = nodes[node_id]
                runtime_update = {"id": runtime_node_names[node_id]}
                if node.type == "llm":
                    runtime_update["instruction"] = _with_delegated_task_context(
                        node.instruction,
                        blueprint.task,
                    )
                runtime_node = node.model_copy(update=runtime_update)

                if node.type == "llm":
                    llm_node = cast(LlmAgentNode, runtime_node)
                    tools, mounted = await self._build_leaf_tools(
                        node,
                        snapshot,
                        tool_context,
                        skill_tasks,
                    )
                    knowledgebases.extend(mounted)
                    value = self._leaf_factory(
                        llm_node,
                        tools,
                        node_id in workflow_members,
                        _parent_agent(tool_context),
                    )
                elif node.type in {"sequential", "parallel", "loop"}:
                    classic_node = cast(
                        SequentialAgentNode | ParallelAgentNode | LoopAgentNode,
                        runtime_node,
                    )
                    children = [await build(child) for child in classic_node.children]
                    value = _build_classic_orchestrator(classic_node, children)
                elif node.type == "workflow":
                    workflow_node = cast(WorkflowAgentNode, runtime_node)
                    dependencies = _workflow_dependencies(workflow_node)
                    resolved = {
                        dependency: await build(dependency)
                        for dependency in dependencies
                    }
                    workflow = _build_workflow(workflow_node, resolved)
                    value = (
                        _WorkflowTransferAgent(
                            name=runtime_name,
                            description=node.description,
                            workflow=workflow,
                        )
                        if node_id == blueprint.root_node
                        else workflow
                    )
                else:  # pragma: no cover - Pydantic prevents this.
                    raise ValueError(f"Unsupported node type: {node.type}")

                building.remove(node_id)
                built[node_id] = value
                return value

            root = await build(blueprint.root_node)
            if not isinstance(root, BaseAgent):
                raise TypeError(
                    f"Blueprint root '{blueprint.root_node}' cannot be registered "
                    "as an ADK agent."
                )
            return BuiltAgent(
                root=root,
                knowledgebases=knowledgebases,
                result=CreatedAgentResult(
                    name=blueprint.name,
                    runtime_name=runtime_name,
                    description=description,
                    root_type=root_type,
                    status="completed",
                    resources=resources,
                    python_tools=python_tools,
                ),
            )
        except Exception as exc:
            await _close_knowledgebases(knowledgebases)
            return BuiltAgent(
                result=CreatedAgentResult(
                    name=blueprint.name,
                    runtime_name=runtime_name,
                    description=description,
                    root_type=root_type,
                    status="failed",
                    resources=resources,
                    python_tools=python_tools,
                    error=str(exc),
                )
            )

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
        tool_resources = [
            resource for resource in selected if resource.descriptor.kind == "tool"
        ]
        tools.extend(
            get_builtin_tool(_builtin_tool_name(resource))
            for resource in tool_resources
        )
        skill_resources = [
            resource for resource in selected if resource.descriptor.kind == "skill"
        ]
        if skill_resources:
            from google.adk.skills import load_skill_from_dir
            from google.adk.tools.skill_toolset import SkillToolset

            skills = await asyncio.gather(
                *(
                    self._load_skill(resource, tool_context, skill_tasks)
                    for resource in skill_resources
                )
            )
            loaded = [
                await asyncio.to_thread(load_skill_from_dir, path) for path in skills
            ]
            runtime_skills = [
                _with_catalog_skill_name(resource, skill)
                for resource, skill in zip(skill_resources, loaded)
            ]
            tools.append(SkillToolset(skills=runtime_skills))

        knowledge_resources = [
            resource
            for resource in selected
            if resource.descriptor.kind == "knowledge_base"
        ]
        mounted: list[Any] = []
        if knowledge_resources:
            credentials = await asyncio.to_thread(
                resolve_cloud_credentials, tool_context
            )
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
        tool_context: Any,
        skill_tasks: dict[str, asyncio.Task[Any]],
    ) -> Any:
        task = skill_tasks.get(resource.descriptor.ref)
        if task is None:
            lock = self._skill_locks.setdefault(
                resource.descriptor.ref,
                threading.Lock(),
            )
            task = asyncio.create_task(
                self._materialize_resource_skill(
                    resource,
                    tool_context,
                    lock,
                )
            )
            skill_tasks[resource.descriptor.ref] = task
        return await task

    async def _materialize_resource_skill(
        self,
        resource: Any,
        tool_context: Any,
        lock: threading.Lock,
    ) -> Any:
        skill = resource.payload
        credentials = None
        region = None
        if resource.descriptor.source.startswith("skill_space:") and not getattr(
            skill, "bucket_name", None
        ):
            credentials = await asyncio.to_thread(
                resolve_cloud_credentials, tool_context
            )
            if credentials is None:
                raise ValueError(
                    "Selected AgentKit Skills require AK/SK or STS credentials."
                )
            region = str(resource.descriptor.metadata.get("region") or "cn-beijing")
            skill = await asyncio.to_thread(
                resolve_agentkit_skill,
                skill,
                credentials=credentials,
                region=region,
                skill_space_name=str(
                    resource.descriptor.metadata.get("space_name") or ""
                )
                or None,
            )
        return await asyncio.to_thread(
            _materialize_skill,
            lock,
            skill,
            self._skill_cache_dir,
            credentials,
            region,
        )


def _materialize_skill(
    lock: threading.Lock,
    skill: Any,
    cache_dir: Any,
    credentials: CloudCredentials | None = None,
    region: str | None = None,
) -> Any:
    with lock:
        credential_tuple = (
            (
                credentials.access_key,
                credentials.secret_key,
                credentials.session_token,
            )
            if credentials is not None
            else None
        )
        options: dict[str, Any] = {"cache_dir": cache_dir}
        if credential_tuple is not None:
            options["credentials"] = credential_tuple
        if region is not None:
            options["region"] = region
        return materialize_remote_skill(skill, **options)


def _with_catalog_skill_name(resource: Any, skill: Any) -> Any:
    """Expose a materialized skill under the name shown in the catalog.

    Public Skill Hub entries can use a marketplace name that differs from the
    ``name`` declared in the downloaded SKILL.md. The create-agent result and
    inherited conversation use the marketplace name, so the runtime toolset
    must accept that same name. The archive is validated before this rename;
    only the in-memory ADK model is copied.
    """
    catalog_name = str(resource.descriptor.name or "").strip()
    declared_name = str(getattr(skill, "name", "") or "").strip()
    if not catalog_name or catalog_name == declared_name:
        return skill
    frontmatter = skill.frontmatter.model_copy(update={"name": catalog_name})
    return skill.model_copy(update={"frontmatter": frontmatter})


def _builtin_tool_name(resource: Any) -> str:
    if isinstance(resource.payload, str) and resource.payload:
        return resource.payload
    name = resource.descriptor.metadata.get("tool_name")
    return str(name or resource.descriptor.name)


def _blueprint_summary(
    blueprint: AgentBlueprint,
    snapshot: ResourceSnapshot,
) -> tuple[str, list[Any], list[Any]]:
    nodes = {node.id: node for node in blueprint.nodes}
    root = nodes.get(blueprint.root_node)
    description = getattr(root, "description", "") or blueprint.task
    resources = []
    seen_refs: set[str] = set()
    python_tools = []
    seen_python_tools: set[tuple[str, str]] = set()
    for node in blueprint.nodes:
        if node.type != "llm":
            continue
        for ref in node.resources:
            resource = snapshot.resources.get(ref)
            if resource is None or ref in seen_refs:
                continue
            seen_refs.add(ref)
            resources.append(resource.descriptor)
        for spec in node.python_tools:
            key = (spec.name, spec.code)
            if key in seen_python_tools:
                continue
            seen_python_tools.add(key)
            python_tools.append(spec)
    return description, resources, python_tools


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
        "disallow_transfer_to_parent": True,
        "disallow_transfer_to_peers": True,
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
    if inherit_parent_model and parent_agent is not None:
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


def _with_delegated_task_context(instruction: str, task: str) -> str:
    """Attach one invocation's task without changing the reusable blueprint."""

    delegated_task = task.strip()
    if not delegated_task:
        return instruction
    return (
        f"{instruction.rstrip()}\n\n"
        "Current delegated task (runtime context, not reusable identity):\n"
        f"{delegated_task}"
    )


def _parent_agent(tool_context: Any) -> Any:
    invocation = getattr(tool_context, "_invocation_context", None)
    return getattr(invocation, "agent", None)
