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

The migration analysis result is a strict contract object.  Delivering it through a
registered dynamic tool keeps the payload in typed JSON-RPC arguments, so a progress
update, a commentary message, or a Markdown-fenced reply can no longer be mistaken for
the result.  Rejections are returned to Codex as ``success: false`` so the same turn can
correct itself instead of failing the whole migration.

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
from .codex_tool_turn import DynamicTool, ToolTurnUnavailable, run_tool_turn
from .contracts import MigrationContractError, validate_analysis_result

logger = logging.getLogger(__name__)

ROUTE_TOOL_NAME = "reportRoute"
ROUTE_TOOL_DESCRIPTION = (
    "提交只读项目分析的最终结果。必须在完成分析后调用一次，"
    "参数严格遵循给定的 JSON Schema；被拒绝时按返回的错误修正后重新调用。"
)
# What Codex is told when nobody answered the questions in time.
UNANSWERED_HINT = (
    "用户没有在时限内回答这些问题。请立即调用 "
    f"{ROUTE_TOOL_NAME} 并返回 status=needs_input，"
    "把原始问题写入 questions（每项包含 id、prompt、required），不要重复提问。"
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


class RouteRecorder:
    """Validate and retain one analysis result delivered by a dynamic tool call."""

    def __init__(self, *, attempt: int, input_sha256: str) -> None:
        self.attempt = attempt
        self.input_sha256 = input_sha256
        self.result: dict[str, object] | None = None
        self.rejections: list[str] = []

    def submit(self, arguments: dict[str, object]) -> CodexDynamicToolResult:
        candidate = {
            **arguments,
            "attempt": self.attempt,
            "input_sha256": self.input_sha256,
        }
        try:
            validated = validate_analysis_result(candidate)
        except MigrationContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(
                False,
                f"分析结果不符合协议（{error}）。请修正后重新调用 {ROUTE_TOOL_NAME}。",
            )
        if self.result is None:
            self.result = validated
        return CodexDynamicToolResult(
            True,
            "分析结果已接收。请用简体中文给出简短的用户可见总结。",
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
    schema: dict[str, object],
    cwd: str,
    attempt: int,
    input_sha256: str,
    model: str = "",
    timeout_seconds: float,
    event_sink: Callable[[object], None] | None = None,
    questioner: AnalysisQuestioner | None = None,
    idle_timeout_seconds: float | None = None,
    host_wait_seconds: Callable[[], float] | None = None,
) -> dict[str, object] | None:
    """Run one analysis turn and return the validated route contract, if any.

    Passing ``questioner`` registers ``askUser`` for this turn; the caller also owns
    the matching window through ``idle_timeout_seconds`` and ``host_wait_seconds``.
    """
    recorder = RouteRecorder(attempt=attempt, input_sha256=input_sha256)
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
    try:
        await run_tool_turn(
            endpoint=endpoint,
            prompt=prompt,
            cwd=cwd,
            tool_name=ROUTE_TOOL_NAME,
            tool_description=ROUTE_TOOL_DESCRIPTION,
            tool_schema=schema,
            handler=recorder.submit,
            has_result=lambda: recorder.result is not None,
            model=model,
            timeout_seconds=timeout_seconds,
            event_sink=event_sink,
            extra_tools=extra_tools,
            idle_timeout_seconds=idle_timeout_seconds,
            host_wait_seconds=host_wait_seconds,
        )
    except ToolTurnUnavailable as error:
        raise MigrationAnalysisUnavailable(str(error)) from error
    return recorder.result


__all__ = [
    "AnalysisQuestioner",
    "MigrationAnalysisUnavailable",
    "ROUTE_TOOL_DESCRIPTION",
    "ROUTE_TOOL_NAME",
    "RouteRecorder",
    "app_server_analysis_enabled",
    "ask_tool_handler",
    "run_route_analysis",
]
