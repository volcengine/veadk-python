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

"""Probe which Codex permission-profile layouts keep a session read-only.

Diagnostic only (no model is called): a stub Responses backend makes the real
Codex binary run one shell command per profile variant, and the script prints
what that command could read and write. Run on the platform to check::

    uv run --extra dev --extra codex python scripts/codex_sandbox_probe.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from openai_codex import ApprovalMode, AsyncCodex, CodexConfig

CHECKS = (
    "own_read",
    "own_write",
    "skill_read",
    "skill_write",
    "sibling_read",
    "home_config_read",
    "tmpdir_write",
    "slash_tmp_write",
)
STATE: dict = {"cmd": "", "outputs": []}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        return None

    def do_GET(self) -> None:
        self._send("application/json", b'{"data":[],"models":[]}')

    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        outputs = [
            item
            for item in body.get("input", [])
            if isinstance(item, dict) and item.get("type") == "function_call_output"
        ]
        if outputs:
            STATE["outputs"].append(str(outputs[-1].get("output")))
            item = {
                "type": "message",
                "id": "m",
                "role": "assistant",
                "status": "completed",
                "content": [{"type": "output_text", "text": "ok", "annotations": []}],
            }
        else:
            item = {
                "type": "function_call",
                "id": "fc",
                "call_id": "call_probe",
                "name": "exec_command",
                "arguments": json.dumps({"cmd": STATE["cmd"]}),
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
            {"type": "response.created", "response": {"id": "r"}},
            {"type": "response.output_item.done", "output_index": 0, "item": item},
            {"type": "response.completed", "response": {"id": "r", "usage": usage}},
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


def variants(tmp: str, own: str, skills: str) -> dict[str, str]:
    """``{name: permissions TOML}``; every variant denies the temp dirs."""
    head = (
        'default_permissions = "p"\nproject_root_markers = []\n#TABLES\n'
        '[permissions.p]\nextends = ":read-only"\n'
    )
    denied = sorted({tmp, os.path.realpath("/tmp")})  # the same dir on Linux
    deny = "[permissions.p.filesystem]\n" + "".join(
        f'"{path}" = "deny"\n' for path in denied
    )
    return {
        # What VeADK generates on macOS. Linux (Codex 0.159.2) cannot reach a
        # read grant under a denied parent: expected to fail there.
        "explicit-read": head + deny + f'"{own}" = "read"\n"{skills}" = "read"\n',
        # What VeADK generates on Linux: reachable, but writable.
        "explicit-write": head + deny + f'"{own}" = "write"\n"{skills}" = "write"\n',
        # Workspace-root grants; also unreachable on Linux (Codex 0.159.2).
        "workspace-roots-read": head
        + f'[permissions.p.workspace_roots]\n"{skills}" = true\n'
        + deny
        + '[permissions.p.filesystem.":workspace_roots"]\n"." = "read"\n',
    }


async def probe(port: int, name: str) -> None:
    tmp = os.path.realpath(tempfile.gettempdir())
    root = tempfile.mkdtemp(prefix="veadk-probe-ws-", dir=tmp)
    own, sibling = os.path.join(root, "own"), os.path.join(root, "other")
    os.makedirs(own)
    os.makedirs(sibling)
    with open(os.path.join(own, "AGENTS.md"), "w") as f:
        f.write("probe")
    with open(os.path.join(sibling, "secret.txt"), "w") as f:
        f.write("SECRET")
    home = os.path.realpath(tempfile.mkdtemp(prefix="veadk-probe-home-", dir=tmp))
    skills = os.path.join(home, "skills")
    os.makedirs(os.path.join(skills, "probe"))
    with open(os.path.join(skills, "probe", "SKILL.md"), "w") as f:
        f.write("---\nname: probe\ndescription: probe\n---\n")
    top, _, tables = variants(tmp, own, skills)[name].partition("#TABLES\n")
    with open(os.path.join(home, "config.toml"), "w") as f:
        f.write(
            top
            + 'model = "m"\nmodel_provider = "b"\napproval_policy = "never"\n'
            + "[model_providers.b]\n"
            + f'name = "b"\nbase_url = "http://127.0.0.1:{port}/v1"\n'
            + 'env_key = "K"\nwire_api = "responses"\n'
            + tables
        )
    STATE["cmd"] = "; ".join(
        (
            f"cat {own}/AGENTS.md >/dev/null 2>&1; echo own_read=$?",
            f"echo x > {own}/w 2>/dev/null; echo own_write=$?",
            f"cat {skills}/probe/SKILL.md >/dev/null 2>&1; echo skill_read=$?",
            f"echo x > {skills}/w 2>/dev/null; echo skill_write=$?",
            f"cat {sibling}/secret.txt >/dev/null 2>&1; echo sibling_read=$?",
            f"cat {home}/config.toml >/dev/null 2>&1; echo home_config_read=$?",
            f"echo x > {tmp}/veadk-w-$$ 2>/dev/null; echo tmpdir_write=$?",
            "echo x > /tmp/veadk-w-$$ 2>/dev/null; echo slash_tmp_write=$?",
        )
    )
    STATE["outputs"] = []
    try:
        config = CodexConfig(cwd=own, env={"CODEX_HOME": home, "K": "x"})
        async with AsyncCodex(config=config) as codex:
            thread = await codex.thread_start(
                model="m",
                model_provider="b",
                cwd=own,
                ephemeral=True,
                approval_mode=ApprovalMode.deny_all,
            )
            await asyncio.wait_for((await thread.turn("probe")).run(), 60)
    except Exception as e:  # noqa: BLE001 - the failure is the result
        print(f"{name:22} ERROR {type(e).__name__}: {str(e)[:200]}")
        return
    text = STATE["outputs"][-1] if STATE["outputs"] else ""
    got = dict(t.split("=", 1) for t in text.split() if t.split("=", 1)[0] in CHECKS)
    cells = " ".join(
        f"{k}={'ok' if got.get(k) == '0' else ('DENY' if k in got else '?')}"
        for k in CHECKS
    )
    print(f"{name:22} {cells}")


async def main() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    linux = sys.platform.startswith("linux")
    own = "ok" if linux else "DENY"  # VeADK grants Linux write; see runtime
    print(
        f"wanted ({sys.platform})  own_read=ok own_write={own} skill_read=ok "
        f"skill_write={own} sibling_read=DENY home_config_read=DENY "
        "tmpdir_write=DENY slash_tmp_write=DENY"
    )
    print(f"VeADK generates: {'explicit-write' if linux else 'explicit-read'}")
    for name in ("explicit-read", "explicit-write", "workspace-roots-read"):
        await probe(server.server_address[1], name)
    server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
