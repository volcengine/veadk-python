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
from typing import Any

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft
from veadk.cli.generated_agent_planner import (
    DEFAULT_GENERATED_MODEL_NAME,
    PLANNER_INSTRUCTION,
    GeneratedAgentDraftPlan,
    GeneratedAgentDraftRequest,
    _to_agent_draft,
    generate_agent_draft,
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
    media_assets = _orchestrator(
        "media_assets",
        "parallel",
        [
            _leaf("visual_creator", ["image_generate", "image_edit"]),
            _leaf("voice_creator", []),
        ],
    )
    review_loop = _orchestrator(
        "video_review_loop",
        "loop",
        [
            _leaf("video_reviewer", []),
            _leaf("video_reviser", ["video_generate"]),
        ],
        max_iterations=4,
    )
    return _orchestrator(
        "video_production",
        "sequential",
        [
            _leaf("trend_researcher", ["web_search", "link_reader"]),
            _leaf("script_writer", []),
            media_assets,
            _leaf("video_renderer", ["video_generate"]),
            review_loop,
        ],
    )


def _image_plan() -> dict[str, Any]:
    concepts = _orchestrator(
        "concept_variants",
        "parallel",
        [
            _leaf("hero_image_creator", ["image_generate"]),
            _leaf("alternate_image_creator", ["image_generate"]),
        ],
    )
    return _orchestrator(
        "image_campaign",
        "sequential",
        [
            _leaf("visual_researcher", ["web_search", "link_reader"]),
            concepts,
            _leaf("image_editor", ["image_edit"]),
            _leaf("brand_reviewer", []),
        ],
    )


def _ops_plan() -> dict[str, Any]:
    remediation_loop = _orchestrator(
        "remediation_loop",
        "loop",
        [
            _leaf("remediation_executor", ["run_code"]),
            _leaf("health_verifier", ["run_code"]),
        ],
        max_iterations=5,
    )
    return _orchestrator(
        "operations_assistant",
        "sequential",
        [
            _leaf(
                "incident_triage",
                ["web_search", "link_reader"],
            ),
            _leaf("diagnostic_runner", ["run_code"]),
            remediation_loop,
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
            "脚本编写、素材生产、视频生成和质量复核。素材阶段并行生成"
            "主视觉图片和中文配音；主视觉需要支持后续图片编辑；视频由图片、"
            "脚本和配音生成。最后最多循环 4 次检查画面、配音和脚本一致性，"
            "并重新生成不合格视频。联网调研必须阅读原始网页，"
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
            "再并行生成两套主视觉方案，随后由独立 Agent 使用图片编辑工具"
            "完成品牌色和版式调整，最后由不带生成工具的审核 Agent 做质量检查。"
            "必须体现有顺序和并行关系的"
            "嵌套 Agent。"
        ),
        {"web_search", "link_reader", "image_generate", "image_edit"},
    ),
    (
        "ops",
        (
            "创建一个生产运维助手。根流程按顺序完成告警研判、诊断脚本执行、"
            "最多 5 轮的修复与健康检查循环，最后生成事故报告。告警研判需要"
            "联网查阅官方故障文档并保留短期上下文，诊断、修复和验证都在"
            "代码沙箱中执行；告警研判开启 APMPlus "
            "链路观测。不要虚构监控系统地址或凭据。"
        ),
        {"web_search", "link_reader", "run_code"},
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


@pytest.mark.parametrize(("name", "plan_factory", "required_tools"), SCENARIOS)
def test_complex_plans_validate_and_generate_runnable_projects(
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
    selected_tools = {tool for node in leaves for tool in node.builtinTools}

    assert plan.rootAgent.agentType == "sequential"
    assert len(nodes) >= 6
    assert all(node.modelName == DEFAULT_GENERATED_MODEL_NAME for node in leaves)
    assert all(node.instruction.strip() for node in leaves)
    assert all(not node.subAgents for node in leaves)
    assert all(not node.modelName and not node.builtinTools for node in orchestrators)
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


def test_planner_prefers_a_flexible_llm_root_agent() -> None:
    assert "Prefer an llm Agent as rootAgent" in PLANNER_INSTRUCTION
    assert "Do not choose an orchestrator merely because" in PLANNER_INSTRUCTION
    assert "strict workflow control is essential" in PLANNER_INSTRUCTION


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
        [_leaf("reviewer", [])],
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
    selected_tools = {tool for node in leaves for tool in node.builtinTools}

    assert draft.agentType == "sequential", name
    assert len(nodes) >= 6, name
    assert any(node.agentType in {"parallel", "loop"} for node in nodes), name
    assert all(node.modelName == DEFAULT_GENERATED_MODEL_NAME for node in leaves), name
    assert all(node.instruction.strip() for node in leaves), name
    assert required_tools <= selected_tools, name
