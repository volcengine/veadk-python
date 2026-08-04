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
"""Tests for frontend-selected skills and sub-agent routing."""

from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace

import pytest

from google.adk.models.llm_request import LlmRequest
from google.adk.skills import load_skill_from_dir
from google.adk.tools.function_tool import FunctionTool
from google.adk.tools.skill_toolset import SkillToolset

from veadk.cli.frontend_invocation import agent_skill_summaries
from veadk.cli.frontend_invocation import FrontendInvocationPlugin


def _tool() -> None:
    return None


def _context(
    *,
    agent_name: str,
    metadata: Mapping[str, object],
    parent_name: str = "",
) -> SimpleNamespace:
    parent = SimpleNamespace(name=parent_name) if parent_name else None
    agent = SimpleNamespace(name=agent_name, parent_agent=parent)
    return SimpleNamespace(
        agent_name=agent_name,
        run_config=SimpleNamespace(custom_metadata={"veadkInvocation": dict(metadata)}),
        _invocation_context=SimpleNamespace(agent=agent),
    )


def _request(*tool_names: str) -> LlmRequest:
    request = LlmRequest()
    request.tools_dict = {name: FunctionTool(_tool) for name in tool_names}
    return request


def test_agent_skill_summaries_supports_google_and_legacy_skills(
    tmp_path: Path,
) -> None:
    skill_dir = tmp_path / "review-code"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text(
        "---\nname: review-code\ndescription: Review code carefully.\n---\nDo it.\n",
        encoding="utf-8",
    )
    google_toolset = SkillToolset(skills=[load_skill_from_dir(skill_dir)])
    legacy_skill = SimpleNamespace(
        name="write-tests", description="Write focused tests."
    )
    agent = SimpleNamespace(
        tools=[google_toolset],
        skills_dict={"write-tests": legacy_skill},
    )

    assert agent_skill_summaries(agent) == [
        {"name": "review-code", "description": "Review code carefully."},
        {"name": "write-tests", "description": "Write focused tests."},
    ]


@pytest.mark.asyncio
async def test_slash_skill_forces_the_available_skill_tool() -> None:
    plugin = FrontendInvocationPlugin()
    request = _request("load_skill")
    context = _context(
        agent_name="root",
        metadata={"skills": [{"name": "review-code"}]},
    )

    await plugin.before_model_callback(
        callback_context=context,  # type: ignore[arg-type]
        llm_request=request,
    )

    instruction = str(request.config.system_instruction)
    assert "`review-code`" in instruction
    assert "`load_skill`" in instruction
    assert "MUST invoke" in instruction


@pytest.mark.asyncio
async def test_agent_mention_routes_one_tree_edge_at_a_time() -> None:
    plugin = FrontendInvocationPlugin()
    metadata = {
        "targetAgent": {
            "name": "writer",
            "path": ["root", "planner", "writer"],
        }
    }

    root_request = _request("transfer_to_agent")
    await plugin.before_model_callback(
        callback_context=_context(  # type: ignore[arg-type]
            agent_name="root", metadata=metadata
        ),
        llm_request=root_request,
    )
    assert "agent_name=`planner`" in str(root_request.config.system_instruction)

    planner_request = _request("transfer_to_agent")
    await plugin.before_model_callback(
        callback_context=_context(  # type: ignore[arg-type]
            agent_name="planner", metadata=metadata, parent_name="root"
        ),
        llm_request=planner_request,
    )
    assert "agent_name=`writer`" in str(planner_request.config.system_instruction)

    writer_request = _request("transfer_to_agent")
    await plugin.before_model_callback(
        callback_context=_context(  # type: ignore[arg-type]
            agent_name="writer", metadata=metadata, parent_name="planner"
        ),
        llm_request=writer_request,
    )
    assert writer_request.config.system_instruction is None


@pytest.mark.asyncio
async def test_target_skill_loads_only_after_reaching_the_target() -> None:
    plugin = FrontendInvocationPlugin()
    metadata = {
        "skills": [{"name": "writer-style"}],
        "targetAgent": {
            "name": "writer",
            "path": ["root", "planner", "writer"],
        },
    }

    root_request = _request("transfer_to_agent", "load_skill")
    await plugin.before_model_callback(
        callback_context=_context(  # type: ignore[arg-type]
            agent_name="root", metadata=metadata
        ),
        llm_request=root_request,
    )
    root_instruction = str(root_request.config.system_instruction)
    assert "agent_name=`planner`" in root_instruction
    assert "`writer-style`" not in root_instruction

    writer_request = _request("transfer_to_agent", "load_skill")
    await plugin.before_model_callback(
        callback_context=_context(  # type: ignore[arg-type]
            agent_name="writer", metadata=metadata, parent_name="planner"
        ),
        llm_request=writer_request,
    )
    writer_instruction = str(writer_request.config.system_instruction)
    assert "`writer-style`" in writer_instruction
    assert "`load_skill`" in writer_instruction


@pytest.mark.asyncio
async def test_agent_mention_routes_back_to_parent_from_another_branch() -> None:
    plugin = FrontendInvocationPlugin()
    request = _request("transfer_to_agent")
    context = _context(
        agent_name="researcher",
        parent_name="root",
        metadata={
            "targetAgent": {
                "name": "writer",
                "path": ["root", "writer"],
            }
        },
    )

    await plugin.before_model_callback(
        callback_context=context,  # type: ignore[arg-type]
        llm_request=request,
    )

    assert "agent_name=`root`" in str(request.config.system_instruction)


@pytest.mark.asyncio
async def test_agent_mention_rejects_a_repeating_path() -> None:
    plugin = FrontendInvocationPlugin()
    request = _request("transfer_to_agent")
    context = _context(
        agent_name="root",
        metadata={
            "targetAgent": {
                "name": "writer",
                "path": ["root", "root", "writer"],
            }
        },
    )

    await plugin.before_model_callback(
        callback_context=context,  # type: ignore[arg-type]
        llm_request=request,
    )

    assert request.config.system_instruction is None
