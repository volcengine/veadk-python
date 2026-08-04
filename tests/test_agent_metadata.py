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
"""Tests for JSON-safe agent metadata summaries."""

from __future__ import annotations

from types import SimpleNamespace

from google.adk.tools.base_toolset import BaseToolset

from veadk.agent_metadata import agent_component_summaries, agent_search_sources


class _SearchToolset(BaseToolset):
    async def get_tools(self, readonly_context=None):
        del readonly_context
        return []


class SkillsToolset(BaseToolset):
    async def get_tools(self, readonly_context=None):
        del readonly_context
        return []


def test_agent_component_summaries_recognizes_supported_components() -> None:
    agent = SimpleNamespace(
        knowledgebase=SimpleNamespace(
            name="user_knowledgebase",
            index="product-docs",
        ),
        short_term_memory=SimpleNamespace(backend="local"),
        long_term_memory=None,
        prompt_manager=SimpleNamespace(name="prompt-hub"),
        example_store=None,
        run_processor=SimpleNamespace(name="authz"),
        tracers=[SimpleNamespace(name="apm")],
        tools=[
            SimpleNamespace(name="ordinary-tool"),
            _SearchToolset(),
            SkillsToolset(),
        ],
        plugins=[SimpleNamespace(name="audit")],
    )

    assert agent_component_summaries(agent) == [
        {
            "kind": "knowledgebase",
            "name": "product-docs",
            "source": "knowledgebase",
        },
        {
            "kind": "memory",
            "name": "SimpleNamespace",
            "source": "short_term_memory",
            "backend": "local",
        },
        {
            "kind": "prompt_manager",
            "name": "prompt-hub",
            "source": "prompt_manager",
        },
        {"kind": "run_processor", "name": "authz"},
        {"kind": "tracer", "name": "apm"},
        {"kind": "toolset", "name": "_SearchToolset"},
        {"kind": "plugin", "name": "audit"},
    ]


def test_agent_component_summaries_ignores_default_processor_and_deduplicates() -> None:
    class NoOpRunProcessor:
        pass

    shared_plugin = SimpleNamespace(name="audit")
    agent = SimpleNamespace(
        run_processor=NoOpRunProcessor(),
        tools=[],
        tracers=[],
        plugins=[shared_plugin, shared_plugin],
    )

    assert agent_component_summaries(agent) == [{"kind": "plugin", "name": "audit"}]


def test_agent_search_sources_excludes_short_term_memory() -> None:
    def web_search() -> None:
        pass

    agent = SimpleNamespace(
        tools=[web_search],
        knowledgebase=SimpleNamespace(index="product-docs"),
        short_term_memory=SimpleNamespace(backend="local"),
        long_term_memory=SimpleNamespace(backend="viking"),
    )

    assert agent_search_sources(agent) == ["web", "knowledge", "memory"]
    assert (
        agent_search_sources(
            SimpleNamespace(short_term_memory=SimpleNamespace(backend="local"))
        )
        == []
    )
