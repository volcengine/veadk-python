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
