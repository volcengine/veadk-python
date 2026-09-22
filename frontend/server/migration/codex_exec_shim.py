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

"""Run the Sandbox migration CLI's `codex exec` on the Sandbox Codex app-server.

Studio installs this file ahead of ``codex`` on the Sandbox ``PATH`` before the
migration CLI runs.  The CLI still drives the migration, but its Codex work happens
on the app-server the Sandbox already hosts, which is what lets the page report the
same numbers the intelligent build reports: ``codex exec --json`` carries neither a
tool's ``duration_ms`` nor the turn's own ``startedAt``/``completedAt``/
``durationMs``/``model``, and the app-server carries all of them.

Only the CLI's own JSON exec form is intercepted.  Every other invocation — and any
failure to reach the app-server before the first log line — is handed to the real
Codex binary, so the CLI keeps behaving exactly as it did before.
"""

from __future__ import annotations

import asyncio
import json
import os
import shlex
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import IO, Any, Callable, Iterable

_REAL_CODEX_ENV = "STUDIO_MIGRATION_REAL_CODEX"
_APP_SERVER_ENV = "STUDIO_MIGRATION_APP_SERVER"
_STATE_ENV = "STUDIO_MIGRATION_SHIM_STATE"
_DEFAULT_APP_SERVER = "ws://127.0.0.1:8199"
_DEFAULT_REAL_CODEX = "/usr/local/libexec/codex-real"
_DEFAULT_STATE_PATH = "/tmp/studio-codex-shim-state.json"

# Codex' own labels, kept identical to the ones the app-server driver writes so a
# migration turn reads like an intelligent-build turn.
_COMMAND_NAME = "运行命令"
_FILE_CHANGE_NAME = "修改文件"
_WEB_SEARCH_NAME = "网络搜索"

_USAGE_KEYS = (
    "totalTokens",
    "inputTokens",
    "outputTokens",
    "cachedInputTokens",
    "cacheWriteInputTokens",
    "reasoningOutputTokens",
)

# `codex exec` flags that pick a sandbox without naming one.
_SANDBOX_FLAGS = {
    "--dangerously-bypass-approvals-and-sandbox": "danger-full-access",
    "--full-auto": "workspace-write",
}

# Flags that take the following token as their value.  Only some are read; the rest
# are skipped so an unexpected flag cannot be mistaken for the prompt.
_VALUE_FLAGS = {
    "--cd",
    "-C",
    "--model",
    "-m",
    "--output-last-message",
    "--output-schema",
    "--config",
    "-c",
    "--profile",
    "-p",
    "--sandbox",
    "-s",
    "--image",
    "-i",
    "--add-dir",
    "--local-provider",
    "--color",
    "--disable",
    "--enable",
}


class CodexShimFallback(RuntimeError):
    """The app-server could not take this call, so the real Codex must run it."""


@dataclass
class Invocation:
    """The part of a `codex exec` command line this shim needs."""

    prompt: str = ""
    resume: str = ""
    resume_last: bool = False
    cwd: str = ""
    model: str = ""
    last_message_path: str = ""
    output_schema_path: str = ""
    sandbox: str = ""


def parse_exec_argv(argv: list[str]) -> Invocation | None:
    """Read the CLI's `codex exec` form, or ``None`` to defer to the real Codex.

    The migration CLI runs ``codex exec [resume <id>|resume --last] --cd DIR
    --dangerously-bypass-approvals-and-sandbox --json --output-last-message FILE
    --model MODEL -``.  A command line this shim does not understand is not its to
    reinterpret, so anything without ``exec`` and ``--json`` runs on the real Codex.
    """
    if not argv or argv[0] != "exec":
        return None
    rest = list(argv[1:])
    invocation = Invocation()
    if rest and rest[0] == "resume":
        rest.pop(0)
        if rest and rest[0] == "--last":
            rest.pop(0)
            invocation.resume_last = True
        elif rest and not rest[0].startswith("-"):
            invocation.resume = rest.pop(0)
    json_output = False
    index = 0
    while index < len(rest):
        token = rest[index]
        value = ""
        if token in _VALUE_FLAGS:
            index += 1
            value = rest[index] if index < len(rest) else ""
        elif token.startswith("--") and "=" in token:
            token, _, value = token.partition("=")
        if token == "--json":
            json_output = True
        elif token in {"--cd", "-C"}:
            invocation.cwd = value
        elif token in {"--model", "-m"}:
            invocation.model = value
        elif token == "--output-last-message":
            invocation.last_message_path = value
        elif token == "--output-schema":
            invocation.output_schema_path = value
        elif token in {"--sandbox", "-s"}:
            if value in {"read-only", "workspace-write", "danger-full-access"}:
                invocation.sandbox = value
        elif token in _SANDBOX_FLAGS:
            invocation.sandbox = _SANDBOX_FLAGS[token]
        elif not token.startswith("-"):
            # `-` means stdin, which is what the CLI passes.
            invocation.prompt = token
        index += 1
    if not json_output:
        return None
    return invocation


def sandbox_policy(invocation: Invocation) -> dict[str, object]:
    """The app-server sandbox that matches what the CLI asked `codex exec` for.

    `codex exec` is conservative by default, so a command line that names no sandbox
    runs read-only here too: the shim must never hand out more access than the real
    Codex would.
    """
    mode = invocation.sandbox or "read-only"
    if mode == "danger-full-access":
        return {"type": "dangerFullAccess"}
    if mode == "workspace-write":
        return {"type": "workspaceWrite"}
    return {"type": "readOnly"}


def read_output_schema(path: str) -> object:
    """The JSON Schema the CLI pinned the model's final message to, if readable."""
    if not path:
        return None
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return None


def real_codex_command() -> str:
    """The Codex binary this shim defers to when the app-server is not an option."""
    configured = os.environ.get(_REAL_CODEX_ENV, "").strip()
    if configured:
        return configured
    if os.path.exists(_DEFAULT_REAL_CODEX):
        return _DEFAULT_REAL_CODEX
    return "codex-real"


def discover_app_servers() -> list[str]:
    """Every app-server URL the Sandbox is already listening on.

    The Sandbox starts its own app-server for the mounted Session, so the shim only
    has to find it: the listener publishes the address on its own command line.
    """
    found: list[str] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return found
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            with open(f"/proc/{entry}/cmdline", "rb") as handle:
                parts = handle.read().decode("utf-8", "replace").split("\x00")
        except OSError:
            continue
        if not any("app-server" in part for part in parts):
            continue
        for part in parts:
            if part.startswith("ws://") or part.startswith("wss://"):
                if part not in found:
                    found.append(part)
    return found


def app_server_candidates() -> list[str]:
    """The app-server URLs to try, in order of how specific they are."""
    candidates: list[str] = []
    configured = os.environ.get(_APP_SERVER_ENV, "").strip()
    for url in (configured, _DEFAULT_APP_SERVER, *discover_app_servers()):
        if url and url not in candidates:
            candidates.append(url)
    return candidates


def _text(value: object, limit: int = 20_000) -> str:
    if not isinstance(value, str):
        return ""
    value = value.strip()
    return value if len(value) <= limit else value[:limit]


def _status(item: dict[str, object], completed: bool) -> str:
    raw = str(item.get("status") or "").strip().lower()
    if raw in {"failed", "declined", "cancelled"}:
        return "failed"
    if raw == "completed" or completed:
        return "completed"
    return "running"


def _duration(item: dict[str, object]) -> int | None:
    value = item.get("durationMs")
    if isinstance(value, int) and not isinstance(value, bool) and value >= 0:
        return value
    return None


def convert_item(
    item: dict[str, object], *, completed: bool
) -> dict[str, object] | None:
    """One app-server item as the activity-log item the migration page reads.

    The page renders whatever the app-server reported, so the fields it reads are
    carried over unchanged: ``duration_ms`` is the tool's own time, ``name`` selects
    Codex' own row, and the item keeps the identity the app-server gave it.
    """
    raw_type = str(item.get("type") or "")
    entry: dict[str, object] = {
        "id": str(item.get("id") or ""),
        "status": _status(item, completed),
    }
    if raw_type == "commandExecution":
        entry["type"] = "command_execution"
        entry["name"] = _COMMAND_NAME
        command = _text(item.get("command"))
        if command:
            entry["command"] = command
        actions = item.get("commandActions")
        if isinstance(actions, list) and actions:
            entry["command_actions"] = actions
        output = item.get("aggregatedOutput")
        if isinstance(output, str) and output:
            entry["aggregated_output"] = _text(output, 200_000)
        exit_code = item.get("exitCode")
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            entry["exit_code"] = exit_code
    elif raw_type == "fileChange":
        entry["type"] = "file_change"
        entry["name"] = _FILE_CHANGE_NAME
        changes = item.get("changes")
        entry["changes"] = changes if isinstance(changes, list) else []
    elif raw_type == "mcpToolCall":
        server = _text(item.get("server"), 200)
        tool = _text(item.get("tool"), 200)
        entry["type"] = "mcp_tool_call"
        entry["name"] = "MCP · " + "/".join(part for part in (server, tool) if part)
        entry["server"] = server
        entry["tool"] = tool
        if isinstance(item.get("arguments"), dict):
            entry["arguments"] = item["arguments"]
        if completed and isinstance(item.get("result"), dict):
            entry["result"] = item["result"]
    elif raw_type == "webSearch":
        entry["type"] = "web_search"
        entry["name"] = _WEB_SEARCH_NAME
        query = _text(item.get("query"))
        if query:
            entry["query"] = query
    elif raw_type == "dynamicToolCall":
        entry["type"] = "dynamic_tool_call"
        entry["name"] = _text(item.get("tool"), 200)
        if isinstance(item.get("arguments"), dict):
            entry["arguments"] = item["arguments"]
        if completed:
            entry["result"] = {
                "success": item.get("success"),
                "contentItems": item.get("contentItems"),
            }
    elif raw_type == "agentMessage":
        text = _text(item.get("text"), 100_000)
        if not text:
            return None
        entry["type"] = "agent_message"
        entry["text"] = text
    elif raw_type == "reasoning":
        summary = item.get("summary")
        text = (
            "\n".join(part for part in summary if isinstance(part, str))
            if isinstance(summary, list)
            else _text(item.get("text"), 4_000)
        )
        text = _text(text, 4_000)
        if not text:
            return None
        entry["type"] = "reasoning"
        entry["text"] = text
    else:
        return None
    duration = _duration(item)
    if duration is not None:
        entry["duration_ms"] = duration
    return entry


def convert_plan(params: dict[str, object]) -> dict[str, object] | None:
    """`turn/plan/updated` as the todo list the migration page draws."""
    todos: list[dict[str, object]] = []
    for step in params.get("plan") or []:
        if not isinstance(step, dict):
            continue
        text = _text(step.get("step"), 4_000)
        if not text:
            continue
        todos.append(
            {
                "text": text,
                "completed": str(step.get("status") or "").strip().lower()
                in {"completed", "done"},
            }
        )
    if not todos:
        return None
    turn_id = str(params.get("turnId") or "")
    return {
        "id": f"plan-{turn_id}" if turn_id else "plan",
        "type": "todo_list",
        "items": todos,
    }


def usage_breakdown(value: object) -> dict[str, int]:
    """One app-server token breakdown, in the naming the page reads."""
    if not isinstance(value, dict):
        return {}
    counts: dict[str, int] = {}
    for key in _USAGE_KEYS:
        count = value.get(key)
        if isinstance(count, int) and not isinstance(count, bool) and count >= 0:
            counts[key] = count
    return counts


def subtract_usage(
    current: dict[str, int], previous: dict[str, int]
) -> dict[str, int] | None:
    """The tokens one call added, or ``None`` when the totals went backwards."""
    difference: dict[str, int] = {}
    for key, count in current.items():
        before = previous.get(key, 0)
        if count < before:
            return None
        difference[key] = count - before
    return difference


def add_usage(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    total = dict(left)
    for key, count in right.items():
        total[key] = total.get(key, 0) + count
    return total


def turn_line(
    turn: dict[str, object],
    *,
    usage: dict[str, int],
    model: str,
) -> dict[str, object]:
    """The turn's own cost, in the shape the migration page already settles.

    This is the one line `codex exec --json` cannot write: the CLI's stream has no
    turn object at all, so its reader has no elapsed time, model or usage to report.
    """
    raw_status = turn.get("status")
    if isinstance(raw_status, dict):
        raw_status = raw_status.get("type")
    status = str(raw_status or "").strip().lower() or "completed"
    event_type = {
        "failed": "turn.failed",
        "interrupted": "turn.interrupted",
    }.get(status, "turn.completed")
    summary: dict[str, object] = {
        "id": str(turn.get("id") or ""),
        "status": status,
    }
    for key in ("startedAt", "completedAt", "durationMs"):
        value = turn.get(key)
        if (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
            and value >= 0
        ):
            summary[key] = value
    if model:
        summary["model"] = model
    line: dict[str, object] = {"type": event_type, "turn": summary}
    if usage:
        line["usage"] = usage
    return line


class _Emitter:
    """The append-only log the CLI redirects to ``codex-attempt-N.jsonl``.

    Lines are flushed as they happen, exactly like Codex' own stream, because the
    page polls this file while the turn runs.
    """

    def __init__(self, stream: IO[str]) -> None:
        self._stream = stream
        self.wrote = False

    def line(self, value: dict[str, object]) -> None:
        self._stream.write(json.dumps(value, ensure_ascii=False) + "\n")
        self._stream.flush()
        self.wrote = True


class _AppServerTurn:
    """One JSON-RPC connection to the Sandbox app-server, for one `codex exec`."""

    def __init__(self, socket: Any, emit: Callable[[dict[str, object]], None]) -> None:
        self._socket = socket
        self._emit = emit
        self._pending: dict[int, asyncio.Future[dict[str, object]]] = {}
        self._next_id = 1
        self.turn_id = ""
        self.model = ""
        self.status = ""
        self.final_text = ""
        self.failure = ""
        self._completed = asyncio.Event()
        self._turn: dict[str, object] = {}
        self._usage: dict[str, int] = {}
        self._thread_total: dict[str, int] | None = None

    async def send(self, message: dict[str, object]) -> None:
        await self._socket.send(json.dumps(message))

    async def request(
        self, method: str, params: dict[str, object]
    ) -> dict[str, object]:
        identifier = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, object]] = (
            asyncio.get_running_loop().create_future()
        )
        self._pending[identifier] = future
        await self.send({"id": identifier, "method": method, "params": params})
        return await future

    async def notify(self, method: str) -> None:
        await self.send({"method": method})

    async def start(self) -> asyncio.Task[None]:
        """Start reading this connection: every request needs the reader running."""
        return asyncio.create_task(self._read())

    async def run_turn(
        self,
        *,
        thread_id: str,
        prompt: str,
        model: str,
        sandbox: dict[str, object],
        output_schema: object = None,
    ) -> None:
        await self.request(
            "turn/start",
            {
                "threadId": thread_id,
                "input": [{"type": "text", "text": prompt}],
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandboxPolicy": sandbox,
                **({"model": model} if model else {}),
                **({"outputSchema": output_schema} if output_schema else {}),
            },
        )
        self._emit({"type": "turn.started"})
        await self._completed.wait()

    async def _read(self) -> None:
        async for raw in self._socket:
            try:
                message = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(message, dict):
                continue
            if "id" in message and ("result" in message or "error" in message):
                future = self._pending.pop(message["id"], None)
                if future is not None and not future.done():
                    if "error" in message:
                        future.set_exception(
                            CodexShimFallback(f"app-server error {message['error']}")
                        )
                    else:
                        result = message.get("result")
                        future.set_result(result if isinstance(result, dict) else {})
                continue
            if "id" in message:
                await self._answer(message)
                continue
            self._notification(
                str(message.get("method") or ""),
                message.get("params"),
            )
        self._fail("app-server connection closed")

    def _fail(self, reason: str) -> None:
        """Hand every waiter its answer when the app-server stops answering.

        A request that was still in flight would otherwise wait forever, and the CLI
        would wait with it, so the connection going away has to unblock them all.
        """
        error = CodexShimFallback(reason)
        for identifier, future in list(self._pending.items()):
            self._pending.pop(identifier, None)
            if not future.done():
                future.set_exception(error)
        if not self._completed.is_set():
            self.status = "failed"
            self.failure = self.failure or reason
            self._completed.set()

    async def _answer(self, message: dict[str, object]) -> None:
        method = str(message.get("method") or "")
        if method in {
            "item/commandExecution/requestApproval",
            "item/fileChange/requestApproval",
            "item/permissions/requestApproval",
        }:
            await self.send({"id": message["id"], "result": {"decision": "accept"}})
            return
        await self.send(
            {
                "id": message["id"],
                "error": {
                    "code": -32601,
                    "message": f"unsupported server request {method}",
                },
            }
        )

    def _notification(self, method: str, params: object) -> None:
        payload = params if isinstance(params, dict) else {}
        if method in {"item/started", "item/completed"}:
            item = payload.get("item")
            if not isinstance(item, dict):
                return
            completed = method == "item/completed"
            if completed and item.get("type") == "agentMessage":
                text = _text(item.get("text"), 100_000)
                if text and str(item.get("phase") or "") != "commentary":
                    self.final_text = text
            converted = convert_item(item, completed=completed)
            if converted is not None:
                self._emit(
                    {
                        "type": "item.completed" if completed else "item.started",
                        "item": converted,
                    }
                )
            return
        if method == "turn/plan/updated":
            item = convert_plan(payload)
            if item is not None:
                self._emit({"type": "item.updated", "item": item})
            return
        if method == "thread/tokenUsage/updated":
            self._observe_usage(payload.get("tokenUsage"))
            return
        if method == "turn/completed":
            turn = payload.get("turn")
            if isinstance(turn, dict):
                self._turn = turn
                raw_status = turn.get("status")
                if isinstance(raw_status, dict):
                    raw_status = raw_status.get("type")
                self.status = str(raw_status or "").strip().lower()
                error = turn.get("error")
                if isinstance(error, dict) and error.get("message"):
                    self.failure = str(error["message"])
            self._completed.set()
            return
        if method == "error":
            message = payload.get("message")
            if isinstance(message, str) and message:
                self._emit({"type": "error", "message": message})

    def _observe_usage(self, value: object) -> None:
        """Accumulate this turn's tokens the way the app-server driver does.

        The thread total is cumulative, so the turn's own cost is the first update's
        ``last`` plus every later increase of ``total``.
        """
        if not isinstance(value, dict):
            return
        total = usage_breakdown(value.get("total"))
        last = usage_breakdown(value.get("last"))
        if not total and not last:
            return
        increment: dict[str, int] | None
        if self._thread_total is None:
            increment = last
        else:
            increment = subtract_usage(total, self._thread_total)
        if not increment:
            increment = last
        if total:
            self._thread_total = total
        if increment:
            self._usage = add_usage(self._usage, increment)

    def summary_line(self, model: str) -> dict[str, object]:
        """The turn's closing line, with the numbers the page shows.

        The app-server names the model it actually ran, which is the only source for
        a `codex exec` that did not name one itself.
        """
        turn = dict(self._turn)
        if self.turn_id:
            turn.setdefault("id", self.turn_id)
        reported = turn.get("model")
        if not model and isinstance(reported, str):
            model = reported
        return turn_line(turn, usage=self._usage, model=model or self.model)


async def serve_turn(
    invocation: Invocation,
    prompt_for: Callable[[], str],
    *,
    emit: Callable[[dict[str, object]], None],
    read_state: Callable[[], dict[str, object]],
    write_state: Callable[[dict[str, object]], None],
) -> int:
    """Run one `codex exec` on the Sandbox app-server and log it for the page."""
    import websockets

    socket = None
    failure = ""
    for url in app_server_candidates():
        try:
            socket = await websockets.connect(
                url, max_size=None, open_timeout=10, proxy=None
            )
            break
        except Exception as error:  # noqa: BLE001 - try the next address
            failure = f"{url} ({type(error).__name__})"
    if socket is None:
        raise CodexShimFallback(f"app-server unreachable at {failure or 'no address'}")
    # The CLI feeds the prompt on stdin, so it is read only once the app-server is
    # going to take the turn: a fallback to the real Codex still has to find it there.
    prompt = prompt_for()
    turn = _AppServerTurn(socket, emit)
    reader = await turn.start()
    try:
        return await _drive_turn(
            turn,
            invocation,
            prompt,
            emit=emit,
            read_state=read_state,
            write_state=write_state,
        )
    except CodexShimFallback:
        raise
    except Exception as trouble:  # noqa: BLE001 - a lost connection is a fallback
        raise CodexShimFallback(
            f"app-server connection failed ({type(trouble).__name__})"
        ) from trouble
    finally:
        reader.cancel()
        await close_socket(socket)


async def close_socket(socket: Any) -> None:
    """Let go of the connection without letting the goodbye become the answer."""
    try:
        await socket.close()
    except Exception:  # noqa: BLE001 - the turn is over either way
        return


async def _drive_turn(
    turn: _AppServerTurn,
    invocation: Invocation,
    prompt: str,
    *,
    emit: Callable[[dict[str, object]], None],
    read_state: Callable[[], dict[str, object]],
    write_state: Callable[[dict[str, object]], None],
) -> int:
    """Drive one turn over a live app-server connection and log it for the page."""
    await turn.request(
        "initialize",
        {
            "clientInfo": {"name": "studio-migration-shim", "version": "1"},
            "capabilities": {"experimentalApi": True},
        },
    )
    await turn.notify("initialized")
    mode = invocation.sandbox or "read-only"
    thread_id = invocation.resume
    if not thread_id and invocation.resume_last:
        thread_id = str(read_state().get("thread_id") or "")
    if thread_id:
        result = await turn.request(
            "thread/resume",
            {
                "threadId": thread_id,
                **({"cwd": invocation.cwd} if invocation.cwd else {}),
                **({"model": invocation.model} if invocation.model else {}),
            },
        )
    else:
        result = await turn.request(
            "thread/start",
            {
                **({"cwd": invocation.cwd} if invocation.cwd else {}),
                **({"model": invocation.model} if invocation.model else {}),
                "approvalPolicy": "never",
                "approvalsReviewer": "user",
                "sandbox": mode,
            },
        )
    thread = result.get("thread")
    if isinstance(thread, dict):
        reported = result.get("model") or thread.get("model")
        if isinstance(reported, str):
            turn.model = reported
    resume_id = str((thread or {}).get("id") or "") if isinstance(thread, dict) else ""
    if not resume_id:
        raise CodexShimFallback("app-server did not return a thread id")
    turn.turn_id = resume_id
    write_state({"thread_id": resume_id})
    emit({"type": "thread.started", "thread_id": resume_id})
    await turn.run_turn(
        thread_id=resume_id,
        prompt=prompt,
        model=invocation.model,
        sandbox=sandbox_policy(invocation),
        output_schema=read_output_schema(invocation.output_schema_path),
    )
    emit(turn.summary_line(invocation.model))
    if invocation.last_message_path and turn.final_text:
        try:
            with open(invocation.last_message_path, "w", encoding="utf-8") as handle:
                handle.write(turn.final_text)
        except OSError as error:
            print(f"studio codex shim: {error}", file=sys.stderr, flush=True)
    if turn.failure:
        print(f"studio codex shim: {turn.failure}", file=sys.stderr, flush=True)
    return 0 if turn.status in {"", "completed"} else 1


def read_state(path: str) -> dict[str, object]:
    try:
        with open(path, encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def write_state(path: str, value: dict[str, object]) -> None:
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(value, handle)
    except OSError:
        return


def run_real_codex(argv: list[str]) -> int:
    """Hand this call to the real Codex binary, exactly as the CLI issued it."""
    parts = [*shlex.split(real_codex_command()), *argv]
    try:
        os.execvp(parts[0], parts)
    except OSError as error:
        print(
            f"studio codex shim: real Codex is unavailable ({error})",
            file=sys.stderr,
        )
        return 127
    return 0


def main(argv: Iterable[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    invocation = parse_exec_argv(arguments)
    if invocation is None:
        return run_real_codex(arguments)

    def prompt_for() -> str:
        return invocation.prompt or sys.stdin.read()

    state_path = os.environ.get(_STATE_ENV, "").strip() or _DEFAULT_STATE_PATH
    emitter = _Emitter(sys.stdout)
    try:
        return asyncio.run(
            serve_turn(
                invocation,
                prompt_for,
                emit=emitter.line,
                read_state=lambda: read_state(state_path),
                write_state=lambda value: write_state(state_path, value),
            )
        )
    except CodexShimFallback as error:
        print(
            f"studio codex shim: {error}; running the real Codex instead",
            file=sys.stderr,
            flush=True,
        )
        if emitter.wrote:
            # This turn already announced a thread; running Codex as well would give
            # the CLI two sessions in one attempt.
            return 1
        return run_real_codex(arguments)
    except Exception as error:  # noqa: BLE001 - the CLI must not fail on shim trouble
        print(
            f"studio codex shim: {type(error).__name__}: {error}",
            file=sys.stderr,
            flush=True,
        )
        return 1 if emitter.wrote else run_real_codex(arguments)


def shim_source() -> str:
    """The shim program Studio installs into the Sandbox.

    Studio writes this module's own source into the Sandbox so the installed shim is
    exactly the code the tests exercise, with no second copy to keep in step.
    """
    return Path(__file__).read_text(encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
