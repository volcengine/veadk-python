# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft
from veadk.cli.generated_agent_planner import (
    _CURRENT_AGENT_DRAFT,
    CONVERSATION_INSTRUCTION,
    DEFAULT_GENERATED_MODEL_NAME,
    GENERATED_AGENT_RESULT_STATE_KEY,
    PLANNER_INSTRUCTION,
    GeneratedAgentConversationRequest,
    GeneratedAgentDraftPlan,
    GeneratedAgentDraftRequest,
    _planner_requirement,
    _to_agent_draft,
    generate_agent,
    generate_agent_draft,
    run_generated_agent_conversation,
)

TOOL_IDS = {
    "web_search",
    "parallel_web_search",
    "link_reader",
    "image_generate",
    "image_edit",
    "video_generate",
    "run_code",
}
HIDDEN_TOOL_IDS = {"web_scraper", "text_to_speech", "vesearch"}
HIDDEN_GENERATED_FIELDS = {
    "memory",
    "shortTermBackend",
    "longTermBackend",
    "autoSaveSession",
    "knowledgebase",
    "knowledgebaseBackend",
}


def test_generated_agent_draft_request_requires_at_least_four_characters() -> None:
    with pytest.raises(ValidationError):
        GeneratedAgentDraftRequest(requirement="abc")

    request = GeneratedAgentDraftRequest(requirement="abcd")

    assert request.requirement == "abcd"


def test_generated_agent_conversation_request_accepts_camel_case_session_id() -> None:
    request = GeneratedAgentConversationRequest.model_validate(
        {
            "sessionId": "studio-create-123",
            "message": "把第二个节点改成审核助手",
            "currentDraft": _orchestrator(
                "content_workflow",
                "sequential",
                [_leaf("writer", []), _leaf("reviewer", [])],
            ),
        }
    )

    assert request.session_id == "studio-create-123"
    assert request.message == "把第二个节点改成审核助手"
    assert request.current_draft is not None
    assert request.current_draft["subAgents"][1]["name"] == "reviewer"


@pytest.mark.asyncio
async def test_generate_agent_tool_calls_planner_and_persists_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "draft": {"name": "sales_agent"},
        "summary": "销售助手",
        "unresolvedItems": ["CRM 地址"],
    }

    async def fake_generate(requirement: str) -> dict[str, Any]:
        assert requirement == "创建一个销售助手"
        return expected

    monkeypatch.setattr(
        "veadk.cli.generated_agent_planner.generate_agent_draft",
        fake_generate,
    )
    tool_context = SimpleNamespace(state={})

    result = await generate_agent("创建一个销售助手", tool_context)  # type: ignore[arg-type]

    assert result == expected
    stored = tool_context.state[GENERATED_AGENT_RESULT_STATE_KEY]
    assert stored["draft"] == expected["draft"]
    assert stored["summary"] == expected["summary"]
    assert stored["unresolvedItems"] == expected["unresolvedItems"]
    assert stored["generationId"]


@pytest.mark.asyncio
async def test_conversation_uses_current_draft_as_internal_update_context() -> None:
    class SessionService:
        async def get_session(self, **_: Any) -> None:
            return None

    class ConversationRunner:
        session_service = SessionService()

        def __init__(self) -> None:
            self.message = ""
            self.context_draft: dict[str, Any] | None = None

        async def run(self, message: str, **_: Any) -> str:
            self.message = message
            self.context_draft = _CURRENT_AGENT_DRAFT.get()
            return "已更新审核节点。"

    runner = ConversationRunner()
    current_draft_payload = _orchestrator(
        "content_workflow",
        "sequential",
        [_leaf("writer", []), _leaf("reviewer", [])],
    )
    current_draft_payload["mcpTools"] = [
        {
            "name": "private_mcp",
            "transport": "http",
            "url": "https://mcp.test",
            "authToken": "secret-token",
        }
    ]
    current_draft_payload["deployment"] = {
        "envValues": {"MODEL_AGENT_API_KEY": "secret-key"}
    }
    result = await run_generated_agent_conversation(
        runner,  # type: ignore[arg-type]
        message="把第二个节点改成合规审核",
        user_id="local",
        session_id="studio-create-123",
        current_draft=current_draft_payload,
    )

    assert result == {"reply": "已更新审核节点。"}
    assert "<current_agent_draft>" in runner.message
    assert '"name":"writer"' in runner.message
    assert '"name":"reviewer"' in runner.message
    assert "secret-token" not in runner.message
    assert "secret-key" not in runner.message
    assert runner.context_draft is not None
    assert runner.context_draft["subAgents"][1]["name"] == "reviewer"
    assert _CURRENT_AGENT_DRAFT.get() is None
    assert runner.message.endswith("用户本轮消息：把第二个节点改成合规审核")


def test_conversation_agent_only_generates_after_requirements_are_clear() -> None:
    assert "正常回答问候、解释、讨论和澄清问题" in CONVERSATION_INSTRUCTION
    assert "需求已经足够具体" in CONVERSATION_INSTRUCTION
    assert "区分顶层工作流步骤和子智能体" in CONVERSATION_INSTRUCTION
    assert "最多两层" in CONVERSATION_INSTRUCTION
    assert "generate_agent" in CONVERSATION_INSTRUCTION


def test_planner_update_context_requires_exact_preservation() -> None:
    current_draft = {
        "name": "content_workflow",
        "agentType": "sequential",
        "subAgents": [
            {"name": "collector", "description": "keep exactly"},
            {"name": "writer", "description": "keep this too"},
        ],
    }

    prompt = _planner_requirement("只修改第二个节点名称", current_draft)

    assert "Copy every node, order, parent-child relationship" in prompt
    assert '"description":"keep exactly"' in prompt
    assert "<user_requirement>只修改第二个节点名称</user_requirement>" in prompt


def _leaf(
    name: str,
    tools: list[str],
) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} 的职责说明",
        "instruction": (f"你是 {name}，严格完成分配给你的步骤并返回结构化结果。"),
        "agentType": "llm",
        "maxIterations": 3,
        "modelName": DEFAULT_GENERATED_MODEL_NAME,
        "builtinTools": tools,
        "customTools": [],
        "subAgents": [],
    }


def _orchestrator(
    name: str,
    agent_type: str,
    children: list[dict[str, Any]],
    *,
    max_iterations: int = 3,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": f"{name} 的流程编排",
        "instruction": "",
        "agentType": agent_type,
        "maxIterations": max_iterations,
        "modelName": "",
        "builtinTools": [],
        "customTools": [],
        "subAgents": children,
    }


def _video_plan() -> dict[str, Any]:
    return _orchestrator(
        "video_production",
        "sequential",
        [
            _leaf("trend_researcher", ["web_search", "link_reader"]),
            _leaf("script_writer", []),
            _leaf("visual_creator", ["image_generate", "image_edit"]),
            _leaf("video_renderer", ["video_generate"]),
            _leaf("video_reviewer", []),
        ],
    )


def _image_plan() -> dict[str, Any]:
    return _orchestrator(
        "image_campaign",
        "sequential",
        [
            _leaf("visual_researcher", ["web_search", "link_reader"]),
            _leaf("hero_image_creator", ["image_generate"]),
            _leaf("image_editor", ["image_edit"]),
            _leaf("brand_reviewer", []),
        ],
    )


def _ops_plan() -> dict[str, Any]:
    return _orchestrator(
        "operations_assistant",
        "sequential",
        [
            _leaf(
                "incident_triage",
                ["web_search", "link_reader"],
            ),
            _leaf("diagnostic_runner", ["run_code"]),
            _leaf("remediation_executor", ["run_code"]),
            _leaf("health_verifier", ["run_code"]),
            _leaf("incident_reporter", []),
        ],
    )


SCENARIOS = [
    (
        "video",
        _video_plan,
        {"image_generate", "image_edit", "video_generate"},
    ),
    ("image", _image_plan, {"image_generate", "image_edit"}),
    ("ops", _ops_plan, {"web_search", "link_reader", "run_code"}),
]


LIVE_REQUIREMENTS = [
    (
        "video",
        (
            "创建一个复杂短视频生产 Agent。根流程按顺序完成趋势调研、"
            "脚本编写、主视觉生产、视频生成和质量复核。主视觉生产节点必须"
            "先生成图片，再使用图片编辑工具完成二次编辑；视频由图片和脚本生成。"
            "联网调研必须阅读原始网页，"
            "不要为只做审查的 Agent 配置媒体生成工具。"
        ),
        {
            "web_search",
            "link_reader",
            "image_generate",
            "image_edit",
            "video_generate",
        },
    ),
    (
        "image",
        (
            "创建一个品牌图片生产 Agent。先联网调研视觉趋势并阅读原始页面，"
            "再生成主视觉方案，随后由独立 Agent 使用图片编辑工具"
            "完成品牌色和版式调整，最后由不带生成工具的审核 Agent 做质量检查。"
            "画布节点必须严格按这个顺序执行。"
        ),
        {"web_search", "link_reader", "image_generate", "image_edit"},
    ),
    (
        "ops",
        (
            "创建一个生产运维助手。根流程按顺序完成告警研判、诊断脚本执行、"
            "修复执行、健康检查，最后生成事故报告。告警研判需要"
            "联网查阅官方故障文档并保留短期上下文，诊断、修复和验证都在"
            "代码沙箱中执行；告警研判开启 APMPlus "
            "链路观测。不要虚构监控系统地址或凭据。"
        ),
        {"web_search", "link_reader", "run_code"},
    ),
]


LIVE_SHAPE_REQUIREMENTS = [
    (
        "single_agent",
        (
            "创建一个企业差旅政策问答 Agent，负责理解员工问题并直接回答。"
            "这是单一职责，不要拆成多个工作流节点，也不需要任何工具。"
        ),
        "llm",
        1,
        set(),
    ),
    (
        "eight_step_workflow",
        (
            "创建一个严格包含八个普通 Agent 节点的市场发布工作流，依次为："
            "需求解析、竞品联网调研、原始网页阅读、数据分析、传播文案、"
            "主视觉生成、品牌合规审核、发布总结。必须保持这八步和顺序；"
            "数据分析使用代码沙箱，主视觉生成使用图片生成工具，审核节点不带生成工具。"
        ),
        "sequential",
        8,
        {"web_search", "link_reader", "run_code", "image_generate"},
    ),
    (
        "parallel_loop_words_are_flattened",
        (
            "创建一个研究报告工作流。需求里原本希望让行业资料和政策资料并行调研，"
            "然后写初稿并循环审核最多三轮，最后定稿。当前 Studio 只展示普通 Agent "
            "节点，请把它安全转换为依次执行的行业调研、政策调研、初稿、审核、修订、"
            "定稿六个节点，不要输出并行、循环或嵌套编排节点。两个调研节点都要联网搜索"
            "并阅读原始页面。"
        ),
        "sequential",
        6,
        {"web_search", "link_reader"},
    ),
]


def _walk_plan(node: Any) -> list[Any]:
    nodes = [node]
    for child in node.subAgents:
        nodes.extend(_walk_plan(child))
    return nodes


def _walk_draft(node: AgentDraft) -> list[AgentDraft]:
    nodes = [node]
    for child in node.subAgents:
        nodes.extend(_walk_draft(child))
    return nodes


def _normalized_tool_capabilities(nodes: list[AgentDraft]) -> set[str]:
    """Treat serial and parallel Internet search as the same user capability."""

    selected_tools = {
        tool for node in nodes if node.agentType == "llm" for tool in node.builtinTools
    }
    if "parallel_web_search" in selected_tools:
        selected_tools.add("web_search")
    return selected_tools


@pytest.mark.parametrize(("name", "plan_factory", "required_tools"), SCENARIOS)
def test_ordered_plans_validate_and_generate_runnable_projects(
    name: str,
    plan_factory: Any,
    required_tools: set[str],
) -> None:
    plan = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": f"{name} complex Agent",
            "rootAgent": plan_factory(),
            "unresolvedItems": [],
        }
    )
    nodes = _walk_plan(plan.rootAgent)
    leaves = [node for node in nodes if node.agentType == "llm"]
    orchestrators = [node for node in nodes if node.agentType != "llm"]
    selected_tools = _normalized_tool_capabilities(nodes)

    assert plan.rootAgent.agentType == "sequential"
    assert len(nodes) >= 4
    assert all(node.modelName == DEFAULT_GENERATED_MODEL_NAME for node in leaves)
    assert all(node.instruction.strip() for node in leaves)
    assert all(not node.subAgents for node in leaves)
    assert all(not node.modelName and not node.builtinTools for node in orchestrators)
    assert orchestrators == [plan.rootAgent]
    assert required_tools <= selected_tools <= TOOL_IDS

    draft = _to_agent_draft(plan.rootAgent)
    project = generate_project_from_draft(draft)
    python_files = [file for file in project.files if file.path.endswith(".py")]
    assert python_files
    for file in python_files:
        compile(file.content, file.path, "exec")


def test_planner_schema_excludes_hidden_create_capabilities() -> None:
    schema = json.dumps(GeneratedAgentDraftPlan.model_json_schema())
    frontend_catalog = (
        Path(__file__).parents[2] / "frontend/src/create/veadkCatalog.ts"
    ).read_text(encoding="utf-8")
    frontend_tool_ids = set(re.findall(r'\bid:\s*"([a-z_]+)"', frontend_catalog))

    assert '"$ref"' in schema
    assert schema.count('"additionalProperties": false') >= 3
    assert TOOL_IDS <= frontend_tool_ids
    assert all(tool_id not in schema for tool_id in HIDDEN_TOOL_IDS)
    assert "tracingExporters" not in schema
    assert all(field not in schema for field in HIDDEN_GENERATED_FIELDS)
    assert all(tool_id in schema for tool_id in TOOL_IDS)
    assert all(tool_id in PLANNER_INSTRUCTION for tool_id in TOOL_IDS)
    assert all(tool_id not in PLANNER_INSTRUCTION for tool_id in HIDDEN_TOOL_IDS)
    assert "tracing" not in PLANNER_INSTRUCTION.lower()
    assert "memory" not in PLANNER_INSTRUCTION.lower()
    assert "knowledgebase" not in PLANNER_INSTRUCTION.lower()


def test_planner_maps_visible_nodes_to_single_or_ordered_workflows() -> None:
    assert "For one Agent node, rootAgent is that llm Agent" in PLANNER_INSTRUCTION
    assert "For two or more ordered Agent nodes" in PLANNER_INSTRUCTION
    assert "may own direct llm subAgents" in PLANNER_INSTRUCTION
    assert "at most two visible levels" in PLANNER_INSTRUCTION
    assert (
        "Do not flatten a requested parent/sub-Agent relationship"
        in PLANNER_INSTRUCTION
    )
    assert "Never generate parallel, loop" in PLANNER_INSTRUCTION
    assert "Never expose" in PLANNER_INSTRUCTION


def test_planner_allows_direct_sub_agents_on_a_single_visible_agent() -> None:
    parent = _leaf("research_coordinator", [])
    parent["subAgents"] = [
        _leaf("source_researcher", ["web_search", "link_reader"]),
        _leaf("fact_checker", ["run_code"]),
    ]

    plan = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": "research team",
            "rootAgent": parent,
            "unresolvedItems": [],
        }
    )

    assert plan.rootAgent.agentType == "llm"
    assert [child.name for child in plan.rootAgent.subAgents] == [
        "source_researcher",
        "fact_checker",
    ]
    project = generate_project_from_draft(_to_agent_draft(plan.rootAgent))
    python_files = [file for file in project.files if file.path.endswith(".py")]
    assert python_files
    assert any("sub_agents=[" in file.content for file in python_files)
    for file in python_files:
        compile(file.content, file.path, "exec")


def test_planner_allows_direct_sub_agents_on_ordered_workflow_nodes() -> None:
    researcher = _leaf("researcher", ["web_search"])
    researcher["subAgents"] = [
        _leaf("interviewer", []),
        _leaf("competitor_analyst", ["link_reader"]),
    ]
    plan = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": "ordered team",
            "rootAgent": _orchestrator(
                "research_workflow",
                "sequential",
                [researcher, _leaf("report_writer", [])],
            ),
            "unresolvedItems": [],
        }
    )

    assert plan.rootAgent.agentType == "sequential"
    assert len(plan.rootAgent.subAgents[0].subAgents) == 2


def test_planner_rejects_agent_hierarchy_deeper_than_two_visible_levels() -> None:
    grandchild_parent = _leaf("specialist", [])
    grandchild_parent["subAgents"] = [_leaf("too_deep", [])]
    parent = _leaf("coordinator", [])
    parent["subAgents"] = [grandchild_parent]

    with pytest.raises(ValidationError, match="at most two levels"):
        GeneratedAgentDraftPlan.model_validate(
            {
                "summary": "too deep",
                "rootAgent": parent,
                "unresolvedItems": [],
            }
        )


@pytest.mark.parametrize("agent_type", ["parallel", "loop"])
def test_planner_rejects_unsupported_workflow_types(agent_type: str) -> None:
    with pytest.raises(ValidationError):
        GeneratedAgentDraftPlan.model_validate(
            {
                "summary": "unsupported",
                "rootAgent": _orchestrator(
                    "unsupported_workflow",
                    agent_type,
                    [_leaf("worker_one", []), _leaf("worker_two", [])],
                ),
                "unresolvedItems": [],
            }
        )


def test_planner_flattens_equivalent_sequential_wrappers() -> None:
    single = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": "single child",
            "rootAgent": _orchestrator(
                "single_child_workflow",
                "sequential",
                [_leaf("worker", [])],
            ),
            "unresolvedItems": [],
        }
    )
    nested = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": "nested",
            "rootAgent": _orchestrator(
                "nested_workflow",
                "sequential",
                [
                    _leaf("worker_one", []),
                    _orchestrator(
                        "nested_sequence",
                        "sequential",
                        [_leaf("worker_two", []), _leaf("worker_three", [])],
                    ),
                ],
            ),
            "unresolvedItems": [],
        }
    )

    assert single.rootAgent.agentType == "llm"
    assert single.rootAgent.name == "worker"
    assert [child.name for child in nested.rootAgent.subAgents] == [
        "worker_one",
        "worker_two",
        "worker_three",
    ]


def test_planner_draft_disables_hidden_capabilities() -> None:
    plan = GeneratedAgentDraftPlan.model_validate(
        {
            "summary": "no hidden capabilities",
            "rootAgent": _leaf("assistant", ["web_search"]),
            "unresolvedItems": [],
        }
    )

    draft = _to_agent_draft(plan.rootAgent)

    assert not draft.tracing
    assert draft.tracingExporters == []
    assert not draft.memory.shortTerm
    assert not draft.memory.longTerm
    assert not draft.autoSaveSession
    assert not draft.knowledgebase


def test_orchestrator_fields_are_normalized_before_strict_validation() -> None:
    raw = _orchestrator(
        "review_flow",
        "sequential",
        [_leaf("writer", []), _leaf("reviewer", [])],
    )
    raw.update(
        instruction="模型错误生成的编排提示词",
        modelName=DEFAULT_GENERATED_MODEL_NAME,
        builtinTools=["web_search"],
        customTools=[{"name": "invalid_tool", "description": "invalid"}],
    )

    plan = GeneratedAgentDraftPlan.model_validate(
        {"summary": "normalized", "rootAgent": raw, "unresolvedItems": []}
    )

    assert plan.rootAgent.instruction == ""
    assert plan.rootAgent.modelName == ""
    assert plan.rootAgent.builtinTools == []
    assert plan.rootAgent.customTools == []


@pytest.mark.asyncio
@pytest.mark.parametrize(("name", "requirement", "required_tools"), LIVE_REQUIREMENTS)
async def test_live_planner_generates_complex_scenarios(
    name: str,
    requirement: str,
    required_tools: set[str],
) -> None:
    if os.getenv("RUN_LIVE_ARK_PLANNER_TESTS") != "1":
        pytest.skip("set RUN_LIVE_ARK_PLANNER_TESTS=1 to call the live Ark model")

    result = await generate_agent_draft(requirement)
    draft = AgentDraft.model_validate(result["draft"])
    nodes = _walk_draft(draft)
    leaves = [node for node in nodes if node.agentType == "llm"]
    selected_tools = _normalized_tool_capabilities(nodes)

    assert draft.agentType == "sequential", name
    assert len(nodes) >= 4, name
    assert all(node.agentType == "llm" for node in nodes[1:]), name
    assert all(node.modelName == DEFAULT_GENERATED_MODEL_NAME for node in leaves), name
    assert all(node.instruction.strip() for node in leaves), name
    assert required_tools <= selected_tools, name


@pytest.mark.asyncio
@pytest.mark.parametrize(
    (
        "name",
        "requirement",
        "expected_root_type",
        "expected_leaf_count",
        "required_tools",
    ),
    LIVE_SHAPE_REQUIREMENTS,
)
async def test_live_planner_handles_shape_boundaries(
    name: str,
    requirement: str,
    expected_root_type: str,
    expected_leaf_count: int,
    required_tools: set[str],
) -> None:
    if os.getenv("RUN_LIVE_ARK_PLANNER_TESTS") != "1":
        pytest.skip("set RUN_LIVE_ARK_PLANNER_TESTS=1 to call the live Ark model")

    result = await generate_agent_draft(requirement)
    draft = AgentDraft.model_validate(result["draft"])
    nodes = _walk_draft(draft)
    leaves = [node for node in nodes if node.agentType == "llm"]
    selected_tools = _normalized_tool_capabilities(nodes)

    assert draft.agentType == expected_root_type, name
    assert len(leaves) == expected_leaf_count, name
    assert all(node.agentType == "llm" and not node.subAgents for node in leaves), name
    assert all(node.modelName == DEFAULT_GENERATED_MODEL_NAME for node in leaves), name
    assert required_tools <= selected_tools, name
    if draft.agentType == "sequential":
        assert nodes[1:] == leaves, name


@pytest.mark.asyncio
async def test_live_planner_preserves_untouched_nodes_during_follow_up() -> None:
    if os.getenv("RUN_LIVE_ARK_PLANNER_TESTS") != "1":
        pytest.skip("set RUN_LIVE_ARK_PLANNER_TESTS=1 to call the live Ark model")

    current_draft = AgentDraft.model_validate(
        _orchestrator(
            "research_workflow",
            "sequential",
            [
                _leaf("requirement_parser", []),
                _leaf("source_researcher", ["parallel_web_search"]),
                _leaf("source_reader", ["link_reader"]),
                _leaf("fact_checker", ["run_code"]),
                _leaf("report_writer", []),
                _leaf("visual_creator", ["image_generate"]),
                _leaf("compliance_reviewer", []),
                _leaf("release_summarizer", []),
            ],
        )
    ).model_dump()
    result = await generate_agent_draft(
        "只把第四个节点的名称改成 source_verifier，其他任何字段都不要修改。",
        current_draft=current_draft,
    )
    updated = result["draft"]

    assert updated["agentType"] == "sequential"
    assert updated["name"] == current_draft["name"]
    assert len(updated["subAgents"]) == 8
    assert updated["subAgents"][3]["name"] == "source_verifier"
    assert {
        key: value for key, value in updated["subAgents"][3].items() if key != "name"
    } == {
        key: value
        for key, value in current_draft["subAgents"][3].items()
        if key != "name"
    }
    for index in (0, 1, 2, 4, 5, 6, 7):
        assert updated["subAgents"][index] == current_draft["subAgents"][index]
