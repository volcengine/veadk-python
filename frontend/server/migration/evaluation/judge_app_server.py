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

"""Judge one evaluation batch through the Sandbox app-server and its dynamic tool.

The legacy judge ran ``codex exec --output-schema`` and parsed the last agent message.
This contract carries the same verdicts as typed ``reportEvaluation`` arguments, so a
progress note or a fenced code block can no longer be mistaken for the batch result, and
a rejected batch is answered inside the same turn so Codex can correct itself.
"""

from __future__ import annotations

from veadk.cli.codex_app_server import CodexDynamicToolResult

from ..codex_tool_turn import ToolTurnUnavailable, run_tool_turn
from .judge_channel import JUDGE_TOOL_NAME
from .runner import judge_schema

JUDGE_TOOL_DESCRIPTION = (
    "提交本批迁移效果评测的判定结果。必须一次性提交全部用例与全部维度，"
    "参数严格遵循给定的 JSON Schema；被拒绝时按返回的错误修正后重新调用。"
)

EVIDENCE_SOURCES = frozenset(
    {
        "user_reference",
        "user_criteria",
        "source_contract",
        "observed_output",
        "runtime_observation",
        "deterministic_assertion",
    }
)
SEVERITIES = frozenset({"none", "low", "medium", "high", "critical", "unknown"})
_WORKFLOW_DIMENSION = "workflow_tool_fidelity"
_MAX_EVIDENCE_ITEMS = 20
_MAX_REASON_CHARS = 4 * 1024
_MAX_EVIDENCE_CHARS = 2 * 1024


class JudgeContractError(ValueError):
    """One ``reportEvaluation`` payload did not satisfy the judging contract."""


class JudgeTurnUnavailable(ToolTurnUnavailable):
    """The Sandbox app-server could not deliver a judge batch.

    The turn ran but produced nothing the runner can validate: no verdict, or a verdict
    that is not a case list.  It is a ``ToolTurnUnavailable`` so the driver answers every
    request that never delivered with an error envelope, whatever went wrong.
    """


def _required_text(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise JudgeContractError(f"{field} 必须是字符串")
    return value


def _bounded_text(value: object, field: str, limit: int) -> str:
    text = _required_text(value, field).strip()
    if not text:
        raise JudgeContractError(f"{field} 不能为空")
    return text[:limit]


def validate_judge_cases(
    arguments: dict[str, object],
    *,
    case_context: list[dict[str, object]],
    dimensions: list[str],
) -> dict[str, object]:
    """Validate one batch verdict against the cases and dimensions it must cover.

    The runner repeats these checks before caching the batch, so a rejection here is
    advice to Codex rather than the last line of defence.
    """
    if not dimensions:
        raise JudgeContractError("评测维度不能为空")
    cases = arguments.get("cases")
    if not isinstance(cases, list) or len(cases) != len(case_context):
        raise JudgeContractError(f"cases 必须恰好包含 {len(case_context)} 个用例")
    expected_ids = [str(item.get("case_id") or "") for item in case_context]
    returned_ids = [
        item.get("case_id") if isinstance(item, dict) else None for item in cases
    ]
    if returned_ids != expected_ids:
        raise JudgeContractError(
            "cases 必须按给定顺序包含全部用例：" + "、".join(expected_ids)
        )
    for index, (case, context) in enumerate(zip(cases, case_context)):
        assert isinstance(case, dict)
        results = case.get("dimensions")
        if not isinstance(results, list) or len(results) != len(dimensions):
            raise JudgeContractError(
                f"cases[{index}].dimensions 必须恰好包含 {len(dimensions)} 个维度"
            )
        returned_dimension_ids = [
            item.get("id") if isinstance(item, dict) else None for item in results
        ]
        if returned_dimension_ids != dimensions:
            raise JudgeContractError(
                f"cases[{index}].dimensions 必须按给定顺序包含全部维度："
                + "、".join(dimensions)
            )
        failed_execution = str(context.get("state") or "") == "failed"
        for dimension, result in zip(dimensions, results):
            assert isinstance(result, dict)
            field = f"cases[{index}].dimensions[{dimension}]"
            score = result.get("score")
            if score is not None and (
                isinstance(score, bool)
                or not isinstance(score, (int, float))
                or not 0 <= score <= 1
            ):
                raise JudgeContractError(
                    f"{field}.score 必须在 0 到 1 之间，证据不足时必须为 null"
                )
            severity = result.get("severity")
            if severity not in SEVERITIES:
                raise JudgeContractError(
                    f"{field}.severity 只能是 " + "、".join(sorted(SEVERITIES))
                )
            if (score is None) is not (severity == "unknown"):
                raise JudgeContractError(
                    f"{field} 的 score 与 severity 必须同时表示 N/A："
                    "score 为 null 时 severity 必须是 unknown，反之亦然"
                )
            result["reason"] = _bounded_text(
                result.get("reason"), f"{field}.reason", _MAX_REASON_CHARS
            )
            evidence = result.get("evidence")
            if not isinstance(evidence, list) or any(
                not isinstance(entry, str) for entry in evidence
            ):
                raise JudgeContractError(f"{field}.evidence 必须是字符串数组")
            result["evidence"] = [
                entry.strip()[:_MAX_EVIDENCE_CHARS]
                for entry in evidence[:_MAX_EVIDENCE_ITEMS]
                if entry.strip()
            ]
            sources = result.get("evidence_sources")
            if (
                not isinstance(sources, list)
                or any(not isinstance(source, str) for source in sources)
                or len(sources) != len(set(sources))
                or any(source not in EVIDENCE_SOURCES for source in sources)
            ):
                raise JudgeContractError(
                    f"{field}.evidence_sources 只能不重复地使用 "
                    + "、".join(sorted(EVIDENCE_SOURCES))
                )
            if failed_execution and score is not None:
                raise JudgeContractError(
                    f"{field} 的执行用例失败，全部维度必须为 N/A（score 为 null、"
                    "severity 为 unknown）"
                )
            if (
                dimension == _WORKFLOW_DIMENSION
                and score is not None
                and context.get("contract") is not True
                and context.get("criteria") is not True
                and context.get("runtime_observation") is not True
            ):
                raise JudgeContractError(
                    f"{field} 缺少 Runtime 原始可观察数据、用户标准和源行为契约，"
                    "必须为 N/A"
                )
    return {"cases": cases}


class JudgeRecorder:
    """Validate and retain the first judge batch delivered by a dynamic tool call.

    ``result`` holds the validated tool arguments, mirroring ``RouteRecorder``; the
    batch verdict itself is the ``cases`` list inside them.
    """

    def __init__(
        self,
        *,
        case_context: list[dict[str, object]],
        dimensions: list[str],
    ) -> None:
        self.case_context = case_context
        self.dimensions = dimensions
        self.result: dict[str, object] | None = None
        self.rejections: list[str] = []

    def submit(self, arguments: dict[str, object]) -> CodexDynamicToolResult:
        try:
            validated = validate_judge_cases(
                arguments,
                case_context=self.case_context,
                dimensions=self.dimensions,
            )
        except JudgeContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(
                False,
                f"判定结果不符合协议（{error}）。请修正后重新调用 {JUDGE_TOOL_NAME}。",
            )
        if self.result is None:
            self.result = validated
        return CodexDynamicToolResult(
            True,
            "本批判定已接收，请直接结束本轮，不要再输出其他内容。",
        )


async def run_judge_turn(
    *,
    endpoint: str,
    prompt: str,
    cwd: str,
    case_context: list[dict[str, object]],
    dimensions: list[str],
    thread_id: str = "",
    model: str = "",
    timeout_seconds: float,
) -> tuple[list[dict[str, object]], str]:
    """Judge one batch and return ``(cases, thread_id)``.

    The verdict is the ``cases`` list, not the whole tool call: the runner validates
    that list against the batch it asked about, so Studio must not wrap it again.
    """
    recorder = JudgeRecorder(case_context=case_context, dimensions=dimensions)
    used_thread = await run_tool_turn(
        endpoint=endpoint,
        prompt=prompt,
        cwd=cwd,
        tool_name=JUDGE_TOOL_NAME,
        tool_description=JUDGE_TOOL_DESCRIPTION,
        tool_schema=judge_schema(),
        handler=recorder.submit,
        has_result=lambda: recorder.result is not None,
        thread_id=thread_id,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    if recorder.result is None:
        raise JudgeTurnUnavailable("裁判回合没有提交判定结果。")
    cases = recorder.result.get("cases")
    if not isinstance(cases, list):
        raise JudgeTurnUnavailable("裁判回合没有提交可用的判定结果。")
    return cases, used_thread


__all__ = [
    "EVIDENCE_SOURCES",
    "JUDGE_TOOL_DESCRIPTION",
    "JUDGE_TOOL_NAME",
    "JudgeContractError",
    "JudgeRecorder",
    "JudgeTurnUnavailable",
    "SEVERITIES",
    "run_judge_turn",
    "validate_judge_cases",
]
