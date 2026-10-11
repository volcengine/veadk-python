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

"""Offline adapters binding each runtime to the conformance harness.

Every adapter replays a ``scripted_backend.Round`` plan at the lowest layer
that runtime reaches the model through, so everything above that layer --
prompt building, tool bridging, event translation, the ``Runner`` -- is the
production code path:

``adk``
    A ``BaseLlm`` wrapping ``ScriptedBackend.as_base_llm``. Under
    ``StreamingMode.SSE`` it also yields one ``partial`` chunk per text part
    before the aggregated response, the way real streaming models do, so the
    streaming scenario means the same thing for every runtime.

``codex``
    The differential suite's ``ShimDrivingCodex`` stands in for the Codex
    app-server and drives the *real* Responses shim over ``ASGITransport``;
    ``litellm.aresponses`` is the scripted model. One shim serves every agent
    of a test (as in production, where it is memoized per backend), so
    requests are routed to a per-agent backend by a tag in the agent's
    instruction, which reaches every request as ``instructions``.

``piagent``
    A real subprocess (``fake_pi_backend.py``) speaking Pi's RPC protocol, with
    the scripted model inside it. ADK tools are executed over the runtime's
    real per-turn HTTP bridge; see that module's docstring. Not emulated: a
    ``Round.raises`` other than ``HANG`` (the model lives in another process),
    Pi's own built-in tools, and Pi-side compaction.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
import json
import os
import shutil
import stat
import sys
import uuid
from pathlib import Path
from typing import Any, Iterable, Sequence

from google.genai import types

import fake_codex_sdk
from conformance_harness import (
    Capability,
    HangForever,
    ModelRequest,
    RuntimeAdapter,
    ScriptedAgent,
)
from scripted_backend import Round, ScriptedBackend

AGENT_NAME = "conformance_agent"
_API_BASE = "https://backend.invalid/v1"
_API_KEY = "backend-key"


def _backend_tag(key: str) -> str:
    return f"[conformance-backend:{key}]"


def _instruction(key: str) -> str:
    return f"Answer the user. {_backend_tag(key)}"


def _key_from(text: str, keys: Iterable[str]) -> str | None:
    for key in keys:
        if _backend_tag(key) in text:
            return key
    return None


def _dump(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, default=str, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return str(value)


async def _park(probe: Any) -> None:
    """Block like a model that never answers, noting when that is abandoned."""
    probe.entered.set()
    try:
        await asyncio.Event().wait()
    except asyncio.CancelledError:
        probe.abandoned = True
        raise


# ------------------------------------------------------------------------ adk


def _adk_request(llm_request: Any) -> ModelRequest:
    config = getattr(llm_request, "config", None)
    chunks: list[str] = []
    system = getattr(config, "system_instruction", None)
    if system is not None:
        parts = getattr(system, "parts", None)
        if parts is not None:
            chunks.extend(p.text for p in parts if getattr(p, "text", None))
        else:
            chunks.append(str(system))
    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            if part.text:
                chunks.append(f"{content.role}: {part.text}")
            if part.function_call is not None:
                call = part.function_call
                chunks.append(f"function_call {call.name} {_dump(call.args)}")
            if part.function_response is not None:
                response = part.function_response
                chunks.append(
                    f"function_response {response.name} {_dump(response.response)}"
                )
    tool_names: list[str] = []
    for tool in getattr(config, "tools", None) or []:
        for declaration in getattr(tool, "function_declarations", None) or []:
            if declaration.name:
                tool_names.append(str(declaration.name))
    return ModelRequest(text="\n".join(chunks), tool_names=tuple(tool_names))


class AdkAdapter(RuntimeAdapter):
    """ADK's own ``BaseLlmFlow``: the reference every runtime is held to."""

    name = "adk"
    capabilities = frozenset(
        {Capability.APPROVALS, Capability.MCP_TOOLS, Capability.SKILLS}
    )
    streams_partials = True
    # ADK lists skills only through SkillToolset's own tool, not in the prompt.
    skill_discovery_tool = "list_skills"

    def __init__(self, monkeypatch: Any, tmp_path: Any) -> None:
        super().__init__(monkeypatch, tmp_path)
        self._requests: dict[str, list[ModelRequest]] = {}

    def setup(self) -> None:
        from veadk.runtime import get_runtime
        from veadk.runtime.compat import reset_warning_state

        get_runtime.cache_clear()
        reset_warning_state()

    def teardown(self) -> None:
        from veadk.runtime import get_runtime
        from veadk.runtime.compat import reset_warning_state

        get_runtime.cache_clear()
        reset_warning_state()

    def build(
        self,
        plan: Iterable[Round],
        *,
        key: str = "main",
        tools: Sequence[Any] = (),
        **agent_kwargs: Any,
    ) -> ScriptedAgent:
        from google.adk.models.base_llm import BaseLlm
        from google.adk.models.llm_response import LlmResponse

        from veadk import Agent

        rounds = tuple(plan)
        inner = ScriptedBackend(rounds, arm="adk").as_base_llm()
        requests = self._requests.setdefault(key, [])
        probe = self.hang_probe(key)

        class _ConformanceLlm(BaseLlm):
            async def generate_content_async(  # type: ignore[override]
                self, llm_request: Any, stream: bool = False
            ) -> Any:
                requests.append(_adk_request(llm_request))
                responses: list[Any] = []
                try:
                    async for response in inner.generate_content_async(
                        llm_request, stream
                    ):
                        responses.append(response)
                except HangForever:
                    await _park(probe)
                for response in responses:
                    if stream:
                        for part in response.content.parts or []:
                            if part.text:
                                yield LlmResponse(
                                    content=types.Content(
                                        role="model", parts=[types.Part(text=part.text)]
                                    ),
                                    partial=True,
                                )
                    yield response

        agent = Agent(
            name=AGENT_NAME,
            description="A runtime conformance agent.",
            instruction=_instruction(key),
            model=_ConformanceLlm(model="scripted-model"),
            model_name="scripted-model",
            model_api_base=_API_BASE,
            model_api_key=_API_KEY,
            runtime="adk",
            tools=list(tools),
            **agent_kwargs,
        )
        return ScriptedAgent(key=key, agent=agent, plan=rounds)

    def requests(self, key: str = "main") -> list[ModelRequest]:
        return list(self._requests.get(key, []))

    def leaks(self) -> list[str]:
        # The ADK flow keeps no per-turn state outside the session.
        return []

    def runtime_entrypoint(self) -> tuple[Any, str]:
        from google.adk.agents.llm_agent import LlmAgent

        # `veadk.Agent._run_async_impl` delegates the adk runtime to this via
        # `super()`, which resolves the (patched) class attribute at call time.
        return LlmAgent, "_run_async_impl"


# ---------------------------------------------------------------------- codex


def _codex_request(kwargs: dict[str, Any], skills: Sequence[str]) -> ModelRequest:
    tool_names: list[str] = []
    for tool in kwargs.get("tools") or []:
        if not isinstance(tool, dict):
            continue
        if tool.get("type") == "function":
            tool_names.append(str(tool.get("name")))
        elif tool.get("type") == "namespace":
            # The direct transport's MCP bridge tools arrive namespaced.
            tool_names.extend(
                str(inner.get("name"))
                for inner in tool.get("tools") or []
                if isinstance(inner, dict) and inner.get("type") == "function"
            )
    chunks = [str(kwargs.get("instructions") or ""), _dump(kwargs.get("input"))]
    chunks.extend(skills)
    return ModelRequest(text="\n".join(chunks), tool_names=tuple(tool_names))


class CodexAdapter(RuntimeAdapter):
    """The Codex runtime against the in-process shim and a fake app-server."""

    name = "codex"
    capabilities = frozenset(
        {
            Capability.APPROVALS,
            Capability.MCP_TOOLS,
            Capability.SKILLS,
            Capability.TURN_TIMEOUT,
        }
    )
    streams_partials = True
    #: ``CodexRuntimeConfig.model_transport`` the agents run with.
    transport = "shim"

    def __init__(self, monkeypatch: Any, tmp_path: Any) -> None:
        super().__init__(monkeypatch, tmp_path)
        self._requests: dict[str, list[ModelRequest]] = {}
        self._aresponses: dict[str, Any] = {}
        self._skills: dict[str, list[str]] = {}
        self.codex_homes: list[str] = []
        self.workspaces: list[str] = []
        self.shim: Any = None

    def setup(self) -> None:
        # Must precede importing the runtime module, which imports
        # `openai_codex` at module scope.
        fake_codex_sdk.install_openai_codex_stub()
        from veadk.runtime import get_runtime
        from veadk.runtime.codex import runtime as runtime_module
        from veadk.runtime.codex.proxy import ResponsesShim
        from veadk.runtime.compat import reset_warning_state

        get_runtime.cache_clear()
        reset_warning_state()

        shim = ResponsesShim(_API_BASE, _API_KEY)
        shim.url = f"http://shim-{uuid.uuid4().hex[:12]}"
        fake_codex_sdk.SHIM_REGISTRY[shim.url] = shim
        self.shim = shim

        async def fake_get_shim(api_base: str, api_key: str) -> Any:
            return shim

        adapter = self

        async def route(**kwargs: Any) -> Any:
            # The shim folds developer instructions into `instructions`; the
            # direct transport sends them as a developer message in `input`.
            instructions = str(kwargs.get("instructions") or "")
            instructions += _dump(kwargs.get("input"))
            key = _key_from(instructions, adapter._aresponses)
            if key is None:
                raise AssertionError(
                    f"no conformance backend tag in instructions: {instructions!r}"
                )
            adapter._requests.setdefault(key, []).append(
                _codex_request(kwargs, adapter._skills.get(key, []))
            )
            try:
                return await adapter._aresponses[key](**kwargs)
            except HangForever:
                await _park(adapter.hang_probe(key))

        class _SkillSnoopingCodex(self._fake_codex_class()):  # type: ignore[misc]
            """Records the skills Codex would discover under ``CODEX_HOME``."""

            async def thread_start(self, **kwargs: Any) -> Any:
                developer = str(kwargs.get("developer_instructions") or "")
                key = _key_from(developer, adapter._aresponses)
                home = Path(self.config.env["CODEX_HOME"])
                if key is not None:
                    adapter._skills[key] = [
                        manifest.read_text(encoding="utf-8")
                        for manifest in sorted(home.glob("skills/*/SKILL.md"))
                    ]
                return await super().thread_start(**kwargs)

        original_home = runtime_module._prepare_codex_home
        original_workspace = runtime_module._prepare_workspace

        def recording_home(*args: Any, **kwargs: Any) -> str:
            home = original_home(*args, **kwargs)
            adapter.codex_homes.append(home)
            return home

        def recording_workspace(*args: Any, **kwargs: Any) -> str:
            workspace = original_workspace(*args, **kwargs)
            if workspace not in adapter.workspaces:
                adapter.workspaces.append(workspace)
            return workspace

        mp = self.monkeypatch
        mp.setattr("veadk.runtime.codex.proxy.litellm.aresponses", route)
        mp.setattr(runtime_module, "get_shim", fake_get_shim)
        mp.setattr(runtime_module, "AsyncCodex", _SkillSnoopingCodex)
        mp.setattr(runtime_module, "_prepare_codex_home", recording_home)
        mp.setattr(runtime_module, "_prepare_workspace", recording_workspace)

    def teardown(self) -> None:
        from veadk.runtime import get_runtime
        from veadk.runtime.compat import reset_warning_state

        if self.shim is not None:
            fake_codex_sdk.SHIM_REGISTRY.pop(self.shim.url, None)
        # Session workspaces deliberately outlive a turn (the next turn of the
        # session must see its files); they are this test's, so remove them.
        for workspace in self.workspaces:
            shutil.rmtree(workspace, ignore_errors=True)
        get_runtime.cache_clear()
        reset_warning_state()

    def build(
        self,
        plan: Iterable[Round],
        *,
        key: str = "main",
        tools: Sequence[Any] = (),
        **agent_kwargs: Any,
    ) -> ScriptedAgent:
        from veadk import Agent

        rounds = tuple(plan)
        self._aresponses[key] = ScriptedBackend(rounds, arm="codex").as_aresponses()
        self._requests.setdefault(key, [])
        agent = Agent(
            name=AGENT_NAME,
            description="A runtime conformance agent.",
            instruction=_instruction(key),
            model_name="scripted-model",
            model_api_base=_API_BASE,
            model_api_key=_API_KEY,
            runtime="codex",
            tools=list(tools),
            codex_runtime_config={
                "model_transport": self.transport,
                **agent_kwargs.pop("codex_runtime_config", {}),
            },
            **agent_kwargs,
        )
        return ScriptedAgent(key=key, agent=agent, plan=rounds)

    def requests(self, key: str = "main") -> list[ModelRequest]:
        return list(self._requests.get(key, []))

    def leaks(self) -> list[str]:
        problems: list[str] = []
        if self.shim is not None and self.shim._turns:
            problems.append(
                f"shim still holds {len(self.shim._turns)} registered turn(s): "
                "their bearer tokens and ADK tool executors outlive the invocation"
            )
        for home in self.codex_homes:
            if os.path.exists(home):
                problems.append(f"per-turn CODEX_HOME was not removed: {home}")
        return problems

    def runtime_entrypoint(self) -> tuple[Any, str]:
        from veadk.runtime.codex.runtime import CodexRuntime

        return CodexRuntime, "run_async"

    def turn_timeout_kwargs(self, seconds: float) -> dict[str, Any]:
        return {"codex_runtime_config": {"turn_timeout_seconds": seconds}}

    def _fake_codex_class(self) -> type:
        return fake_codex_sdk.ShimDrivingCodex


#: `McpBridge` coroutines that run for the bridge's whole lifetime.
_BRIDGE_SERVICE_COROUTINES = frozenset({"_serve", "_run_manager"})


class CodexDirectAdapter(CodexAdapter):
    """The Codex runtime on the direct transport: no shim, ADK tools over MCP.

    The fake app-server calls the scripted model itself and reaches the
    agent's tools through the runtime's real MCP bridge, so every scenario
    exercises the bridge, the per-turn token and the event de-duplication.
    """

    name = "codex-direct"
    transport = "direct"
    capabilities = CodexAdapter.capabilities | {
        Capability.RESUME_ACROSS_RESTART,
        Capability.STEER,
        Capability.COMPACTION,
    }

    def __init__(self, monkeypatch: Any, tmp_path: Any) -> None:
        super().__init__(monkeypatch, tmp_path)
        # session id -> Codex thread id, as last written to the thread store.
        self._saved_threads: dict[str, str] = {}

    def setup(self) -> None:
        super().setup()
        from veadk.runtime.codex import runtime as runtime_module

        original_save = runtime_module._save_thread
        adapter = self

        async def recording_save(store, key, codex_home, thread_id, *args, **kw):
            await original_save(store, key, codex_home, thread_id, *args, **kw)
            record = await store.load(key)
            if record is not None:
                adapter._saved_threads[key.session_id] = record.thread_id

        self.monkeypatch.setattr(runtime_module, "_save_thread", recording_save)

    def restart(self) -> None:
        """Drop everything a process would lose; keep the thread store.

        Every invocation already runs in a fresh Codex process with a fresh
        CODEX_HOME. What survives a real restart is the store (the session
        database in production), so only process state is reset here: the
        memoized runtime and the loop's MCP bridge.
        """
        from veadk.runtime import get_runtime
        from veadk.runtime.codex import mcp_bridge

        get_runtime.cache_clear()
        with mcp_bridge._BRIDGES_LOCK:
            bridges = list(mcp_bridge._BRIDGES.items())
            mcp_bridge._BRIDGES.clear()
        for _, bridge in bridges:
            bridge.force_close()

    def native_thread_id(self, session_id: str) -> str | None:
        return self._saved_threads.get(session_id)

    async def steer(self, session_id: str, text: str) -> None:
        from conformance_harness import ConformanceHarness
        from veadk.runtime.codex.runtime import CodexRuntime

        # Through the runtime's public entry point, as `Runner.steer` does.
        agent = SimpleNamespace(name=AGENT_NAME)
        delivered = await CodexRuntime().steer(
            agent,  # type: ignore[arg-type]
            app_name=ConformanceHarness.APP_NAME,
            user_id=ConformanceHarness.USER_ID,
            session_id=session_id,
            text=text,
        )
        assert delivered, "the steer found no running turn for the session"

    def compaction_kwargs(self) -> dict[str, Any]:
        # Codex compacts once the last response reports at least this many
        # tokens; every scripted round reports 2, so turn 1 crosses it and
        # turn 2 starts by compacting.
        return {"codex_runtime_config": {"auto_compact_token_limit": 1}}

    def teardown(self) -> None:
        from veadk.runtime.codex import mcp_bridge

        # One bridge per event loop; the test's loop is gone by now, so close
        # its bridge here rather than leaving it to the next `get_bridge`.
        with mcp_bridge._BRIDGES_LOCK:
            bridges = list(mcp_bridge._BRIDGES.items())
            for loop, _ in bridges:
                if loop.is_closed():
                    mcp_bridge._BRIDGES.pop(loop, None)
        for loop, bridge in bridges:
            if loop.is_closed():
                bridge.force_close()
        super().teardown()

    def leaks(self) -> list[str]:
        from veadk.runtime.codex import mcp_bridge

        problems = super().leaks()
        for bridge in list(mcp_bridge._BRIDGES.values()):
            if bridge._turns:
                problems.append(
                    f"MCP bridge still holds {len(bridge._turns)} registered "
                    "turn(s): their bearer tokens and ADK tool executors outlive "
                    "the invocation"
                )
        return problems

    def is_service_task(self, task: "asyncio.Task[Any]") -> bool:
        # The bridge is started lazily by the first turn and then serves every
        # later turn on this loop; its server and session-manager tasks are
        # meant to outlive any one turn.
        # Only the server loop and the MCP session manager: a per-call task the
        # bridge spawns for a tool must still count as a leak.
        code = getattr(task.get_coro(), "cr_code", None)
        return (
            code is not None
            and code.co_filename.endswith("mcp_bridge.py")
            and code.co_name in _BRIDGE_SERVICE_COROUTINES
        )

    def _fake_codex_class(self) -> type:
        return fake_codex_sdk.DirectDrivingCodex


# -------------------------------------------------------------------- piagent


_FAKE_PI = Path(__file__).resolve().parent / "fake_pi_backend.py"


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


class PiAgentAdapter(RuntimeAdapter):
    """The Pi runtime against a scripted Pi subprocess."""

    name = "piagent"
    capabilities = frozenset({Capability.MCP_TOOLS, Capability.SKILLS})
    streams_partials = True

    def __init__(self, monkeypatch: Any, tmp_path: Any) -> None:
        super().__init__(monkeypatch, tmp_path)
        self.pi_dir = Path(tmp_path) / "fake-pi"
        self._keys: set[str] = set()

    def setup(self) -> None:
        from veadk.runtime import get_runtime
        from veadk.runtime.compat import reset_warning_state

        get_runtime.cache_clear()
        reset_warning_state()
        self.pi_dir.mkdir(parents=True, exist_ok=True)
        workdir = Path(self.tmp_path) / "pi-workdir"
        workdir.mkdir(parents=True, exist_ok=True)
        binary = self.pi_dir / "pi"
        binary.write_text(
            f"#!{sys.executable}\n"
            "import runpy\n"
            f"runpy.run_path({str(_FAKE_PI)!r}, run_name='__main__')\n",
            encoding="utf-8",
        )
        binary.chmod(binary.stat().st_mode | stat.S_IXUSR)
        mp = self.monkeypatch
        mp.setenv("PIAGENT_BINARY", str(binary))
        mp.setenv("PIAGENT_AGENT_DIR", str(Path(self.tmp_path) / "pi-home"))
        mp.setenv("PIAGENT_WORKDIR", str(workdir))
        mp.setenv("PIAGENT_TIMEOUT_SECONDS", "120")
        mp.setenv("CONFORMANCE_PI_DIR", str(self.pi_dir))

    def teardown(self) -> None:
        from veadk.runtime import get_runtime
        from veadk.runtime.compat import reset_warning_state

        # A test that failed mid-turn must not leave a Pi process behind.
        for pid in self._pids():
            if _pid_alive(pid):
                try:
                    os.kill(pid, 9)
                except OSError:
                    pass
        get_runtime.cache_clear()
        reset_warning_state()

    def _model(self, key: str) -> str:
        return f"scripted-{key}"

    def build(
        self,
        plan: Iterable[Round],
        *,
        key: str = "main",
        tools: Sequence[Any] = (),
        **agent_kwargs: Any,
    ) -> ScriptedAgent:
        from veadk import Agent

        rounds = tuple(plan)
        encoded: list[dict[str, Any]] = []
        for rnd in rounds:
            if rnd.raises is not None and not isinstance(rnd.raises, HangForever):
                raise NotImplementedError(
                    "the scripted Pi backend cannot raise into the runtime; "
                    f"got {rnd.raises!r}"
                )
            encoded.append(
                {
                    "texts": list(rnd.reply_texts),
                    "tool_calls": [[name, dict(args)] for name, args in rnd.tool_calls],
                    "usage": list(rnd.usage),
                    "hang": isinstance(rnd.raises, HangForever),
                }
            )
        model = self._model(key)
        (self.pi_dir / f"{model}.plan.json").write_text(
            json.dumps(encoded), encoding="utf-8"
        )
        # Rebuilding a key restarts its script, as for the other adapters.
        (self.pi_dir / f"{model}.cursor").unlink(missing_ok=True)
        self._keys.add(key)
        agent = Agent(
            name=AGENT_NAME,
            description="A runtime conformance agent.",
            instruction=_instruction(key),
            model_name=model,
            model_api_base=_API_BASE,
            model_api_key=_API_KEY,
            model_api_key_name="",
            runtime="piagent",
            tools=list(tools),
            **agent_kwargs,
        )
        return ScriptedAgent(key=key, agent=agent, plan=rounds)

    def _records(self, key: str) -> list[dict[str, Any]]:
        path = self.pi_dir / f"{self._model(key)}.calls.jsonl"
        if not path.exists():
            return []
        return [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]

    def requests(self, key: str = "main") -> list[ModelRequest]:
        requests: list[ModelRequest] = []
        for record in self._records(key):
            chunks = [record["prompt"], _dump(record["tool_results"])]
            chunks.extend(record.get("skills") or [])
            requests.append(
                ModelRequest(
                    text="\n".join(chunks),
                    tool_names=tuple(record.get("tool_names") or ()),
                )
            )
        return requests

    def _pids(self) -> list[int]:
        pids: list[int] = []
        for key in self._keys:
            path = self.pi_dir / f"{self._model(key)}.pids"
            if path.exists():
                pids.extend(int(p) for p in path.read_text().split() if p.strip())
        return pids

    async def wait_for_hang(self, key: str = "main", timeout: float = 30.0) -> bool:
        from conformance_harness import wait_until

        marker = self.pi_dir / f"{self._model(key)}.hang"
        return await wait_until(marker.exists, timeout=timeout)

    def hang_abandoned(self, key: str = "main") -> bool:
        marker = self.pi_dir / f"{self._model(key)}.hang"
        if not marker.exists():
            return False
        return not _pid_alive(int(marker.read_text()))

    def leaks(self) -> list[str]:
        problems: list[str] = []
        for pid in self._pids():
            if _pid_alive(pid):
                problems.append(f"Pi subprocess {pid} is still running")
        for key in self._keys:
            for record in self._records(key):
                for path in [*record["extensions"], *record["skill_dirs"]]:
                    if os.path.exists(path):
                        problems.append(f"per-turn Pi file was not removed: {path}")
        return sorted(set(problems))

    def runtime_entrypoint(self) -> tuple[Any, str]:
        from veadk.runtime.piagent.runtime import PiAgentRuntime

        return PiAgentRuntime, "run_async"


#: Every runtime the suite knows how to drive. Adding a runtime means adding
#: its adapter here -- nothing in the scenarios changes.
ADAPTERS: dict[str, type[RuntimeAdapter]] = {
    AdkAdapter.name: AdkAdapter,
    CodexAdapter.name: CodexAdapter,
    CodexDirectAdapter.name: CodexDirectAdapter,
    PiAgentAdapter.name: PiAgentAdapter,
}
