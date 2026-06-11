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

"""Unit tests for veadk.runtime.base_runtime."""

import inspect
from types import SimpleNamespace
from typing import Any, AsyncGenerator

import pytest

from veadk.runtime.base_runtime import BaseRuntime, build_system_append


def _agent(name: str = "", description: str = "", instruction: Any = "") -> Any:
    """A minimal duck-typed stand-in for veadk.agent.Agent."""
    return SimpleNamespace(name=name, description=description, instruction=instruction)


class TestBuildSystemAppend:
    def test_combines_name_description_instruction_in_order(self):
        agent = _agent(
            name="helper",
            description="A helpful agent.",
            instruction="Always be concise.",
        )
        result = build_system_append(agent)
        assert result == (
            "Your name is helper.\n\nA helpful agent.\n\nAlways be concise."
        )

    def test_empty_agent_returns_empty_string(self):
        assert build_system_append(_agent()) == ""

    def test_only_name(self):
        assert build_system_append(_agent(name="bot")) == "Your name is bot."

    def test_blank_instruction_is_skipped(self):
        # Whitespace-only instruction must not produce a trailing block.
        agent = _agent(name="bot", instruction="   ")
        assert build_system_append(agent) == "Your name is bot."

    def test_callable_instruction_is_skipped(self):
        # An InstructionProvider (non-str) needs a context to resolve, so it is
        # dropped rather than stringified.
        def provider(_ctx):
            return "resolved"

        agent = _agent(name="bot", instruction=provider)
        assert build_system_append(agent) == "Your name is bot."

    def test_description_only(self):
        assert build_system_append(_agent(description="Does things.")) == "Does things."


class TestBaseRuntimeContract:
    def test_is_abstract_cannot_instantiate(self):
        with pytest.raises(TypeError):
            BaseRuntime()  # type: ignore[abstract]

    def test_default_name_is_base(self):
        assert BaseRuntime.name == "base"

    def test_run_async_is_abstract(self):
        assert getattr(BaseRuntime.run_async, "__isabstractmethod__", False)

    def test_run_async_signature(self):
        sig = inspect.signature(BaseRuntime.run_async)
        assert list(sig.parameters) == ["self", "agent", "ctx"]

    def test_subclass_must_implement_run_async(self):
        class Incomplete(BaseRuntime):
            pass

        with pytest.raises(TypeError):
            Incomplete()  # type: ignore[abstract]

    @pytest.mark.asyncio
    async def test_concrete_subclass_streams_events(self):
        sentinel = object()

        class Concrete(BaseRuntime):
            name = "concrete"

            async def run_async(self, agent, ctx) -> AsyncGenerator:  # type: ignore[override]
                yield sentinel

        runtime = Concrete()
        ctx: Any = object()
        collected = [e async for e in runtime.run_async(_agent(), ctx)]
        assert collected == [sentinel]
        assert runtime.name == "concrete"
