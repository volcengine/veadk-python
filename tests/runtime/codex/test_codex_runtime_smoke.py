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

"""One real end-to-end Codex turn: real binary, real sandbox, real shim socket.

Every other Codex test in this tree stubs at least one of three boundaries: the
model backend (``litellm.aresponses`` monkeypatched), the Codex subprocess
(faked), and the socket (``httpx.ASGITransport``, so ``ResponsesShim.start()``
is never called anywhere else). That leaves a class of deployment-blocking
failures with zero coverage: the Codex CLI binary spawning at all, OS sandbox
availability (macOS seatbelt / Linux landlock+seccomp), real port binding, the
shim's start/stop lifecycle, and whether the ``config.toml`` written by
``_prepare_codex_home`` is actually accepted by the pinned binary.

This test closes exactly that gap and nothing else. **There is no real model**:
the shim is pointed at a stub Responses backend served on another loopback
port, which replies with a canned script. So the only real things here are the
blockers above -- no network, no credentials, no model nondeterminism.

What the canned script drives, in order:

1. a call to *Codex's own* ``shell`` tool (``/bin/echo``), which Codex executes
   inside the OS sandbox -- this is the sandbox-establishment probe, and its
   output is read back off the next request;
2. a call to the agent's ADK tool, which the *shim* executes (Codex never sees
   it), proving the ADK tool path works over a real socket;
3. a final assistant message.

Opt in with ``CODEX_RUN_SMOKE=1``; the ``codex_smoke`` marker (registered in
``pytest.ini``) keeps it out of the parallel ``pytest -n 16`` CI job, which it
must never join: it binds two real ports and spawns a real subprocess.

    CODEX_RUN_SMOKE=1 pytest tests/runtime/codex/test_codex_runtime_smoke.py \
        -p no:xdist -s

Note: ``pytest_configure`` is deliberately NOT defined here. pytest only
collects that hook from ``conftest.py`` and plugins, never from a test module,
so a copy of the version in some other test files would be dead code.
"""

from __future__ import annotations

import asyncio
import contextlib
import importlib.util
import json
import os
import platform
import shutil
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

#: Echoed by Codex's own sandboxed command tool. Its presence in the tool
#: output is the proof that the OS sandbox was established and ran a command.
_SANDBOX_PROBE_MARKER = "veadk-codex-sandbox-probe-ok"
#: Written by the same probe: `sandbox="read_only"` must refuse the write, so
#: which of these comes back says whether the sandbox is actually enforcing.
_WRITE_ALLOWED_MARKER = "veadk-codex-write-allowed"
_WRITE_DENIED_MARKER = "veadk-codex-write-denied"
#: Path the probe tries to create, relative to the turn's workspace (cwd).
_WRITE_PROBE_FILE = "veadk-codex-write-probe"
#: Passed to the ADK tool by the stub backend and recorded by the tool body.
_TOOL_MARKER = "veadk-codex-smoke-tool-marker"
#: The canned final assistant message.
_FINAL_ANSWER = "veadk-codex-smoke-final-answer"
#: Name of the agent's ADK tool. Must match the function's `__name__`.
_ADK_TOOL_NAME = "veadk_smoke_record_marker"
#: Hard ceiling on the whole run, so a wedged subprocess fails the test instead
#: of hanging CI.
_RUN_TIMEOUT_SECONDS = 60.0


def _codex_binary() -> Path | None:
    """Resolve the Codex CLI the SDK would spawn, or None if unavailable."""
    try:
        from codex_cli_bin import bundled_codex_path  # type: ignore[import-not-found]
    except Exception:  # noqa: BLE001 - the bin package is an optional extra
        found = shutil.which("codex")
        return Path(found) if found else None
    try:
        path = Path(bundled_codex_path())
    except Exception:  # noqa: BLE001
        return None
    return path if path.exists() and os.access(path, os.X_OK) else None


def _skip_reason() -> str | None:
    """Three distinct skips: platform, SDK, binary. Never one blurred message."""
    system = platform.system()
    if system not in ("Darwin", "Linux"):
        return (
            f"codex smoke: unsupported platform {system!r}; the runtime's OS "
            "sandbox is macOS seatbelt / Linux landlock+seccomp only"
        )
    if importlib.util.find_spec("openai_codex") is None:
        return (
            "codex smoke: the `openai-codex` SDK is not installed "
            "(install the `codex` extra: uv sync --all-extras)"
        )
    if _codex_binary() is None:
        return (
            "codex smoke: no runnable Codex CLI binary "
            "(`openai-codex-cli-bin` missing, or its bundled binary is not "
            "executable on this platform)"
        )
    return None


class _StubResponsesBackend:
    """A scripted Responses API on 127.0.0.1:0, standing in for the model.

    The shim forwards through ``litellm.aresponses`` with
    ``custom_llm_provider="openai"``, which POSTs to ``{api_base}/responses``
    -- so this serves ``/v1/responses`` and speaks the Responses wire format,
    not chat completions.

    It is a state machine over the requests of a single turn, and it adapts to
    what Codex actually advertises: the sandbox probe is only sent if Codex
    offers a ``shell``-shaped function tool, and the ADK tool call is only sent
    once the shim has advertised the tool.
    """

    def __init__(self) -> None:
        self.url: str | None = None
        self.requests: list[dict[str, Any]] = []
        #: Raw output Codex reported for the sandboxed `shell` call, once seen.
        self.sandbox_probe_output: str | None = None
        self.shell_tool_name: str | None = None
        self._shell_call_id: str | None = None
        self._adk_call_sent = False
        self._server: uvicorn.Server | None = None
        self._task: asyncio.Task[Any] | None = None

        app = FastAPI()

        @app.post("/v1/responses")
        async def responses(request: Request) -> Any:  # noqa: D401
            body = await request.json()
            self.requests.append(body)
            self._capture_sandbox_probe(body)
            return JSONResponse(self._script(body))

        self._app = app

    async def start(self) -> str:
        config = uvicorn.Config(
            self._app, host="127.0.0.1", port=0, log_level="warning", lifespan="off"
        )
        server = uvicorn.Server(config)
        server.install_signal_handlers = lambda: None  # type: ignore[method-assign]
        self._server = server
        self._task = asyncio.create_task(server.serve())
        deadline = time.monotonic() + 10
        while not server.started:
            if self._task.done():
                raise RuntimeError("stub backend exited before binding")
            if time.monotonic() >= deadline:
                raise TimeoutError("stub backend did not bind within 10s")
            await asyncio.sleep(0.02)
        port = server.servers[0].sockets[0].getsockname()[1]
        self.url = f"http://127.0.0.1:{port}"
        return self.url

    async def stop(self) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._task is not None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._task, 10)

    # -- scripting ---------------------------------------------------------

    def _script(self, body: dict[str, Any]) -> dict[str, Any]:
        names = {
            tool.get("name")
            for tool in (body.get("tools") or [])
            if isinstance(tool, dict)
        }
        if self.shell_tool_name is None and self._shell_call_id is None:
            probe = _sandbox_probe_call(body.get("tools"))
            if probe is not None:
                self.shell_tool_name, arguments = probe
                self._shell_call_id = f"call_{uuid.uuid4().hex[:16]}"
                return self._response(
                    body,
                    [
                        self._function_call(
                            self.shell_tool_name,
                            arguments,
                            call_id=self._shell_call_id,
                        )
                    ],
                )
        if not self._adk_call_sent and _ADK_TOOL_NAME in names:
            self._adk_call_sent = True
            return self._response(
                body,
                [self._function_call(_ADK_TOOL_NAME, {"marker": _TOOL_MARKER})],
            )
        return self._response(body, [self._message(_FINAL_ANSWER)])

    def _capture_sandbox_probe(self, body: dict[str, Any]) -> None:
        """Read the sandboxed `shell` result out of the replayed conversation."""
        if self._shell_call_id is None or self.sandbox_probe_output is not None:
            return
        for item in body.get("input") or []:
            if not isinstance(item, dict):
                continue
            if item.get("type") != "function_call_output":
                continue
            if item.get("call_id") != self._shell_call_id:
                continue
            output = item.get("output")
            self.sandbox_probe_output = (
                output if isinstance(output, str) else json.dumps(output)
            )
            return

    @staticmethod
    def _function_call(
        name: str, arguments: dict[str, Any], *, call_id: str | None = None
    ) -> dict[str, Any]:
        cid = call_id or f"call_{uuid.uuid4().hex[:16]}"
        return {
            "type": "function_call",
            "id": f"fc_{uuid.uuid4().hex[:16]}",
            "call_id": cid,
            "name": name,
            "arguments": json.dumps(arguments),
            "status": "completed",
        }

    @staticmethod
    def _message(text: str) -> dict[str, Any]:
        return {
            "type": "message",
            "id": f"msg_{uuid.uuid4().hex[:16]}",
            "role": "assistant",
            "status": "completed",
            "content": [{"type": "output_text", "text": text, "annotations": []}],
        }

    @staticmethod
    def _response(body: dict[str, Any], output: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "id": f"resp_{uuid.uuid4().hex[:16]}",
            "object": "response",
            "created_at": int(time.time()),
            "model": body.get("model", "stub-model"),
            "status": "completed",
            "output": output,
            "parallel_tool_calls": False,
            "tool_choice": "auto",
            "tools": [],
            "usage": {
                "input_tokens": 11,
                "output_tokens": 7,
                "total_tokens": 18,
                "input_tokens_details": {"cached_tokens": 0},
                "output_tokens_details": {"reasoning_tokens": 0},
            },
        }


#: One command, two answers: it echoes a marker (proving the sandbox was
#: established and executed something) and then tries a write (proving
#: `sandbox="read_only"` is actually enforced, not merely configured).
_PROBE_SCRIPT = (
    f"/bin/echo {_SANDBOX_PROBE_MARKER}; "
    f"if /usr/bin/touch ./{_WRITE_PROBE_FILE} 2>/dev/null; "
    f"then /bin/echo {_WRITE_ALLOWED_MARKER}; "
    f"else /bin/echo {_WRITE_DENIED_MARKER}; fi"
)


def _sandbox_probe_call(tools: Any) -> tuple[str, dict[str, Any]] | None:
    """Codex's own command-execution tool and arguments for the probe.

    Matched structurally rather than by name: the pinned CLI (0.137) offers
    unified exec as ``exec_command`` with a ``cmd`` *string*, while older and
    other model families offer ``shell`` with a ``command`` *array*. Both
    shapes are handled so a CLI bump does not silently stop exercising the
    sandbox -- if neither is found the test fails loudly instead.

    The shim drops every non-``function`` tool before forwarding, so only
    function-shaped variants can be probed at all.
    """
    for tool in tools or []:
        if not isinstance(tool, dict) or tool.get("type") != "function":
            continue
        name = tool.get("name")
        if not isinstance(name, str):
            continue
        properties = (tool.get("parameters") or {}).get("properties") or {}
        if properties.get("cmd", {}).get("type") == "string":
            arguments: dict[str, Any] = {"cmd": _PROBE_SCRIPT, "login": False}
            if "yield_time_ms" in properties:
                arguments["yield_time_ms"] = 5000
            return name, arguments
        if properties.get("command", {}).get("type") == "array":
            return name, {"command": ["/bin/sh", "-c", _PROBE_SCRIPT]}
    return None


@pytest.mark.codex_smoke
@pytest.mark.asyncio
async def test_real_codex_binary_completes_one_tool_using_turn(monkeypatch) -> None:
    """Drive a real Codex subprocess through Runner over a real shim socket."""
    if os.getenv("CODEX_RUN_SMOKE") != "1":
        pytest.skip(
            "set CODEX_RUN_SMOKE=1 to spawn the real Codex binary "
            "(no model is called; the backend is stubbed)"
        )
    reason = _skip_reason()
    if reason is not None:
        pytest.skip(reason)

    from google.genai import types

    from veadk import Agent, Runner
    from veadk.runtime.codex import proxy as proxy_module
    from veadk.runtime.codex import runtime as runtime_module
    from veadk.runtime.codex.config import CodexRuntimeConfig
    from veadk.runtime.codex.proxy import ResponsesShim

    # Keep every wait bounded: a stalled backend call must not eat the run
    # budget, and the shim must fail rather than spin if it cannot bind.
    monkeypatch.setenv("CODEX_SHIM_TIMEOUT", "20")
    monkeypatch.setenv("CODEX_SHIM_START_TIMEOUT", "10")

    executed: list[str] = []

    def veadk_smoke_record_marker(marker: str) -> dict:
        """Record a marker string.

        Args:
            marker: Opaque text to record.

        Returns:
            dict: Echo of the recorded marker.
        """
        executed.append(marker)
        return {"status": "ok", "recorded": marker}

    backend = _StubResponsesBackend()
    backend_url = await backend.start()

    # Constructed and started DIRECTLY, never through `get_shim`: that helper
    # inserts into the process-global `_SHIMS` cache (a uvicorn server and a
    # port that outlive the test). `run_async` calls `get_shim` itself, so the
    # lookup -- and only the lookup -- is redirected to this instance.
    shim = ResponsesShim(api_base=f"{backend_url}/v1", api_key="veadk-smoke-key")
    shims_before = dict(proxy_module._SHIMS)
    await shim.start()
    assert shim.url and shim.url.startswith("http://127.0.0.1:"), (
        "the shim must bind a real loopback port, not an ASGI transport"
    )

    async def _shim_lookup(api_base: str, api_key: str) -> ResponsesShim:
        return shim

    monkeypatch.setattr(runtime_module, "get_shim", _shim_lookup)

    agent = Agent(
        name="codex_smoke_agent",
        description="Codex end-to-end smoke agent.",
        instruction="Call the tool once, then answer in one short sentence.",
        runtime="codex",
        model_name="veadk-codex-smoke-model",
        model_api_base=f"{backend_url}/v1",
        model_api_key="veadk-smoke-key",
        model_api_key_name="",
        tools=[veadk_smoke_record_marker],
        codex_runtime_config=CodexRuntimeConfig(
            reasoning_effort="minimal",
            sandbox="read_only",
            network_access=False,
            max_tool_iterations=2,
            tool_timeout_seconds=20.0,
        ),
    )
    runner = Runner(agent=agent, app_name="codex_smoke")

    temp_root = Path(tempfile.gettempdir())
    codex_homes_before = _codex_homes(temp_root)
    workspace_root = Path(runtime_module._SESSION_WORKSPACE_ROOT)
    workspaces_before = set(workspace_root.iterdir())
    # Dot-entries are excluded so a tool cache written by the test session
    # itself (`.pytest_cache`) cannot masquerade as a leak; a leaked workspace
    # would never be dot-prefixed.
    cwd_before = {name for name in os.listdir(os.getcwd()) if name[0] != "."}

    session_id = f"codex-smoke-{uuid.uuid4().hex[:8]}"
    user_id = "codex-smoke-user"
    await runner.short_term_memory.create_session(
        app_name="codex_smoke", user_id=user_id, session_id=session_id
    )

    events: list[Any] = []

    async def _drive() -> None:
        # `aclosing` so that a timeout still throws GeneratorExit into the
        # runtime's generator: that is what runs its `finally` (unregister the
        # turn, close toolsets, remove CODEX_HOME, reap the subprocess) instead
        # of leaving a live Codex process behind for the rest of the session.
        stream = runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user", parts=[types.Part(text="Run the smoke tool.")]
            ),
        )
        async with contextlib.aclosing(stream) as events_stream:
            async for event in events_stream:
                events.append(event)

    try:
        await asyncio.wait_for(_drive(), _RUN_TIMEOUT_SECONDS)
    finally:
        await shim.stop()
        await backend.stop()

    # -- the Codex binary really ran and really talked to the shim ---------
    assert backend.requests, (
        "the Codex subprocess never reached the shim: no backend request "
        "arrived, so either the binary did not spawn or it rejected the "
        "generated config.toml"
    )

    # -- the OS sandbox: established, or documented ------------------------
    assert backend.shell_tool_name is not None, (
        "Codex advertised no function-shaped command tool, so the OS sandbox "
        f"was never exercised; tools seen: {_tool_names(backend.requests)}"
    )
    probe_output = backend.sandbox_probe_output
    assert probe_output is not None, (
        f"Codex never reported a result for its {backend.shell_tool_name!r} "
        "call, so the sandboxed command neither succeeded nor failed visibly"
    )
    assert _SANDBOX_PROBE_MARKER in probe_output, (
        "the OS sandbox did not establish, or refused to run a trivial "
        f"read-only command. Codex reported: {probe_output!r}"
    )
    assert _WRITE_DENIED_MARKER in probe_output, (
        "sandbox='read_only' did not actually block a write from inside the "
        f"sandbox. Codex reported: {probe_output!r}"
    )

    # -- the ADK tool path over a real socket ------------------------------
    assert executed == [_TOOL_MARKER], (
        f"the ADK tool executor did not run exactly once: {executed!r}"
    )
    function_responses = [
        response
        for event in events
        for response in (event.get_function_responses() or [])
        if response.name == _ADK_TOOL_NAME
    ]
    assert function_responses, (
        "no function_response event reached the Runner for the ADK tool"
    )

    # -- a final text event ------------------------------------------------
    final_texts = [
        part.text
        for event in events
        if not event.partial and event.content and event.content.parts
        for part in event.content.parts
        if part.text and not part.thought
    ]
    assert any(_FINAL_ANSWER in text for text in final_texts), (
        f"the canned final answer never reached the Runner: {final_texts!r}"
    )

    # -- teardown left nothing behind --------------------------------------
    assert shim._turns == {}, (
        f"the turn was not unregistered from the shim: {list(shim._turns)}"
    )
    assert dict(proxy_module._SHIMS) == shims_before, (
        "the process-global shim cache was mutated; this test must construct "
        "ResponsesShim directly and never call get_shim()"
    )
    assert _codex_homes(temp_root) == codex_homes_before, (
        "a CODEX_HOME temp dir survived the turn: "
        f"{sorted(_codex_homes(temp_root) - codex_homes_before)}"
    )
    new_workspaces = set(workspace_root.iterdir()) - workspaces_before
    assert len(new_workspaces) == 1, (
        f"expected exactly one session workspace, got {sorted(new_workspaces)}"
    )
    # Session workspaces are deliberately kept for the next turn of the same
    # session and reaped later; what must not happen is one escaping the
    # process-owned root or landing in the working directory.
    workspace = next(iter(new_workspaces))
    assert workspace.parent == workspace_root
    assert not (workspace / _WRITE_PROBE_FILE).exists(), (
        "the read-only sandbox let Codex create a file in the workspace"
    )
    cwd_after = {name for name in os.listdir(os.getcwd()) if name[0] != "."}
    assert cwd_after == cwd_before, (
        "the turn created entries in the working directory: "
        f"{sorted(cwd_after - cwd_before)}"
    )
    shutil.rmtree(workspace, ignore_errors=True)


def _codex_homes(temp_root: Path) -> set[Path]:
    """Invocation-scoped CODEX_HOME dirs, excluding the workspace root.

    ``_prepare_codex_home`` and ``_SESSION_WORKSPACE_ROOT`` share the
    ``veadk-codex-`` prefix; only the former must be gone after a turn.
    """
    return {
        path
        for path in temp_root.glob("veadk-codex-*")
        if path.is_dir() and not path.name.startswith("veadk-codex-workspaces-")
    }


def _tool_names(requests: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(tool.get("name"))
            for request in requests
            for tool in (request.get("tools") or [])
            if isinstance(tool, dict)
        }
    )
