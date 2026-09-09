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

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from veadk import Agent
from veadk.skills import check_skills_callback as refresh
from veadk.skills.skill import Skill


def remote(name="demo", version="v1", description="same"):
    return Skill(
        name=name,
        description=description,
        path=f"{version}.zip",
        skill_space_id="ss-one",
        id="s-demo",
        version_id=version,
    )


def make_agent(sources=None, instruction="User instruction", dynamic=True):
    return Agent(
        name="test",
        skills=["ss-one"] if sources is None else sources,
        skills_mode="local",
        enable_dynamic_load_skills=dynamic,
        instruction=instruction,
        model_api_key="offline-test",
    )


async def turn(agent):
    await refresh.check_skills(
        SimpleNamespace(_invocation_context=SimpleNamespace(agent=agent))
    )


@pytest.mark.asyncio
async def test_package_change_on_first_callback_keeps_prompt_and_callbacks():
    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        agent = make_agent()
    prompt = agent.instruction
    toolset = agent.tools[-1]
    previous = toolset._tools["skills"]
    agent.instruction += "\nOther callback suffix"
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote(version="v2")]
    ):
        await turn(agent)
    assert agent.instruction == prompt + "\nOther callback suffix"
    assert agent.skills_dict["demo"].path == "v2.zip"
    assert toolset._tools["skills"] is not previous
    assert agent.before_agent_callback is refresh.check_skills


@pytest.mark.asyncio
async def test_agents_have_independent_baselines_and_reorder_is_stable():
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote(), remote("other")]
    ):
        one, two = make_agent(), make_agent()
    prompt = one.instruction
    original = one.tools[-1]._tools
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote("other"), remote()]
    ):
        await turn(one)
    assert one.tools[-1]._tools is original
    assert one.instruction == prompt
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote(version="v2")]
    ):
        await turn(one)
        await turn(two)
    assert one.skills_dict == two.skills_dict


@pytest.mark.asyncio
async def test_failure_retains_successful_empty_and_removed_sources_delete():
    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        agent = make_agent()
    with patch.object(
        refresh, "load_skills_from_cloud", side_effect=RuntimeError("offline")
    ):
        await turn(agent)
    assert "demo" in agent.skills_dict
    assert agent.tools[-1].status()["issues"]
    with patch.object(refresh, "load_skills_from_cloud", return_value=[]):
        await turn(agent)
    assert agent.skills_dict == {}
    assert agent.instruction == "User instruction"
    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        await turn(agent)
    agent.skills = []
    with patch.object(refresh, "load_skills_from_cloud") as load:
        await turn(agent)
    load.assert_not_called()
    assert agent.skills_dict == {}


@pytest.mark.asyncio
async def test_failed_removed_source_does_not_reappear_and_same_name_falls_back():
    with patch.object(
        refresh,
        "load_skills_from_cloud",
        side_effect=lambda source, **kw: [remote(version=source)],
    ):
        agent = make_agent(["ss-one", "ss-two"])
        assert agent.skills_dict["demo"].path == "ss-two.zip"
        agent.skills = ["ss-one"]
        await turn(agent)
    assert agent.skills_dict["demo"].path == "ss-one.zip"
    agent.skills = ["ss-three"]
    with patch.object(refresh, "load_skills_from_cloud", side_effect=RuntimeError):
        await turn(agent)
    assert not agent.skills_dict


@pytest.mark.asyncio
async def test_local_content_and_same_content_source_replacement(tmp_path):
    roots = [tmp_path / "one", tmp_path / "two"]
    for root in roots:
        (root / "demo").mkdir(parents=True)
        (root / "demo/SKILL.md").write_text(
            "---\nname: demo\ndescription: same\n---\nfirst"
        )
    agent = make_agent([str(roots[0])])
    prompt = agent.instruction
    old_tools = agent.tools[-1]._tools
    (roots[0] / "demo/SKILL.md").write_text(
        "---\nname: demo\ndescription: same\n---\nsecond"
    )
    await turn(agent)
    assert agent.tools[-1]._tools is not old_tools
    assert agent.instruction == prompt
    agent.skills = [str(roots[1])]
    await turn(agent)
    assert agent.skills_dict["demo"].path == str(roots[1] / "demo")
    assert agent.instruction == prompt


@pytest.mark.asyncio
async def test_empty_initial_sources_can_gain_skills_and_disabled_does_not_reload():
    agent = make_agent([])
    agent.skills = ["ss-one"]
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote()]
    ) as load:
        await turn(agent)
        assert load.call_count == 1
    assert "demo" in agent.skills_dict
    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        disabled = make_agent(dynamic=False)
    with patch.object(refresh, "load_skills_from_cloud") as load:
        await turn(disabled)
    load.assert_not_called()


@pytest.mark.asyncio
async def test_description_refresh_preserves_user_text_and_checklist_identity():
    base = "User text: You have the following skills: keep all this"
    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        agent = make_agent(instruction=base)
    checklist = agent._skills_with_checklist
    agent.instruction += "\nOther callback suffix"
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote(description="updated")]
    ):
        await turn(agent)
    assert agent.instruction.startswith(base)
    assert agent.instruction.endswith("\nOther callback suffix")
    assert "description: updated" in agent.instruction
    assert agent._skills_with_checklist is checklist
    assert checklist["demo"].description == "updated"


@pytest.mark.asyncio
async def test_callable_instruction_and_failed_candidate():
    async def base(context):
        return "Callable base"

    with patch.object(refresh, "load_skills_from_cloud", return_value=[remote()]):
        agent = make_agent(instruction=base)
    old = agent.instruction
    with patch.object(
        refresh, "load_skills_from_cloud", return_value=[remote(version="v2")]
    ):
        await turn(agent)
    assert agent.instruction is old
    assert (await agent.instruction(None)).startswith("Callable base")
    toolset = agent.tools[-1]
    tools = toolset._tools
    with (
        patch.object(
            refresh, "load_skills_from_cloud", return_value=[remote(description="new")]
        ),
        patch.object(toolset, "build_tools", side_effect=RuntimeError),
    ):
        await turn(agent)
    assert toolset._tools is tools
    assert agent.instruction is old
    assert agent.skills_dict["demo"].description == "same"


def test_agent_has_no_new_runtime_or_callable_parameters():
    assert (
        not {"skills_transform", "skill_tool_wrapper", "skills_refresh_failure_policy"}
        & Agent.model_fields.keys()
    )
    assert "run_async" not in Agent.__dict__
    assert "_skill_runtime" not in Agent.__private_attributes__


@pytest.mark.asyncio
async def test_source_switch_changes_actual_local_tool_output(tmp_path):
    from veadk.tools.skills_tools.skills_tool import SkillsTool

    for version in ("v1", "v2"):
        root = tmp_path / version / "demo"
        root.mkdir(parents=True)
        (root / "SKILL.md").write_text(
            f"---\nname: demo\ndescription: same\n---\n{version}"
        )
    session = tmp_path / "session"
    (session / "skills").mkdir(parents=True)
    agent = make_agent([str(tmp_path / "v1")])
    context = SimpleNamespace(session=SimpleNamespace(id="test"))
    with patch(
        "veadk.tools.skills_tools.skills_tool.get_session_path", return_value=session
    ):
        assert "v1" in SkillsTool(agent.skills_dict)._invoke_skill("demo", context)
        agent.skills = [str(tmp_path / "v2")]
        await turn(agent)
        assert "v2" in agent.tools[-1]._tools["skills"]._invoke_skill("demo", context)
    assert (session / "skills/demo").resolve() == tmp_path / "v2/demo"
    assert not list(session.glob(".skill-link-*"))
