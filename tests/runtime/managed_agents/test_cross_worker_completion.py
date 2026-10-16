"""Two independent Pod caches consuming the same canonical event ledger."""

import asyncio
from types import SimpleNamespace

from .test_managed_agent_loop import ManagedAgentsLoop, _Runner, _SDK, _AsyncPage


class Ledger:
    def __init__(self):
        self.events = []

    def append(self, kind, **fields):
        seq = len(self.events) + 1
        item = {"seq": seq, "id": f"event-{seq}", "type": kind, **fields}
        self.events.append(item)
        return item

    def list(self, _session, **options):
        cursor = int(options.get("page", 0))
        return _AsyncPage([e for e in self.events if e["seq"] > cursor])


def test_two_pods_do_not_repeat_other_pods_completed_input():
    async def check():
        ledger = Ledger()
        sdk = _SDK()
        sdk.beta.sessions.events.list = ledger.list

        # Preserve actual _run_turn and persisted completion, not a fake guard.
        async def send(_session, *, events):
            data = []
            for event in events:
                fields = dict(event)
                kind = fields.pop("type")
                data.append(SimpleNamespace(**ledger.append(kind, **fields)))
            return SimpleNamespace(data=data)

        sdk.beta.sessions.events.send = send
        pods = [
            ManagedAgentsLoop(runner=_Runner([]), session_id="session")
            for _ in range(2)
        ]
        ledger.append("user.message", content=[{"type": "text", "text": "first"}])
        assert await pods[0].run_pending(sdk) == 1
        ledger.append("user.message", content=[{"type": "text", "text": "recovery"}])
        assert await pods[1].run_pending(sdk) == 1
        # The stale Pod returns on a delayed successor, after the other Pod's idle.
        assert await pods[0].run_pending(sdk) == 0
        fresh = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
        assert await fresh.run_pending(sdk) == 0
        ledger.append("user.message", content=[{"type": "text", "text": "next"}])
        assert await pods[0].run_pending(sdk) == 1
        assert await pods[1].run_pending(sdk) == 0
        assert [len(p.runner.calls) for p in pods] == [2, 1]

    asyncio.run(check())


def test_interrupt_cancels_all_earlier_inputs_without_consuming_next_turn():
    loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
    loop._restore_completed_inputs(
        [
            {"id": "a", "type": "user.message"},
            {"id": "b", "type": "user.message"},
            {"id": "interrupt", "type": "user.interrupt"},
            {"id": "next", "type": "user.message"},
        ]
    )
    assert loop._completed_inputs == {"a", "b"}


def test_duplicate_terminal_replay_does_not_consume_next_queued_input():
    loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
    one = {"id": "one", "type": "user.message", "seq": 1}
    two = {"id": "two", "type": "user.message", "seq": 2}
    idle = {
        "id": "idle",
        "type": "session.status_idle",
        "seq": 3,
        "stop_reason": {"type": "end_turn"},
    }
    loop._restore_completed_inputs([one, two, idle, idle])
    assert loop._completed_inputs == {"one"}
    loop._restore_completed_inputs([one, two, idle])
    assert loop._completed_inputs == {"one"}


def test_fresh_workers_reconcile_actual_sdk_http_event_ledger():
    import json
    import anthropic
    import httpx2

    ledger = []
    requests = []

    def append(event):
        seq = len(ledger) + 1
        persisted = {
            "id": f"event-{seq}",
            "seq": seq,
            "processed_at": "2026-10-10T00:00:00Z",
            **event,
        }
        ledger.append(persisted)
        return persisted

    def transport(request):
        requests.append(request)
        assert request.url.path == "/v1/sessions/session/events"
        if request.method == "POST":
            body = json.loads(request.content)
            return httpx2.Response(
                200, json={"data": [append(event) for event in body["events"]]}
            )
        cursor = int(request.url.params.get("page", "0"))
        return httpx2.Response(
            200,
            json={
                "data": [event for event in ledger if event["seq"] > cursor],
                "has_more": False,
            },
        )

    async def check():
        pods = [
            ManagedAgentsLoop(runner=_Runner([]), session_id="session")
            for _ in range(2)
        ]
        async with anthropic.AsyncAnthropic(
            auth_token="synthetic-token",
            base_url="http://ledger.invalid",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport)),
        ) as sdk:
            for prompt, pod in (("first", 0), ("second", 1), ("third", 0)):
                append(
                    {
                        "type": "user.message",
                        "content": [{"type": "text", "text": prompt}],
                    }
                )
                assert await pods[pod].run_pending(sdk) == 1
                assert await pods[1 - pod].run_pending(sdk) == 0
            fresh = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
            assert await fresh.run_pending(sdk) == 0
            assert [len(pod.runner.calls) for pod in pods] == [2, 1]

    asyncio.run(check())
    assert any(request.url.params.get("page") for request in requests)


def test_transient_event_publish_uses_actual_sdk_transport(caplog):
    import json
    import anthropic
    import httpx2

    captured = []

    def transport(request):
        captured.append(json.loads(request.content))
        return httpx2.Response(200, json={"data": []})

    async def check():
        loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
        async with anthropic.AsyncAnthropic(
            auth_token="synthetic-token",
            base_url="http://ledger.invalid",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport)),
        ) as sdk:
            await loop._publish_transient(
                sdk, {"type": "agent.message_stream_start", "message_id": "message"}
            )
            await loop._publish_transient(
                sdk,
                {
                    "type": "agent.message_chunk",
                    "message_id": "message",
                    "delta": "hello",
                },
            )

    asyncio.run(check())
    assert [entry["events"][0]["type"] for entry in captured] == [
        "event_start",
        "event_delta",
    ]
    assert "publish failed" not in caplog.text


def test_transient_transport_failure_propagates_without_secret_logs(caplog):
    import anthropic
    import httpx2
    import pytest

    def transport(request):
        return httpx2.Response(
            500,
            json={
                "type": "error",
                "error": {"type": "api_error", "message": "secret-provider-marker"},
            },
        )

    async def check():
        loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session")
        async with anthropic.AsyncAnthropic(
            auth_token="synthetic-token",
            base_url="http://ledger.invalid",
            max_retries=0,
            http_client=httpx2.AsyncClient(transport=httpx2.MockTransport(transport)),
        ) as sdk:
            with pytest.raises(anthropic.APIStatusError):
                await loop._publish_transient(
                    sdk, {"type": "agent.message_stream_start", "message_id": "message"}
                )

    asyncio.run(check())
    assert "publish failed" in caplog.text
    assert "secret-provider-marker" not in caplog.text
