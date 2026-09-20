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
"""

from __future__ import annotations

from collections.abc import Callable
import os

from veadk.cli.codex_app_server import CodexDynamicToolResult

from .codex_tool_turn import ToolTurnUnavailable, run_tool_turn
from .contracts import MigrationContractError, validate_analysis_result

ROUTE_TOOL_NAME = "reportRoute"
ROUTE_TOOL_DESCRIPTION = (
    "提交只读项目分析的最终结果。必须在完成分析后调用一次，"
    "参数严格遵循给定的 JSON Schema；被拒绝时按返回的错误修正后重新调用。"
)
_APP_SERVER_ENV = "AGENTKIT_MIGRATION_APP_SERVER"
_DISABLED_VALUES = {"0", "false", "no", "off"}


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
) -> dict[str, object] | None:
    """Run one analysis turn and return the validated route contract, if any."""
    recorder = RouteRecorder(attempt=attempt, input_sha256=input_sha256)
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
        )
    except ToolTurnUnavailable as error:
        raise MigrationAnalysisUnavailable(str(error)) from error
    return recorder.result


__all__ = [
    "MigrationAnalysisUnavailable",
    "ROUTE_TOOL_DESCRIPTION",
    "ROUTE_TOOL_NAME",
    "RouteRecorder",
    "app_server_analysis_enabled",
    "run_route_analysis",
]
