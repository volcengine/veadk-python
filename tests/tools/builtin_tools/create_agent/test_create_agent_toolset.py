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
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.genai import types

from veadk.skills.skill import Skill
from veadk.knowledgebase.entry import KnowledgebaseEntry
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
from veadk.tools.builtin_tools.create_agent.sources import SourceCollection
from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgePayload,
    CloudCredentials,
)


def _context(
    session_id: str = "session-1",
    parent_agent: Any = None,
    invocation_id: str | None = None,
) -> Any:
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
    return SimpleNamespace(state={}, _invocation_context=invocation)


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
    modern_schema = json.dumps(
        modern_tools[1]._get_declaration().parameters_json_schema
    )
    legacy_schema = json.dumps(
        legacy_tools[1]._get_declaration().parameters_json_schema
    )
    assert '"const": "workflow"' in modern_schema
    assert '"const": "workflow"' not in legacy_schema


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


def test_default_sources_include_public_and_private_skill_spaces(monkeypatch) -> None:
    monkeypatch.setenv("SKILL_HUB_SPACE_ID", "sp-public")
    monkeypatch.setenv("SKILL_SPACE_ID", "ss-private")

    toolset = CreateAgentToolset()

    assert [source.name for source in toolset._collector._sources] == [
        "skill_hub:sp-public",
        "skill_space:ss-private",
        "agentkit_knowledge",
        "veadk_builtin_tools",
    ]


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
    }


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
        },
        tool_context=context,
    )

    assert result["results"] == [
        {
            "name": "research_pipeline",
            "description": "research",
            "root_type": "sequential",
            "status": "completed",
            "resources": [],
            "python_tools": [],
            "output": "reviewer",
            "error": None,
        }
    ]


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
    collected = await toolset.collect_resources()
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
    collected = await toolset.collect_resources()

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
    )

    assert result["results"][0]["status"] == "completed"
    assert result["results"][0]["root_type"] == "workflow"
    assert result["results"][0]["output"] == "second"


@pytest.mark.asyncio
async def test_rejects_more_than_two_orchestration_layers() -> None:
    toolset = CreateAgentToolset(resource_sources=[], leaf_factory=_leaf_factory)
    collected = await toolset.collect_resources()

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
    )

    assert result["results"][0]["status"] == "failed"
    assert "Maximum orchestration depth exceeded" in result["results"][0]["error"]


@pytest.mark.asyncio
async def test_collection_is_scoped_to_the_calling_session() -> None:
    toolset = CreateAgentToolset(resource_sources=[])
    collected = await toolset.collect_resources(tool_context=_context("one"))

    with pytest.raises(ValueError, match="different invocation or session"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[],
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
            agents=[],
            tool_context=_context("shared-session", invocation_id="invocation-two"),
        )


@pytest.mark.asyncio
async def test_collection_is_released_after_create_agents() -> None:
    toolset = CreateAgentToolset(resource_sources=[])
    context = _context(invocation_id="one-shot")
    collected = await toolset.collect_resources(tool_context=context)

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[],
        tool_context=context,
    )

    assert result["results"] == []
    with pytest.raises(ValueError, match="Unknown or expired collection_id"):
        await toolset.create_agents(
            collection_id=collected["collection_id"],
            agents=[],
            tool_context=context,
        )


@pytest.mark.asyncio
async def test_agents_run_concurrently_and_fail_independently() -> None:
    started: set[str] = set()
    ready = asyncio.Event()

    async def executor(root, task: str, name: str) -> str:
        del root, task
        started.add(name)
        if len(started) == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), timeout=0.5)
        if name == "broken":
            raise RuntimeError("boom")
        return "ok"

    toolset = CreateAgentToolset(
        resource_sources=[],
        leaf_factory=_leaf_factory,
        executor=executor,
    )
    collected = await toolset.collect_resources()
    node = [{"id": "worker", "type": "llm", "instruction": "work"}]

    result = await toolset.create_agents(
        collection_id=collected["collection_id"],
        agents=[
            {"name": "healthy", "task": "one", "root_node": "worker", "nodes": node},
            {"name": "broken", "task": "two", "root_node": "worker", "nodes": node},
        ],
    )

    assert started == {"healthy", "broken"}
    assert [item["status"] for item in result["results"]] == [
        "completed",
        "failed",
    ]
    assert result["results"][1]["error"] == "boom"


@pytest.mark.asyncio
async def test_default_leaf_inherits_parent_model() -> None:
    observed = []

    async def executor(root, task, name):
        del task, name
        observed.append(root.model)
        return "ok"

    toolset = CreateAgentToolset(resource_sources=[], executor=executor)
    context = _context(
        parent_agent=SimpleNamespace(
            model="parent-model",
            model_api_key="parent-key",
        )
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
        tool_context=context,
    )

    assert result["results"][0]["status"] == "completed"
    assert observed == ["parent-model"]


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
    collected = await toolset.collect_resources()
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
    )

    assert result["results"][0]["status"] == "completed"
    assert calls == ["demo-skill"]
    assert observed_tools == [["SkillToolset"]]


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
        "veadk.tools.builtin_tools.create_agent.orchestrator._resolve_credentials",
        lambda context: CloudCredentials("ak", "sk", "sts"),
    )

    def leaf_factory(node, tools, workflow_member, parent_agent):
        del workflow_member, parent_agent
        return _ToolAwareAgent(name=node.id, mounted_tools=tools)

    async def executor(root, task, name):
        del task, name
        knowledge_tool = root.mounted_tools[0]
        result = await knowledge_tool.func("policy", 3)
        return result[0]["entries"][0]["content"]

    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource([resource])],
        leaf_factory=leaf_factory,
        knowledge_factory=lambda selected, credentials: Knowledge(),
        executor=executor,
    )
    collected = await toolset.collect_resources()

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
    )

    assert result["results"][0]["status"] == "completed"
    assert result["results"][0]["output"] == "policy:3"
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
        "veadk.tools.builtin_tools.create_agent.orchestrator._resolve_credentials",
        lambda context: CloudCredentials("ak", "sk"),
    )
    toolset = CreateAgentToolset(
        resource_sources=[_StaticSource(resources)],
        leaf_factory=_leaf_factory,
        knowledge_factory=knowledge_factory,
    )
    collected = await toolset.collect_resources()

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
