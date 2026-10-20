# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""The Sandbox `codex` shim: what it intercepts, what it logs, and its fallback."""

from __future__ import annotations

import asyncio
import json
import os
import pathlib
import shlex
import subprocess
import sys
import threading

import pytest

from frontend.server.migration import codex_exec_shim as shim
from frontend.server.migration.service import (
    _migration_codex_shim_lines,
    _parse_activity_log,
)

THREAD_ID = "01a0c900-43b7-7333-b191-1b500a8bb440"
TURN_ID = "01a0c900-43cd-78e0-8141-ac8d15cc1bd8"
MODEL = "doubao-seed-2-1-pro-260628"

CLI_FRESH = [
    "exec",
    "--cd",
    "/home/gem/project",
    "--skip-git-repo-check",
    "--dangerously-bypass-approvals-and-sandbox",
    "--json",
    "--output-last-message",
    "/tmp/last.txt",
    "--model",
    MODEL,
    "-",
]


def test_parse_exec_argv_reads_the_cli_form() -> None:
    invocation = shim.parse_exec_argv(CLI_FRESH)
    assert invocation is not None
    assert invocation.cwd == "/home/gem/project"
    assert invocation.model == MODEL
    assert invocation.last_message_path == "/tmp/last.txt"
    assert invocation.sandbox == "danger-full-access"
    assert shim.sandbox_policy(invocation) == {"type": "dangerFullAccess"}


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["exec", "resume", "0199-abc", "--json"], {"resume": "0199-abc"}),
        (["exec", "resume", "--last", "--json"], {"resume_last": True}),
        (
            [
                "exec",
                "--json",
                "--sandbox",
                "read-only",
                "--output-schema",
                "/s.json",
                "-",
            ],
            {"sandbox": "read-only", "output_schema_path": "/s.json"},
        ),
        (
            ["exec", "--json", "--sandbox", "workspace-write", "-"],
            {"sandbox": "workspace-write"},
        ),
        (["exec", "--json", "--full-auto", "-"], {"sandbox": "workspace-write"}),
        (
            ["exec", "--json", "--skip-git-repo-check", "--ignore-rules", "-"],
            {"sandbox": ""},
        ),
    ],
)
def test_parse_exec_argv_reads_every_form_the_cli_uses(
    argv: list[str], expected: dict[str, object]
) -> None:
    invocation = shim.parse_exec_argv(list(argv))
    assert invocation is not None
    for name, value in expected.items():
        assert getattr(invocation, name) == value


def test_parse_exec_argv_defers_anything_else() -> None:
    # Only the CLI's own JSON exec form is the shim's to run; everything else, and
    # any exec that would not have been logged as JSON, belongs to the real Codex.
    assert shim.parse_exec_argv(["mcp", "list"]) is None
    assert shim.parse_exec_argv([]) is None
    assert shim.parse_exec_argv(["exec", "--cd", "/w"]) is None


def test_sandbox_policy_never_grants_more_than_the_cli_asked() -> None:
    assert shim.sandbox_policy(shim.Invocation()) == {"type": "readOnly"}
    assert shim.sandbox_policy(shim.Invocation(sandbox="workspace-write")) == {
        "type": "workspaceWrite"
    }


def test_convert_item_carries_the_app_servers_own_numbers() -> None:
    entry = shim.convert_item(
        {
            "id": "call_1",
            "type": "commandExecution",
            "command": "/bin/bash -lc 'sleep 3'",
            "aggregatedOutput": "ok",
            "exitCode": 0,
            "durationMs": 2854,
        },
        completed=True,
    )
    assert entry is not None
    assert entry["type"] == "command_execution"
    assert entry["name"] == "运行命令"
    assert entry["duration_ms"] == 2854
    assert entry["command"] == "/bin/bash -lc 'sleep 3'"
    assert entry["aggregated_output"] == "ok"
    assert entry["exit_code"] == 0
    assert entry["status"] == "completed"


@pytest.mark.parametrize(
    "item", [{"id": "a", "type": "agentMessage", "text": ""}, {"id": "b"}]
)
def test_convert_item_skips_what_the_page_cannot_draw(item: dict[str, object]) -> None:
    assert shim.convert_item(item, completed=True) is None


def test_convert_plan_builds_the_todo_list() -> None:
    item = shim.convert_plan(
        {"plan": [{"step": "分析项目", "status": "completed"}, {"step": "改写入口"}]}
    )
    assert item is not None
    assert item["type"] == "todo_list"
    assert [row["completed"] for row in item["items"]] == [True, False]


def test_turn_line_reports_the_turns_own_cost() -> None:
    line = shim.turn_line(
        {
            "id": TURN_ID,
            "status": "completed",
            "startedAt": 1790078632,
            "completedAt": 1790078642,
            "durationMs": 9111,
        },
        usage={"totalTokens": 11968, "inputTokens": 11860, "outputTokens": 108},
        model=MODEL,
    )
    assert line["type"] == "turn.completed"
    assert line["turn"]["durationMs"] == 9111
    assert line["turn"]["model"] == MODEL
    assert line["usage"]["totalTokens"] == 11968


def test_a_failed_turn_closes_as_one() -> None:
    line = shim.turn_line({"id": TURN_ID, "status": "failed"}, usage={}, model="")
    assert line["type"] == "turn.failed"


def test_usage_is_this_turns_share_of_a_cumulative_thread() -> None:
    # The thread total is cumulative, so a turn's cost is the first update's own
    # increment plus every later increase of the total.
    turn = shim._AppServerTurn(None, lambda _line: None)
    turn._observe_usage({"last": {"inputTokens": 10, "outputTokens": 5}})
    turn._observe_usage({"total": {"inputTokens": 60, "outputTokens": 20}})
    turn._observe_usage({"total": {"inputTokens": 100, "outputTokens": 30}})
    assert turn._usage == {"inputTokens": 50, "outputTokens": 15}


class FakeAppServer:
    """The part of the Sandbox app-server one `codex exec` talks to.

    It runs on its own thread and loop so the shim can be driven synchronously, the
    way the CLI drives it.
    """

    def __init__(
        self,
        *,
        model: str = MODEL,
        status: str = "completed",
        step_seconds: int = 0,
    ) -> None:
        self.model = model
        self.status = status
        self.step_seconds = step_seconds
        self.turns = 0
        self.requests: list[dict[str, object]] = []
        self.port = 0
        self._ready = threading.Event()
        self._stop: asyncio.Event | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def __enter__(self) -> "FakeAppServer":
        self._thread = threading.Thread(target=self._serve_forever, daemon=True)
        self._thread.start()
        assert self._ready.wait(30), "fake app-server never started"
        return self

    def __exit__(self, *_error: object) -> None:
        assert self._loop is not None and self._stop is not None
        self._loop.call_soon_threadsafe(self._stop.set)
        assert self._thread is not None
        self._thread.join(timeout=30)

    def _serve_forever(self) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._main())

    async def _main(self) -> None:
        import websockets

        self._stop = asyncio.Event()
        async with websockets.serve(self._serve, "127.0.0.1", 0) as server:
            self.port = server.sockets[0].getsockname()[1]
            self._ready.set()
            await self._stop.wait()

    async def _serve(self, websocket: object) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            method = str(message.get("method") or "")
            if not method:
                continue
            self.requests.append(message)
            if "id" not in message:
                # A notification, e.g. the client's own `initialized`.
                continue
            if method == "turn/start":
                await websocket.send(
                    json.dumps(
                        {"id": message["id"], "result": {"turn": {"id": TURN_ID}}}
                    )
                )
                await self._play_turn(websocket)
                continue
            result: dict[str, object] = {}
            if method == "thread/start":
                result = {"thread": {"id": THREAD_ID}, "model": self.model}
            await websocket.send(json.dumps({"id": message["id"], "result": result}))

    async def _play_turn(self, websocket: object) -> None:
        self.turns += 1
        shift = self.step_seconds * (self.turns - 1)

        async def notify(method: str, params: dict[str, object]) -> None:
            await websocket.send(json.dumps({"method": method, "params": params}))

        await notify(
            "item/completed",
            {"item": {"id": "rs_1", "type": "reasoning", "summary": ["先跑一条命令"]}},
        )
        await notify(
            "item/started",
            {
                "item": {
                    "id": "call_1",
                    "type": "commandExecution",
                    "command": "sleep 3",
                }
            },
        )
        await notify(
            "item/completed",
            {
                "item": {
                    "id": "call_1",
                    "type": "commandExecution",
                    "command": "sleep 3",
                    "aggregatedOutput": "ok",
                    "exitCode": 0,
                    "durationMs": 2854,
                }
            },
        )
        await notify(
            "item/completed",
            {"item": {"id": "msg_1", "type": "agentMessage", "text": "DONE"}},
        )
        await notify(
            "thread/tokenUsage/updated", {"tokenUsage": {"last": {"inputTokens": 7}}}
        )
        await notify(
            "turn/completed",
            {
                "turn": {
                    "id": TURN_ID,
                    "status": self.status,
                    "startedAt": 1790078632 + shift,
                    "completedAt": 1790078642 + shift,
                    "durationMs": 9111,
                }
            },
        )


def run_shim_turn(
    server: FakeAppServer, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> tuple[int, list[dict[str, object]]]:
    """One `codex exec` line, driven through the shim against the fake app-server."""
    monkeypatch.setenv("STUDIO_MIGRATION_APP_SERVER", f"ws://127.0.0.1:{server.port}")
    lines: list[dict[str, object]] = []
    state: dict[str, object] = {}
    invocation = shim.parse_exec_argv(
        [
            "exec",
            "--cd",
            str(tmp_path),
            "--json",
            "--output-last-message",
            str(tmp_path / "last.txt"),
            "-",
        ]
    )
    assert invocation is not None

    async def drive() -> int:
        return await shim.serve_turn(
            invocation,
            lambda: "run a command",
            emit=lines.append,
            read_state=lambda: state,
            write_state=state.update,
        )

    return asyncio.run(drive()), lines


def test_one_exec_becomes_one_app_server_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    with FakeAppServer() as server:
        code, lines = run_shim_turn(server, monkeypatch, tmp_path)
        requests = list(server.requests)
    assert code == 0
    kinds = [line["type"] for line in lines]
    assert kinds[0] == "thread.started"
    assert lines[0]["thread_id"] == THREAD_ID
    assert kinds[-1] == "turn.completed"
    started_command = next(
        line["item"]
        for line in lines
        if line["type"] == "item.started"
        and isinstance(line.get("item"), dict)
        and line["item"].get("type") == "command_execution"
    )
    command = next(
        line["item"]
        for line in lines
        if line["type"] == "item.completed"
        and isinstance(line.get("item"), dict)
        and line["item"].get("type") == "command_execution"
    )
    assert "duration_ms" not in started_command
    assert command["duration_ms"] == 2854
    assert command["name"] == "运行命令"
    assert lines[-1]["turn"]["durationMs"] == 9111
    assert lines[-1]["turn"]["model"] == MODEL
    assert lines[-1]["usage"]["inputTokens"] == 7
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "DONE"
    thread_start = next(r for r in requests if r["method"] == "thread/start")
    turn_start = next(r for r in requests if r["method"] == "turn/start")
    assert thread_start["params"]["sandbox"] == "read-only"
    assert turn_start["params"]["sandboxPolicy"] == {"type": "readOnly"}


def test_the_shim_log_becomes_the_pages_turn_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """What the shim logs is exactly what the migration page settles a turn from."""
    with FakeAppServer() as server:
        _, lines = run_shim_turn(server, monkeypatch, tmp_path)
    content = (
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    ).encode()
    items = _parse_activity_log(content, 1, phase="migration")
    summary = next(item for item in items if item["id"] == "migration:1:turn-summary")
    assert summary["status"] == "completed"
    assert summary["turn"]["durationMs"] == 9111
    assert summary["turn"]["model"] == MODEL
    assert summary["turn"]["toolCalls"] == 1
    assert summary["turn"]["toolDurationComplete"] is True
    assert summary["turn"]["toolDurationMs"] == 2854
    assert summary["turn"]["usage"]["inputTokens"] == 7
    rows = [item for item in items if item["kind"] == "command"]
    assert [row["durationMs"] for row in rows] == [2854]
    assert rows[0]["itemType"] == "commandExecution"


CONTRACT_FINDINGS = json.dumps(
    {
        "status": "failed",
        "summary": {"fatal": 0, "repairable": 1, "degraded": 0, "info": 0},
        "fatal": [],
        "repairable": [
            {
                "name": "config:stability",
                "status": "failed",
                "severity": "repairable",
                "detail": "configuration matches the ak init baseline",
            }
        ],
        "degraded": [],
    },
    ensure_ascii=False,
)


def install_contract(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    failures: int,
    judged: bool = True,
) -> pathlib.Path:
    """A stand-in for the CLI's contract script, with a fixed number of bad runs.

    The shim reads the same two variables the migration prompt tells the model to use,
    so a fake validator only has to answer in the same shape: the CLI's own
    ``Validation finished:`` line and the findings file it leaves behind.
    """
    asset = tmp_path / "skills" / "source-to-veadk"
    scripts = asset / "scripts"
    scripts.mkdir(parents=True)
    output = tmp_path / "output"
    output.mkdir()
    counter = tmp_path / "contract-runs.txt"
    script = scripts / "validate_runtime.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -u\n"
        f"counter={shlex.quote(str(counter))}\n"
        f"findings={shlex.quote(str(output / 'validation_findings.json'))}\n"
        "runs=0\n"
        '[ -f "$counter" ] && runs="$(cat "$counter")"\n'
        "runs=$((runs + 1))\n"
        'printf "%s" "$runs" > "$counter"\n'
        f'if [ "$runs" -le {failures} ]; then\n'
        '  if [ "$VERDICT" = 1 ]; then\n'
        "    printf 'Validation finished: local=passed release=Failed blocking=true\\n'\n"
        "    printf 'Validation failed: configuration matches the ak init baseline\\n' >&2\n"
        "  fi\n"
        f"  printf '%s\\n' {shlex.quote(CONTRACT_FINDINGS)} > \"$findings\"\n"
        "  exit 1\n"
        "fi\n"
        "printf 'Validation finished: local=passed release=Passed blocking=false\\n'\n"
        'printf \'%s\\n\' \'{"status":"passed","fatal":[],"repairable":[],"degraded":[]}\' > "$findings"\n'
        "exit 0\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    monkeypatch.setenv("AGENTKIT_MIGRATE_ASSET_DIR", str(asset))
    monkeypatch.setenv("AGENTKIT_MIGRATE_OUTPUT_DIR", str(output))
    monkeypatch.setenv("VERDICT", "1" if judged else "0")
    return counter


def contract_rows(lines: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        line["item"]
        for line in lines
        if line["type"] == "item.completed"
        and isinstance(line.get("item"), dict)
        and line["item"].get("name") == shim._CONTRACT_ROW_NAME
    ]


def test_a_blocked_contract_is_repaired_inside_the_same_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    install_contract(tmp_path, monkeypatch, failures=1)
    with FakeAppServer() as server:
        code, lines = run_shim_turn(server, monkeypatch, tmp_path)
        requests = list(server.requests)
    turns = [r for r in requests if r["method"] == "turn/start"]
    assert code == 0
    assert len(turns) == 2, "the repair has to stay in this one exec"
    assert all(r["params"]["threadId"] == THREAD_ID for r in turns)
    repair = turns[1]["params"]["input"][0]["text"]
    assert "确定性校验未通过" in repair
    assert "config:stability" in repair
    assert "validation_findings.json" in repair
    assert [line["type"] for line in lines].count("thread.started") == 1
    assert [line["type"] for line in lines].count("turn.completed") == 1
    rows = contract_rows(lines)
    assert [row["status"] for row in rows] == ["failed", "completed"]
    assert [row["exit_code"] for row in rows] == [1, 0]
    assert "Validation failed" in rows[0]["aggregated_output"]
    assert rows[1]["name"] == shim._CONTRACT_ROW_NAME
    assert (tmp_path / "last.txt").read_text(encoding="utf-8") == "DONE"


def test_a_passing_contract_leaves_the_turn_alone(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    install_contract(tmp_path, monkeypatch, failures=0)
    with FakeAppServer() as server:
        code, lines = run_shim_turn(server, monkeypatch, tmp_path)
        turns = [r for r in server.requests if r["method"] == "turn/start"]
    assert code == 0
    assert len(turns) == 1
    rows = contract_rows(lines)
    assert [row["status"] for row in rows] == ["completed"]


def test_a_contract_without_a_verdict_never_holds_the_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """A validator the shim cannot read a verdict from is the CLI's business."""
    install_contract(tmp_path, monkeypatch, failures=1, judged=False)
    with FakeAppServer() as server:
        code, lines = run_shim_turn(server, monkeypatch, tmp_path)
        turns = [r for r in server.requests if r["method"] == "turn/start"]
    assert code == 0
    assert len(turns) == 1
    assert [row["status"] for row in contract_rows(lines)] == ["failed"]


def test_the_repair_budget_stops_the_loop(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    install_contract(tmp_path, monkeypatch, failures=99)
    with FakeAppServer() as server:
        code, lines = run_shim_turn(server, monkeypatch, tmp_path)
        turns = [r for r in server.requests if r["method"] == "turn/start"]
    assert code == 0
    assert len(turns) == shim._MAX_CONTRACT_REPAIRS + 1
    assert len(contract_rows(lines)) == shim._MAX_CONTRACT_REPAIRS + 1


def test_one_exec_with_several_sub_turns_reports_the_whole_window(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    install_contract(tmp_path, monkeypatch, failures=1)
    with FakeAppServer(step_seconds=20) as server:
        _, lines = run_shim_turn(server, monkeypatch, tmp_path)
    summary = next(line for line in lines if line["type"] == "turn.completed")
    assert summary["turn"]["startedAt"] == 1790078632
    assert summary["turn"]["completedAt"] == 1790078662
    assert summary["turn"]["durationMs"] == 30_000


def test_the_page_settles_the_repaired_exec_as_one_turn(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    install_contract(tmp_path, monkeypatch, failures=1)
    with FakeAppServer() as server:
        _, lines = run_shim_turn(server, monkeypatch, tmp_path)
    content = (
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines)
    ).encode()
    items = _parse_activity_log(content, 1, phase="migration")
    summaries = [item for item in items if item["id"] == "migration:1:turn-summary"]
    assert len(summaries) == 1
    assert summaries[0]["status"] == "completed"
    rows = [item for item in items if item["kind"] == "command"]
    assert [row["tool"]["name"] for row in rows] == [
        "运行命令",
        shim._CONTRACT_ROW_NAME,
        shim._CONTRACT_ROW_NAME,
    ]
    assert summaries[0]["turn"]["toolCalls"] == 3
    assert summaries[0]["turn"]["toolDurationComplete"] is True


def test_the_shim_install_block_puts_the_shim_ahead_of_the_real_codex() -> None:
    script = "\n".join(_migration_codex_shim_lines())
    assert 'export PATH="$studio_codex_shim_dir:$PATH"' in script
    # The real Codex has to be resolved before the shim takes the front of PATH, and
    # a repeat install must not record the shim itself as the real Codex.
    assert script.index("STUDIO_MIGRATION_REAL_CODEX") < script.index(
        'export PATH="$studio_codex_shim_dir:$PATH"'
    )
    assert "_MIGRATION_CODEX_SHIM_WRAPPER_PATH" not in script
    assert subprocess.run(["bash", "-n"], input=script, text=True).returncode == 0


class AppServerThatGoesAway(FakeAppServer):
    """Answers the handshake, then drops the connection mid-turn."""

    async def _serve(self, websocket: object) -> None:
        async for raw in websocket:
            message = json.loads(raw)
            if "id" not in message:
                continue
            await websocket.send(json.dumps({"id": message["id"], "result": {}}))
            if message.get("method") == "initialize":
                await websocket.close()
                return


def test_a_lost_app_server_does_not_leave_the_cli_waiting(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    with AppServerThatGoesAway() as server:
        monkeypatch.setenv(
            "STUDIO_MIGRATION_APP_SERVER", f"ws://127.0.0.1:{server.port}"
        )
        invocation = shim.parse_exec_argv(["exec", "--json", "-"])
        assert invocation is not None

        async def drive() -> int:
            return await shim.serve_turn(
                invocation,
                lambda: "run a command",
                emit=lambda _line: None,
                read_state=dict,
                write_state=lambda _value: None,
            )

        with pytest.raises(shim.CodexShimFallback):
            asyncio.run(asyncio.wait_for(drive(), timeout=30))


def test_a_fallback_does_not_consume_the_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The prompt is the CLI's stdin, so the shim must not read it speculatively."""
    monkeypatch.setattr(shim, "app_server_candidates", list)
    asked: list[bool] = []

    async def drive() -> int:
        return await shim.serve_turn(
            shim.Invocation(),
            lambda: (asked.append(True), "the prompt")[1],
            emit=lambda _line: None,
            read_state=dict,
            write_state=lambda _value: None,
        )

    with pytest.raises(shim.CodexShimFallback):
        asyncio.run(drive())
    assert asked == []


def test_the_real_codex_still_finds_the_prompt_on_a_fallback(tmp_path) -> None:
    real = tmp_path / "codex-real"
    real.write_text("#!/bin/sh\ncat\n", encoding="utf-8")
    real.chmod(0o755)
    runner = tmp_path / "runner.py"
    runner.write_text(
        "import importlib.util, sys\n"
        f"spec = importlib.util.spec_from_file_location('shim', {shim.__file__!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['shim'] = module\n"
        "spec.loader.exec_module(module)\n"
        "module.app_server_candidates = lambda: []\n"
        "sys.exit(module.main(sys.argv[1:]))\n",
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, str(runner), "exec", "--json", "-"],
        input="the migration prompt",
        capture_output=True,
        text=True,
        env={**os.environ, "STUDIO_MIGRATION_REAL_CODEX": str(real)},
        timeout=60,
    )
    assert result.returncode == 0
    assert result.stdout == "the migration prompt"
