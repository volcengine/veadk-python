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

"""Record an app-server analysis turn as the activity log the page already reads.

The scripted driver gets this log for free: ``codex exec --json`` writes its event
stream inside the Sandbox, and ``MigrationService.activity`` parses it into the items
the migration page renders.  An app-server turn never writes that file, so analysis on
the app-server driver showed an empty activity feed even though Codex was working.

Rather than teach the page a second source, this module translates the app-server's
typed events back into the same ``codex exec --json`` line shape, so exactly one reader
(``_parse_activity_log``) serves both drivers and the Sandbox stays the source of truth.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
import contextlib
import json
import logging

from veadk.cli.codex_app_server import CodexAppServerEvent

logger = logging.getLogger(__name__)

DEFAULT_FLUSH_SECONDS = 2.0
DEFAULT_MAX_BYTES = 4 * 1024 * 1024
_MAX_TEXT_CHARS = 120_000
_TRUNCATED_MARKER = "\n…内容已截断"

_COMPLETED_STATUSES = {"completed", "done"}
_FAILED_STATUSES = {"failed", "error", "declined"}

# The turn's own verdict, which the reader renders as one summary row the way the
# intelligent build renders its ``turn-summary`` block.
_TERMINAL_TURN_STATUSES = {"completed", "failed", "cancelled", "interrupted"}
_TURN_EVENT_TYPES = {
    "completed": "turn.completed",
    "failed": "turn.failed",
    "cancelled": "turn.interrupted",
    "interrupted": "turn.interrupted",
}
_TURN_FIELDS = ("startedAt", "completedAt", "durationMs", "model")

_TOOL_ITEM_TYPES = {
    "commandExecution": "command_execution",
    "fileChange": "file_change",
    "mcpToolCall": "mcp_tool_call",
    "webSearch": "web_search",
}

_TODO_STATUSES = {
    "completed": "completed",
    "done": "completed",
    "inprogress": "in_progress",
    "in_progress": "in_progress",
    "running": "in_progress",
    "failed": "failed",
    "error": "failed",
}


def _turn_status(value: object) -> str:
    """Read the turn status the app-server reports as a string or a tagged object."""
    if isinstance(value, dict):
        value = value.get("type")
    return str(value or "").strip().lower()


def _text(value: object, limit: int = _MAX_TEXT_CHARS) -> str:
    if not isinstance(value, str):
        return ""
    return value[:limit]


def _bounded(value: object, limit: int = _MAX_TEXT_CHARS) -> object:
    """Keep a payload small; the parser truncates and redacts what it renders."""
    if isinstance(value, str):
        return value[:limit]
    return value


class AnalysisActivityLog:
    """Turn an app-server turn's events into an append-only analysis activity log.

    ``record`` is the turn's event sink, so it must stay cheap: events are buffered and
    the Sandbox file is replaced as a whole by ``flush``, which the caller runs on a
    timer and once more when the turn ends.  A flush is best-effort by design — an
    activity feed must never fail an analysis.

    Studio's own dynamic tools are normally the turn's contract rather than page
    content.  The delivery turn is the exception: its ``publishArtifact`` call *is* the
    hand-over of the deliverable, so ``include_dynamic_tools`` records it the way the
    intelligent build records its result tool.
    """

    def __init__(
        self,
        write: Callable[[bytes], None],
        *,
        flush_seconds: float = DEFAULT_FLUSH_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
        include_dynamic_tools: bool = False,
    ) -> None:
        self._write = write
        self._flush_seconds = max(0.1, flush_seconds)
        self._max_bytes = max(1, max_bytes)
        self._include_dynamic_tools = include_dynamic_tools
        self._lines: list[str] = []
        self._dirty = False
        self._texts: dict[str, str] = {}
        self._outputs: dict[str, str] = {}
        self._names: dict[str, str] = {}
        self._commands: dict[str, str] = {}
        self._turn: dict[str, object] = {}
        self._usage: dict[str, object] = {}

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    def line(self, event: CodexAppServerEvent) -> dict[str, object] | None:
        """One ``codex exec --json`` line for ``event``; ``None`` when it has no item."""
        turn = self._turn_line(event)
        if turn is not None:
            return turn
        item = self._item(event)
        if item is None:
            return None
        return {"type": self._event_type(event), "item": item}

    def record(self, event: object) -> None:
        if not isinstance(event, CodexAppServerEvent):
            return
        line = self.line(event)
        if line is None:
            return
        self._lines.append(json.dumps(line, ensure_ascii=False))
        self._dirty = True

    def flush(self) -> None:
        """Replace the Sandbox log with everything recorded so far."""
        if not self._dirty:
            return
        self._write(self._content())
        self._dirty = False

    def complete_dynamic_tools(self) -> None:
        """Close Studio tool rows the turn ended on.

        A turn that finishes as soon as its verdict arrives can be interrupted before
        the app-server reports the call as completed, which would leave the page
        showing a running row for a delivery that already landed. Callers invoke this
        only once they accepted the turn's outcome, so a still-running row really is a
        call that succeeded.
        """
        if not self._include_dynamic_tools:
            return
        lines: list[str] = []
        for line in self._lines:
            try:
                event = json.loads(line)
            except ValueError:
                lines.append(line)
                continue
            item = event.get("item") if isinstance(event, dict) else None
            raw_status = (
                str(item.get("status") or "").lower() if isinstance(item, dict) else ""
            )
            if (
                isinstance(item, dict)
                and item.get("type") == "dynamic_tool_call"
                and raw_status not in _COMPLETED_STATUSES
                and raw_status not in _FAILED_STATUSES
            ):
                item["status"] = "completed"
                self._dirty = True
                lines.append(json.dumps(event, ensure_ascii=False))
                continue
            lines.append(line)
        self._lines = lines

    def close(self) -> None:
        try:
            self.flush()
        except Exception as error:  # noqa: BLE001 - the feed is not the analysis result
            logger.warning(
                "Studio migration activity log could not be written error_type=%s",
                type(error).__name__,
            )

    async def run(self) -> None:
        """Flush on a timer for as long as the caller keeps this task alive."""
        while True:
            await asyncio.sleep(self._flush_seconds)
            with contextlib.suppress(Exception):
                await asyncio.to_thread(self.flush)

    async def aclose(self) -> None:
        await asyncio.to_thread(self.close)

    def _content(self) -> bytes:
        lines = list(self._lines)
        size = sum(len(line) + 1 for line in lines)
        while lines and size > self._max_bytes:
            size -= len(lines.pop(0)) + 1
        return ("\n".join(lines) + "\n").encode("utf-8") if lines else b""

    def _turn_line(self, event: CodexAppServerEvent) -> dict[str, object] | None:
        """One line for the turn's own cost, written when the turn settles.

        The page reports the same turn metrics the intelligent build does — how long
        the turn took, how many tools it ran, what it cost in tokens — and the
        intelligent build reads them off the app-server's turn lifecycle and usage
        events rather than off any item.  Items never carry them, so they are
        accumulated here and written as one ``turn.*`` line that the reader turns into
        a summary of everything logged before it.
        """
        kind = str(event.kind or "")
        if kind == "usage":
            if event.usage is not None:
                self._usage["usage"] = event.usage.public_dict()
            if event.thread_total is not None:
                self._usage["thread_total"] = event.thread_total.public_dict()
            window = event.model_context_window
            if isinstance(window, int) and not isinstance(window, bool):
                self._usage["model_context_window"] = window
            return None
        if kind not in {"turn_started", "turn_completed"}:
            return None
        response = event.response if isinstance(event.response, dict) else {}
        turn = {**self._turn, **response}
        if event.turn_id:
            turn["id"] = event.turn_id
        status = _turn_status(event.status or turn.get("status"))
        if kind == "turn_started" or status not in _TERMINAL_TURN_STATUSES:
            self._turn = turn
            return None
        summary: dict[str, object] = {
            "type": _TURN_EVENT_TYPES.get(status, "turn.completed"),
            "turn": {
                "id": str(turn.get("id") or ""),
                "status": status,
                **{key: turn[key] for key in _TURN_FIELDS if key in turn},
            },
        }
        summary.update(self._usage)
        self._turn = {}
        self._usage = {}
        return summary

    def _event_type(self, event: CodexAppServerEvent) -> str:
        status = str(event.status or "").lower()
        if status in _FAILED_STATUSES:
            return "item.failed"
        if status in _COMPLETED_STATUSES:
            return "item.completed"
        return "item.updated"

    def _item(self, event: CodexAppServerEvent) -> dict[str, object] | None:
        item_id = str(event.item_id or "")
        kind = str(event.kind or "")
        item: dict[str, object] | None
        if kind == "thinking":
            item = self._message_item(item_id, "reasoning", event.text, append=False)
        elif kind == "commentary":
            item = self._message_item(
                item_id, "agent_message", event.text, append=False
            )
        elif kind == "text":
            # Live deltas: the reader keeps the last text it saw for an item.
            item = self._message_item(item_id, "agent_message", event.text, append=True)
        elif kind in {"text_snapshot", "assistant_final"}:
            item = self._message_item(
                item_id, "agent_message", event.text, append=False
            )
        elif kind == "tool":
            item = self._tool_item(item_id, event)
        elif kind == "tool_output":
            item = self._output_item(item_id, event)
        elif kind == "plan":
            item = self._plan_item(event)
        else:
            return None
        return self._timed(item, event)

    @staticmethod
    def _timed(
        item: dict[str, object] | None,
        event: CodexAppServerEvent,
    ) -> dict[str, object] | None:
        """Carry the app-server's own phase and timing onto the log line.

        The page renders these lines the way the intelligent build renders its own
        Codex activity, and that rendering reads ``phase`` and ``duration_ms`` off the
        item: a line that drops them turns a call that ran for minutes into one that
        looks like it never took any time.
        """
        if item is None:
            return None
        phase = str(event.phase or "")
        if phase:
            item["phase"] = phase
        duration = event.duration_ms
        if (
            isinstance(duration, int)
            and not isinstance(duration, bool)
            and duration >= 0
        ):
            item["duration_ms"] = duration
        return item

    def _message_item(
        self,
        item_id: str,
        item_type: str,
        text: str,
        *,
        append: bool,
    ) -> dict[str, object] | None:
        value = _text(text)
        if not value:
            return None
        if append and item_id:
            value = self._append(self._texts, item_id, value)
        elif item_id:
            self._texts[item_id] = value
        return {"id": item_id, "type": item_type, "text": value}

    def _output_item(
        self, item_id: str, event: CodexAppServerEvent
    ) -> dict[str, object] | None:
        value = _text(event.text)
        if not value:
            return None
        if item_id:
            value = self._append(self._outputs, item_id, value)
        item: dict[str, object] = {
            "id": item_id,
            "type": "command_execution",
            "status": str(event.status or "running") or "running",
            "aggregated_output": value,
        }
        # 输出增量常常是这一条 id 的最后一行，而它只带增量文本。页面要从行名认这条
        # 命令、从命令本身算标签，所以把这条调用已有的身份字段补齐，让最后读到的那
        # 一行和 app-server 报完成时那一行是同一件事。
        name = self._names.get(item_id, "") if item_id else ""
        if name:
            item["name"] = name
        command = self._commands.get(item_id, "") if item_id else ""
        if command:
            item["command"] = command
        return item

    @staticmethod
    def _append(store: dict[str, str], key: str, value: str) -> str:
        combined = f"{store.get(key, '')}{value}"
        if len(combined) > _MAX_TEXT_CHARS:
            combined = f"{_TRUNCATED_MARKER}\n{combined[-_MAX_TEXT_CHARS:]}"
        store[key] = combined
        return combined

    def _tool_item(
        self,
        item_id: str,
        event: CodexAppServerEvent,
    ) -> dict[str, object] | None:
        raw_type = str(event.item_type or "")
        item_type = _TOOL_ITEM_TYPES.get(raw_type)
        if item_type is None:
            if raw_type == "dynamicToolCall" and self._include_dynamic_tools:
                return self._dynamic_tool_item(item_id, event)
            # Studio's own dynamic tools are the turn's contract, not page content.
            return None
        arguments = event.arguments if isinstance(event.arguments, dict) else {}
        response = event.response if isinstance(event.response, dict) else {}
        status = str(event.status or "running") or "running"
        item: dict[str, object] = {"id": item_id, "type": item_type, "status": status}
        # The app-server names its own rows; the page labels them from that name so a
        # migration turn reads exactly like the intelligent build's turn.
        name = _text(event.name, 100)
        if name:
            item["name"] = name
            if item_id:
                self._names[item_id] = name
        if item_type == "command_execution":
            command = _text(arguments.get("command"), 20_000)
            if command:
                item["command"] = command
                if item_id:
                    self._commands[item_id] = command
            output = response.get("output")
            if output not in (None, ""):
                item["aggregated_output"] = _bounded(output)
            exit_code = response.get("exitCode")
            if isinstance(exit_code, int) and not isinstance(exit_code, bool):
                item["exit_code"] = exit_code
            if output in (None, ""):
                item["aggregated_output"] = self._outputs.get(item_id, "")
            actions = arguments.get("commandActions")
            if actions:
                item["command_actions"] = _bounded(actions)
            return item
        if item_type == "file_change":
            item["changes"] = _bounded(arguments.get("changes"))
            return item
        if item_type == "mcp_tool_call":
            server, _, tool = (
                str(event.name or "").removeprefix("MCP · ").partition("/")
            )
            item["server"] = server
            item["tool"] = tool
            item["arguments"] = _bounded(arguments)
            if response:
                item["result"] = _bounded(response)
            return item
        item["query"] = _text(arguments.get("query"), 4_000)
        return item

    @staticmethod
    def _dynamic_tool_item(
        item_id: str,
        event: CodexAppServerEvent,
    ) -> dict[str, object] | None:
        """One Studio tool call, in the same item shape the reader already parses."""
        item: dict[str, object] = {
            "id": item_id,
            "type": "dynamic_tool_call",
            "status": str(event.status or "running") or "running",
            "name": _text(event.name, 100) or "studio_tool",
        }
        arguments = event.arguments if isinstance(event.arguments, dict) else {}
        if arguments:
            item["arguments"] = _bounded(arguments)
        response = event.response if isinstance(event.response, dict) else {}
        if response:
            item["result"] = _bounded(response)
        return item

    def _plan_item(self, event: CodexAppServerEvent) -> dict[str, object] | None:
        steps = event.response if isinstance(event.response, list) else []
        todos: list[dict[str, object]] = []
        for step in steps:
            if not isinstance(step, dict):
                continue
            raw = str(step.get("status") or "").lower()
            text = _text(step.get("step"), 4_000)
            if not text:
                continue
            todos.append({"text": text, "status": _TODO_STATUSES.get(raw, "pending")})
        if not todos:
            return None
        return {
            "id": f"plan-{event.turn_id}" if event.turn_id else "plan",
            "type": "todo_list",
            "items": todos,
        }


__all__ = ["AnalysisActivityLog", "DEFAULT_FLUSH_SECONDS", "DEFAULT_MAX_BYTES"]
