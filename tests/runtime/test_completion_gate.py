# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""The first idle is not acceptance: wait for the Work successor transaction."""

import asyncio
import json
import runpy
import sys
from types import SimpleNamespace

import pytest

from test_fault_recovery_boundary import Events, client, event, fault, turn
import soak_load_test as soak


class Page:
    def __init__(self, items):
        self.data = items
        self.next_page = None


class WorkAPI:
    def __init__(self, rows):
        self.rows = rows
        self.calls = 0

    async def list(self, *_args, **_kwargs):
        self.calls += 1
        return Page(self.rows)


def work(work_id, state, *, kind="agent_loop"):
    return {
        "id": work_id,
        "state": state,
        "data": {"id": "session", "type": "session"},
        "runtime_type": "default" if kind == "agent_loop" else None,
        "metadata": {"managed_agent_worker_id": work_id},
        "environment_id": "env",
    }


def setup(*, later=(), rows=None):
    events = Events(turn())
    history = turn() + list(later)

    async def list_events(*_args, **_kwargs):
        return Page(history)

    events.list = list_events
    sdk = client(events)
    sdk.beta.environments = SimpleNamespace(
        work=WorkAPI(rows or [work("pod-a", "stopped")])
    )
    return sdk


def run(sdk):
    return asyncio.run(
        fault.run_verified_tool_turn(
            sdk,
            "session",
            marker="mark",
            prompt="prompt",
            timeout=0.15,
            environment_id="env",
        )
    )


def test_late_different_work_execution_after_first_idle_fails():
    sdk = setup(
        later=[event(15, "agent.tool_use", id="second-call")],
        rows=[work("pod-a", "stopped"), work("pod-b", "active")],
    )
    result = run(sdk)
    with pytest.raises(AssertionError, match="after.*idle"):
        fault.assert_tool_turn(result, "mark")
    assert result["completion"]["events"][-1]["id"] == "second-call"
    assert len(result["completion"]["work"]) == 2
    assert result["input_event_id"] == "event-10"


def test_idle_with_queued_successor_never_passes_or_archives_early():
    result = run(setup(rows=[work("pod-a", "stopped"), work("pod-b", "queued")]))
    with pytest.raises(AssertionError, match="TimeoutError"):
        fault.assert_tool_turn(result, "mark")
    assert not result["completion"]["settled"]


def test_terminal_work_graph_and_no_new_execution_passes():
    sdk = setup(rows=[work("pod-a", "stopped"), work("sandbox", "active", kind="tool")])
    result = run(sdk)
    fault.assert_tool_turn(result, "mark")
    assert result["completion"]["settled"]
    assert sdk.beta.environments.work.calls >= 2


def test_missing_work_evidence_cannot_pass():
    sdk = setup(rows=[work("sandbox", "active", kind="tool")])
    result = run(sdk)
    with pytest.raises(AssertionError):
        fault.assert_tool_turn(result, "mark")


def test_delayed_execution_is_seen_while_successor_is_pending():
    sdk = setup(rows=[work("pod-a", "stopped"), work("pod-b", "queued")])

    async def delayed_history(*_args, **_kwargs):
        items = turn()
        if sdk.beta.environments.work.calls >= 2:
            items += [event(15, "agent.tool_use", id="late-other-pod")]
        return Page(items)

    sdk.beta.sessions.events.list = delayed_history
    result = run(sdk)
    assert "after end_turn idle" in result["error"]
    assert result["completion"]["events"][-1]["id"] == "late-other-pod"


def test_soak_uses_same_gate_and_preserves_failure_evidence():
    async def check():
        sdk = setup(later=[event(15, "agent.tool_use", id="late-other-pod")])
        now = soak.time.monotonic()
        record = await soak.run_one_turn(
            sdk,
            "session",
            marker="mark",
            prompt="prompt",
            timeout=0.2,
            require_tool=True,
            worker=1,
            request_id="request",
            run_start=now,
            deadline=now + 1,
            environment_id="env",
        )
        assert not record.ok
        assert "after end_turn idle" in record.error_reason
        assert record.completion["input_event_id"] == "event-10"
        assert record.completion["work"]

    asyncio.run(check())


def test_multiple_tools_in_one_input_are_legal():
    sdk = setup()
    items = [
        *turn()[:3],
        event(13, "agent.tool_use", id="second-call"),
        event(14, "agent.tool_result", tool_use_id="second-call", content="mark"),
        event(15, "agent.message", content="mark"),
        event(16, "session.status_idle", stop_reason={"type": "end_turn"}),
    ]
    sdk.beta.sessions.events.events = items

    async def list_events(*_args, **_kwargs):
        return Page(items)

    sdk.beta.sessions.events.list = list_events
    result = run(sdk)
    fault.assert_tool_turn(result, "mark")
    assert len(result["tool_uses"]) == 2
    assert result["completion"]["settled"]


def test_fault_cli_exits_nonzero_and_writes_failed_gate(monkeypatch, tmp_path):
    second = run(setup(later=[event(15, "agent.tool_use", id="duplicate")]))
    result = {
        "recovery_ok": False,
        "second_turn": second,
        "cleanup": "archived",
        "physical_cleanup_reclaimed": True,
    }
    output = tmp_path / "result.json"

    def completed(coro):
        coro.close()
        return result

    monkeypatch.setattr(asyncio, "run", completed)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            fault.__file__,
            "--base-url",
            "http://fixture",
            "--agent-id",
            "agent",
            "--environment-id",
            "env",
            "--tool-id",
            "tool",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as raised:
        runpy.run_path(fault.__file__, run_name="__main__")
    assert raised.value.code == 1
    assert (
        json.loads(output.read_text())["second_turn"]["completion"]["events"][-1]["id"]
        == "duplicate"
    )
