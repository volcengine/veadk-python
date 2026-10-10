from __future__ import annotations

import asyncio
import importlib
import json
from types import SimpleNamespace

import pytest
from pydantic import BaseModel


debug = importlib.import_module("veadk.runtime.managed_agents.events")


def records(capsys):
    return [
        json.loads(line.removeprefix("MA_DEBUG_EVENT "))
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("MA_DEBUG_EVENT ")
    ]


@pytest.mark.parametrize("value", [None, "0", "false", "off"])
def test_disabled_trace_does_not_serialize_events(monkeypatch, capsys, value):
    monkeypatch.delenv("MA_DEBUG_EVENTS", raising=False)
    if value is not None:
        monkeypatch.setenv("MA_DEBUG_EVENTS", value)

    class Event:
        def model_dump(self, **kwargs):
            pytest.fail("Disabled tracing must not serialize events")

    debug.trace_event("received", "runner", "session-1", Event())
    assert capsys.readouterr().out == ""


def test_complete_payload_is_logged_without_mutation_or_credentials(
    monkeypatch, capsys
):
    monkeypatch.setenv("MA_DEBUG_EVENTS", "1")

    class Event(BaseModel):
        type: str
        content: str
        metadata: dict

    event = Event(
        type="user.message",
        content="完整内容\n" * 10000,
        metadata={
            "API-Key": "private-key",
            "nested": [{"Authorization": "Bearer private-token", "text": "visible"}],
        },
    )
    debug.trace_event("received", "sse", "session-1", event)
    (record,) = records(capsys)
    assert record["direction"] == "received"
    assert record["source"] == "sse"
    assert record["session_id"] == "session-1"
    assert record["event"]["content"] == event.content
    assert record["event"]["metadata"] == {
        "API-Key": "[REDACTED]",
        "nested": [{"Authorization": "[REDACTED]", "text": "visible"}],
    }
    assert event.metadata["API-Key"] == "private-key"


def test_trace_failure_does_not_fail_a_turn_or_print_error_secrets(monkeypatch, capsys):
    monkeypatch.setenv("MA_DEBUG_EVENTS", "true")

    class Event:
        def model_dump(self, **kwargs):
            raise RuntimeError("private-error")

    debug.trace_event("received", "runner", "session-1", Event())
    assert "private-error" not in capsys.readouterr().out


@pytest.mark.asyncio
async def test_send_and_paginated_receive_preserve_payloads(monkeypatch, capsys):
    monkeypatch.setenv("MA_DEBUG_EVENTS", "1")
    events = [{"type": "session.status_running"}, {"type": "agent.message"}]
    response = SimpleNamespace(data=[SimpleNamespace(type="agent.message", id="saved")])

    class Events:
        async def send(self, session_id, *, events):
            assert session_id == "session-1"
            assert events is outgoing
            return response

        async def list(self, session_id, **options):
            assert session_id == "session-1"
            assert options == {"page": "5", "order": "asc"}
            for event in events:
                await asyncio.sleep(0)
                yield event

    outgoing = events
    sdk = SimpleNamespace(
        beta=SimpleNamespace(sessions=SimpleNamespace(events=Events()))
    )
    assert await debug.send_session_events(sdk, "session-1", events=events) is response
    received = [
        event
        async for event in debug.iter_session_events(
            sdk, "session-1", page="5", order="asc"
        )
    ]
    assert all(actual is expected for actual, expected in zip(received, events))
    logged = records(capsys)
    assert [(item["direction"], item["source"]) for item in logged] == [
        ("sent", "send"),
        ("sent", "send"),
        ("received", "send_response"),
        ("received", "list"),
        ("received", "list"),
    ]


def test_sync_client_traces_send_response_and_list(monkeypatch, capsys):
    from veadk.integrations.mpa.session_client import SelfHostSandboxClient

    monkeypatch.setenv("MA_DEBUG_EVENTS", "1")
    event = {"type": "agent.tool_result", "content": "complete tool output"}
    response = SimpleNamespace(data=[event])
    api = SimpleNamespace(
        send=lambda **kwargs: response, list=lambda **kwargs: response
    )
    client = SelfHostSandboxClient.__new__(SelfHostSandboxClient)
    client.session_id = "session-sync"
    client.client = SimpleNamespace(
        beta=SimpleNamespace(sessions=SimpleNamespace(events=api))
    )
    client.post_events([event])
    assert client.list_events() == [event]
    logged = records(capsys)
    assert [record["source"] for record in logged] == ["send", "send_response", "list"]
    assert all(record["event"] == event for record in logged)
