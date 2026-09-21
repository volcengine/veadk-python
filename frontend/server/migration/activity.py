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
    """

    def __init__(
        self,
        write: Callable[[bytes], None],
        *,
        flush_seconds: float = DEFAULT_FLUSH_SECONDS,
        max_bytes: int = DEFAULT_MAX_BYTES,
    ) -> None:
        self._write = write
        self._flush_seconds = max(0.1, flush_seconds)
        self._max_bytes = max(1, max_bytes)
        self._lines: list[str] = []
        self._dirty = False
        self._texts: dict[str, str] = {}
        self._outputs: dict[str, str] = {}

    @property
    def lines(self) -> list[str]:
        return list(self._lines)

    def line(self, event: CodexAppServerEvent) -> dict[str, object] | None:
        """One ``codex exec --json`` line for ``event``; ``None`` when it has no item."""
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
        if kind == "thinking":
            return self._message_item(item_id, "reasoning", event.text, append=False)
        if kind == "commentary":
            return self._message_item(
                item_id, "agent_message", event.text, append=False
            )
        if kind == "text":
            # Live deltas: the reader keeps the last text it saw for an item.
            return self._message_item(item_id, "agent_message", event.text, append=True)
        if kind in {"text_snapshot", "assistant_final"}:
            return self._message_item(
                item_id, "agent_message", event.text, append=False
            )
        if kind == "tool":
            return self._tool_item(item_id, event)
        if kind == "tool_output":
            return self._output_item(item_id, event)
        if kind == "plan":
            return self._plan_item(event)
        return None

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
        return {
            "id": item_id,
            "type": "command_execution",
            "status": str(event.status or "running") or "running",
            "aggregated_output": value,
        }

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
        item_type = _TOOL_ITEM_TYPES.get(str(event.item_type or ""))
        if item_type is None:
            # Studio's own dynamic tools are the turn's contract, not page content.
            return None
        arguments = event.arguments if isinstance(event.arguments, dict) else {}
        response = event.response if isinstance(event.response, dict) else {}
        status = str(event.status or "running") or "running"
        item: dict[str, object] = {"id": item_id, "type": item_type, "status": status}
        if item_type == "command_execution":
            command = _text(arguments.get("command"), 20_000)
            if command:
                item["command"] = command
            output = response.get("output")
            if output not in (None, ""):
                item["aggregated_output"] = _bounded(output)
            exit_code = response.get("exitCode")
            if isinstance(exit_code, int) and not isinstance(exit_code, bool):
                item["exit_code"] = exit_code
            if output in (None, ""):
                item["aggregated_output"] = self._outputs.get(item_id, "")
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
