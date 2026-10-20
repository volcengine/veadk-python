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

"""Codex app-server route analysis for Studio project migration.

The analysis result arrives through registered dynamic tools, so a progress update, a
commentary message, or a Markdown-fenced reply can no longer be mistaken for the result.
Acceptance is deliberately liberal: Studio owns the state-file format, fills in the
protocol bookkeeping itself, and defaults or drops whatever the model could not shape,
so a model that writes imperfect arguments still lands a usable result.  Only the
destructive ``unsupported`` verdict is held to a deterministic bar, and a refusal is
returned to Codex as ``success: false`` so the same turn corrects itself.

The same turn also carries ``askUser``.  When the project cannot answer a question that
changes the migration, Codex asks the user inside the turn and keeps analysing with the
answer, which is cheaper and more accurate than re-running the analysis afterwards.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable

from veadk.cli.codex_app_server import CodexDynamicToolResult

from .analysis_input import (
    ASK_TOOL_DESCRIPTION,
    ASK_TOOL_NAME,
    ASK_TOOL_SCHEMA,
    AnalysisAskError,
    Answers,
    normalize_questions,
)
from .analysis_contract import (
    NEEDS_INPUT_KIND,
    RECOMMENDATION_KIND,
    UNSUPPORTED_KIND,
    AnalysisAcceptanceError,
    AnalysisAssemblyError,
    acceptance_feedback,
    analysis_tool_schema,
    build_analysis_result,
)
from .codex_tool_turn import DynamicTool, ToolTurnUnavailable, run_tool_turn

logger = logging.getLogger(__name__)

RECOMMENDATION_TOOL_NAME = "reportRecommendation"
NEEDS_INPUT_TOOL_NAME = "reportNeedsInput"
UNSUPPORTED_TOOL_NAME = "reportUnsupported"
TOOL_NAME_BY_KIND = {
    RECOMMENDATION_KIND: RECOMMENDATION_TOOL_NAME,
    NEEDS_INPUT_KIND: NEEDS_INPUT_TOOL_NAME,
    UNSUPPORTED_KIND: UNSUPPORTED_TOOL_NAME,
}
TOOL_DESCRIPTION_BY_KIND = {
    RECOMMENDATION_KIND: (
        "提交只读项目分析的最终结论：推荐一种可执行的迁移方式。"
        "在完成分析后调用一次；只有 summary 是必填的，其余字段能给多少给多少，"
        "缺失的字段会被 Studio 用已核实的事实补齐，不会被拒绝。"
    ),
    NEEDS_INPUT_KIND: (
        "提交只读项目分析的结论：必须先由用户补充信息才能决定迁移方式。"
        "把要向用户提出的问题写入 questions（每项含 prompt）。"
    ),
    UNSUPPORTED_KIND: (
        "提交「该项目无法迁移」的结论。这是最后一个手段，只用于材料不足或"
        "证据完整的高风险行为链；必须给出 summary 和至少两条指向项目真实文件的"
        "证据，证据无法核实会被拒绝。"
    ),
}
# What Codex is told when nobody answered the questions in time.
UNANSWERED_HINT = (
    "用户没有在时限内回答这些问题。请立即调用 "
    f"{NEEDS_INPUT_TOOL_NAME}，"
    "把原始问题写入 questions（每项包含 prompt），不要重复提问。"
)

_APP_SERVER_ENV = "AGENTKIT_MIGRATION_APP_SERVER"
_DISABLED_VALUES = {"0", "false", "no", "off"}

# Publishes the questions to the page and returns the user's answers, or ``None`` when
# the user did not answer inside the window the caller allows.
AnalysisQuestioner = Callable[
    [tuple[dict[str, object], ...]],
    Awaitable[Answers | None],
]


def app_server_analysis_enabled() -> bool:
    """Whether route analysis should use the Sandbox Codex app-server.

    The app-server carries the analysis result in typed dynamic-tool arguments, so a
    progress update or a Markdown-fenced reply can no longer be mistaken for the
    result.  It runs on a Studio background worker, and the scripted ``codex exec``
    path remains the fallback whenever the app-server is unreachable, so this is on by
    default; set ``AGENTKIT_MIGRATION_APP_SERVER=0`` to pin the scripted path.
    """
    return os.getenv(_APP_SERVER_ENV, "").strip().lower() not in _DISABLED_VALUES


class MigrationAnalysisUnavailable(RuntimeError):
    """The Sandbox app-server could not produce a usable analysis result."""


class AnalysisRecorder:
    """Accept one terminal analysis submission and retain the assembled result.

    The record carries the outcome facts a caller may want to persist: which tool
    landed, what acceptance had to default or drop, and why earlier submissions were
    refused.  None of that is a verdict about the project.
    """

    def __init__(
        self,
        *,
        attempt: int,
        input_sha256: str,
        detection: dict[str, object] | None = None,
    ) -> None:
        self.attempt = attempt
        self.input_sha256 = input_sha256
        self.detection = detection
        self.result: dict[str, object] | None = None
        self.kind = ""
        self.notes: list[str] = []
        self.refusals: list[str] = []

    def handler(
        self,
        kind: str,
    ) -> Callable[[dict[str, object]], CodexDynamicToolResult]:
        def handle(arguments: dict[str, object]) -> CodexDynamicToolResult:
            return self._accept(kind, arguments)

        return handle

    def _accept(
        self,
        kind: str,
        arguments: dict[str, object],
    ) -> CodexDynamicToolResult:
        if self.result is not None:
            return CodexDynamicToolResult(
                True,
                "分析结果已经提交，请直接给出简短的简体中文总结。",
            )
        try:
            document, notes = build_analysis_result(
                kind,
                arguments,
                attempt=self.attempt,
                input_sha256=self.input_sha256,
                detection=self.detection,
            )
        except AnalysisAcceptanceError as error:
            self.refusals.append(
                "; ".join(f"{item.path}:{item.actual}" for item in error.issues)
            )
            return CodexDynamicToolResult(False, acceptance_feedback(kind, error))
        except AnalysisAssemblyError:
            logger.exception("Studio migration analysis assembly failed kind=%s", kind)
            return CodexDynamicToolResult(
                False,
                "Studio 暂时无法保存这次结论，请稍后重新调用同一个工具。",
            )
        self.result = document
        self.kind = kind
        self.notes = notes
        if notes:
            logger.info(
                "Studio migration analysis accepted with defaults kind=%s notes=%s",
                kind,
                notes,
            )
        return CodexDynamicToolResult(
            True,
            "结论已接收。请用简体中文给出简短的用户可见总结，不要重复分析过程。",
        )


def ask_tool_handler(questioner: AnalysisQuestioner) -> Callable[..., object]:
    """Build the ``askUser`` handler that bridges one turn to the browser.

    The result carries the answers exactly like Codex' native
    ``ToolRequestUserInputResponse``, and an unanswered question set is a *successful*
    call: the model is told nobody answered so it can fall back to ``needs_input``
    instead of asking again.  The description lives on the tool spec, so a caller that
    is not a read-only analysis can promise the right thing while reusing the channel.
    """

    async def handle(arguments: dict[str, object]) -> CodexDynamicToolResult:
        try:
            questions = normalize_questions(arguments)
        except AnalysisAskError as error:
            return CodexDynamicToolResult(
                False,
                f"提问不符合要求（{error}）。请修正后重新调用 {ASK_TOOL_NAME}。",
            )
        try:
            answers = await questioner(questions)
        except Exception:  # noqa: BLE001 - a broken channel must not kill the turn
            logger.exception("Studio migration askUser channel failed")
            answers = None
        if answers is None:
            return CodexDynamicToolResult(
                True,
                json.dumps(
                    {"answers": {}, "unanswered": True, "hint": UNANSWERED_HINT},
                    ensure_ascii=False,
                ),
            )
        return CodexDynamicToolResult(
            True,
            json.dumps(
                {
                    "answers": {
                        question_id: {"answers": list(values)}
                        for question_id, values in answers.items()
                    }
                },
                ensure_ascii=False,
            ),
        )

    return handle


async def run_route_analysis(
    *,
    endpoint: str,
    prompt: str,
    cwd: str,
    attempt: int,
    input_sha256: str,
    model: str = "",
    timeout_seconds: float,
    event_sink: Callable[[object], None] | None = None,
    questioner: AnalysisQuestioner | None = None,
    idle_timeout_seconds: float | None = None,
    host_wait_seconds: Callable[[], float] | None = None,
    detection: dict[str, object] | None = None,
    diagnostics: dict[str, object] | None = None,
) -> dict[str, object] | None:
    """Run one analysis turn and return the accepted analysis document, if any.

    Passing ``questioner`` registers ``askUser`` for this turn; the caller also owns
    the matching window through ``idle_timeout_seconds`` and ``host_wait_seconds``.
    ``detection`` carries Studio's own verified facts, which acceptance uses to fill
    defaults and to check the one verdict that must cite real files.  ``diagnostics``,
    when given, is filled in place with what happened, so a caller can persist it.
    """
    recorder = AnalysisRecorder(
        attempt=attempt,
        input_sha256=input_sha256,
        detection=detection,
    )
    extra_tools = (
        (
            DynamicTool(
                name=ASK_TOOL_NAME,
                description=ASK_TOOL_DESCRIPTION,
                schema=ASK_TOOL_SCHEMA,
                handler=ask_tool_handler(questioner),
            ),
        )
        if questioner is not None
        else ()
    )
    # Counting Codex' own output is what lets a caller tell "the turn never reached
    # the model" (an infrastructure fallback) from "the model worked and delivered
    # nothing acceptable" (a conclusion Studio must fall back for itself).
    seen = {"events": 0}

    def sink(event: object) -> None:
        seen["events"] += 1
        if event_sink is not None:
            event_sink(event)

    tools = tuple(
        DynamicTool(
            name=TOOL_NAME_BY_KIND[kind],
            description=TOOL_DESCRIPTION_BY_KIND[kind],
            schema=analysis_tool_schema(kind),
            handler=recorder.handler(kind),
        )
        for kind in (RECOMMENDATION_KIND, NEEDS_INPUT_KIND, UNSUPPORTED_KIND)
    )
    try:
        await run_tool_turn(
            endpoint=endpoint,
            prompt=prompt,
            cwd=cwd,
            tools=tools,
            has_result=lambda: recorder.result is not None,
            model=model,
            timeout_seconds=timeout_seconds,
            event_sink=sink,
            extra_tools=extra_tools,
            idle_timeout_seconds=idle_timeout_seconds,
            host_wait_seconds=host_wait_seconds,
        )
    except ToolTurnUnavailable as error:
        raise MigrationAnalysisUnavailable(str(error)) from error
    if diagnostics is not None:
        diagnostics.update(
            {
                "accepted": recorder.result is not None,
                "kind": recorder.kind,
                "notes": list(recorder.notes),
                "refusals": list(recorder.refusals),
                "events": seen["events"],
            }
        )
    return recorder.result


__all__ = [
    "AnalysisQuestioner",
    "AnalysisRecorder",
    "MigrationAnalysisUnavailable",
    "NEEDS_INPUT_TOOL_NAME",
    "RECOMMENDATION_TOOL_NAME",
    "TOOL_DESCRIPTION_BY_KIND",
    "TOOL_NAME_BY_KIND",
    "UNSUPPORTED_TOOL_NAME",
    "app_server_analysis_enabled",
    "ask_tool_handler",
    "run_route_analysis",
]
