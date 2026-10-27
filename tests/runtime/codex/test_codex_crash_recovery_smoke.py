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

"""A server killed mid-turn loses no conversation and repeats no tool.

Three VeADK processes serve one session stored in SQLite, each running the
real Codex binary against a stubbed Responses backend (no model is called):

1. Process A runs turn 1 to completion; its rollout is saved.
2. Process B runs turn 2: the agent books a table (once), then calls a tool
   that blocks, and B is killed (``SIGKILL``) inside it, so B never saves.
3. Process C runs turn 3 and must resume turn 1's Codex thread, be handed turn
   2 (message and tool result) back from the session transcript, and not run
   the tool again.

Run it with::

    CODEX_RUN_SMOKE=1 uv run --extra dev pytest -m codex_smoke -p no:xdist \\
        tests/runtime/codex/test_codex_crash_recovery_smoke.py -rs
"""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("openai_codex")

_TOOL_RESULT = "BOOKED-42"

# One invocation per process: argv = db, backend url, session id, message,
# bookings file. Prints the session's stored Codex thread afterwards.
_CHILD = r'''
import asyncio, json, sys

from google.adk.runners import Runner
from google.adk.sessions import DatabaseSessionService
from google.genai import types

from veadk import Agent
from veadk.runtime.codex.config import CodexRuntimeConfig
from veadk.runtime.codex.thread_store import ThreadKey, select_thread_store

db, url, session_id, text, bookings = sys.argv[1:6]


def book_table(guests: int) -> dict:
    """Book a restaurant table."""
    with open(bookings, "a", encoding="utf-8") as f:
        f.write(f"booked {guests}\n")
    return {"confirmation": "BOOKED-42"}


async def wait_for_kitchen() -> dict:
    """Wait until the kitchen confirms."""
    await asyncio.sleep(300)
    return {"kitchen": "ready"}


async def main() -> None:
    service = DatabaseSessionService(db_url=f"sqlite+aiosqlite:///{db}")
    if await service.get_session(
        app_name="crash", user_id="user", session_id=session_id
    ) is None:
        await service.create_session(
            app_name="crash", user_id="user", session_id=session_id
        )
    agent = Agent(
        name="crash_agent",
        description="Crash recovery probe.",
        instruction="Help the user.",
        runtime="codex",
        model_name="veadk-codex-probe-model",
        model_api_base=url,
        model_api_key="probe-key",
        model_api_key_name="",
        tools=[book_table, wait_for_kitchen],
        codex_runtime_config=CodexRuntimeConfig(
            model_transport="direct", reasoning_effort="minimal"
        ),
    )
    runner = Runner(app_name="crash", agent=agent, session_service=service)
    async for _ in runner.run_async(
        user_id="user",
        session_id=session_id,
        new_message=types.Content(role="user", parts=[types.Part(text=text)]),
    ):
        pass
    record = await select_thread_store(service).load(
        ThreadKey("crash", "user", session_id, "crash_agent")
    )
    print(json.dumps({"thread_id": record.thread_id if record else None}))


asyncio.run(asyncio.wait_for(main(), 120))
'''


class _Backend:
    """Responses stub. ``mode`` is ``"answer"`` or ``"book_then_wait"``."""

    def __init__(self) -> None:
        self.mode = "answer"
        self.bodies: list[str] = []
        self.tool_calls = 0
        self.waiting = threading.Event()
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return None

            def do_GET(self) -> None:
                self._send("application/json", b'{"data":[],"models":[]}')

            def do_POST(self) -> None:
                raw = self.rfile.read(int(self.headers.get("content-length", 0)))
                text = raw.decode("utf-8", "replace")
                backend.bodies.append(text)
                body = json.loads(raw or b"{}")
                outputs = {
                    item.get("call_id")
                    for item in body.get("input", [])
                    if isinstance(item, dict)
                    and item.get("type") == "function_call_output"
                }
                call: tuple[str, str, dict[str, Any]] | None = None
                if backend.mode == "book_then_wait" and "call_book" not in outputs:
                    backend.tool_calls += 1
                    call = ("call_book", "book_table", {"guests": 2})
                elif backend.mode == "book_then_wait" and "call_wait" not in outputs:
                    # The booking is done; the process dies in the next tool.
                    backend.waiting.set()
                    call = ("call_wait", "wait_for_kitchen", {})
                if call is not None:
                    item: dict[str, Any] = {
                        "type": "function_call",
                        "id": f"fc_{call[0]}",
                        "call_id": call[0],
                        "name": call[1],
                        "arguments": json.dumps(call[2]),
                        "status": "completed",
                    }
                    namespace = _namespace_of(call[1], body.get("tools"))
                    if namespace:
                        item["namespace"] = namespace
                else:
                    item = {
                        "type": "message",
                        "id": "msg",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "ok", "annotations": []}
                        ],
                    }
                usage = {
                    "input_tokens": 1,
                    "input_tokens_details": {"cached_tokens": 0},
                    "output_tokens": 1,
                    "output_tokens_details": {"reasoning_tokens": 0},
                    "total_tokens": 2,
                }
                events = (
                    {"type": "response.created", "response": {"id": "resp"}},
                    {
                        "type": "response.output_item.done",
                        "output_index": 0,
                        "item": item,
                    },
                    {
                        "type": "response.completed",
                        "response": {"id": "resp", "usage": usage},
                    },
                )
                self._send(
                    "text/event-stream",
                    b"".join(
                        f"event: {e['type']}\ndata: {json.dumps(e)}\n\n".encode()
                        for e in events
                    ),
                )

            def _send(self, content_type: str, data: bytes) -> None:
                self.send_response(200)
                self.send_header("content-type", content_type)
                self.send_header("content-length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"


def _namespace_of(name: str, tools: Any) -> str:
    """The namespace Codex advertises an MCP tool in (``mcp__<server>``)."""
    for tool in tools or []:
        if isinstance(tool, dict) and tool.get("type") == "namespace":
            for inner in tool.get("tools") or []:
                if isinstance(inner, dict) and inner.get("name") == name:
                    return str(tool.get("name"))
    return ""


def _db_contains(db: Path, needle: str) -> bool:
    """Whether any row of the session database mentions ``needle``."""
    if not db.exists():
        return False
    with sqlite3.connect(db, timeout=5) as conn:
        tables = [
            row[0]
            for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")
        ]
        return any(
            needle in str(row)
            for table in tables
            for row in conn.execute(f'SELECT * FROM "{table}"')  # noqa: S608
        )


@pytest.mark.codex_smoke
def test_a_turn_killed_mid_way_resumes_without_repeating_its_tool(tmp_path) -> None:
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip(
            "set CODEX_RUN_SMOKE=1 to spawn the real Codex binary "
            "(no model is called; the backend is stubbed)"
        )
    if not hasattr(signal, "SIGKILL"):
        pytest.skip("needs SIGKILL")
    db, bookings = tmp_path / "sessions.db", tmp_path / "bookings.txt"
    child = tmp_path / "child.py"
    child.write_text(_CHILD, encoding="utf-8")
    session_id = f"crash-{uuid.uuid4().hex[:8]}"
    backend = _Backend()

    def command(text: str) -> list[str]:
        return [
            sys.executable,
            str(child),
            str(db),
            backend.url,
            session_id,
            text,
            str(bookings),
        ]

    def run(text: str) -> dict[str, Any]:
        done = subprocess.run(
            command(text), capture_output=True, text=True, timeout=150
        )
        assert done.returncode == 0, done.stderr[-3000:]
        return json.loads(done.stdout.strip().splitlines()[-1])

    try:
        # 1. Process A: turn 1 completes and saves its rollout.
        first = run("remember the word PAPAYA")
        assert first["thread_id"], "turn 1 saved no Codex thread"

        # 2. Process B: the tool runs, then B is killed before it can save.
        backend.mode = "book_then_wait"
        victim = subprocess.Popen(
            command("book a table for two"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            assert backend.waiting.wait(120), "turn 2 never finished booking"
            deadline = time.monotonic() + 20
            while not _db_contains(db, _TOOL_RESULT):
                assert time.monotonic() < deadline, "tool result never persisted"
                time.sleep(0.2)
            victim.send_signal(signal.SIGKILL)
            victim.wait(30)
        finally:
            if victim.poll() is None:
                victim.kill()
        assert victim.returncode == -signal.SIGKILL

        # 3. Process C: a new process continues the session.
        backend.mode = "answer"
        resumed_from = len(backend.bodies)
        third = run("which booking did you make?")
    finally:
        backend.server.shutdown()

    assert bookings.read_text(encoding="utf-8").splitlines() == ["booked 2"], (
        "the tool ran again after the crash"
    )
    assert backend.tool_calls == 1
    assert third["thread_id"] == first["thread_id"], (
        "turn 3 did not resume the stored Codex thread"
    )
    turn_three = "\n".join(backend.bodies[resumed_from:])
    assert "remember the word PAPAYA" in turn_three, "turn 1 history was lost"
    assert "book a table for two" in turn_three, "the crashed turn was not handed back"
    assert _TOOL_RESULT in turn_three, "the crashed turn's tool result was lost"
