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

"""The runtime conformance suite: one contract, every ``Agent(runtime=...)``.

Each scenario here runs once per adapter in ``conformance_adapters.ADAPTERS``
(``adk``, ``codex``, ``piagent``), offline, through the real ``Runner``. The
scenarios pin what the ``Runner`` and the model can *observe*, never how a
runtime is built, so a runtime whose internals are rewritten (Codex thread
resume, an MCP bridge, steering) is held to the same contract before and after.

Two kinds of scenario:

Required
    Run for every runtime. A runtime that genuinely fails one is marked
    ``xfail(strict=True)`` for that runtime only, with the precise gap as the
    reason (see :data:`KNOWN_GAPS`) -- never by weakening the assertion. Strict
    means closing the gap turns the suite red until the marker is removed.

Capability-gated
    Run only when the adapter declares the capability (see
    ``conformance_harness.Capability``), otherwise skipped with a reason naming
    it. ``resume_across_restart``, ``steer``, ``turn_timeout`` and
    ``compaction`` are declared by no runtime yet: their scenarios are written
    against adapter hooks that raise ``NotImplementedError`` today, so the PR
    that implements one adds the hook and flips the capability on.

Adding a runtime: write a ``RuntimeAdapter`` subclass, register it in
``ADAPTERS``, declare its capabilities. Nothing in this file changes.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from google.adk.agents.run_config import RunConfig, StreamingMode
from google.genai import types

from conformance_harness import (
    HANG,
    Capability,
    ConformanceHarness,
    Round,
    marker,
    pending_tasks,
    settle,
    wait_until,
)

#: ``{(scenario, runtime): reason}`` for required scenarios a runtime fails
#: today. Applied as ``xfail(strict=True)``.
KNOWN_GAPS: dict[tuple[str, str], str] = {
    ("tool_failure", "adk"): (
        "runtime='adk' lets a raising FunctionTool crash the invocation: "
        "google.adk.flows.llm_flows.functions re-raises the tool's exception "
        "when no on_tool_error_callback returns a response, so Runner.run_async "
        "raises instead of the model seeing an error result (codex and piagent "
        "report {'status': 'failed', 'error': ...} to the model)"
    ),
    ("cancellation_tool", "piagent"): (
        "PiAgentRuntime never cancels an in-flight bridged tool call: on "
        "cancellation PiToolRuntime.close() awaits asyncio.Server.wait_closed(), "
        "which (Python >= 3.12) waits for the _handle_client task still running "
        "the tool, so the cancelled turn never finishes and the tool keeps running"
    ),
}


def _known_gap(request: pytest.FixtureRequest, scenario: str) -> None:
    runtime = request.node.callspec.params["harness"]
    reason = KNOWN_GAPS.get((scenario, runtime))
    if reason is not None:
        request.applymarker(pytest.mark.xfail(strict=True, reason=reason))


def _final_texts(events: list[Any]) -> list[str]:
    return [
        "".join(p.text or "" for p in e.content.parts if not p.thought).strip()
        for e in events
        if e.is_final_response() and e.content and e.content.parts
    ]


def _usage_total(events: list[Any]) -> int:
    return sum(
        int(getattr(getattr(e, "usage_metadata", None), "total_token_count", 0) or 0)
        for e in events
    )


# ------------------------------------------------------------------- tools


class _ToolLog:
    """Per-test record of what the tools actually did."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancelled = False


def _lookup_tool(log: _ToolLog, result: str):
    def lookup_code(item: str) -> dict:
        """Look up the code for an item.

        Args:
            item (str): The item to look up.

        Returns:
            dict: The item's code.
        """
        log.calls.append({"item": item})
        return {"item": item, "code": result}

    return lookup_code


def _failing_tool(log: _ToolLog, message: str):
    def flaky_lookup(item: str) -> dict:
        """Look up an item from a service that is down.

        Args:
            item (str): The item to look up.

        Returns:
            dict: Never returns.
        """
        log.calls.append({"item": item})
        raise RuntimeError(message)

    return flaky_lookup


def _blocking_tool(log: _ToolLog):
    async def block_forever(item: str) -> dict:
        """Start a long job.

        Args:
            item (str): The job to start.

        Returns:
            dict: Nothing; returns only if the test releases it.
        """
        log.calls.append({"item": item})
        log.started.set()
        try:
            await log.release.wait()
        except asyncio.CancelledError:
            log.cancelled = True
            raise
        return {}

    return block_forever


# ======================================================== required scenarios


@pytest.mark.asyncio
async def test_basic_single_turn(harness: ConformanceHarness, request) -> None:
    """One text round yields exactly one final response, correctly attributed.

    ``author`` is how the ``Runner`` finds the agent that answered (and how
    multi-agent history is rebuilt); ``invocation_id`` is how every consumer
    groups a turn's events. A runtime that mints its own ids or authors breaks
    both silently: the answer is still there, just unattributable.
    """
    _known_gap(request, "basic_single_turn")
    answer = marker("BASIC-ANSWER")
    scripted = harness.adapter.build([Round(text=answer, usage=(3, 2))])
    session_id = await harness.new_session()

    turn = await harness.run_turn(scripted, session_id, "hello")

    assert turn.error is None, turn.error
    assert _final_texts(turn.events) == [answer], (
        f"expected exactly one final response {answer!r}, got "
        f"{_final_texts(turn.events)}"
    )
    final = turn.finals[0]
    assert final.author == scripted.agent.name, final.author
    invocation_ids = {e.invocation_id for e in turn.events}
    assert len(invocation_ids) == 1 and all(invocation_ids), (
        f"one turn must carry one non-empty invocation id: {invocation_ids}"
    )
    persisted = [
        e
        for e in turn.session.events
        if e.content and any(p.text == answer for p in e.content.parts or [])
    ]
    assert len(persisted) == 1, "the answer must be persisted exactly once"
    assert persisted[0].invocation_id == final.invocation_id
    user_events = [e for e in turn.session.events if e.author == "user"]
    assert [e.invocation_id for e in user_events] == [final.invocation_id], (
        "the user message and the answer must belong to the same invocation"
    )


@pytest.mark.asyncio
async def test_streaming_partials_precede_one_final(
    harness: ConformanceHarness, request
) -> None:
    """Partials stream first, then exactly one final response closes the turn.

    ``Event.is_final_response()`` is the end-of-turn signal for ``output_key``,
    evaluation and the A2A reply; a second one makes them last-writer-wins, and
    a partial arriving after it is text the client renders after the turn
    "ended". Partial deltas must also add up to the answer, or a streaming UI
    shows something other than what is persisted.
    """
    _known_gap(request, "streaming")
    answer = marker("STREAMED-ANSWER")
    scripted = harness.adapter.build([Round(text=answer, usage=(3, 2))])
    session_id = await harness.new_session()

    turn = await harness.run_turn(
        scripted,
        session_id,
        "stream please",
        run_config=RunConfig(streaming_mode=StreamingMode.SSE),
    )

    assert turn.error is None, turn.error
    finals = [i for i, e in enumerate(turn.events) if e.is_final_response()]
    assert _final_texts(turn.events) == [answer], _final_texts(turn.events)
    assert len(finals) == 1, f"expected one final response, got {len(finals)}"
    partial_at = [i for i, e in enumerate(turn.events) if e.partial]
    assert all(i < finals[0] for i in partial_at), (
        f"partial events at {partial_at} arrived after the final at {finals[0]}"
    )
    partial_text = "".join(
        p.text or ""
        for i in partial_at
        for p in (turn.events[i].content.parts if turn.events[i].content else [])
        if not p.thought
    )
    if harness.adapter.streams_partials:
        assert partial_at, "the runtime declares streaming but yielded no partials"
        assert partial_text.strip() == answer, (
            f"streamed deltas {partial_text!r} do not add up to {answer!r}"
        )
    persisted_partials = [e for e in turn.session.events if e.partial]
    assert not persisted_partials, "partial events must never be persisted"


@pytest.mark.asyncio
async def test_multi_turn_carries_history(harness: ConformanceHarness, request) -> None:
    """Turn 2's model request carries what was said in turn 1.

    The form is the runtime's business (ADK ``contents``, a Codex prompt blob,
    a Pi prompt); the contract is only that the model can see it. A runtime
    that dropped history would still answer turn 2 -- wrongly, and silently.
    """
    _known_gap(request, "multi_turn")
    user_1, answer_1 = marker("TURN1-USER"), marker("TURN1-ANSWER")
    user_2, answer_2 = marker("TURN2-USER"), marker("TURN2-ANSWER")
    scripted = harness.adapter.build(
        [Round(text=answer_1, usage=(1, 1)), Round(text=answer_2, usage=(1, 1))]
    )
    session_id = await harness.new_session()

    first = await harness.run_turn(scripted, session_id, user_1)
    second = await harness.run_turn(scripted, session_id, user_2)

    assert first.error is None and second.error is None, (first.error, second.error)
    assert first.final_text == answer_1
    assert second.final_text == answer_2
    requests = harness.adapter.requests()
    assert len(requests) == 2, f"expected one model call per turn: {len(requests)}"
    seen = requests[1].text
    for label, text in (("turn-1 user", user_1), ("turn-1 answer", answer_1)):
        assert text in seen, f"turn 2's request lost the {label} {text!r}"
    assert user_2 in seen, "turn 2's request does not carry turn 2's own message"
    assert first.finals[0].invocation_id != second.finals[0].invocation_id


@pytest.mark.asyncio
async def test_sessions_are_isolated(harness: ConformanceHarness, request) -> None:
    """Two sessions of one agent never see each other's conversation.

    Same agent object, same backend, same process -- the arrangement of a
    multi-tenant server. Anything a runtime caches per agent or per process
    instead of per session (a reused thread, a shared workspace transcript)
    shows up here as one tenant's text in the other's request.
    """
    _known_gap(request, "session_isolation")
    secret_a, answer_a = marker("SECRET-A"), marker("ANSWER-A")
    user_b, answer_b = marker("USER-B"), marker("ANSWER-B")
    scripted = harness.adapter.build(
        [Round(text=answer_a, usage=(1, 1)), Round(text=answer_b, usage=(1, 1))]
    )
    session_a = await harness.new_session()
    session_b = await harness.new_session()

    turn_a = await harness.run_turn(scripted, session_a, secret_a)
    turn_b = await harness.run_turn(scripted, session_b, user_b)

    assert turn_a.error is None and turn_b.error is None, (turn_a.error, turn_b.error)
    assert turn_b.final_text == answer_b
    seen_b = harness.adapter.requests()[1].text
    assert user_b in seen_b
    for leaked in (secret_a, answer_a):
        assert leaked not in seen_b, f"session B's request contains {leaked!r}"
    assert not any(
        p.text and (secret_a in p.text or answer_a in p.text)
        for e in turn_b.session.events
        if e.content
        for p in e.content.parts or []
    ), "session A's content was persisted into session B"


async def _cancel_turn(
    harness: ConformanceHarness, scripted, started, *, unblock=None
) -> Any:
    """Start a turn, cancel it once ``started()`` returns true, return the task.

    ``unblock`` releases whatever the turn is parked on. It is only used when
    the runtime fails to finish after cancellation, so a runtime that hangs is
    reported as a failure instead of leaving a task pending past the test.
    """
    harness.record_runtime_exits()
    session_id = await harness.new_session()
    task = asyncio.create_task(harness.run_turn(scripted, session_id, "go"))
    reached = await started()
    if not reached:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        pytest.fail("the turn never reached the point it was meant to be cancelled")
    task.cancel()
    done, _ = await asyncio.wait({task}, timeout=15)
    if not done:
        if unblock is not None:
            unblock()
        task.cancel()
        await asyncio.wait({task}, timeout=15)
        pytest.fail(
            "the cancelled turn did not finish within 15s: the runtime hangs on "
            "cancellation instead of releasing its turn"
        )
    return task


def _assert_cancel_propagated(harness: ConformanceHarness, task: Any) -> None:
    assert task.cancelled() or isinstance(task.exception(), asyncio.CancelledError), (
        f"the caller saw {task.exception()!r} instead of CancelledError"
    )
    assert harness.runtime_exits, "the runtime generator never ended"
    exit_ = harness.runtime_exits[-1]
    assert isinstance(exit_, asyncio.CancelledError), (
        "the runtime itself did not re-raise CancelledError; it ended with "
        f"{exit_!r}. Runner re-raises on its own, so only this check can tell "
        "a swallowed cancellation apart"
    )


@pytest.mark.asyncio
async def test_cancel_while_waiting_on_model(
    harness: ConformanceHarness, request
) -> None:
    """Cancelling a turn parked on the model stops the model call and cleans up.

    ``CancelledError`` must leave the runtime unchanged (asyncio's contract;
    otherwise the ``Runner`` treats the run as finished), the in-flight backend
    call must be abandoned rather than orphaned, and per-turn resources must be
    released -- a server cancels turns on every client disconnect.
    """
    _known_gap(request, "cancellation_model")
    adapter = harness.adapter
    scripted = adapter.build([HANG, Round(text="never sent", usage=(1, 1))])
    before = pending_tasks()

    task = await _cancel_turn(harness, scripted, adapter.wait_for_hang)

    _assert_cancel_propagated(harness, task)
    assert await wait_until(adapter.hang_abandoned), (
        "the backend call the turn was waiting on kept running after cancel"
    )
    calls = len(adapter.requests())
    await settle()
    assert len(adapter.requests()) == calls == 1, (
        "the backend was called again after the turn was cancelled"
    )
    assert await wait_until(lambda: not adapter.leaks()), adapter.leaks()
    leaked = {t for t in pending_tasks() - before if not adapter.is_service_task(t)}
    assert await wait_until(lambda: all(t.done() for t in leaked)), (
        f"tasks outlived the cancelled turn: {leaked}"
    )


@pytest.mark.asyncio
async def test_cancel_during_tool_execution(
    harness: ConformanceHarness, request
) -> None:
    """Cancelling mid-tool cancels the tool itself, not just the event stream.

    Runtimes that execute ADK tools off the caller's task (Codex's shim, Pi's
    HTTP bridge) must carry the cancellation there explicitly. A tool left
    running keeps doing side effects for an invocation that no longer exists.
    """
    _known_gap(request, "cancellation_tool")
    adapter = harness.adapter
    log = _ToolLog()
    scripted = adapter.build(
        [
            Round(tool_calls=(("block_forever", {"item": "job"}),), usage=(1, 1)),
            Round(text="never reached", usage=(1, 1)),
        ],
        tools=[_blocking_tool(log)],
    )

    async def tool_started() -> bool:
        try:
            await asyncio.wait_for(log.started.wait(), 30)
        except asyncio.TimeoutError:
            return False
        return True

    task = await _cancel_turn(harness, scripted, tool_started, unblock=log.release.set)

    _assert_cancel_propagated(harness, task)
    assert len(log.calls) == 1, log.calls
    assert await wait_until(lambda: log.cancelled), (
        "the tool kept running after its turn was cancelled"
    )
    await settle()
    assert len(adapter.requests()) == 1, (
        "the model was asked again after the turn was cancelled"
    )
    assert await wait_until(lambda: not adapter.leaks()), adapter.leaks()


@pytest.mark.asyncio
async def test_tool_call_executes_once_and_result_reaches_model(
    harness: ConformanceHarness, request
) -> None:
    """A Python function tool runs exactly once and the model sees its result.

    Exactly once, because a replayed or re-bridged call is a duplicated side
    effect (a second payment, a second email). And the *result* must reach the
    next model request, or the model re-issues the call or answers blind.
    """
    _known_gap(request, "tool_call")
    adapter = harness.adapter
    log = _ToolLog()
    result = marker("TOOL-RESULT")
    answer = marker("TOOL-ANSWER")
    scripted = adapter.build(
        [
            Round(tool_calls=(("lookup_code", {"item": "widget"}),), usage=(2, 1)),
            Round(text=answer, usage=(3, 2)),
        ],
        tools=[_lookup_tool(log, result)],
    )
    session_id = await harness.new_session()

    turn = await harness.run_turn(scripted, session_id, "what is the code?")

    assert turn.error is None, turn.error
    assert log.calls == [{"item": "widget"}], (
        f"the tool must run exactly once with the model's arguments: {log.calls}"
    )
    requests = adapter.requests()
    assert "lookup_code" in requests[0].tool_names, requests[0].tool_names
    assert len(requests) == 2, f"expected a tool round and an answer round: {requests}"
    assert result in requests[1].text, (
        "the tool's result never reached the model's next request"
    )
    assert _final_texts(turn.events) == [answer], _final_texts(turn.events)
    calls = [c for e in turn.events for c in e.get_function_calls()]
    responses = [r for e in turn.events for r in e.get_function_responses()]
    assert [c.name for c in calls] == ["lookup_code"], calls
    assert [r.name for r in responses] == ["lookup_code"], responses


@pytest.mark.asyncio
async def test_tool_failure_is_reported_to_model(
    harness: ConformanceHarness, request
) -> None:
    """A raising tool becomes an error result for the model, not a crash.

    Tools fail routinely (a timeout, a 500 from a service); the model is the
    component that can recover (retry, apologise, pick another tool), so it
    must be told what failed -- and the invocation must still end in an answer.
    """
    _known_gap(request, "tool_failure")
    adapter = harness.adapter
    log = _ToolLog()
    failure = marker("TOOL-FAILURE")
    answer = marker("RECOVERED")
    scripted = adapter.build(
        [
            Round(tool_calls=(("flaky_lookup", {"item": "widget"}),), usage=(1, 1)),
            Round(text=answer, usage=(1, 1)),
        ],
        tools=[_failing_tool(log, failure)],
    )
    session_id = await harness.new_session()

    turn = await harness.run_turn(scripted, session_id, "look it up")

    assert turn.error is None, f"a failing tool crashed the invocation: {turn.error!r}"
    assert len(log.calls) == 1, log.calls
    requests = adapter.requests()
    assert len(requests) == 2, f"the model was not asked again: {len(requests)}"
    assert failure in requests[1].text, (
        "the model's next request does not say why the tool failed"
    )
    assert _final_texts(turn.events) == [answer], _final_texts(turn.events)


class _Rendezvous:
    """Releases its callers only once ``parties`` of them have arrived."""

    def __init__(self, parties: int) -> None:
        self._parties = parties
        self._arrived = 0
        self._all_here = asyncio.Event()

    async def wait(self, timeout: float = 30.0) -> bool:
        self._arrived += 1
        if self._arrived >= self._parties:
            self._all_here.set()
        try:
            await asyncio.wait_for(self._all_here.wait(), timeout)
        except asyncio.TimeoutError:
            return False
        return True


@pytest.mark.asyncio
async def test_concurrent_sessions_do_not_cross_talk(
    harness: ConformanceHarness, request
) -> None:
    """Two turns in flight at once each get their own request, tool and answer.

    The rendezvous holds both tools until both are inside their executor, so
    this is a real overlap rather than two sequential turns: any per-process
    "current turn" state (a shared shim slot, a global prompt buffer) hands one
    turn the other's data.
    """
    _known_gap(request, "concurrent_sessions")
    adapter = harness.adapter
    rendezvous = _Rendezvous(2)
    overlapped: dict[str, bool] = {}

    async def checkpoint(label: str) -> dict:
        """Wait until the other tenant's turn is also in flight.

        Args:
            label (str): This tenant.

        Returns:
            dict: A receipt naming the tenant.
        """
        overlapped[label] = await rendezvous.wait()
        return {"receipt": f"RECEIPT-{label}"}

    labels = (marker("alpha"), marker("beta"))
    agents = {
        label: adapter.build(
            [
                Round(tool_calls=(("checkpoint", {"label": label}),), usage=(1, 1)),
                Round(text=f"ANSWER-{label}", usage=(1, 1)),
            ],
            key=label,
            tools=[checkpoint],
        )
        for label in labels
    }
    sessions = {label: await harness.new_session() for label in labels}

    turns = await asyncio.gather(
        *(
            harness.run_turn(agents[label], sessions[label], f"USER-{label}")
            for label in labels
        )
    )

    assert overlapped == {labels[0]: True, labels[1]: True}, (
        f"the two turns never overlapped inside their tools: {overlapped}"
    )
    for label, other, turn in zip(labels, reversed(labels), turns):
        assert turn.error is None, turn.error
        assert turn.final_text == f"ANSWER-{label}", turn.final_text
        requests = adapter.requests(label)
        assert len(requests) == 2, requests
        assert f"USER-{label}" in requests[0].text
        assert f"RECEIPT-{label}" in requests[1].text, (
            f"{label}'s own tool result did not reach its model"
        )
        for request_ in requests:
            assert other not in request_.text, (
                f"{label}'s request carries the other tenant's data ({other})"
            )


@pytest.mark.asyncio
async def test_final_event_carries_usage(harness: ConformanceHarness, request) -> None:
    """The backend's reported usage reaches the events, counted exactly once.

    Token accounting (quotas, billing, portal metrics) sums ``usage_metadata``
    across a turn's events without deduplicating, so the contract is: the
    final response carries usage when the backend reported any, and the turn's
    total equals what the backend declared -- no double counting of a
    cumulative total, no dropped tool round.
    """
    _known_gap(request, "usage")
    adapter = harness.adapter
    scripted = adapter.build([Round(text=marker("USAGE"), usage=(7, 3))])
    session_id = await harness.new_session()

    turn = await harness.run_turn(scripted, session_id, "count me")

    assert turn.error is None, turn.error
    usage = turn.finals[0].usage_metadata
    assert usage is not None, "the final response carries no usage_metadata"
    assert (
        usage.prompt_token_count,
        usage.candidates_token_count,
        usage.total_token_count,
    ) == (7, 3, 10), usage
    assert _usage_total(turn.events) == 10, "usage was counted more than once"

    log = _ToolLog()
    tool_agent = adapter.build(
        [
            Round(tool_calls=(("lookup_code", {"item": "x"}),), usage=(11, 5)),
            Round(text=marker("USAGE-TOOL"), usage=(7, 3)),
        ],
        key="tool-usage",
        tools=[_lookup_tool(log, "code")],
    )
    tool_turn = await harness.run_turn(
        tool_agent, await harness.new_session(), "count the tool round too"
    )
    assert tool_turn.error is None, tool_turn.error
    assert _usage_total(tool_turn.events) == 26, (
        f"a two-call turn reported {_usage_total(tool_turn.events)} tokens; the "
        "backend declared 11+5 and 7+3"
    )


@pytest.mark.asyncio
async def test_turns_release_per_turn_state(
    harness: ConformanceHarness, request
) -> None:
    """Completed turns leave no per-turn state behind.

    A server runs one process for days; anything a turn registers (a shim turn
    token and its executors, a temp ``CODEX_HOME``, a Pi subprocess or its
    generated extension, a background task) and does not release is a leak
    proportional to traffic -- and a turn token that outlives its turn is a
    credential that still works.
    """
    _known_gap(request, "lifecycle_cleanup")
    adapter = harness.adapter
    log = _ToolLog()
    scripted = adapter.build(
        [
            Round(tool_calls=(("lookup_code", {"item": "x"}),), usage=(1, 1)),
            Round(text=marker("FIRST"), usage=(1, 1)),
            Round(text=marker("SECOND"), usage=(1, 1)),
        ],
        tools=[_lookup_tool(log, "code")],
    )
    session_id = await harness.new_session()
    before = pending_tasks()

    for text in ("first", "second"):
        turn = await harness.run_turn(scripted, session_id, text)
        assert turn.error is None, turn.error

    assert adapter.leaks() == [], adapter.leaks()
    await settle()
    leaked = {
        t
        for t in pending_tasks() - before
        if not t.done() and not adapter.is_service_task(t)
    }
    assert not leaked, f"tasks outlived their turns: {leaked}"


# ================================================ capability-gated scenarios


@pytest.mark.asyncio
async def test_mcp_tool_call(harness: ConformanceHarness) -> None:
    """An MCP toolset's tool is callable and its result reaches the model.

    MCP tools are resolved from a live server rather than declared in Python,
    so a runtime that bridges tools by inspecting function signatures can
    advertise nothing at all for them. The demo server is a real stdio MCP
    subprocess; nothing leaves the machine.
    """
    adapter = harness.adapter
    adapter.require(Capability.MCP_TOOLS)
    pytest.importorskip("mcp")
    answer = marker("MCP-ANSWER")
    scripted = adapter.build(
        [
            Round(
                tool_calls=(("get_order_status", {"order_id": "A10086"}),),
                usage=(1, 1),
            ),
            Round(text=answer, usage=(1, 1)),
        ],
        tools=[adapter.mcp_toolset()],
    )
    session_id = await harness.new_session()

    turn = await asyncio.wait_for(
        harness.run_turn(scripted, session_id, "where is order A10086?"), 120
    )

    assert turn.error is None, turn.error
    requests = adapter.requests()
    assert "get_order_status" in requests[0].tool_names, requests[0].tool_names
    assert len(requests) == 2, requests
    assert "will arrive tomorrow" in requests[1].text, (
        "the MCP tool's result never reached the model"
    )
    assert turn.final_text == answer
    assert adapter.leaks() == [], adapter.leaks()


@pytest.mark.asyncio
async def test_skill_is_visible_to_the_harness(harness: ConformanceHarness) -> None:
    """A skill attached to the agent is discoverable by the model's harness.

    Each runtime surfaces skills its own way (ADK through ``SkillToolset``'s
    ``list_skills`` tool, Codex by discovering ``$CODEX_HOME/skills``, Pi by
    being passed ``--skill``), so the contract is only that the skill's
    description -- what the model decides to load it by -- reaches the model
    within the turn.
    """
    adapter = harness.adapter
    adapter.require(Capability.SKILLS)
    from google.adk.skills.models import Frontmatter, Skill
    from google.adk.tools.skill_toolset import SkillToolset

    description = marker("SKILL-DESCRIPTION")
    answer = marker("SKILL-ANSWER")
    skill = Skill(
        frontmatter=Frontmatter(name="order-lookup", description=description),
        instructions="Look orders up carefully.",
    )
    plan = [Round(text=answer, usage=(1, 1))]
    if adapter.skill_discovery_tool:
        # The runtime only lists skills on request; the model asks first.
        plan.insert(
            0, Round(tool_calls=((adapter.skill_discovery_tool, {}),), usage=(1, 1))
        )
    scripted = adapter.build(plan, tools=[SkillToolset(skills=[skill])])
    session_id = await harness.new_session()

    turn = await harness.run_turn(scripted, session_id, "use your skills")

    assert turn.error is None, turn.error
    requests = adapter.requests()
    assert len(requests) == len(plan), requests
    assert description in requests[-1].text, (
        "the skill's description was not visible to the model's harness"
    )
    assert turn.final_text == answer
    assert adapter.leaks() == [], adapter.leaks()


@pytest.mark.asyncio
async def test_approval_gates_tool_until_confirmed(
    harness: ConformanceHarness,
) -> None:
    """A confirmation-gated tool waits for the user, then runs exactly once.

    Turn 1 must surface ADK's ``adk_request_confirmation`` and must *not* run
    the tool (running it first and asking afterwards is no gate). Turn 2
    answers the request; the tool then runs once and its result reaches the
    model. A runtime without this resume path either never runs the tool or
    runs it on every later turn.

    How many model calls turn 1 makes is deliberately *not* pinned: ADK pauses
    the invocation at the confirmation request, while Codex hands the model a
    ``confirmation_required`` result and lets it reply. Turn 2 therefore gets a
    freshly built plan, so neither shape can misalign the script.
    """
    adapter = harness.adapter
    adapter.require(Capability.APPROVALS)
    from google.adk.tools.function_tool import FunctionTool

    log = _ToolLog()
    result = marker("APPROVED-RESULT")
    answer = marker("APPROVED-ANSWER")

    def delete_item(item: str) -> dict:
        """Delete an item permanently.

        Args:
            item (str): The item to delete.

        Returns:
            dict: A deletion receipt.
        """
        log.calls.append({"item": item})
        return {"deleted": item, "receipt": result}

    tools = [FunctionTool(delete_item, require_confirmation=True)]
    scripted = adapter.build(
        [
            Round(tool_calls=(("delete_item", {"item": "widget"}),), usage=(1, 1)),
            Round(text=marker("AWAITING-CONFIRMATION"), usage=(1, 1)),
        ],
        tools=tools,
    )
    session_id = await harness.new_session()

    first = await harness.run_turn(scripted, session_id, "delete the widget")

    assert first.error is None, first.error
    assert log.calls == [], "the tool ran before it was confirmed"
    confirmation = next(
        (
            call
            for event in first.events
            for call in event.get_function_calls()
            if call.name == "adk_request_confirmation"
        ),
        None,
    )
    assert confirmation is not None, "no adk_request_confirmation was surfaced"

    scripted = adapter.build([Round(text=answer, usage=(1, 1))], tools=tools)
    second = await harness.run_turn(
        scripted,
        session_id,
        message=types.Content(
            role="user",
            parts=[
                types.Part(
                    function_response=types.FunctionResponse(
                        id=confirmation.id,
                        name="adk_request_confirmation",
                        response={"confirmed": True},
                    )
                )
            ],
        ),
    )

    assert second.error is None, second.error
    assert log.calls == [{"item": "widget"}], (
        f"the confirmed tool must run exactly once: {log.calls}"
    )
    assert result in adapter.requests()[-1].text, (
        "the confirmed tool's result never reached the model"
    )
    assert second.final_text == answer, second.final_text


@pytest.mark.asyncio
async def test_resume_across_restart(harness: ConformanceHarness) -> None:
    """A session's native thread survives a process restart.

    Today every external runtime rebuilds its harness conversation from the
    ADK session on every turn. Once a runtime keeps a native thread (Codex
    ``thread_resume``), a restart between turns must resume *that* thread --
    same handle, history intact -- instead of silently starting a new one
    with a replayed transcript.
    """
    adapter = harness.adapter
    adapter.require(Capability.RESUME_ACROSS_RESTART)
    remembered, answer_1, answer_2 = (
        marker("REMEMBER"),
        marker("A1"),
        marker("A2"),
    )
    scripted = adapter.build(
        [Round(text=answer_1, usage=(1, 1)), Round(text=answer_2, usage=(1, 1))]
    )
    session_id = await harness.new_session()

    first = await harness.run_turn(scripted, session_id, remembered)
    thread_before = adapter.native_thread_id(session_id)
    adapter.restart()
    second = await harness.run_turn(scripted, session_id, "what did I say?")

    assert first.error is None and second.error is None, (first.error, second.error)
    assert thread_before, "the runtime reported no native thread for the session"
    assert adapter.native_thread_id(session_id) == thread_before, (
        "the restart started a new native thread instead of resuming"
    )
    resumed_prompt = adapter.requests()[-1].text
    assert remembered in resumed_prompt
    # A resumed native thread already carries turn 1; replaying the ADK
    # transcript on top of it would put the same history in front of the model
    # twice.
    assert resumed_prompt.count(remembered) == 1, (
        "turn 1 reached the model more than once: the resumed thread's history "
        "was also replayed from the ADK session"
    )
    assert second.final_text == answer_2
    assert adapter.leaks() == [], adapter.leaks()


@pytest.mark.asyncio
async def test_steer_in_flight_turn(harness: ConformanceHarness) -> None:
    """Input steered into a running turn reaches the model within that turn.

    The turn is held inside a tool; the steer arrives; the model's next
    request in the *same* invocation must carry it, and the turn still ends in
    exactly one final response.
    """
    adapter = harness.adapter
    adapter.require(Capability.STEER)
    log = _ToolLog()
    release = asyncio.Event()
    steer_text = marker("STEER")
    answer = marker("STEERED-ANSWER")

    async def wait_for_steer(item: str) -> dict:
        """Wait for more instructions.

        Args:
            item (str): What is being worked on.

        Returns:
            dict: Acknowledgement.
        """
        log.calls.append({"item": item})
        log.started.set()
        await release.wait()
        return {"ok": True}

    scripted = adapter.build(
        [
            Round(tool_calls=(("wait_for_steer", {"item": "x"}),), usage=(1, 1)),
            Round(text=answer, usage=(1, 1)),
        ],
        tools=[wait_for_steer],
    )
    session_id = await harness.new_session()
    task = asyncio.create_task(harness.run_turn(scripted, session_id, "start"))
    await asyncio.wait_for(log.started.wait(), 30)
    await adapter.steer(session_id, steer_text)
    release.set()
    turn = await asyncio.wait_for(task, 30)

    assert turn.error is None, turn.error
    assert steer_text in adapter.requests()[-1].text, (
        "the steer never reached the model"
    )
    assert _final_texts(turn.events) == [answer]
    assert len({e.invocation_id for e in turn.events}) == 1, (
        "steering must not start a second invocation"
    )


@pytest.mark.asyncio
async def test_turn_timeout(harness: ConformanceHarness) -> None:
    """A turn stuck on the model ends at its deadline, with resources released.

    Codex CLI 0.159 retries an unreachable backend forever unless told not to;
    a runtime-level turn deadline is the backstop. The turn must fail with a
    timeout the ``Runner`` can surface, not hang, and must release its turn.
    """
    adapter = harness.adapter
    adapter.require(Capability.TURN_TIMEOUT)
    scripted = adapter.build([HANG], **adapter.turn_timeout_kwargs(0.5))
    session_id = await harness.new_session()

    turn = await asyncio.wait_for(harness.run_turn(scripted, session_id, "go"), 30)

    assert isinstance(turn.error, (TimeoutError, asyncio.TimeoutError)), turn.error
    assert await wait_until(adapter.hang_abandoned)
    assert await wait_until(lambda: not adapter.leaks()), adapter.leaks()


@pytest.mark.asyncio
async def test_compaction_preserves_turn_contract(harness: ConformanceHarness) -> None:
    """After the runtime compacts, the next turn still sees the summary.

    Compaction replaces history with a summary; the contract is that later
    turns carry that summary (not nothing, and not the full transcript), and
    that the compaction pass itself never receives the agent's ADK tools.
    """
    adapter = harness.adapter
    adapter.require(Capability.COMPACTION)
    remembered = marker("COMPACT-ME")
    summary = marker("SUMMARY")
    scripted = adapter.build(
        [
            Round(text=marker("A1"), usage=(1, 1)),
            Round(text=summary, usage=(1, 1)),
            Round(text=marker("A2"), usage=(1, 1)),
        ],
        **adapter.compaction_kwargs(),
    )
    session_id = await harness.new_session()

    await harness.run_turn(scripted, session_id, remembered)
    turn = await harness.run_turn(scripted, session_id, "and now?")

    assert turn.error is None, turn.error
    last = adapter.requests()[-1].text
    assert summary in last, "the next turn lost the compaction summary"
