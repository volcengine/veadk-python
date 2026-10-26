# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

"""Fault gate regressions: canonical turn identity, not prompt/marker heuristics."""

import asyncio
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).parents[2] / "examples/16_self_host_sandbox"))
fault = importlib.import_module("soak_fault_preflight")


def event(seq, kind, **fields):
    return {"seq": seq, "id": f"event-{seq}", "type": kind, **fields}


def turn(start=10, *, error=False):
    return [
        event(start, "user.message"),
        event(start + 1, "agent.tool_use", id=f"call-{start}"),
        event(
            start + 2,
            "agent.tool_result",
            tool_use_id=f"call-{start}",
            is_error=error,
            content="failed" if error else "mark",
        ),
        event(start + 3, "agent.message", content="mark"),
        event(start + 4, "session.status_idle", stop_reason={"type": "end_turn"}),
    ]


class Events:
    def __init__(self, events, *, acknowledged=None, stall=False):
        self.events = events
        self.acknowledged = acknowledged or event(10, "user.message")
        self.stall = stall
        self.closed = False
        self.options = None

    async def send(self, *_args, **_kwargs):
        return {"data": [self.acknowledged]}

    async def stream(self, *_args, **kwargs):
        self.options = kwargs
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        self.closed = True

    async def __aiter__(self):
        for item in self.events:
            if isinstance(item, Exception):
                raise item
            yield item
        if self.stall:
            await asyncio.Event().wait()


def client(events):
    return SimpleNamespace(
        beta=SimpleNamespace(sessions=SimpleNamespace(events=events))
    )


def run(events):
    return asyncio.run(
        fault.run_verified_tool_turn(
            client(events), "session", marker="mark", prompt="new prompt", timeout=0.1
        )
    )


def test_old_error_idle_replay_cannot_finish_recovery():
    events = Events(turn(1, error=True) + turn())
    result = run(events)
    fault.assert_tool_turn(result, "mark")
    assert result["tool_uses"] == ["call-10"]
    assert events.options["extra_headers"] == {"Last-Event-ID": "9"}
    assert result["input_event_id"] == "event-10"
    assert events.closed


def test_new_tool_error_still_fails_and_keeps_evidence():
    result = run(Events(turn(error=True)))
    with pytest.raises(AssertionError, match="tool execution failed"):
        fault.assert_tool_turn(result, "mark")
    assert result["tool_error_ids"] == ["call-10"]
    assert result["events"][-1]["type"] == "session.status_idle"


@pytest.mark.parametrize(
    "items",
    [
        turn(1),  # No acknowledged new input, even if old final contains marker.
        [
            event(10, "user.message"),
            event(11, "agent.message", content="mark"),
            event(12, "session.status_idle"),
        ],  # No new tool.
        turn()[:-1],  # EOF before idle.
        [*turn()[:3], event(13, "session.status_idle"), turn()[3]],  # Early idle.
        [*turn()[:3], event(13, "session.error")],
        [*turn()[:3], event(13, "user.message")],  # Concurrent unrelated turn.
    ],
)
def test_incomplete_or_interleaved_turn_fails(items):
    result = run(Events(items))
    with pytest.raises(AssertionError):
        fault.assert_tool_turn(result, "mark")


def test_timeout_retains_partial_turn_and_closes_stream():
    events = Events(turn()[:2], stall=True)
    result = run(events)
    with pytest.raises(AssertionError, match="TimeoutError"):
        fault.assert_tool_turn(result, "mark")
    assert result["tool_uses"] == ["call-10"]
    assert events.closed


def test_duplicate_event_replay_is_idempotent():
    items = turn()
    result = run(Events([items[0], items[1], items[1], *items[2:]]))
    fault.assert_tool_turn(result, "mark")
    assert result["tool_uses"] == ["call-10"]


def test_conflicting_duplicate_sequence_fails():
    items = turn()
    result = run(Events([*items[:3], {**items[2], "is_error": True}, *items[3:]]))
    with pytest.raises(AssertionError, match="sequence"):
        fault.assert_tool_turn(result, "mark")


def test_pre_tool_commentary_is_not_the_final():
    items = turn()
    result = run(
        Events(
            [
                items[0],
                event(11, "agent.message", content="I will run the tool"),
                *[{**item, "seq": item["seq"] + 1} for item in items[1:]],
            ]
        )
    )
    fault.assert_tool_turn(result, "mark")
    assert result["final"] == "mark"


def test_no_fault_injection_cannot_pass():
    with pytest.raises(AssertionError, match="physical sandbox"):
        asyncio.run(
            fault.run_loss_during_active_tool(
                client(
                    Events(
                        [event(10, "user.message"), event(11, "session.status_idle")]
                    )
                ),
                object(),
                "session",
                marker="mark",
                timeout=0.1,
            )
        )


def test_real_sdk_history_pagination_uses_decimal_cursor():
    import anthropic
    import httpx2
    from managed_agent_loop import ManagedAgentsLoop

    seen = []

    def handle(request):
        page = request.url.params.get("page")
        seen.append(page)
        if page not in {"100", "102"}:
            return httpx2.Response(
                400,
                json={
                    "error": {
                        "type": "invalid_request_error",
                        "message": "page is invalid",
                    }
                },
            )
        seqs = (101, 102) if page == "100" else (103,)
        return httpx2.Response(
            200,
            json={
                "data": [event(n, "system.message") for n in seqs],
                "has_more": page == "100",
                "next_page": "102" if page == "100" else None,
            },
        )

    async def check():
        async with anthropic.AsyncAnthropic(
            api_key="test",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        ) as sdk:
            loop = ManagedAgentsLoop(runner=object(), session_id="session")
            result = await loop._list_events_after(sdk, 100)
            assert [loop._event_seq(item) for item in result] == [101, 102, 103]

    asyncio.run(check())
    assert seen == ["100", "102"]


def test_real_sdk_send_ack_and_durable_sse_replay():
    import json

    import anthropic
    import httpx2

    def handle(request):
        if request.method == "POST":
            return httpx2.Response(200, json={"data": [event(10, "user.message")]})
        assert request.headers["Last-Event-ID"] == "9"
        frames = "".join(
            f"id: {item['seq']}\nevent: {item['type']}\ndata: {json.dumps(item)}\n\n"
            for item in turn()
        )
        return httpx2.Response(
            200, text=frames, headers={"Content-Type": "text/event-stream"}
        )

    async def check():
        async with anthropic.AsyncAnthropic(
            api_key="test",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(handle)),
        ) as sdk:
            result = await fault.run_verified_tool_turn(
                sdk, "session", marker="mark", prompt="new prompt", timeout=1
            )
            fault.assert_tool_turn(result, "mark")

    asyncio.run(check())


@pytest.mark.parametrize(
    "failure",
    [
        "tool",
        "timeout",
        "snapshot",
        "cleanup_snapshot",
        "fault_timeout",
        "not_injected",
    ],
)
def test_main_keeps_failed_second_turn_before_cleanup(monkeypatch, failure):
    items = turn(error=failure == "tool")
    items[3]["content"] = "fault-b-12345678"
    monkeypatch.setattr(fault.uuid, "uuid4", lambda: SimpleNamespace(hex="12345678"))
    events = Events(
        items[:2] if failure == "timeout" else items, stall=failure == "timeout"
    )

    class Sessions:
        async def create(self, **_kwargs):
            return SimpleNamespace(id="session")

        async def archive(self, _session):
            return None

    sessions = Sessions()
    sessions.events = events

    class Client:
        beta = SimpleNamespace(sessions=sessions)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            pass

    class Inspector:
        async def wait_absent(self, *_args, **_kwargs):
            pass

        async def wait_present(self, *_args, **_kwargs):
            return {"session_id": "replacement"}

    async def loss(*_args, **_kwargs):
        if failure == "not_injected":
            raise AssertionError("fault never injected")
        if failure == "fault_timeout":
            return {"physical": {"session_id": "deleted"}, "error": "TimeoutError"}
        return {"physical": {"session_id": "deleted"}, "error": None}

    calls = 0

    async def snapshot(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        if failure == "snapshot" and calls == 2:
            raise RuntimeError("snapshot unavailable")
        if failure == "cleanup_snapshot" and calls == 3:
            raise RuntimeError("cleanup snapshot unavailable")
        return {"rows": [{"work_id": "work", "state": "stopped"}]}

    monkeypatch.setattr(fault.anthropic, "AsyncAnthropic", lambda **_kwargs: Client())
    monkeypatch.setattr(fault, "AgentKitInspector", lambda *_args: Inspector())
    monkeypatch.setattr(fault, "run_loss_during_active_tool", loss)
    monkeypatch.setattr(fault, "session_work_snapshot", snapshot)
    args = SimpleNamespace(
        inspector_script="unused",
        tool_id="tool",
        base_url="http://fixture",
        auth_token="test",
        turn_timeout=1,
        agent_id="agent",
        environment_id="env",
        recovery_timeout=0.01,
    )
    result = asyncio.run(fault.main(args))
    assert result["recovery_ok"] is False
    if failure in {"fault_timeout", "not_injected"}:
        assert events.options is None  # Never start the dependent recovery turn.
        assert result["error"]
        assert result["cleanup"] == "archived"
        return
    assert result["second_turn"]["tool_uses"] == ["call-10"]
    assert result["second_turn"]["events"]
    assert result["cleanup"] == "archived"
    if failure == "tool":
        assert result["second_turn"]["tool_error_ids"] == ["call-10"]
    elif failure == "timeout":
        assert "TimeoutError" in result["second_turn"]["error"]
    elif failure == "snapshot":
        assert "snapshot unavailable" in result["error"]
    else:
        assert result["work_after_cleanup_query"]["complete"] is False
        assert (
            "cleanup snapshot unavailable"
            in result["work_after_cleanup_query"]["error"]
        )
