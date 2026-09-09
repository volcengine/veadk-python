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

"""Behavioral coverage for stable skill refresh and external-source composition."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from veadk.skills.runtime import SkillRuntime
from veadk.skills.skill import Skill


def remote(name="demo", version="v1", description="description"):
    return Skill(
        name=name,
        description=description,
        path=f"skills/s-demo/{version}/demo.zip",
        id="s-demo",
        version_id=version,
        skill_space_id="ss-one",
    )


def runtime(dynamic=True, **kwargs):
    agent = SimpleNamespace(
        skills=["ss-one"],
        instruction="Original instruction\nYou have the following skills: user text",
        enable_dynamic_load_skills=dynamic,
        skills_mode="local",
        tools=[object()],
        skills_transform=None,
        skill_tool_wrapper=None,
        skills_refresh_failure_policy="retain",
        _skills_with_checklist={},
        **kwargs,
    )
    rt = SkillRuntime(agent)
    return rt, agent


@pytest.mark.asyncio
async def test_no_change_or_reorder_keeps_prompt_and_toolset():
    rt, agent = runtime()
    values = [remote(), remote("other")]
    with patch(
        "veadk.skills.runtime.load_skills_from_cloud",
        side_effect=lambda *a, **k: values,
    ):
        rt.initialize()
        prompt, toolset = agent.instruction, rt.toolset
        values.reverse()
        await rt.prepare(None)
    assert agent.instruction == prompt
    assert rt.toolset is toolset
    assert agent.instruction.startswith(rt.base_instruction)


@pytest.mark.asyncio
async def test_version_change_updates_execution_without_prompt_churn():
    rt, agent = runtime()
    with patch("veadk.skills.runtime.load_skills_from_cloud", return_value=[remote()]):
        rt.initialize()
    prompt, toolset = agent.instruction, rt.toolset
    with patch(
        "veadk.skills.runtime.load_skills_from_cloud",
        return_value=[remote(version="v2")],
    ):
        await rt.prepare(None)
    assert agent.skills_dict["demo"].version_id == "v2"
    assert rt.toolset is not toolset
    assert agent.instruction == prompt


@pytest.mark.asyncio
async def test_external_results_survive_refresh_and_can_be_removed():
    rt, agent = runtime()
    extra = remote("explicit")
    extra.id = "s-explicit"
    agent.skills_transform = lambda skills, ctx: skills + [extra]
    with patch("veadk.skills.runtime.load_skills_from_cloud", return_value=[remote()]):
        rt.initialize()
        await rt.prepare(None)
        await rt.prepare(None)
        assert set(agent.skills_dict) == {"demo", "explicit"}
        agent.skills_transform = lambda skills, ctx: skills
        await rt.prepare(None)
        assert set(agent.skills_dict) == {"demo"}


@pytest.mark.asyncio
async def test_failure_retains_but_empty_success_removes_and_instances_are_independent():
    rt, agent = runtime()
    other, _ = runtime()
    with patch("veadk.skills.runtime.load_skills_from_cloud", return_value=[remote()]):
        rt.initialize()
    with patch(
        "veadk.skills.runtime.load_skills_from_cloud",
        side_effect=RuntimeError("private detail"),
    ):
        await rt.prepare(None)
    assert "demo" in agent.skills_dict
    assert rt.status()["issues"] == [{"source": "ss-one", "error": "RuntimeError"}]
    assert other.sources == {}
    with patch("veadk.skills.runtime.load_skills_from_cloud", return_value=[]):
        await rt.prepare(None)
    assert agent.skills_dict == {}
    assert agent.instruction == rt.base_instruction


@pytest.mark.asyncio
async def test_wrapper_failure_does_not_publish_partial_state():
    rt, agent = runtime()
    with patch("veadk.skills.runtime.load_skills_from_cloud", return_value=[remote()]):
        rt.initialize()
    old = agent.instruction, agent.skills_dict, rt.toolset
    agent.skill_tool_wrapper = lambda tool: (_ for _ in ()).throw(ValueError("wrapper"))
    with patch(
        "veadk.skills.runtime.load_skills_from_cloud",
        return_value=[remote(description="new")],
    ):
        with pytest.raises(ValueError, match="wrapper"):
            await rt.prepare(None)
    assert (agent.instruction, agent.skills_dict, rt.toolset) == old


@pytest.mark.asyncio
async def test_disabled_does_not_reload_sdk_sources():
    rt, agent = runtime(dynamic=False)
    with patch(
        "veadk.skills.runtime.load_skills_from_cloud", return_value=[remote()]
    ) as load:
        rt.initialize()
        await rt.prepare(None)
        assert load.call_count == 1


@pytest.mark.asyncio
async def test_local_change_and_deleted_file(tmp_path):
    root = tmp_path / "skills"
    skill = root / "local"
    skill.mkdir(parents=True)
    readme = skill / "SKILL.md"
    readme.write_text("---\nname: local\ndescription: first\n---\nbody\n")
    rt, agent = runtime()
    agent.skills = [str(root)]
    rt.initialize()
    readme.write_text("---\nname: local\ndescription: second\n---\nbody\n")
    await rt.prepare(None)
    assert "second" in agent.instruction
    readme.unlink()
    await rt.prepare(None)
    assert not agent.skills_dict


@pytest.mark.asyncio
async def test_agent_holds_lock_through_stream_and_releases_on_close():
    import asyncio
    from veadk import Agent
    from google.adk.agents import LlmAgent
    from google.adk.models.base_llm import BaseLlm

    class OfflineModel(BaseLlm):
        async def generate_content_async(self, llm_request, stream=False):
            raise AssertionError("model should not run in lifecycle test")
            yield

    agent = Agent(
        name="lifecycle",
        model=OfflineModel(model="offline"),
        model_api_key="offline-test",
        skills_mode="local",
        enable_dynamic_load_skills=True,
    )
    entered = []
    closed = []

    async def events(self, context):
        entered.append(context)
        try:
            yield context
            await asyncio.Event().wait()
        finally:
            closed.append(context)

    with patch.object(LlmAgent, "run_async", events):
        first = agent.run_async("first")
        assert await anext(first) == "first"
        second = agent.run_async("second")
        pending = asyncio.create_task(anext(second))
        await asyncio.sleep(0)
        assert entered == ["first"]
        await first.aclose()
        assert await asyncio.wait_for(pending, 2) == "second"
        await second.aclose()
    assert closed == ["first", "second"]
    assert not agent._skill_runtime.lock.locked()
