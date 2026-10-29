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

"""Real-sandbox check that one session's commands cannot reach another's files.

A stubbed Responses backend makes the real Codex binary run one probe command
through its own ``exec_command`` tool, on the direct transport, via ``Runner``.
No model is called. Run it on every platform VeADK is deployed on (the Linux
sandbox differs from macOS Seatbelt)::

    CODEX_RUN_SMOKE=1 uv run --extra dev pytest -m codex_smoke -p no:xdist \\
        tests/runtime/codex/test_codex_sandbox_isolation_smoke.py -rs
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import tempfile
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("openai_codex")

_CHECKS = (
    "own_read",
    "own_write",
    "skill_read",
    "sibling_read",
    "sibling_write",
    "home_read",
    "home_write",
    "tmpdir_write",
    "slash_tmp_write",
    "tmp_env",
    "proc_environ",
)


def _probe_command(own: str, sibling: str, home: str, skill: str) -> str:
    tmp = os.path.realpath(tempfile.gettempdir())
    environ = f"/proc/{os.getpid()}/environ"
    return "; ".join(
        (
            f"cat {own}/AGENTS.md >/dev/null 2>&1; echo own_read=$?",
            f"echo x > {own}/probe 2>/dev/null; echo own_write=$?",
            f"cat {skill} >/dev/null 2>&1; echo skill_read=$?",
            f"cat {sibling}/secret.txt >/dev/null 2>&1; echo sibling_read=$?",
            f"echo x > {sibling}/w 2>/dev/null; echo sibling_write=$?",
            f"cat {home}/sessions/rollout.jsonl >/dev/null 2>&1; echo home_read=$?",
            f"echo x >> {home}/config.toml 2>/dev/null; echo home_write=$?",
            f"echo x > {tmp}/veadk-probe-$$ 2>/dev/null; echo tmpdir_write=$?",
            "echo x > /tmp/veadk-probe-$$ 2>/dev/null; echo slash_tmp_write=$?",
            "python3 -c 'import tempfile; tempfile.NamedTemporaryFile()' "
            "2>/dev/null; echo tmp_env=$?",
            f"test -e {environ} && (cat {environ} >/dev/null 2>&1; "
            "echo proc_environ=$?) || echo proc_environ=absent",
        )
    )


class _Backend:
    """Responses stub: one ``exec_command`` call, then a final message."""

    def __init__(self, command: str) -> None:
        self.command = command
        self.outputs: list[str] = []
        self.bodies: list[str] = []
        backend = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, format: str, *args: Any) -> None:
                return None

            def do_GET(self) -> None:
                self._send("application/json", b'{"data":[],"models":[]}')

            def do_POST(self) -> None:
                size = int(self.headers.get("content-length", 0))
                raw = self.rfile.read(size) or b"{}"
                backend.bodies.append(raw.decode("utf-8", "replace"))
                body = json.loads(raw)
                outputs = [
                    item
                    for item in body.get("input", [])
                    if isinstance(item, dict)
                    and item.get("type") == "function_call_output"
                ]
                if outputs:
                    backend.outputs.append(str(outputs[-1].get("output")))
                    item: dict[str, Any] = {
                        "type": "message",
                        "id": "msg",
                        "role": "assistant",
                        "status": "completed",
                        "content": [
                            {"type": "output_text", "text": "done", "annotations": []}
                        ],
                    }
                else:
                    item = {
                        "type": "function_call",
                        "id": "fc",
                        "call_id": "call_probe",
                        "name": "exec_command",
                        "arguments": json.dumps({"cmd": backend.command}),
                        "status": "completed",
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
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"


@pytest.mark.codex_smoke
@pytest.mark.asyncio
@pytest.mark.parametrize("sandbox", ["workspace_write", "read_only"])
async def test_sandboxed_commands_reach_only_their_own_session(
    sandbox: str, monkeypatch
) -> None:
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip(
            "set CODEX_RUN_SMOKE=1 to spawn the real Codex binary "
            "(no model is called; the backend is stubbed)"
        )
    from google.adk.runners import Runner
    from google.adk.sessions.in_memory_session_service import (
        InMemorySessionService,
    )
    from google.genai import types

    from veadk import Agent
    from veadk.runtime import get_runtime
    from veadk.runtime.codex import runtime as runtime_module
    from veadk.runtime.codex.config import CodexRuntimeConfig
    from veadk.runtime.codex.mcp_bridge import shutdown_bridge

    get_runtime.cache_clear()
    # Another session's workspace (same root) and another invocation's home.
    root = Path(runtime_module._SESSION_WORKSPACE_ROOT)
    sibling = root / f"other-{uuid.uuid4().hex[:8]}"
    sibling.mkdir()
    (sibling / "secret.txt").write_text("SECRET")
    home = Path(tempfile.mkdtemp(prefix="veadk-codex-"))
    (home / "sessions").mkdir()
    (home / "sessions" / "rollout.jsonl").write_text("{}\n")
    (home / "config.toml").write_text("")

    # A workspace AGENTS.md is still loaded; Codex's search above the
    # workspace (denied) once failed every `read_only` turn on Linux.
    session_id = f"isolation-{uuid.uuid4().hex[:8]}"
    ctx = SimpleNamespace(
        session=SimpleNamespace(id=session_id, app_name="isolation", user_id="user"),
        agent=SimpleNamespace(name="isolation_agent"),
    )
    own = runtime_module._prepare_workspace(CodexRuntimeConfig(), ctx)  # type: ignore[arg-type]
    Path(own, "AGENTS.md").write_text("WORKSPACE-AGENTS-MARKER")
    backend = _Backend("")
    real_sync = runtime_module.sync_skills_to_codex_home

    def sync_with_probe_skill(agent: Any, codex_home: str, **kwargs: Any) -> int:
        # The invocation's own CODEX_HOME is only known here.
        written = real_sync(agent, codex_home, **kwargs)
        skill = Path(codex_home, "skills", "probe_skill", "SKILL.md")
        skill.parent.mkdir(parents=True, exist_ok=True)
        skill.write_text("---\nname: probe_skill\ndescription: probe\n---\n")
        backend.command = _probe_command(own, str(sibling), str(home), str(skill))
        return written

    monkeypatch.setattr(
        runtime_module, "sync_skills_to_codex_home", sync_with_probe_skill
    )
    agent = Agent(
        name="isolation_agent",
        description="Sandbox isolation probe.",
        instruction="Run the probe.",
        runtime="codex",
        model_name="veadk-codex-probe-model",
        model_api_base=backend.url,
        model_api_key="probe-key",
        model_api_key_name="",
        codex_runtime_config=CodexRuntimeConfig(
            model_transport="direct",
            sandbox=sandbox,  # type: ignore[arg-type]
            network_access=False,
            reasoning_effort="minimal",
        ),
    )
    service = InMemorySessionService()
    await service.create_session(
        app_name="isolation", user_id="user", session_id=session_id
    )
    runner = Runner(app_name="isolation", agent=agent, session_service=service)

    async def _drive() -> None:
        async for _ in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text="probe")]),
        ):
            pass

    try:
        await asyncio.wait_for(_drive(), 120)
    finally:
        await runtime_module._PROCESS_POOL.close_all()
        await shutdown_bridge()
        backend.server.shutdown()
        shutil.rmtree(sibling, ignore_errors=True)
        shutil.rmtree(home, ignore_errors=True)

    assert backend.outputs, "Codex never ran the probe command"
    assert "WORKSPACE-AGENTS-MARKER" in backend.bodies[0], "workspace AGENTS.md lost"
    got = dict(
        token.split("=", 1)
        for token in backend.outputs[-1].split()
        if token.split("=", 1)[0] in _CHECKS
    )
    assert got.get("own_read") == "0", got
    assert got.get("skill_read") == "0", got
    if sandbox == "workspace_write":
        assert got.get("own_write") == "0", got
        assert got.get("tmp_env") == "0", got  # TMPDIR points into the workspace
    elif not sys.platform.startswith("linux"):
        # Linux grants it `write` to work around Codex's sandbox bug; see
        # `runtime._nested_read_access`.
        assert got.get("own_write") not in (None, "0"), got
    for denied in (
        "sibling_read",
        "sibling_write",
        "home_read",
        "home_write",
        "tmpdir_write",
        "slash_tmp_write",
    ):
        assert got.get(denied) not in (None, "0"), (denied, got)
    if sys.platform.startswith("linux"):
        # The VeADK process's environment holds the real credentials.
        assert got.get("proc_environ") != "0", got
