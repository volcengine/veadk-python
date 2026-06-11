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

"""Behavior tests for ``veadk.agent.Agent``.

These exercise the ``model_post_init`` wiring branches and helper methods that
are not covered by ``tests/test_agent.py`` (signatures/defaults) or the contract
tests: prompt-manager instruction binding, skills injection, knowledgebase
profile tool, long-term-memory + auto-save callbacks, authz callback wiring,
ghostchar/tunnel/dataset-gen tools, tool-dependency validation, tracer
preparation, llm-flow selection, runtime dispatch and ``update_model``.

All external/model dependencies are mocked; no network or real LLM calls.
"""

import os
from unittest.mock import Mock, PropertyMock, patch

import pytest

from veadk import Agent
from veadk.processors import NoOpRunProcessor

_ENV = {"MODEL_AGENT_API_KEY": "mock_api_key"}


@patch.dict(os.environ, _ENV)
def test_default_run_processor_is_noop():
    agent = Agent()
    assert isinstance(agent.run_processor, NoOpRunProcessor)


@patch.dict(os.environ, _ENV)
def test_enable_responses_uses_ark_llm():
    mock_ark = Mock()
    with patch("veadk.models.ark_llm.ArkLlm", return_value=mock_ark) as mock_cls:
        agent = Agent(enable_responses=True)
    mock_cls.assert_called_once()
    assert agent.model is mock_ark


@patch.dict(os.environ, _ENV)
@patch("veadk.agent.LiteLlm")
def test_model_name_list_sets_primary_and_fallbacks(mock_lite_llm):
    Agent(
        model_name=["primary", "second", "third"],
        model_provider="prov",
    )
    _, kwargs = mock_lite_llm.call_args
    assert kwargs["model"] == "prov/primary"
    assert kwargs["fallbacks"] == ["prov/second", "prov/third"]


@patch.dict(os.environ, _ENV)
@patch("veadk.agent.LiteLlm")
def test_empty_model_name_list_falls_back_to_settings(mock_lite_llm):
    with patch("veadk.agent.settings.model.name", new="settings-model"):
        Agent(model_name=[], model_provider="prov")
    _, kwargs = mock_lite_llm.call_args
    assert kwargs["model"] == "prov/settings-model"
    assert kwargs["fallbacks"] is None


@patch.dict(os.environ, _ENV)
def test_prompt_manager_binds_instruction():
    from veadk.prompts.prompt_manager import BasePromptManager

    class _PM(BasePromptManager):
        def get_prompt(self, *args, **kwargs):
            return "managed prompt"

    prompt_manager = _PM()
    agent = Agent(prompt_manager=prompt_manager)
    # instruction is bound to the prompt manager's get_prompt callable.
    assert agent.instruction == prompt_manager.get_prompt
    assert callable(agent.instruction)
    assert agent.instruction() == "managed prompt"  # type: ignore[operator]


@patch.dict(os.environ, _ENV)
def test_knowledgebase_profile_adds_both_tools():
    from veadk.knowledgebase import KnowledgeBase

    kb = KnowledgeBase(index="test_index", backend="local")
    kb.enable_profile = True

    load_kb_tool = Mock()
    kb_queries = Mock()
    with (
        patch(
            "veadk.tools.builtin_tools.load_knowledgebase.LoadKnowledgebaseTool",
            return_value=load_kb_tool,
        ),
        patch(
            "veadk.tools.builtin_tools.load_kb_queries.load_kb_queries",
            new=kb_queries,
        ),
    ):
        agent = Agent(knowledgebase=kb)

    assert load_kb_tool in agent.tools
    assert kb_queries in agent.tools


@patch.dict(os.environ, _ENV)
def test_knowledgebase_without_profile_adds_single_tool():
    from veadk.knowledgebase import KnowledgeBase

    kb = KnowledgeBase(index="test_index", backend="local")
    kb.enable_profile = False

    load_kb_tool = Mock()
    with patch(
        "veadk.tools.builtin_tools.load_knowledgebase.LoadKnowledgebaseTool",
        return_value=load_kb_tool,
    ):
        agent = Agent(knowledgebase=kb)

    assert load_kb_tool in agent.tools


@patch.dict(os.environ, _ENV)
def test_long_term_memory_wires_load_memory_backend():
    from google.adk.tools import load_memory

    from veadk.memory.long_term_memory import LongTermMemory

    ltm = LongTermMemory(backend="local")
    agent = Agent(long_term_memory=ltm)

    assert load_memory in agent.tools
    metadata = getattr(load_memory, "custom_metadata", None)
    if metadata is not None:
        assert metadata["backend"] == "local"


@patch.dict(os.environ, _ENV)
def test_enable_authz_sets_callback_when_none():
    from veadk.tools.builtin_tools.agent_authorization import (
        check_agent_authorization,
    )

    agent = Agent(enable_authz=True)
    assert agent.before_agent_callback is check_agent_authorization


@patch.dict(os.environ, _ENV)
def test_enable_authz_appends_to_existing_list_callback():
    from veadk.tools.builtin_tools.agent_authorization import (
        check_agent_authorization,
    )

    existing = Mock()
    agent = Agent(enable_authz=True, before_agent_callback=[existing])
    assert isinstance(agent.before_agent_callback, list)
    assert existing in agent.before_agent_callback
    assert check_agent_authorization in agent.before_agent_callback


@patch.dict(os.environ, _ENV)
def test_enable_authz_promotes_single_callback_to_list():
    from veadk.tools.builtin_tools.agent_authorization import (
        check_agent_authorization,
    )

    def existing(*args, **kwargs):
        return None

    agent = Agent(enable_authz=True, before_agent_callback=existing)
    assert isinstance(agent.before_agent_callback, list)
    assert existing in agent.before_agent_callback
    assert check_agent_authorization in agent.before_agent_callback


@patch.dict(os.environ, _ENV)
def test_auto_save_session_without_ltm_warns_no_callback():
    agent = Agent(auto_save_session=True)
    # long_term_memory missing -> no after_agent_callback installed
    assert agent.after_agent_callback is None


@patch.dict(os.environ, _ENV)
def test_auto_save_session_installs_after_callback():
    from veadk.memory.save_session_callback import (
        save_session_to_long_term_memory,
    )

    from veadk.memory.long_term_memory import LongTermMemory

    ltm = LongTermMemory(backend="local")
    agent = Agent(auto_save_session=True, long_term_memory=ltm)
    assert agent.after_agent_callback is save_session_to_long_term_memory


@patch.dict(os.environ, _ENV)
def test_example_store_appends_example_tool():
    from google.adk.examples.base_example_provider import BaseExampleProvider

    class _Store(BaseExampleProvider):
        def get_examples(self, query):
            return []

    store = _Store()
    agent = Agent(example_store=store)
    from google.adk.tools.example_tool import ExampleTool

    assert any(isinstance(t, ExampleTool) for t in agent.tools)


@patch.dict(os.environ, _ENV)
def test_enable_ghostchar_appends_tool_and_instruction():
    agent = Agent(enable_ghostchar=True)
    from veadk.tools.ghost_char import GhostcharTool

    assert any(isinstance(t, GhostcharTool) for t in agent.tools)
    assert "character" in agent.instruction  # type: ignore[operator]


@patch.dict(os.environ, _ENV)
def test_enable_tunnel_appends_toolset():
    tunnel_toolset = Mock()
    with patch("veadk.tunnel.TunnelToolset", return_value=tunnel_toolset) as mock_cls:
        agent = Agent(enable_tunnel=True, name="tunnel_agent")
    mock_cls.assert_called_once_with(agent_name="tunnel_agent")
    assert tunnel_toolset in agent.tools


@patch.dict(os.environ, _ENV)
def test_enable_a2ui_appends_toolset():
    toolset = Mock()
    with patch("veadk.a2ui.build_a2ui_toolset", return_value=toolset) as mock_build:
        agent = Agent(enable_a2ui=True)
    mock_build.assert_called_once()
    assert toolset in agent.tools


@patch.dict(os.environ, _ENV)
def test_enable_dataset_gen_installs_after_callback():
    from veadk.toolkits.dataset_auto_gen_callback import (
        dataset_auto_gen_callback,
    )

    agent = Agent(enable_dataset_gen=True)
    assert agent.after_agent_callback is dataset_auto_gen_callback


@patch.dict(os.environ, _ENV)
def test_video_generate_pulls_in_task_query():
    video_generate = Mock()
    video_generate.__name__ = "video_generate"
    video_task_query = Mock()
    video_task_query.__name__ = "video_task_query"

    with patch(
        "veadk.tools.builtin_tools.video_generate.video_task_query",
        new=video_task_query,
    ):
        agent = Agent(tools=[video_generate])

    assert video_task_query in agent.tools


@patch.dict(os.environ, _ENV)
def test_video_task_query_pulls_in_generate():
    video_task_query = Mock()
    video_task_query.__name__ = "video_task_query"
    video_generate = Mock()
    video_generate.__name__ = "video_generate"

    with patch(
        "veadk.tools.builtin_tools.video_generate.video_generate",
        new=video_generate,
    ):
        agent = Agent(tools=[video_task_query])

    assert video_generate in agent.tools


@patch.dict(os.environ, _ENV)
def test_update_model_copies_with_new_model_string():
    agent = Agent(model_provider="prov")
    fake_model = Mock()
    new_model = Mock()
    fake_model.model_copy.return_value = new_model
    agent.model = fake_model

    agent.update_model("new-model")

    fake_model.model_copy.assert_called_once_with(update={"model": "prov/new-model"})
    assert agent.model is new_model


# ---------------------------------------------------------------------------
# Tracer preparation
# ---------------------------------------------------------------------------


@patch.dict(os.environ, {**_ENV, "ENABLE_APMPLUS": "true"})
def test_prepare_tracers_appends_apmplus_exporter():
    from veadk.tracing.telemetry.exporters.apmplus_exporter import (
        APMPlusExporter,
    )

    # A real (no-network) subclass so the ``isinstance`` dedupe check in
    # ``_prepare_tracers`` still works while avoiding the real constructor's
    # token fetch.
    class _FakeAPMPlus(APMPlusExporter):
        def __init__(self):  # noqa: D401 - test stub, skip real init
            pass

    with (
        patch(
            "veadk.tracing.telemetry.exporters.apmplus_exporter.APMPlusExporter",
            new=_FakeAPMPlus,
        ),
        patch(
            "veadk.tracing.telemetry.telemetry.init_global_meter_uploader_from_exporters"
        ) as mock_init,
    ):
        agent = Agent()

    # A default OpentelemetryTracer is created and the APMPlus exporter appended.
    assert agent.tracers
    exporters = agent.tracers[0].exporters  # type: ignore[attr-defined]
    assert any(isinstance(e, _FakeAPMPlus) for e in exporters)
    mock_init.assert_called()


@patch.dict(os.environ, _ENV)
def test_prepare_tracers_noop_without_env():
    agent = Agent()
    # No exporter env flags -> no tracer auto-created.
    assert agent.tracers == []


# ---------------------------------------------------------------------------
# Skills injection
# ---------------------------------------------------------------------------


def _make_skill(name, description="d", checklist=None):
    skill = Mock()
    skill.name = name
    skill.description = description
    skill.checklist = checklist
    return skill


@patch.dict(os.environ, _ENV)
def test_load_skills_local_mode_builds_instruction_and_toolset():
    skill = _make_skill("alpha", "does alpha")
    toolset = Mock()

    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch(
            "veadk.tools.skills_tools.skills_toolset.SkillsToolset",
            return_value=toolset,
        ) as mock_toolset,
    ):
        agent = Agent(skills=["alpha"], skills_mode="local")

    assert agent.skills_mode == "local"
    assert "You have the following skills" in agent.instruction  # type: ignore[operator]
    assert "alpha" in agent.instruction  # type: ignore[operator]
    assert "skills_tool" in agent.instruction  # type: ignore[operator]
    mock_toolset.assert_called_once()
    assert toolset in agent.tools


@patch.dict(os.environ, _ENV)
def test_load_skills_default_mode_is_local_without_tool_id():
    skill = _make_skill("beta")
    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch("veadk.tools.skills_tools.skills_toolset.SkillsToolset"),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("AGENTKIT_TOOL_ID", None)
        agent = Agent(skills=["beta"])
    assert agent.skills_mode == "local"


@patch.dict(os.environ, _ENV)
def test_load_skills_sandbox_mode_instruction_mentions_execute_skills():
    skill = _make_skill("gamma")
    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch("veadk.tools.skills_tools.skills_toolset.SkillsToolset"),
    ):
        agent = Agent(skills=["gamma"], skills_mode="skills_sandbox")
    assert "execute_skills" in agent.instruction  # type: ignore[operator]


@patch.dict(os.environ, _ENV)
def test_load_skills_checklist_instruction_and_callback():
    skill = _make_skill("delta", checklist=["step1"])
    init_callback = Mock()
    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch("veadk.tools.skills_tools.skills_toolset.SkillsToolset"),
        patch(
            "veadk.skills.utils.create_init_skill_check_list_callback",
            return_value=init_callback,
        ),
    ):
        agent = Agent(
            skills=["delta"],
            skills_mode="local",
            enable_skills_checklist=True,
        )
    assert "checklist" in agent.instruction  # type: ignore[operator]
    assert agent.before_tool_callback is init_callback


@patch.dict(os.environ, _ENV)
def test_load_skills_invalid_mode_raises():
    # ``skills_mode`` is a Literal on the model, so an invalid value can only be
    # forced post-construction; ``load_skills`` then rejects it.
    skill = _make_skill("eps")
    agent = Agent()
    object.__setattr__(agent, "skills", ["eps"])
    object.__setattr__(agent, "skills_mode", "bogus")
    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch("veadk.tools.skills_tools.skills_toolset.SkillsToolset"),
        pytest.raises(ValueError, match="Unsupported skill mode"),
    ):
        agent.load_skills()


@patch.dict(os.environ, _ENV)
def test_load_skills_dynamic_load_installs_before_agent_callback():
    skill = _make_skill("zeta")
    check_skills = Mock()
    with (
        patch("veadk.skills.utils.load_skills_from_cloud", return_value=[skill]),
        patch("veadk.tools.skills_tools.skills_toolset.SkillsToolset"),
        patch("veadk.skills.check_skills_callback.check_skills", new=check_skills),
    ):
        agent = Agent(
            skills=["zeta"],
            skills_mode="local",
            enable_dynamic_load_skills=True,
        )
    assert agent.before_agent_callback is check_skills


@patch.dict(os.environ, _ENV)
def test_load_skills_skips_empty_skill_entries():
    toolset = Mock()
    with patch(
        "veadk.tools.skills_tools.skills_toolset.SkillsToolset",
        return_value=toolset,
    ):
        agent = Agent(skills=["", "   "], skills_mode="local")
    # No skills loaded -> instruction unchanged, but toolset still appended.
    assert toolset in agent.tools


# ---------------------------------------------------------------------------
# _llm_flow selection
# ---------------------------------------------------------------------------


@patch.dict(os.environ, _ENV)
def test_llm_flow_single_flow_when_transfers_disallowed():
    from google.adk.flows.llm_flows.single_flow import SingleFlow

    agent = Agent(
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
    )
    assert isinstance(agent._llm_flow, SingleFlow)


@patch.dict(os.environ, _ENV)
def test_llm_flow_auto_flow_by_default():
    from google.adk.flows.llm_flows.auto_flow import AutoFlow

    agent = Agent()
    assert isinstance(agent._llm_flow, AutoFlow)


@patch.dict(os.environ, _ENV)
def test_llm_flow_supervisor_single_flow():
    agent = Agent(
        disallow_transfer_to_parent=True,
        disallow_transfer_to_peers=True,
        enable_supervisor=True,
    )
    supervisor_flow = Mock()
    with patch(
        "veadk.flows.supervise_single_flow.SupervisorSingleFlow",
        return_value=supervisor_flow,
    ) as mock_cls:
        flow = agent._llm_flow
    mock_cls.assert_called_once_with(supervised_agent=agent)
    assert flow is supervisor_flow


@patch.dict(os.environ, _ENV)
def test_llm_flow_supervisor_auto_flow():
    agent = Agent(enable_supervisor=True)
    supervisor_flow = Mock()
    with patch(
        "veadk.flows.supervise_auto_flow.SupervisorAutoFlow",
        return_value=supervisor_flow,
    ) as mock_cls:
        flow = agent._llm_flow
    mock_cls.assert_called_once_with(supervised_agent=agent)
    assert flow is supervisor_flow


# ---------------------------------------------------------------------------
# Runtime dispatch (_run_async_impl) and run() deprecation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_async_impl_adk_runtime_defers_to_super():
    agent = Agent(runtime="adk")
    ctx = Mock()

    async def _fake_super_impl(_ctx):
        yield "event-1"
        yield "event-2"

    with patch(
        "google.adk.agents.llm_agent.LlmAgent._run_async_impl",
        side_effect=_fake_super_impl,
    ):
        events = [e async for e in agent._run_async_impl(ctx)]
    assert events == ["event-1", "event-2"]


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_async_impl_non_adk_runtime_uses_get_runtime():
    agent = Agent()
    object.__setattr__(agent, "runtime", "codex")
    ctx = Mock()

    async def _runtime_stream(_agent, _ctx):
        yield "codex-event"

    runtime = Mock()
    runtime.run_async = _runtime_stream
    with patch("veadk.runtime.get_runtime", return_value=runtime) as mock_get:
        events = [e async for e in agent._run_async_impl(ctx)]
    mock_get.assert_called_once_with("codex")
    assert events == ["codex-event"]


@pytest.mark.asyncio
@patch.dict(os.environ, _ENV)
async def test_run_method_is_deprecated():
    agent = Agent()
    if not hasattr(agent, "run"):
        pytest.skip("run() not overridden on this ADK version")
    with pytest.raises(NotImplementedError, match="deprecated"):
        await agent.run()


@patch.dict(os.environ, _ENV)
def test_existing_model_skips_client_creation():
    from google.adk.models.lite_llm import LiteLlm

    existing = LiteLlm(model="prov/preset")
    with patch("veadk.agent.LiteLlm") as mock_lite_llm:
        agent = Agent(model=existing)
    mock_lite_llm.assert_not_called()
    assert agent.model is existing


@patch.dict(os.environ, {})
def test_agent_uses_settings_property_for_api_key():
    with patch(
        "veadk.configs.model_configs.ModelConfig.api_key",
        new_callable=PropertyMock,
        return_value="from-settings",
    ):
        agent = Agent()
    assert agent.model_api_key == "from-settings"
