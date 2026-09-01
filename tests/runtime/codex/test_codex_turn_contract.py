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

"""End-to-end contract tests for one Codex turn, driven through the real runtime.

The shim-level file next door (``test_codex_shim_rounds.py``) can express what
one HTTP request does, but not what the *runtime* guarantees across a whole
invocation. Everything here therefore runs ``CodexRuntime.run_async`` against
the differential suite's offline doubles -- the fake Codex SDK drives the real
shim over ``httpx.ASGITransport``, and a scripted backend stands in for the
model -- so no assertion here can be satisfied by a hand-built request body.

That matters most for :func:`test_agent_turn_still_gets_tools_and_replay`, the
paired positive for the compaction-isolation tests: whatever marks a request as
"the agent's own turn", this test gets it the way production does.
"""

from __future__ import annotations

import asyncio
import contextvars
import shutil
import sys
import uuid
from pathlib import Path
from typing import Any

import pytest
from google.adk.agents.invocation_context import LlmCallsLimitExceededError
from google.adk.agents.run_config import RunConfig
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

# Same import-by-path arrangement as `test_codex_tracing.py`: the differential
# suite owns the offline Codex doubles, and this file must run both standalone
# and inside a full-tree collection.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "differential"))

import fake_codex_sdk  # noqa: E402
from scripted_backend import Round, ScriptedBackend  # noqa: E402


def record_fact(fact: str) -> dict:
    """Record a fact."""
    return {"stored": fact}


class _BrokenStreamCodex(fake_codex_sdk.ShimDrivingCodex):
    """Drives the shim normally, then drops the stream on the way out.

    Models a connection reset (or any SDK-side failure) arriving *after* the
    shim has already recorded a turn error. That ordering is the whole point:
    the runtime must still surface the recorded error rather than the transport
    exception that happened to arrive last.
    """

    async def thread_start(self, **kwargs: Any) -> Any:
        return _BrokenThread(await super().thread_start(**kwargs))


class _BrokenThread:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def turn(self, input_items: Any, **kwargs: Any) -> Any:
        return _BrokenTurn(await self._inner.turn(input_items, **kwargs))


class _BrokenTurn:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.id = inner.id

    async def interrupt(self) -> None:
        return None

    def stream(self) -> Any:
        async def _gen():
            async for note in self._inner.stream():
                yield note
            raise RuntimeError("codex stream dropped")

        return _gen()


async def _run_turn(
    monkeypatch,
    *,
    plan,
    agent_kwargs: dict | None = None,
    run_config: RunConfig | None = None,
    codex_class: type | None = None,
):
    """Run one Codex invocation offline; return (events, session, backend, error)."""
    from veadk import Agent
    from veadk.runtime import get_runtime

    # Must precede the `runtime` import: that module imports `openai_codex` at
    # module scope, and the stub is what stands in for it when it is absent.
    fake_codex_sdk.install_openai_codex_stub()
    get_runtime.cache_clear()

    from veadk.runtime.codex import runtime as runtime_module
    from veadk.runtime.codex.proxy import ResponsesShim

    backend = ScriptedBackend(plan, arm="codex")
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    shim.url = f"http://shim-{uuid.uuid4().hex[:12]}"
    fake_codex_sdk.SHIM_REGISTRY[shim.url] = shim

    async def fake_get_shim(api_base, api_key):
        return shim

    monkeypatch.setattr(
        "veadk.runtime.codex.proxy.litellm.aresponses", backend.as_aresponses()
    )
    monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
    monkeypatch.setattr(
        runtime_module, "AsyncCodex", codex_class or fake_codex_sdk.ShimDrivingCodex
    )

    agent = Agent(
        name="contract_agent",
        description="A codex contract agent.",
        instruction="Answer the user.",
        model_name="scripted-model",
        model_api_base="https://backend.invalid/v1",
        model_api_key="backend-key",
        runtime="codex",
        **(agent_kwargs or {}),
    )

    session_id = f"session-{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="contract", user_id="user", session_id=session_id
    )
    runner = Runner(app_name="contract", agent=agent, session_service=session_service)

    events: list[Any] = []
    error: BaseException | None = None
    try:
        try:
            async for event in runner.run_async(
                user_id="user",
                session_id=session_id,
                new_message=types.Content(role="user", parts=[types.Part(text="go")]),
                **({"run_config": run_config} if run_config is not None else {}),
            ):
                events.append(event)
        except BaseException as e:  # noqa: BLE001 - the error IS the observable
            error = e

        session = await session_service.get_session(
            app_name="contract", user_id="user", session_id=session_id
        )
    finally:
        # Process-global, and this file runs under `pytest -n 16`: a leaked
        # registry entry or a memoized runtime would follow every later test in
        # this worker.
        fake_codex_sdk.SHIM_REGISTRY.clear()
        get_runtime.cache_clear()
    return events, session, backend, error


# ------------------------------------------ paired positive for compaction gating


@pytest.mark.asyncio
async def test_agent_turn_still_gets_tools_and_replay(monkeypatch) -> None:
    """The agent's own turn must keep getting ADK tools and transcript replay.

    Paired positive for
    ``test_codex_shim_rounds.py::test_compaction_request_gets_no_adk_tools_*``:
    those assert the shim leaves a *non*-agent-turn request alone, and without
    this one they could all be satisfied by never injecting anything at all,
    which would silently disable ADK tools for the codex runtime entirely.

    Deliberately end-to-end. A hand-built POST could be made to satisfy any
    gating rule by construction; only a request the runtime itself produced
    proves the real agent turn is still recognized as one.
    """
    events, _session, backend, error = await _run_turn(
        monkeypatch,
        plan=(
            Round(tool_calls=(("record_fact", {"fact": "sky is blue"}),), usage=(0, 0)),
            Round(text="The sky is blue.", usage=(10, 4)),
        ),
        agent_kwargs={"tools": [record_fact]},
    )
    assert error is None, error
    assert events, "the codex turn produced no events"

    assert backend.calls, "the scripted backend was never called"
    assert "record_fact" in backend.calls[0].tool_names, (
        "the agent's ADK tool was not advertised on its own turn -- gating "
        f"over-corrected into never injecting: {backend.calls[0].tool_names}"
    )

    assert (
        len(backend.calls) >= 2
    ), f"expected a tool round then an answer round: {backend.calls}"
    assert backend.calls[1].tool_records == (
        ("function_call", "record_fact"),
        ("function_response", "record_fact"),
    ), (
        "the agent turn's own tool transcript was not replayed to the model, so "
        f"it would re-issue the call: {backend.calls[1].tool_records}"
    )


@pytest.mark.asyncio
async def test_agent_turn_replays_across_two_codex_requests(monkeypatch) -> None:
    """The cross-request half of the same guarantee, end to end.

    The test above stays inside one Codex request (the shim's own tool loop).
    This one forces Codex to issue a *second* request under the same turn token,
    by having the model ask for a tool the shim has no executor for: the shim
    hands that call back to Codex, which answers it and re-POSTs. Only
    ``turn_context.state.replay_items`` can put the earlier ADK pair into that
    second request, since Codex rebuilds ``input`` from its own thread and never
    saw it.

    Without this, gating tool-transcript replay on "is this the agent's turn?"
    could pass every compaction-isolation test while quietly disabling replay
    for the shape that motivated it.
    """
    events, _session, backend, error = await _run_turn(
        monkeypatch,
        plan=(
            # Round 1: an ADK tool the shim executes itself.
            Round(tool_calls=(("record_fact", {"fact": "blue"}),), usage=(0, 0)),
            # Round 2: a call the shim cannot execute -> returned to Codex,
            # which answers it locally and re-POSTs. Second request, one token.
            Round(tool_calls=(("codex_owned_tool", {"q": "x"}),), usage=(0, 0)),
            Round(text="The sky is blue.", usage=(10, 4)),
        ),
        agent_kwargs={"tools": [record_fact]},
    )
    assert error is None, error
    assert events, "the codex turn produced no events"
    assert (
        len(backend.calls) >= 3
    ), f"codex never issued a second request: {len(backend.calls)} backend calls"

    replayed = backend.calls[2].tool_records
    assert ("function_call", "record_fact") in replayed, (
        "the first request's ADK tool pair was not replayed into Codex's second "
        f"request, so the model would re-issue the call: {replayed}"
    )
    assert ("function_response", "record_fact") in replayed, replayed


# ---------------------------------------- the recorded turn error must survive


@pytest.mark.asyncio
async def test_budget_error_survives_a_failing_turn(monkeypatch) -> None:
    """``max_llm_calls`` must fire even when the turn also fails.

    The shim serves backend calls on the server's task, so an exhausted budget
    cannot propagate from there: it is recorded on the turn state and returned
    to Codex as a 429, and ``run_async`` re-reads it afterwards. But that read
    happens on only one of three exits -- if the stream then raises, the
    ``finally``'s ``unregister_turn`` drops the recorded error and the caller
    sees the transport exception instead. ``max_llm_calls`` then silently does
    nothing on every failure path, and ``on_model_error`` callbacks are handed
    the wrong exception.
    """
    _events, _session, _backend, error = await _run_turn(
        monkeypatch,
        plan=(
            Round(tool_calls=(("record_fact", {"fact": "blue"}),), usage=(0, 0)),
            Round(text="The sky is blue.", usage=(10, 4)),
        ),
        agent_kwargs={"tools": [record_fact]},
        run_config=RunConfig(max_llm_calls=1),
        codex_class=_BrokenStreamCodex,
    )

    assert isinstance(error, LlmCallsLimitExceededError), (
        "the recorded max_llm_calls error was dropped when the turn failed; "
        f"the caller saw {type(error).__name__}: {error!r}"
    )


# ------------------------------------------------- a tool-only turn still counts


@pytest.mark.asyncio
async def test_tool_only_turn_propagates_state_delta_and_usage(monkeypatch) -> None:
    """A turn that ends without assistant text must not lose its bookkeeping.

    The runtime builds exactly one merged response per turn -- that is where
    after-model callbacks run, where the turn's ``usage_metadata`` is attached,
    and where a callback's ``callback_context.state`` writes become a
    ``state_delta``. Dropping that event because it carries no text throws all
    of it away: ``output_key``-style state writes never reach the session and
    the turn's tokens never reach usage accounting. Marking the event partial
    instead would not help, since partial events are never persisted.
    """

    def _before_model(callback_context, llm_request):  # noqa: ANN001
        callback_context.state["seen_by_callback"] = "yes"
        return None

    events, session, _backend, error = await _run_turn(
        monkeypatch,
        plan=(
            Round(tool_calls=(("record_fact", {"fact": "blue"}),), usage=(11, 5)),
            # The turn ends on a tool round with no assistant text at all.
            Round(usage=(7, 3)),
        ),
        agent_kwargs={
            "tools": [record_fact],
            "before_model_callback": _before_model,
        },
    )
    assert error is None, error

    state = dict(getattr(session, "state", None) or {})
    assert state.get("seen_by_callback") == "yes", (
        "a tool-only turn dropped the merged event, so the callback's state "
        f"write never reached the session: {state}"
    )

    total = sum(
        int(getattr(getattr(e, "usage_metadata", None), "total_token_count", 0) or 0)
        for e in events
    )
    assert (
        total == 26
    ), f"a tool-only turn reported {total} tokens; the turn spent 11+5 and 7+3"


# ----------------------------------- the workspace an ADK tool is able to find


class _Rendezvous:
    """Releases its callers only once ``parties`` of them have arrived.

    Turns "two turns ran" into "two turns were *inside their tool* at the same
    instant", which is the only arrangement in which a shared-state mechanism
    can be caught handing one tenant another's workspace.
    """

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._all_here = asyncio.Event()

    async def wait(self, timeout: float = 60.0) -> None:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_here.set()
        await asyncio.wait_for(self._all_here.wait(), timeout)


#: A workspace no turn owns, bound in the context the detached driver below
#: hands to the shim. It stands in for the first-ever invocation's value, which
#: is what a production shim's server task carries forever.
_DECOY_WORKSPACE = "/tmp/veadk-decoy-workspace-owned-by-no-turn"


class _DetachedShimCodex(fake_codex_sdk.ShimDrivingCodex):
    """Drives the shim from a task that does not descend from the invocation.

    ``httpx.ASGITransport`` calls the shim's handler inline, on the caller's
    task, which makes the offline harness *friendlier than production*: there
    the handler runs on a task descended from the uvicorn server task, which
    ``asyncio.create_task`` created -- and whose context it snapshotted -- when
    the first invocation in the process started the shim. A ContextVar the
    invocation merely sets is therefore not visible to a tool; the first
    invocation's value is. (Measured: with the var set in ``run_async``, three
    later turns' tools all read the first turn's workspace. It is the same
    asymmetry that forces the shim to capture an OTel context in
    ``register_turn`` and re-attach it around tool execution.)

    So the request is issued here from a task created in a context where
    :data:`_DECOY_WORKSPACE` is bound. Any design that lets the tool read the
    workspace out of ambient task context now reports the decoy instead of the
    turn's own directory, in the test as it would in production.
    """

    async def thread_start(self, **kwargs: Any) -> Any:
        return _DetachedThread(await super().thread_start(**kwargs))


class _DetachedThread:
    def __init__(self, inner: Any) -> None:
        self._inner = inner

    async def turn(self, input_items: Any, **kwargs: Any) -> Any:
        return _DetachedTurn(await self._inner.turn(input_items, **kwargs))


class _DetachedTurn:
    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.id = inner.id

    async def interrupt(self) -> None:
        await self._inner.interrupt()

    def stream(self) -> Any:
        from veadk.runtime.codex.workspace import bind_workspace

        inner = self._inner.stream()
        queue: asyncio.Queue = asyncio.Queue()
        done = object()

        async def _pump() -> None:
            try:
                async for note in inner:
                    await queue.put(note)
            except BaseException as e:  # noqa: BLE001 - relayed to the consumer
                await queue.put(e)
            finally:
                await queue.put(done)

        # A fresh copy per turn: a Context cannot be entered twice at once, and
        # these two turns overlap.
        with bind_workspace(_DECOY_WORKSPACE):
            detached = contextvars.copy_context()
        task = detached.run(asyncio.create_task, _pump())

        async def _gen():
            try:
                while True:
                    item = await queue.get()
                    if item is done:
                        return
                    if isinstance(item, BaseException):
                        raise item
                    yield item
            finally:
                if not task.done():
                    task.cancel()

        return _gen()


#: Set by the concurrency test; ``None`` leaves ``stage_dataset`` sequential.
_RENDEZVOUS: _Rendezvous | None = None

#: What each call of ``stage_dataset`` saw, in completion order.
_STAGED: list[dict[str, str]] = []


async def stage_dataset(label: str) -> dict:
    """Write this tenant's dataset into your working directory.

    Args:
        label (str): The tenant this turn belongs to.

    Returns:
        dict: A receipt with the workspace-relative path.
    """
    from veadk.runtime.codex import current_workspace

    if _RENDEZVOUS is not None:
        # Both tools are now in flight; whatever each reads next, it reads
        # while the other turn's tool is also inside its executor.
        await _RENDEZVOUS.wait()
    workspace = current_workspace()
    # Recorded before the write, so a wrong-but-plausible path is reported as
    # the wrong path rather than as an unwritable one.
    _STAGED.append({"label": label, "workspace": workspace or ""})
    if workspace is None:
        return {"status": "error", "message": "no codex workspace on this call"}
    path = Path(workspace) / "staged.txt"
    try:
        path.write_text(label, encoding="utf-8")
    except OSError as e:
        return {"status": "error", "message": str(e)}
    return {"status": "ok", "path": "staged.txt"}


async def _run_two_turns_concurrently(monkeypatch, labels: tuple[str, str]):
    """Drive two invocations at once, through one shim, and return their events.

    Deliberately *one* shim for both turns (that is what a server does: the
    shim is memoized per backend), no ``workspace_root``, and no
    ``reuse_workspace`` -- so each turn gets its own session-keyed workspace,
    which is the arrangement the examples now rely on.
    """
    from veadk import Agent
    from veadk.runtime import get_runtime

    fake_codex_sdk.install_openai_codex_stub()
    get_runtime.cache_clear()

    from veadk.runtime.codex import runtime as runtime_module
    from veadk.runtime.codex.proxy import ResponsesShim

    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    shim.url = f"http://shim-{uuid.uuid4().hex[:12]}"
    fake_codex_sdk.SHIM_REGISTRY[shim.url] = shim

    async def fake_get_shim(api_base, api_key):
        return shim

    # One scripted backend per turn, since the plan cursor is per-arm and the
    # two turns interleave. Routed by the tenant name in each agent's own
    # instruction, which reaches the wire as the request's `instructions` on
    # every request of that turn. (Not the prompt text: the offline fake reads
    # `TextInput.value`, an attribute only its stub has, so prompts arrive
    # empty when the real openai-codex SDK is installed.)
    backends = {
        label: ScriptedBackend(
            (
                Round(tool_calls=(("stage_dataset", {"label": label}),), usage=(0, 0)),
                Round(text=f"staged for {label}", usage=(3, 2)),
            ),
            arm="codex",
        )
        for label in labels
    }
    adapters = {label: backend.as_aresponses() for label, backend in backends.items()}

    async def dispatch(**kwargs: Any) -> Any:
        instructions = str(kwargs.get("instructions") or "")
        for label, adapter in adapters.items():
            if f"tenant {label}" in instructions:
                return await adapter(**kwargs)
        raise AssertionError(f"no tenant in request instructions: {instructions!r}")

    monkeypatch.setattr("veadk.runtime.codex.proxy.litellm.aresponses", dispatch)
    monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
    # Not `ShimDrivingCodex`: the shim must be driven from a task that does not
    # descend from either invocation, the way uvicorn drives it in production.
    monkeypatch.setattr(runtime_module, "AsyncCodex", _DetachedShimCodex)

    session_service = InMemorySessionService()

    async def _drive(label: str) -> list[Any]:
        agent = Agent(
            name="tenant_agent",
            description="A codex contract agent.",
            instruction=f"Answer the user. You serve tenant {label}.",
            model_name="scripted-model",
            model_api_base="https://backend.invalid/v1",
            model_api_key="backend-key",
            runtime="codex",
            tools=[stage_dataset],
        )
        session_id = f"session-{label}-{uuid.uuid4().hex[:8]}"
        await session_service.create_session(
            app_name="contract", user_id=label, session_id=session_id
        )
        runner = Runner(
            app_name="contract", agent=agent, session_service=session_service
        )
        return [
            event
            async for event in runner.run_async(
                user_id=label,
                session_id=session_id,
                new_message=types.Content(
                    role="user", parts=[types.Part(text=f"stage data for {label}")]
                ),
            )
        ]

    try:
        return await asyncio.gather(*(_drive(label) for label in labels))
    finally:
        fake_codex_sdk.SHIM_REGISTRY.clear()
        get_runtime.cache_clear()


@pytest.mark.asyncio
async def test_concurrent_turns_each_see_their_own_workspace(monkeypatch) -> None:
    """Two turns at once, each tool writing into its own session's workspace.

    This is the multi-tenant requirement in one test. Before
    ``current_workspace()`` existed, the examples had to pin ``workspace_root``
    *and* ``reuse_workspace=True`` purely so their ADK tools could find the
    directory Codex was working in -- which put every session in one shared
    directory. Nothing here is pinned: both turns take the default, per-session
    workspace, and the tool still finds the right one.

    The rendezvous is what makes it a concurrency test rather than two
    sequential ones: neither tool reads the workspace until both are inside
    their executor, so a mechanism that keeps "the current workspace" anywhere
    process-wide (or that lets the shim's own task context supply it) hands at
    least one of them the wrong path.
    """
    global _RENDEZVOUS
    _STAGED.clear()
    _RENDEZVOUS = _Rendezvous(2)
    try:
        results = await _run_two_turns_concurrently(monkeypatch, ("alpha", "beta"))
    finally:
        _RENDEZVOUS = None

    assert all(events for events in results), "a turn produced no events"
    assert len(_STAGED) == 2, (
        "both tools should have run and recorded a workspace (a missing entry "
        f"means one turn never reached its tool): {_STAGED}"
    )

    seen = {entry["label"]: entry["workspace"] for entry in _STAGED}
    assert seen.keys() == {"alpha", "beta"}
    assert all(seen.values()), (
        "a tool could not find the turn's workspace, so an ADK tool has no "
        f"supported way to hand Codex a file: {_STAGED}"
    )
    assert seen["alpha"] != seen["beta"], (
        "both tenants were handed the same workspace -- per-session isolation "
        f"is gone and one tenant can read the other's files: {seen}"
    )
    for label, workspace in seen.items():
        staged = Path(workspace) / "staged.txt"
        assert staged.read_text(encoding="utf-8") == label, (
            f"{label}'s file landed in the wrong workspace: "
            f"{staged} holds {staged.read_text(encoding='utf-8')!r}"
        )

    # Nothing was pinned, so both workspaces must be the runtime's own
    # per-session directories under the process-owned root.
    from veadk.runtime.codex import runtime as runtime_module

    root = Path(runtime_module._SESSION_WORKSPACE_ROOT)
    for workspace in seen.values():
        assert Path(workspace).parent == root, (
            f"{workspace} is not a per-session workspace under {root}; the "
            "turn fell back to a shared directory"
        )
        shutil.rmtree(workspace, ignore_errors=True)


@pytest.mark.asyncio
async def test_tool_workspace_is_bound_per_call_not_inherited(monkeypatch) -> None:
    """The binding must survive the shim's task, and never leak between turns.

    The offline arrangement above drives the shim over ``ASGITransport``, so
    its handler runs on the invocation's own task -- friendlier than production,
    where the handler descends from the uvicorn server task whose context was
    snapshotted when the *first* invocation in the process started the shim.
    Measured against a real shim, a ContextVar merely set in ``run_async`` made
    every later turn's tool read the first turn's workspace: a silent
    cross-tenant leak, not a miss.

    This reproduces that topology directly. The wrapped executor is invoked
    from a task created while a *different* workspace is bound, exactly as the
    shim's handler would be, and must still report its own turn's.
    """
    from veadk.runtime.codex.workspace import (
        bind_workspace,
        bind_workspace_to_executors,
        current_workspace,
    )

    async def _probe(args: dict[str, Any], call_id: str) -> str:
        return str(current_workspace())

    wrapped = bind_workspace_to_executors({"probe": _probe}, "/tmp/tenant-b")["probe"]

    with bind_workspace("/tmp/tenant-a"):
        # The task inherits tenant A's context, the way the shim's server task
        # inherited the first invocation's.
        task = asyncio.create_task(wrapped({}, "call-1"))
        assert await task == "/tmp/tenant-b", (
            "the executor read the workspace from the calling task's context "
            "instead of its own turn's"
        )

    assert current_workspace() is None, "the binding outlived its call"


def test_current_workspace_is_none_outside_a_codex_turn() -> None:
    """Outside a turn the accessor reports absence rather than raising.

    An ADK tool is not codex-specific: the same object is run by the default
    LLM flow, by ``AgentTool`` and by unit tests, so raising here would make a
    workspace-aware tool unusable everywhere else. ``None`` is one branch, and
    the tool can return a model-readable error of its own.
    """
    from veadk.runtime.codex import current_workspace

    assert current_workspace() is None


# --------------------------------- what the model is told about its own tools


@pytest.mark.asyncio
async def test_turn_corrects_codex_prompt_about_unusable_tools(monkeypatch) -> None:
    """The developer channel must correct Codex's prompt on two tools.

    Codex keeps its own ~21KB system prompt (the runtime never sends
    ``base_instructions``, which would *replace* it), and that prompt tells the
    model to edit files with ``apply_patch`` -- a tool the shim never forwards,
    because it forwards only ``function``-typed tools. It also leaves
    ``request_user_input`` advertised, though an ADK invocation has nobody to
    answer it, so a call to it ends the turn having done nothing.

    Both example agents had to counter-instruct this in their own prompts. The
    note belongs to the runtime, on the additive developer channel, next to the
    agent's instruction.
    """
    _events, _session, backend, error = await _run_turn(
        monkeypatch,
        plan=(Round(text="Done.", usage=(4, 2)),),
    )
    assert error is None, error
    assert backend.calls, "the scripted backend was never called"

    instructions = backend.calls[0].system_instruction
    assert "apply_patch" in instructions, (
        "nothing tells the model apply_patch is unavailable, so it will call a "
        f"tool the backend was never given: {instructions!r}"
    )
    assert "exec_command" in instructions, instructions
    assert "request_user_input" in instructions, (
        "nothing tells the model its question cannot be answered mid-turn: "
        f"{instructions!r}"
    )
    # The note is additive, never a replacement: the agent's own instruction
    # and identity must still be there.
    assert "Answer the user." in instructions, instructions
    assert "contract_agent" in instructions, instructions


# ------------------------------------------ importing must not touch the disk


def test_importing_the_runtime_creates_no_workspace_root(tmp_path) -> None:
    """Importing the module must not create a temp directory.

    ``_SESSION_WORKSPACE_ROOT`` used to be a module-level
    ``tempfile.mkdtemp(...)``, so every process that merely imported this
    module made a ``veadk-codex-workspaces-*`` root in ``$TMPDIR`` -- reclaimed
    by an ``atexit`` hook, which a ``SIGKILL`` (an OOM kill, a torn-down xdist
    worker) never runs. A smoke run found several orphaned roots predating it,
    and ``pytest -n 16`` leaves one per killed worker.

    Run in a subprocess with a private ``TMPDIR``: the root is process-global
    and this suite has already served turns, so nothing in-process can still
    observe a first import -- and a shared ``$TMPDIR`` would see roots made by
    any other process on the machine.
    """
    import os
    import subprocess

    differential = str(Path(__file__).resolve().parents[1] / "differential")
    program = (
        "import sys\n"
        f"sys.path.insert(0, {differential!r})\n"
        "import fake_codex_sdk\n"
        "fake_codex_sdk.install_openai_codex_stub()\n"
        "import veadk.runtime.codex.runtime as runtime\n"
        "print(runtime._session_workspace_root)\n"
    )
    private_tmp = tmp_path / "tmp"
    private_tmp.mkdir()
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=180,
        env={**os.environ, "TMPDIR": str(private_tmp)},
    )
    assert result.returncode == 0, result.stderr[-2000:]
    assert (
        result.stdout.strip() == "None"
    ), f"the module built a workspace root on import: {result.stdout.strip()}"
    assert not list(private_tmp.iterdir()), (
        "importing the module created "
        f"{[p.name for p in private_tmp.iterdir()]} in $TMPDIR"
    )
