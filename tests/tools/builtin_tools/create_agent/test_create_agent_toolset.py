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

import asyncio
import json
import threading
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.agents import BaseAgent, LlmAgent
from google.adk.events import Event
from google.adk.events.event_actions import EventActions
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.genai import types

from veadk import Agent
from veadk.knowledgebase.entry import KnowledgebaseEntry
from veadk.skills.skill import Skill
from veadk.tools.builtin_tools.create_agent import CreateAgentToolset
from veadk.tools.builtin_tools.create_agent.capabilities import (
    detect_agent_capabilities,
)
from veadk.tools.builtin_tools.create_agent.models import (
    AgentCapabilities,
    PythonToolSpec,
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.python_tools import compile_python_tool
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgePayload,
    CloudCredentials,
    SourceCollection,
)


def _context(
    session_id: str = "session-1",
    parent_agent: Any = None,
    invocation_id: str | None = None,
) -> Any:
    if parent_agent is None:
        parent_agent = _TextAgent(name="main", marker="main")
    session = SimpleNamespace(
        id=session_id,
        app_name="test-app",
        user_id="test-user",
    )
    invocation = SimpleNamespace(
        session=session,
        user_id="test-user",
        agent=parent_agent,
        invocation_id=invocation_id,
    )
    return SimpleNamespace(
        state={},
        actions=EventActions(),
        _invocation_context=invocation,
    )


class _StaticSource:
    name = "static"

    def __init__(self, resources: list[StoredResource] | None = None) -> None:
        self.resources = resources or []

    async def collect(self, tool_context=None) -> SourceCollection:
        return SourceCollection(
            resources=self.resources,
            status=ResourceSourceStatus(
                source=self.name,
                status="ok",
                count=len(self.resources),
            ),
        )


class _BarrierSource:
    def __init__(self, name: str, barrier: asyncio.Event, started: set[str]) -> None:
        self.name = name
        self._barrier = barrier
        self._started = started

    async def collect(self, tool_context=None) -> SourceCollection:
        self._started.add(self.name)
        if len(self._started) == 2:
            self._barrier.set()
        await asyncio.wait_for(self._barrier.wait(), timeout=0.5)
        return SourceCollection(
            status=ResourceSourceStatus(source=self.name, status="ok")
        )


class _TextAgent(BaseAgent):
    marker: str

    async def _run_async_impl(self, ctx):
        yield Event(
            author=self.name,
            content=types.ModelContent(parts=[types.Part(text=self.marker)]),
        )


class _ToolAwareAgent(BaseAgent):
    mounted_tools: Any

    async def _run_async_impl(self, ctx):
        if False:
            yield


def _leaf_factory(node, tools, workflow_member, parent_agent):
    del tools, workflow_member, parent_agent
    return _TextAgent(name=node.id, marker=node.id)


def _blueprint(name: str = "child") -> dict[str, Any]:
    return {
        "name": name,
        "task": "run",
        "root_node": "worker",
        "nodes": [{"id": "worker", "type": "llm", "instruction": "work"}],
    }


@pytest.mark.asyncio
async def test_toolset_exposes_exactly_two_tools_and_dynamic_schema() -> None:
    modern = CreateAgentToolset(
        resource_sources=[],
        capabilities=AgentCapabilities(
            google_adk_version="2.2.0",
            agent_types=["llm", "sequential", "parallel", "loop", "workflow"],
        ),
    )
    legacy = CreateAgentToolset(
        resource_sources=[],
        capabilities=AgentCapabilities(
            google_adk_version="1.34.0",
            agent_types=["llm", "sequential", "parallel", "loop"],
        ),
    )

    modern_tools = await modern.get_tools()
    legacy_tools = await legacy.get_tools()

    assert [tool.name for tool in modern_tools] == [
        "collect_resources",
        "create_agents",
    ]
    modern_declaration = modern_tools[1]._get_declaration()
    legacy_declaration = legacy_tools[1]._get_declaration()
    assert modern_declaration is not None
    assert legacy_declaration is not None
    modern_schema = json.dumps(modern_declaration.parameters_json_schema)
    legacy_schema = json.dumps(legacy_declaration.parameters_json_schema)
    assert '"const": "workflow"' in modern_schema
    assert '"const": "workflow"' not in legacy_schema
    assert "Resources are not mounted automatically" in modern_schema
    assert "include each relevant Skill ref explicitly" in modern_schema
    assert "Use an empty string only when" in modern_schema
    assert modern_declaration.description is not None
    assert "pass an empty collection_id" in modern_declaration.description
    assert "explicitly prohibits network" in modern_declaration.description
    assert "when relevant Skills were returned, bind at least one" in (
        modern_declaration.description or ""
    )


@pytest.mark.asyncio
async def test_collect_resources_queries_all_sources_concurrently() -> None:
    barrier = asyncio.Event()
    started: set[str] = set()
    toolset = CreateAgentToolset(
        resource_sources=[
            _BarrierSource("public", barrier, started),
            _BarrierSource("private", barrier, started),
        ]
    )

    result = await toolset.collect_resources()

    assert started == {"public", "private"}
    assert [item["source"] for item in result["sources"]] == [
        "public",
        "private",
    ]


def test_default_sources_include_public_and_agentkit_skill_spaces(monkeypatch) -> None:
    monkeypatch.setenv("SKILL_HUB_SPACE_ID", "sp-public")
    monkeypatch.setenv("SKILL_SPACE_ID", "ss-private")

    toolset = CreateAgentToolset()

    assert [source.name for source in toolset._collector._sources] == [
        "skill_hub:sp-public",
        "skill_space:agentkit",
        "agentkit_knowledge",
        "veadk_builtin_tools",
    ]
    assert toolset._collector._sources[1].space_ids == ("ss-private",)


def test_default_sources_search_all_agentkit_skill_spaces(monkeypatch) -> None:
    monkeypatch.delenv("SKILL_HUB_SPACE_ID", raising=False)
    monkeypatch.delenv("SKILL_SPACE_ID", raising=False)

    toolset = CreateAgentToolset()

    assert [source.name for source in toolset._collector._sources] == [
        "skill_space:agentkit",
        "agentkit_knowledge",
        "veadk_builtin_tools",
    ]
    assert toolset._collector._sources[0].space_ids == ()


@pytest.mark.asyncio
async def test_default_collection_includes_veadk_builtin_tools(monkeypatch) -> None:
    monkeypatch.delenv("SKILL_HUB_SPACE_ID", raising=False)
    monkeypatch.delenv("SKILL_SPACE_ID", raising=False)
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.sources.builtin_tools.list_builtin_tools",
        lambda: ["web_search", "run_code"],
    )
    toolset = CreateAgentToolset()

    result = await toolset.collect_resources()

    assert [resource["ref"] for resource in result["resources"]] == [
        "veadk_tool:web_search",
        "veadk_tool:run_code",
    ]
    assert all(resource["kind"] == "tool" for resource in result["resources"])
    assert result["sources"][-1] == {
        "source": "veadk_builtin_tools",
        "status": "ok",
        "count": 2,
        "message": None,
        "search_keywords": [],
    }


@pytest.mark.asyncio
async def test_collect_resources_searches_skill_hub_with_supplied_keywords(
    monkeypatch,
) -> None:
    captured: list[list[str]] = []

    class SearchSource:
        name = "skill_hub:public"

        def __init__(self, keywords):
            captured.append(list(keywords))

        async def collect(self, tool_context=None):
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name,
                    status="ok",
                    search_keywords=captured[-1],
                )
            )

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.toolset.SkillHubSearchSource",
        SearchSource,
    )
    toolset = CreateAgentToolset(resource_sources=[])

    result = await toolset.collect_resources(
        skill_hub_keywords=[" AgentKit ", "公开资料", "AgentKit"],
    )

    assert captured == [["AgentKit", "公开资料"]]
    assert result["sources"][0]["search_keywords"] == ["AgentKit", "公开资料"]


@pytest.mark.asyncio
async def test_collect_then_create_nested_agents_through_function_tools() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource()],
        leaf_factory=_leaf_factory,
    )
    collect_tool, create_tool = await toolset.get_tools()
    context = _context()

    collected = await collect_tool.run_async(args={}, tool_context=context)
    result = await create_tool.run_async(
        args={
            "collection_id": collected["collection_id"],
            "agents": [
                {
                    "name": "research_pipeline",
                    "task": "research",
                    "root_node": "pipeline",
                    "nodes": [
                        {"id": "researcher", "type": "llm", "instruction": "r"},
                        {"id": "analyst", "type": "llm", "instruction": "a"},
                        {"id": "reviewer", "type": "llm", "instruction": "v"},
                        {
                            "id": "analysis_group",
                            "type": "parallel",
                            "children": ["analyst", "reviewer"],
                        },
                        {
                            "id": "pipeline",
                            "type": "sequential",
                            "children": ["researcher", "analysis_group"],
                        },
                    ],
                }
            ],
            "handoff_to": "research_pipeline",
        },
        tool_context=context,
    )

    created = result["results"][0]
    assert created["name"] == "research_pipeline"
    assert created["description"] == "research"
    assert created["root_type"] == "sequential"
    assert created["status"] == "completed"
    assert created["output"] is None
    assert result["handoff_to"] == created["runtime_name"]
    assert context.actions.transfer_to_agent == created["runtime_name"]
    assert context._invocation_context.agent.find_agent(created["runtime_name"])


@pytest.mark.asyncio
async def test_delegated_task_is_injected_into_each_runtime_leaf_instruction() -> None:
    captured_instructions: list[str] = []

    def capture_leaf(node, tools, workflow_member, parent_agent):
        del tools, workflow_member, parent_agent
        captured_instructions.append(node.instruction)
        return _TextAgent(name=node.id, marker=node.id)

    toolset = CreateAgentToolset(resource_sources=[], leaf_factory=capture_leaf)
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)
    task = "Compare the three user-provided options and return a decision matrix."
    reusable_instruction = "Analyze user-specified candidates using requested criteria."
    blueprint = {
        "name": "comparison_agent",
        "task": task,
        "root_node": "comparison_flow",
        "nodes": [
            {
                "id": "researcher",
                "type": "llm",
                "instruction": reusable_instruction,
            },
            {
                "id": "writer",
                "type": "llm",
                "instruction": "Write the requested structured result.",
            },
            {
                "id": "comparison_flow",
                "type": "sequential",
                "children": ["researcher", "writer"],
            },
        ],
    }

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[blueprint],
        handoff_to="comparison_agent",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    assert len(captured_instructions) == 2
    assert all(
        "Current delegated task (runtime context, not reusable identity):" in value
        for value in captured_instructions
    )
    assert all(task in value for value in captured_instructions)
    assert captured_instructions[0].startswith(reusable_instruction)
    assert blueprint["nodes"][0]["instruction"] == reusable_instruction


@pytest.mark.asyncio
async def test_create_agents_accepts_empty_collection_without_querying_sources() -> (
    None
):
    class UnexpectedSource:
        name = "unexpected"
        called = False

        async def collect(self, tool_context=None):
            del tool_context
            self.called = True
            raise AssertionError("resource source must not be queried")

    source = UnexpectedSource()
    toolset = CreateAgentToolset(
        resource_sources=[source],
        leaf_factory=_leaf_factory,
    )
    context = _context()

    result = await toolset.create_agents(
        collection_id="",
        agents=[_blueprint("offline_worker")],
        handoff_to="offline_worker",
        tool_context=context,
    )

    assert not source.called
    assert result["collection_id"].startswith("resources_")
    assert result["results"][0]["status"] == "completed"
    assert result["handoff_to"] == result["results"][0]["runtime_name"]


@pytest.mark.asyncio
async def test_selected_builtin_tool_is_resolved_during_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    builtin = object()
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="veadk_tool:web_search",
            kind="tool",
            name="web_search",
            description="Search the web.",
            source="veadk_builtin_tools",
            metadata={"tool_name": "web_search"},
        ),
        payload="web_search",
    )
    resolved: list[str] = []

    def get_tool(name: str):
        resolved.append(name)
        return builtin

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.get_builtin_tool",
        get_tool,
    )
    mounted: list[list[Any]] = []

    def leaf_factory(node, tools, workflow_member, parent_agent):
        del workflow_member, parent_agent
        mounted.append(tools)
        return _TextAgent(name=node.id, marker=node.id)

    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=leaf_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)
    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "researcher",
                "task": "research",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "description": "Find current information",
                        "instruction": "Use web search",
                        "resources": ["veadk_tool:web_search"],
                    }
                ],
            }
        ],
        handoff_to="researcher",
        tool_context=context,
    )

    assert resolved == ["web_search"]
    assert mounted == [[builtin]]
    assert result["results"][0]["description"] == "Find current information"
    assert result["results"][0]["resources"] == [resource.descriptor.model_dump()]


@pytest.mark.skipif(
    "workflow" not in detect_agent_capabilities().agent_types,
    reason="installed google-adk does not expose Workflow",
)
@pytest.mark.asyncio
async def test_workflow_executes_when_adk_supports_it() -> None:
    toolset = CreateAgentToolset(resource_sources=[], leaf_factory=_leaf_factory)
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "workflow_demo",
                "task": "run",
                "root_node": "flow",
                "nodes": [
                    {"id": "first", "type": "llm", "instruction": "first"},
                    {"id": "second", "type": "llm", "instruction": "second"},
                    {
                        "id": "flow",
                        "type": "workflow",
                        "edges": [
                            {"from": "START", "to": "first"},
                            {"from": "first", "to": "second"},
                        ],
                    },
                ],
            }
        ],
        handoff_to="workflow_demo",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    assert result["results"][0]["root_type"] == "workflow"
    assert result["results"][0]["output"] is None
    assert context.actions.transfer_to_agent == result["handoff_to"]


@pytest.mark.asyncio
async def test_rejects_more_than_two_orchestration_layers() -> None:
    toolset = CreateAgentToolset(resource_sources=[], leaf_factory=_leaf_factory)
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "too_deep",
                "task": "run",
                "root_node": "outer",
                "nodes": [
                    {"id": "leaf", "type": "llm", "instruction": "leaf"},
                    {
                        "id": "inner",
                        "type": "loop",
                        "children": ["leaf"],
                    },
                    {
                        "id": "middle",
                        "type": "parallel",
                        "children": ["inner"],
                    },
                    {
                        "id": "outer",
                        "type": "sequential",
                        "children": ["middle"],
                    },
                ],
            }
        ],
        handoff_to="too_deep",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "failed"
    assert "Maximum orchestration depth exceeded" in result["results"][0]["error"]
    assert result["handoff_to"] is None
    assert context.actions.transfer_to_agent is None


@pytest.mark.asyncio
async def test_create_agents_requires_an_active_agent_context() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    collected = await toolset.collect_resources()

    with pytest.raises(ValueError, match="active ADK agent invocation"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="child",
        )


@pytest.mark.asyncio
async def test_create_agents_rejects_unknown_handoff_target() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    with pytest.raises(ValueError, match="must match one of agents"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="missing",
            tool_context=context,
        )


@pytest.mark.asyncio
async def test_collection_is_scoped_to_the_calling_session() -> None:
    toolset = CreateAgentToolset(resource_sources=[])
    collected = await toolset.collect_resources(tool_context=_context("one"))

    with pytest.raises(ValueError, match="different invocation or session"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="child",
            tool_context=_context("two"),
        )


@pytest.mark.asyncio
async def test_collection_is_scoped_to_the_calling_invocation() -> None:
    toolset = CreateAgentToolset(resource_sources=[])
    collected = await toolset.collect_resources(
        tool_context=_context("shared-session", invocation_id="invocation-one")
    )

    with pytest.raises(ValueError, match="different invocation or session"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="child",
            tool_context=_context("shared-session", invocation_id="invocation-two"),
        )


@pytest.mark.asyncio
async def test_collection_can_create_additional_agents_in_same_invocation() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    context = _context(invocation_id="one-shot")
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[_blueprint()],
        handoff_to="child",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    second = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[_blueprint("reviewer")],
        handoff_to="reviewer",
        tool_context=context,
    )

    assert second["results"][0]["status"] == "completed"
    assert second["handoff_to"].startswith("reviewer__")


@pytest.mark.asyncio
async def test_repeating_create_agents_returns_existing_runtime() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    context = _context(invocation_id="retry")
    collected = await toolset.collect_resources(tool_context=context)

    first = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[_blueprint()],
        handoff_to="child",
        tool_context=context,
    )
    second = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[_blueprint()],
        handoff_to="child",
        tool_context=context,
    )

    assert second == first


@pytest.mark.asyncio
async def test_parallel_duplicate_create_agents_calls_build_once() -> None:
    built_nodes: list[str] = []

    def counting_leaf_factory(node, tools, workflow_member, parent_agent):
        del tools, workflow_member, parent_agent
        built_nodes.append(node.id)
        return _TextAgent(name=node.id, marker=node.id)

    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=counting_leaf_factory,
    )
    parent = _TextAgent(name="main", marker="main")
    first_context = _context(
        parent_agent=parent,
        invocation_id="parallel-duplicate",
    )
    second_context = _context(
        parent_agent=parent,
        invocation_id="parallel-duplicate",
    )
    collected = await toolset.collect_resources(tool_context=first_context)

    first, second = await asyncio.gather(
        toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="child",
            tool_context=first_context,
        ),
        toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[_blueprint()],
            handoff_to="child",
            tool_context=second_context,
        ),
    )

    assert first == second
    assert len(built_nodes) == 1
    assert built_nodes[0].startswith("child__")
    assert first_context.actions.transfer_to_agent == first["handoff_to"]
    assert second_context.actions.transfer_to_agent == first["handoff_to"]


@pytest.mark.asyncio
async def test_agents_are_registered_and_selected_target_is_handed_off() -> None:
    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            _blueprint("researcher"),
            _blueprint("writer"),
        ],
        handoff_to="writer",
        tool_context=context,
    )

    runtime_names = [item["runtime_name"] for item in result["results"]]
    assert all(
        context._invocation_context.agent.find_agent(name) for name in runtime_names
    )
    assert context.actions.transfer_to_agent == runtime_names[1]
    assert result["handoff_to"] == runtime_names[1]


@pytest.mark.asyncio
async def test_default_leaf_inherits_parent_model() -> None:
    toolset = CreateAgentToolset(resource_sources=[])
    parent = LlmAgent(name="main", model="parent-model")
    context = _context(
        parent_agent=parent,
    )
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "child",
                "task": "run",
                "root_node": "worker",
                "nodes": [{"id": "worker", "type": "llm", "instruction": "work"}],
            }
        ],
        handoff_to="child",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    runtime_name = result["results"][0]["runtime_name"]
    created_agent = parent.find_agent(runtime_name)
    assert created_agent is not None
    assert getattr(created_agent, "model", None) == "parent-model"


@pytest.mark.asyncio
async def test_skill_is_materialized_only_during_create(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = Skill(
        name="demo-skill",
        description="Demo",
        path="remote/path/v1",
        id="skill-1",
        skill_space_id="sp-public",
        source_type="skillhub",
        version_id="v1",
    )
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="sp-public:skill-1",
            kind="skill",
            name="demo-skill",
            description="Demo",
            source="skill_hub:sp-public",
            version="v1",
        ),
        payload=skill,
    )
    calls: list[str] = []
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\nUse this skill.",
        encoding="utf-8",
    )

    def materialize(value, *, cache_dir=None):
        del cache_dir
        calls.append(value.name)
        return skill_dir

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.materialize_remote_skill",
        materialize,
    )
    observed_tools: list[list[str]] = []

    def leaf_factory(node, tools, workflow_member, parent_agent):
        del workflow_member, parent_agent
        observed_tools.append([tool.__class__.__name__ for tool in tools])
        return _TextAgent(name=node.id, marker=node.id)

    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=leaf_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)
    assert calls == []

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "skilled",
                "task": "run",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "instruction": "use skill",
                        "resources": ["sp-public:skill-1"],
                    }
                ],
            }
        ],
        handoff_to="skilled",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    assert calls == ["demo-skill"]
    assert observed_tools == [["SkillToolset"]]


@pytest.mark.asyncio
async def test_skill_hub_catalog_name_remains_callable_when_manifest_name_differs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = Skill(
        name="seedance-video-generation",
        description="Generate videos",
        path="clawhub/example/seedance-video-generation",
        id="clawhub/example/seedance-video-generation",
        source_type="findskill",
    )
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="skill_hub:clawhub/example/seedance-video-generation",
            kind="skill",
            name="seedance-video-generation",
            description="Generate videos",
            source="skill_hub:public",
        ),
        payload=skill,
    )
    skill_dir = tmp_path / "seedance-video"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: seedance-video\ndescription: Generate videos\n---\n"
        "Use the video generation tools.",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.materialize_remote_skill",
        lambda value, *, cache_dir=None: skill_dir,
    )
    mounted_tools: list[Any] = []

    def leaf_factory(node, tools, workflow_member, parent_agent):
        del workflow_member, parent_agent
        mounted_tools.extend(tools)
        return _TextAgent(name=node.id, marker=node.id)

    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=leaf_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)
    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "video_creator",
                "task": "create a video",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "instruction": "Use the selected skill",
                        "resources": [resource.descriptor.ref],
                    }
                ],
            }
        ],
        handoff_to="video_creator",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    skill_toolset = mounted_tools[0]
    tools = await skill_toolset.get_tools()
    load_skill = next(tool for tool in tools if tool.name == "load_skill")
    load_result = await load_skill.run_async(
        args={"skill_name": "seedance-video-generation"},
        tool_context=SimpleNamespace(
            invocation_id="invocation-1",
            agent_name="worker",
            state={},
        ),
    )
    assert load_result["skill_name"] == "seedance-video-generation"
    assert load_result["frontmatter"]["name"] == "seedance-video-generation"
    assert "video generation tools" in load_result["instructions"]


@pytest.mark.asyncio
async def test_agentkit_skill_is_hydrated_only_when_selected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = Skill(
        name="private-writer",
        description="Write private reports",
        path="skill-private",
        id="skill-private",
        skill_space_id="ss-private",
        source_type="skillspace",
        version_id="v7",
    )
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="ss-private:skill-private",
            kind="skill",
            name="private-writer",
            description="Write private reports",
            source="skill_space:ss-private",
            version="v7",
            metadata={
                "region": "cn-beijing",
                "space_name": "Private Team",
            },
        ),
        payload=skill,
    )
    version_requests = []

    class Client:
        def get_skill_version(self, request):
            version_requests.append(request)
            return SimpleNamespace(
                name="private-writer",
                description="Write private reports",
                version="v7",
                bucket_name="private-skills",
                tos_path="skills/skill-private/v7/archive.zip",
            )

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.sources.skills._default_agentkit_client_factory",
        lambda credentials, region: Client(),
    )
    skill_dir = tmp_path / "private-writer"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: private-writer\ndescription: Demo\n---\nUse this skill.",
        encoding="utf-8",
    )
    materialized: list[Skill] = []

    def materialize(value, *, cache_dir=None, credentials=None, region=None):
        del cache_dir
        materialized.append(value)
        assert credentials == ("ak", "sk", "sts")
        assert region == "cn-beijing"
        return skill_dir

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.materialize_remote_skill",
        materialize,
    )
    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=_leaf_factory,
    )
    context = _context()
    context.state.update(
        {
            "VOLCENGINE_ACCESS_KEY": "ak",
            "VOLCENGINE_SECRET_KEY": "sk",
            "VOLCENGINE_SESSION_TOKEN": "sts",
        }
    )
    collected = await toolset.collect_resources(tool_context=context)
    assert version_requests == []

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "private_agent",
                "task": "run",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "instruction": "use private skill",
                        "resources": ["ss-private:skill-private"],
                    }
                ],
            }
        ],
        handoff_to="private_agent",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    assert len(version_requests) == 1
    assert version_requests[0].id == "skill-private"
    assert version_requests[0].skill_version == "v7"
    assert len(materialized) == 1
    assert materialized[0].bucket_name == "private-skills"
    assert materialized[0].path == "skills/skill-private/v7/archive.zip"


@pytest.mark.asyncio
async def test_concurrent_invocations_serialize_same_skill_materialization(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    skill = Skill(
        name="demo-skill",
        description="Demo",
        path="remote/path/v1",
        id="skill-1",
        skill_space_id="sp-public",
        source_type="skillhub",
        version_id="v1",
    )
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="sp-public:skill-1",
            kind="skill",
            name="demo-skill",
            source="skill_hub:sp-public",
        ),
        payload=skill,
    )
    skill_dir = tmp_path / "demo-skill"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: demo-skill\ndescription: Demo\n---\nUse this skill.",
        encoding="utf-8",
    )
    guard = threading.Lock()
    active = 0
    max_active = 0

    def materialize(value, *, cache_dir=None):
        nonlocal active, max_active
        del value, cache_dir
        with guard:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.05)
        with guard:
            active -= 1
        return skill_dir

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.materialize_remote_skill",
        materialize,
    )
    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=_leaf_factory,
    )
    contexts = [
        _context(invocation_id="invocation-one"),
        _context(invocation_id="invocation-two"),
    ]
    collections = await asyncio.gather(
        *(toolset.collect_resources(tool_context=context) for context in contexts)
    )
    blueprint = {
        "name": "skilled",
        "task": "run",
        "root_node": "worker",
        "nodes": [
            {
                "id": "worker",
                "type": "llm",
                "instruction": "use skill",
                "resources": ["sp-public:skill-1"],
            }
        ],
    }

    results = await asyncio.gather(
        *(
            toolset.create_agents(
                collection_id=collection["collection_id"],
                agents=[blueprint],
                handoff_to="skilled",
                tool_context=context,
            )
            for collection, context in zip(collections, contexts)
        )
    )

    assert [result["results"][0]["status"] for result in results] == [
        "completed",
        "completed",
    ]
    assert max_active == 1


@pytest.mark.asyncio
async def test_selected_knowledge_is_mounted_as_read_only_search_tool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = AgentKitKnowledgePayload(
        knowledge_id="kb-agentkit-1",
        provider_knowledge_id="provider_index",
        provider_type="VIKINGDB_KNOWLEDGE",
        name="handbook",
        description="Internal handbook",
        project_name="default",
        region="cn-beijing",
        cloud_provider="volcengine",
    )
    resource = StoredResource(
        descriptor=ResourceDescriptor(
            ref="agentkit_kb:kb-agentkit-1",
            kind="knowledge_base",
            name="handbook",
            description="Internal handbook",
            source="agentkit_knowledge",
        ),
        payload=payload,
    )
    closed: list[bool] = []

    class Knowledge:
        def search(self, query: str, top_k: int):
            return [KnowledgebaseEntry(content=f"{query}:{top_k}")]

        def close(self):
            closed.append(True)

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.resolve_cloud_credentials",
        lambda context: CloudCredentials("ak", "sk", "sts"),
    )

    def leaf_factory(node, tools, workflow_member, parent_agent):
        del workflow_member, parent_agent
        return _ToolAwareAgent(name=node.id, mounted_tools=tools)

    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=leaf_factory,
        knowledge_factory=lambda selected, credentials: Knowledge(),
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "grounded",
                "task": "run",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "instruction": "use knowledge",
                        "resources": ["agentkit_kb:kb-agentkit-1"],
                    }
                ],
            }
        ],
        handoff_to="grounded",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    runtime_name = result["results"][0]["runtime_name"]
    root = context._invocation_context.agent.find_agent(runtime_name)
    knowledge_tool = root.mounted_tools[0]
    search_result = await knowledge_tool.func("policy", 3)
    assert search_result[0]["entries"][0]["content"] == "policy:3"
    assert closed == []
    await toolset.close()
    assert closed == [True]


@pytest.mark.asyncio
async def test_partial_knowledge_mount_failure_closes_created_instances(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resources = []
    for knowledge_id in ("healthy", "broken"):
        payload = AgentKitKnowledgePayload(
            knowledge_id=knowledge_id,
            provider_knowledge_id=f"provider_{knowledge_id}",
            provider_type="VIKINGDB_KNOWLEDGE",
            name=knowledge_id,
            description="",
            project_name="default",
            region="cn-beijing",
            cloud_provider="volcengine",
        )
        resources.append(
            StoredResource(
                descriptor=ResourceDescriptor(
                    ref=f"agentkit_kb:{knowledge_id}",
                    kind="knowledge_base",
                    name=knowledge_id,
                    source="agentkit_knowledge",
                ),
                payload=payload,
            )
        )
    closed: list[bool] = []

    class Knowledge:
        def close(self):
            closed.append(True)

    def knowledge_factory(payload, credentials):
        del credentials
        if payload.knowledge_id == "broken":
            raise RuntimeError("mount failed")
        return Knowledge()

    monkeypatch.setattr(
        "veadk.tools.builtin_tools.create_agent.orchestrator.resolve_cloud_credentials",
        lambda context: CloudCredentials("ak", "sk"),
    )
    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource(resources)],
        leaf_factory=_leaf_factory,
        knowledge_factory=knowledge_factory,
    )
    context = _context()
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {
                "name": "grounded",
                "task": "run",
                "root_node": "worker",
                "nodes": [
                    {
                        "id": "worker",
                        "type": "llm",
                        "instruction": "use knowledge",
                        "resources": [
                            "agentkit_kb:healthy",
                            "agentkit_kb:broken",
                        ],
                    }
                ],
            }
        ],
        handoff_to="grounded",
        tool_context=context,
    )

    assert result["results"][0]["status"] == "failed"
    assert result["results"][0]["error"] == "mount failed"
    assert closed == [True]


def test_python_tool_runs_locally_and_checks_current_dependencies() -> None:
    tool = compile_python_tool(
        PythonToolSpec(
            name="double",
            description="Double a value",
            code="def double(value: int) -> int:\n    return value * 2",
            dependencies=["pydantic>=2"],
        )
    )
    assert tool(3) == 6

    dataclass_tool = compile_python_tool(
        PythonToolSpec(
            name="build_value",
            description="Build a dataclass value",
            code=(
                "from dataclasses import dataclass\n"
                "@dataclass\n"
                "class Value:\n"
                "    amount: int\n"
                "def build_value(amount: int) -> int:\n"
                "    return Value(amount).amount"
            ),
            dependencies=["package-that-does-not-exist; python_version < '3'"],
        )
    )
    assert dataclass_tool(7) == 7

    with pytest.raises(ValueError, match="not installed automatically"):
        compile_python_tool(
            PythonToolSpec(
                name="missing",
                description="Missing dependency",
                code="def missing():\n    return None",
                dependencies=["definitely-not-installed-veadk-package>=1"],
            )
        )


@pytest.mark.asyncio
async def test_main_agent_can_answer_without_delegating() -> None:
    class DirectLlm(BaseLlm):
        async def generate_content_async(
            self, llm_request, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            del llm_request, stream
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(text="direct answer")],
                )
            )

    toolset = CreateAgentToolset(resource_sources=[])
    main = Agent(
        name="main",
        model=DirectLlm(model="direct-llm"),
        model_api_key="test-key",
        instruction="Answer simple requests directly.",
        tools=[toolset],
    )
    runner = InMemoryRunner(agent=main, app_name="dynamic-direct-test")
    session_id = "dynamic-direct-session"
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="test-user",
        session_id=session_id,
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=session_id,
            new_message=types.UserContent(parts=[types.Part(text="hello")]),
        )
    ]

    assert not [call for event in events for call in (event.get_function_calls() or [])]
    assert any(
        event.content
        and any(part.text == "direct answer" for part in (event.content.parts or []))
        for event in events
    )


@pytest.mark.asyncio
async def test_runner_transfers_from_create_agents_to_dynamic_sub_agent() -> None:
    class DelegatingLlm(BaseLlm):
        call_count: int = 0

        async def generate_content_async(
            self, llm_request, stream: bool = False
        ) -> AsyncGenerator[LlmResponse, None]:
            del stream
            self.call_count += 1
            if self.call_count == 1:
                function_call = types.FunctionCall(
                    id="collect-call",
                    name="collect_resources",
                    args={},
                )
            else:
                collection_id = next(
                    (part.function_response.response or {})["collection_id"]
                    for content in reversed(llm_request.contents or [])
                    for part in (content.parts or [])
                    if part.function_response
                    and part.function_response.name == "collect_resources"
                )
                function_call = types.FunctionCall(
                    id="create-call",
                    name="create_agents",
                    args={
                        "collection_id": collection_id,
                        "agents": [_blueprint("specialist")],
                        "handoff_to": "specialist",
                    },
                )
            yield LlmResponse(
                content=types.Content(
                    role="model",
                    parts=[types.Part(function_call=function_call)],
                )
            )

    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
    )
    main = Agent(
        name="main",
        model=DelegatingLlm(model="delegating-llm"),
        model_api_key="test-key",
        instruction="Delegate this task.",
        tools=[toolset],
    )
    runner = InMemoryRunner(agent=main, app_name="test-app")
    session_id = "dynamic-transfer-session"
    await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="test-user",
        session_id=session_id,
    )

    events = [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=session_id,
            new_message=types.UserContent(
                parts=[types.Part(text="Complete the specialist task")]
            ),
        )
    ]

    create_event = next(
        event
        for event in events
        if any(
            response.name == "create_agents"
            for response in event.get_function_responses()
        )
    )
    target = create_event.actions.transfer_to_agent
    assert target and target.startswith("specialist__")
    assert any(event.author == target for event in events), [
        (
            event.author,
            event.actions.transfer_to_agent,
            [response.name for response in (event.get_function_responses() or [])],
            event.error_message,
        )
        for event in events
    ]
    assert any(
        event.author == target
        and event.content
        and any(part.text == target for part in (event.content.parts or []))
        for event in events
    )
    assert target in toolset._registrations, (
        [agent.name for agent in main.sub_agents],
        list(toolset._registrations),
    )
