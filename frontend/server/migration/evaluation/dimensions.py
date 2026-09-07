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

"""Stable dimension registry for migration-effect evaluation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

EvaluationDimensionId = Literal[
    "semantic_fidelity",
    "output_contract",
    "workflow_tool_fidelity",
    "context_memory_fidelity",
    "boundary_error_fidelity",
    "safety_refusal_fidelity",
]


@dataclass(frozen=True)
class EvaluationDimension:
    id: EvaluationDimensionId
    label: str
    description: str


EVALUATION_DIMENSIONS: tuple[EvaluationDimension, ...] = (
    EvaluationDimension(
        "semantic_fidelity",
        "语义与任务效果",
        "迁移后是否保持原 Agent 的意图理解、事实口径与任务完成效果。",
    ),
    EvaluationDimension(
        "output_contract",
        "输出格式",
        "结构、字段、语言和其他可观察输出约定是否保持一致。",
    ),
    EvaluationDimension(
        "workflow_tool_fidelity",
        "工作流与工具效果",
        "多步流程和外部工具带来的最终行为是否与迁移前证据一致。",
    ),
    EvaluationDimension(
        "context_memory_fidelity",
        "上下文与记忆",
        "在协议可验证的范围内，多轮上下文和记忆行为是否保持一致。",
    ),
    EvaluationDimension(
        "boundary_error_fidelity",
        "边界与异常",
        "缺参、无结果、依赖故障等边界场景的响应是否保持一致。",
    ),
    EvaluationDimension(
        "safety_refusal_fidelity",
        "安全与拒答",
        "敏感或越权请求的安全边界及拒答行为是否保持一致。",
    ),
)

EVALUATION_DIMENSION_IDS: tuple[EvaluationDimensionId, ...] = tuple(
    item.id for item in EVALUATION_DIMENSIONS
)
STANDARD_DIMENSION_IDS: tuple[EvaluationDimensionId, ...] = (
    "semantic_fidelity",
    "output_contract",
    "workflow_tool_fidelity",
)

__all__ = [
    "EVALUATION_DIMENSIONS",
    "EVALUATION_DIMENSION_IDS",
    "STANDARD_DIMENSION_IDS",
    "EvaluationDimension",
    "EvaluationDimensionId",
]
