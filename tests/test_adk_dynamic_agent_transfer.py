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

"""Exercise transfer routing through the real Runner without a cloud model."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from types import SimpleNamespace

import pytest
from google.adk.agents import BaseAgent
from google.adk.events import Event
from google.adk.models.base_llm import BaseLlm
from google.adk.models.llm_response import LlmResponse
from google.adk.runners import InMemoryRunner
from google.adk.workflow import _dynamic_node_scheduler
from google.genai import types
from packaging.version import Version

from veadk import Agent
from veadk.tools.builtin_tools.create_agent import CreateAgentToolset
from veadk.utils.adk_compat import get_adk_version
from veadk.utils.patches import patch_adk_dynamic_agent_transfer

if get_adk_version() >= Version("2.8.0"):
    from google.adk.workflow.utils import _transfer_utils
else:
    _transfer_utils = None


class _RoutingModel(BaseLlm):
    targets: list[str]
    calls: int = 0

    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del llm_request, stream
        index = self.calls
        self.calls += 1
        if index < len(self.targets):
            part = types.Part(
                function_call=types.FunctionCall(
                    id=f"transfer-{self.model}-{index}",
                    name="transfer_to_agent",
                    args={"agent_name": self.targets[index]},
                )
            )
        else:
            part = types.Part(text=f"done:{self.model}")
        yield LlmResponse(content=types.ModelContent(parts=[part]))


def _agent(name: str, targets: list[str], children: list[BaseAgent] | None = None):
    return Agent(
        name=name,
        model=_RoutingModel(model=name, targets=targets),
        model_api_key="test-key",
        sub_agents=children or [],
    )


async def _run(runner: InMemoryRunner, session_id: str) -> list[Event]:
    await runner.session_service.create_session(
        app_name=runner.app_name, user_id="test-user", session_id=session_id
    )
    return [
        event
        async for event in runner.run_async(
            user_id="test-user",
            session_id=session_id,
            new_message=types.UserContent(parts=[types.Part(text=session_id)]),
        )
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ["child", "parent", "sibling"])
async def test_runner_preserves_static_agent_transfer_routes(route: str) -> None:
    first_targets = {"child": [], "parent": ["main"], "sibling": ["second"]}[route]
    first = _agent("first", first_targets)
    children = [first]
    if route == "sibling":
        children.append(_agent("second", []))
    main = _agent("main", ["first"], children)
    runner = InMemoryRunner(agent=main, app_name="static-transfers")

    events = await _run(runner, f"static-{route}")

    expected_target = {"child": "first", "parent": "main", "sibling": "second"}[route]
    assert any(
        event.author == expected_target
        and event.content
        and any(
            part.text == f"done:{expected_target}"
            for part in (event.content.parts or [])
        )
        for event in events
    )
    assert [child.name for child in main.sub_agents] == [
        child.name for child in children
    ]
    assert all(child.parent_agent is main for child in children)


class _DynamicModel(BaseLlm):
    async def generate_content_async(
        self, llm_request, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        del stream
        await asyncio.sleep(0)
        collection = next(
            (
                part.function_response.response["collection_id"]
                for content in reversed(llm_request.contents or [])
                for part in (content.parts or [])
                if part.function_response
                and part.function_response.name == "collect_resources"
            ),
            None,
        )
        if collection is None:
            call = types.FunctionCall(id="collect", name="collect_resources", args={})
        else:
            call = types.FunctionCall(
                id="create",
                name="create_agents",
                args={
                    "collection_id": collection,
                    "handoff_to": "specialist",
                    "agents": [
                        {
                            "name": "specialist",
                            "task": "work",
                            "root_node": "worker",
                            "nodes": [
                                {"id": "worker", "type": "llm", "instruction": "work"}
                            ],
                        }
                    ],
                },
            )
        yield LlmResponse(
            content=types.ModelContent(parts=[types.Part(function_call=call)])
        )


class _TextAgent(BaseAgent):
    async def _run_async_impl(self, ctx):
        del ctx
        yield Event(
            author=self.name,
            content=types.ModelContent(parts=[types.Part(text=self.name)]),
        )


def _leaf_factory(node, tools, workflow_member, parent_agent):
    del tools, workflow_member, parent_agent
    return _TextAgent(name=node.id)


def test_transfer_patch_is_idempotent_or_noop_on_older_adk() -> None:
    before = getattr(_transfer_utils, "resolve_and_derive_transfer_context", None)
    patch_adk_dynamic_agent_transfer()
    patch_adk_dynamic_agent_transfer()
    assert (
        getattr(_transfer_utils, "resolve_and_derive_transfer_context", None) is before
    )
    if hasattr(_dynamic_node_scheduler, "resolve_and_derive_transfer_context"):
        assert _dynamic_node_scheduler.resolve_and_derive_transfer_context is before


@pytest.mark.skipif(
    get_adk_version() < Version("2.9.0"),
    reason="Native parent and peer transfer restrictions were added in ADK 2.9",
)
@pytest.mark.parametrize("target", ["main", "second"])
def test_executing_clone_keeps_parent_and_peer_transfer_restrictions(
    target: str,
) -> None:
    main = _agent("main", [], [_agent("first", []), _agent("second", [])])
    template = main.sub_agents[0]
    runtime_root = main.clone()
    active = runtime_root.sub_agents[0]
    active.disallow_transfer_to_parent = True
    active.disallow_transfer_to_peers = True

    with pytest.raises(ValueError, match="disallow_transfer_to_"):
        _transfer_utils.resolve_and_derive_transfer_context(
            target_name=target,
            current_agent=template,
            root_agent=main,
            curr_ctx=SimpleNamespace(node=active),
            curr_parent_ctx=None,
        )


@pytest.mark.asyncio
@pytest.mark.skipif(
    _transfer_utils is None,
    reason="ADK 2.7 does not clone chat agents through the workflow scheduler",
)
async def test_concurrent_dynamic_transfers_keep_agents_off_shared_root() -> None:
    toolset = CreateAgentToolset(resource_sources=[], leaf_factory=_leaf_factory)
    main = Agent(
        name="main",
        model=_DynamicModel(model="dynamic"),
        model_api_key="test-key",
        tools=[toolset],
    )
    initial_children = tuple(main.sub_agents)
    runner = InMemoryRunner(agent=main, app_name="isolated-dynamic-transfers")
    try:
        runs = await asyncio.gather(
            _run(runner, "session-one"), _run(runner, "session-two")
        )
        targets = []
        parents = []
        for events in runs:
            target = next(
                event.actions.transfer_to_agent
                for event in events
                if event.actions.transfer_to_agent
            )
            targets.append(target)
            assert any(
                event.author == target
                and event.content
                and any(part.text == target for part in (event.content.parts or []))
                for event in events
            )
            parent, _, _ = toolset._registrations[target]
            parents.append(parent)
            assert parent is not main
            assert [
                child.name
                for child in parent.sub_agents
                if child.name.startswith("specialist__")
            ] == [target]
        assert targets[0] != targets[1]
        assert parents[0] is not parents[1]
        assert tuple(main.sub_agents) == initial_children
        for events, other_target in zip(runs, reversed(targets), strict=True):
            assert all(event.author != other_target for event in events)
    finally:
        await toolset.close()
    assert toolset._registrations == {}
