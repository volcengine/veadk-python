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

"""Close one migration delivery on a Studio-owned Codex app-server turn.

The Sandbox runs the migration CLI and writes the delivery triple itself, so the
delivery phase used to end the moment the launch script published its status: a run
that stopped early reached the page as a generic "the command did not finish", and a
run that produced warnings reached it as one fixed sentence with the details left in a
log nobody opens.

The closing turn keeps the AgentKit CLI as the authority on *what happened* and makes
Studio the authority on *what the user is told*:

* the artifact is published through a dynamic tool, so Studio reads the bytes back and
  checks them against the manifest the CLI wrote before the delivery may complete;
* the verdict arrives as typed arguments and is validated against the state Studio
  derived from the Sandbox, so a turn that misreads a log can explain a delivery but
  never upgrade or downgrade it;
* a failed run is diagnosed inside the turn, which can also ask for information only a
  human has instead of leaving an unusable "see the logs" behind.

``publishArtifact`` is why this turn has to live on the Studio side at all: dynamic
tools are registered on a Studio-driven app-server turn, and the Sandbox has no return
path to Studio, so an in-Sandbox ``codex exec`` can never call one.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from veadk.cli.codex_app_server import CodexDynamicToolResult

from .codex_tool_turn import DynamicTool, ToolTurnUnavailable, run_tool_turn

DELIVERY_TOOL_NAME = "reportDelivery"
DELIVERY_TOOL_DESCRIPTION = (
    "提交本次迁移交付的最终结论。必须调用一次，参数严格遵循给定的 JSON Schema；"
    "被拒绝时按返回的错误修正后重新调用。"
)
ARTIFACT_TOOL_NAME = "publishArtifact"
ARTIFACT_TOOL_DESCRIPTION = (
    "发布本次迁移交付的产物文件，由 Studio 读取并核对字节。"
    "参数 path 固定为 migration-result.zip。"
)

# ``askUser`` inside the closing turn: the analysis wording promises a read-only
# analysis, and this turn is about a delivery that already happened.
DELIVERY_ASK_TOOL_DESCRIPTION = (
    "在交付收尾过程中向用户提出必须由用户决定的问题，并等待用户回答。"
    "只在交付结论依赖用户才知道的信息时提问（例如缺失的密钥、部署目标、"
    "是否接受降级交付），一次提出 1-3 个问题，每个问题给出简短 header 和完整 question；"
    "有自然选择时给出 2-3 个 options（每个含 label 和 description，第一项为推荐项）。"
)

# The states the AgentKit CLI can settle a delivery in.  The turn may only report the
# one Studio derived from the Sandbox evidence.
DELIVERY_STATES = frozenset(
    {"succeeded", "succeeded_with_warnings", "partial", "failed"}
)
ARTIFACT_PATH = "migration-result.zip"
_MAX_MESSAGE_CHARS = 600
_MIN_MESSAGE_CHARS = 4
_MAX_WARNINGS = 8
_MAX_WARNING_CHARS = 400


DELIVERY_APP_SERVER_ENV = "AGENTKIT_MIGRATION_DELIVERY_APP_SERVER"
_DISABLED_VALUES = {"0", "false", "no", "off"}


def delivery_app_server_enabled() -> bool:
    """Whether a finished delivery is closed on a Studio Codex app-server turn.

    The turn explains the delivery the AgentKit CLI already settled and publishes its
    artifact, so it is additive: when the app-server is unreachable, or when this is
    switched off, the task keeps the CLI's own delivery state.  Set
    ``AGENTKIT_MIGRATION_DELIVERY_APP_SERVER=0`` to pin that scripted behaviour.
    """
    return (
        os.getenv(DELIVERY_APP_SERVER_ENV, "").strip().lower() not in _DISABLED_VALUES
    )


class DeliveryContractError(ValueError):
    """One delivery turn payload did not satisfy the delivery contract."""


class DeliveryTurnUnavailable(ToolTurnUnavailable):
    """The delivery turn ended without a verdict Studio can publish."""


@dataclass(frozen=True)
class PublishedArtifact:
    """An artifact Studio read back from the Sandbox and checked against the manifest."""

    path: str
    sha256: str
    size: int

    def public(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256, "size": self.size}


# Reads the artifact inside the Sandbox and returns its verified descriptor, or raises
# ``DeliveryContractError`` when the bytes disagree with what the CLI manifest says.
ArtifactPublisher = Callable[[str], PublishedArtifact]


def _exact_arguments(
    arguments: dict[str, object],
    *,
    expected: set[str],
    tool: str,
) -> None:
    """Reject arguments the tool schema does not describe.

    A dynamic tool result is typed JSON-RPC, and an unexpected field means the model is
    answering a different contract than the one Studio registered.
    """
    unknown = sorted(set(arguments) - expected)
    if unknown:
        raise DeliveryContractError(f"{tool} 不接受参数 " + "、".join(unknown))


def _bounded_text(value: object, field: str, limit: int, *, minimum: int = 1) -> str:
    if not isinstance(value, str):
        raise DeliveryContractError(f"{field} 必须是字符串")
    text = value.strip()
    if len(text) < minimum:
        raise DeliveryContractError(
            f"{field} 必须说明具体情况（至少 {minimum} 个字符）"
        )
    return text[:limit]


def _warnings(value: object) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise DeliveryContractError("warnings 必须是字符串数组")
    warnings: list[str] = []
    for entry in value[:_MAX_WARNINGS]:
        if not isinstance(entry, str):
            raise DeliveryContractError("warnings 必须是字符串数组")
        text = entry.strip()
        if text:
            warnings.append(text[:_MAX_WARNING_CHARS])
    return warnings


class DeliveryRecorder:
    """Validate and retain the artifact and the verdict of one delivery turn.

    ``expected_state`` is the state Studio derived from the Sandbox evidence, and any
    other state is rejected: the turn explains the delivery, it does not decide it.
    """

    def __init__(
        self,
        *,
        run_id: str,
        expected_state: str,
        publisher: ArtifactPublisher,
    ) -> None:
        self.run_id = run_id
        self.expected_state = expected_state
        self.artifact: PublishedArtifact | None = None
        self.verdict: dict[str, object] | None = None
        self.rejections: list[str] = []
        self._publisher = publisher

    @property
    def ready(self) -> bool:
        return self.verdict is not None

    def publish(self, arguments: dict[str, object]) -> CodexDynamicToolResult:
        try:
            _exact_arguments(
                arguments,
                expected={"path"},
                tool=ARTIFACT_TOOL_NAME,
            )
        except DeliveryContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(False, f"参数不符合协议（{error}）。")
        path = arguments.get("path")
        if path != ARTIFACT_PATH:
            self.rejections.append("artifact path")
            return CodexDynamicToolResult(
                False,
                f"产物路径必须是 {ARTIFACT_PATH}，而不是 {path!r}。",
            )
        try:
            artifact = self._publisher(ARTIFACT_PATH)
        except DeliveryContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(False, f"产物核对失败（{error}）。")
        except Exception as error:  # noqa: BLE001 - a Sandbox read must not kill the turn
            self.rejections.append(type(error).__name__)
            return CodexDynamicToolResult(
                False,
                "产物读取失败，请确认迁移产物已经生成后重新调用。",
            )
        self.artifact = artifact
        return CodexDynamicToolResult(
            True,
            f"产物已核对：path={artifact.path} sha256={artifact.sha256} "
            f"size={artifact.size}。请继续调用 {DELIVERY_TOOL_NAME} 提交结论。",
        )

    def report(self, arguments: dict[str, object]) -> CodexDynamicToolResult:
        try:
            _exact_arguments(
                arguments,
                expected={"state", "message", "warnings"},
                tool=DELIVERY_TOOL_NAME,
            )
        except DeliveryContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(False, f"参数不符合协议（{error}）。")
        state = arguments.get("state")
        if state not in DELIVERY_STATES:
            self.rejections.append("state")
            return CodexDynamicToolResult(
                False,
                "state 必须是 " + "、".join(sorted(DELIVERY_STATES)) + " 之一。",
            )
        if state != self.expected_state:
            self.rejections.append("state mismatch")
            return CodexDynamicToolResult(
                False,
                f"这次交付的 state 已经确定为 {self.expected_state}，"
                "请按沙箱里的交付证据重新调用。",
            )
        try:
            message = _bounded_text(
                arguments.get("message"),
                "message",
                _MAX_MESSAGE_CHARS,
                minimum=_MIN_MESSAGE_CHARS,
            )
            warnings = _warnings(arguments.get("warnings"))
        except DeliveryContractError as error:
            self.rejections.append(str(error))
            return CodexDynamicToolResult(False, f"结论不符合协议（{error}）。")
        if state == "failed" and self.artifact is not None:
            self.rejections.append("failed delivery published an artifact")
            return CodexDynamicToolResult(
                False,
                "这次交付已经失败，不应该有产物；请确认后重新调用。",
            )
        if state != "failed" and self.artifact is None:
            self.rejections.append("missing artifact")
            return CodexDynamicToolResult(
                False,
                f"请先调用 {ARTIFACT_TOOL_NAME} 发布产物，再提交结论。",
            )
        self.verdict = {"state": state, "message": message, "warnings": warnings}
        return CodexDynamicToolResult(True, "交付结论已接收，请结束本轮。")


async def run_delivery_turn(
    *,
    endpoint: str,
    prompt: str,
    cwd: str,
    run_id: str,
    expected_state: str,
    publisher: ArtifactPublisher,
    model: str = "",
    timeout_seconds: float,
    event_sink: Callable[[object], None] | None = None,
    extra_tools: Sequence[DynamicTool] = (),
    idle_timeout_seconds: float | None = None,
    host_wait_seconds: Callable[[], float] | None = None,
) -> dict[str, object] | None:
    """Publish the artifact and the verdict of one finished delivery.

    Returns the validated report, or ``None`` when the turn ended without one; the
    delivery state itself stays whatever the AgentKit CLI published.
    """
    recorder = DeliveryRecorder(
        run_id=run_id,
        expected_state=expected_state,
        publisher=publisher,
    )
    try:
        await run_tool_turn(
            endpoint=endpoint,
            prompt=prompt,
            cwd=cwd,
            tool_name=DELIVERY_TOOL_NAME,
            tool_description=DELIVERY_TOOL_DESCRIPTION,
            tool_schema=delivery_schema(expected_state),
            handler=recorder.report,
            has_result=lambda: recorder.ready,
            model=model,
            timeout_seconds=timeout_seconds,
            event_sink=event_sink,
            extra_tools=(
                DynamicTool(
                    name=ARTIFACT_TOOL_NAME,
                    description=ARTIFACT_TOOL_DESCRIPTION,
                    schema=artifact_schema(),
                    handler=recorder.publish,
                ),
                *extra_tools,
            ),
            idle_timeout_seconds=idle_timeout_seconds,
            host_wait_seconds=host_wait_seconds,
        )
    except ToolTurnUnavailable as error:
        # 任何回合故障都要变成调用方认识的那一种，否则它的兜底分支不会触发。
        raise DeliveryTurnUnavailable(str(error)) from error
    if recorder.verdict is None:
        return None
    return {
        "schema_version": 1,
        "run_id": run_id,
        "driver": "app-server",
        **recorder.verdict,
        "artifact": recorder.artifact.public() if recorder.artifact else None,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


def artifact_schema() -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["path"],
        "properties": {
            "path": {
                "type": "string",
                "description": f"产物文件名，固定为 {ARTIFACT_PATH}。",
            }
        },
    }


def delivery_schema(expected_state: str = "") -> dict[str, object]:
    """The verdict schema, narrowed to the state the Sandbox already published.

    Offering all four states invites a wrong pick - a successful delivery that carries a
    warning looks like ``succeeded_with_warnings`` - and a rejected verdict costs the
    whole attempt. The handler keeps checking the state as the server-side guard.
    """
    known = expected_state in DELIVERY_STATES
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["state", "message", "warnings"],
        "properties": {
            "state": {
                "type": "string",
                "enum": [expected_state] if known else sorted(DELIVERY_STATES),
                "description": (
                    f"本次交付的终态已经确定为 {expected_state}，只能是这个值。"
                    if known
                    else "本次交付的终态，必须与沙箱里的交付状态一致。"
                ),
            },
            "message": {
                "type": "string",
                "description": (
                    "给用户看的中文结论：成功时说明产物内容；失败时说明失败在哪一步、"
                    "关键证据是什么、用户下一步可以做什么。"
                ),
            },
            "warnings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "用户需要知道的迁移提示，没有就留空数组。",
            },
        },
    }


__all__ = [
    "ARTIFACT_PATH",
    "DELIVERY_APP_SERVER_ENV",
    "DELIVERY_ASK_TOOL_DESCRIPTION",
    "ARTIFACT_TOOL_DESCRIPTION",
    "ARTIFACT_TOOL_NAME",
    "DELIVERY_STATES",
    "DELIVERY_TOOL_DESCRIPTION",
    "DELIVERY_TOOL_NAME",
    "ArtifactPublisher",
    "DeliveryContractError",
    "DeliveryRecorder",
    "DeliveryTurnUnavailable",
    "PublishedArtifact",
    "artifact_schema",
    "delivery_app_server_enabled",
    "delivery_schema",
    "run_delivery_turn",
]
