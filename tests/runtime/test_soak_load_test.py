# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


SCRIPT = (
    Path(__file__).parents[2]
    / "examples"
    / "16_self_host_sandbox"
    / "soak_load_test.py"
)
SPEC = importlib.util.spec_from_file_location("soak_load_test", SCRIPT)
assert SPEC and SPEC.loader
soak = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = soak
SPEC.loader.exec_module(soak)


class _Stream:
    def __init__(self, events):
        self._events = events

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for event in self._events:
            if isinstance(event, BaseException):
                raise event
            yield event


class _Events:
    def __init__(self, events):
        self._events = events

    async def stream(self, *_args, **_kwargs):
        return _Stream(self._events)

    async def send(self, *_args, **_kwargs):
        return None


def _client(events):
    return SimpleNamespace(
        beta=SimpleNamespace(
            sessions=SimpleNamespace(events=_Events(events)),
        )
    )


def _event(event_type, **values):
    return SimpleNamespace(type=event_type, **values)


def _fault_module():
    fault_path = SCRIPT.with_name("soak_fault_preflight.py")
    spec = importlib.util.spec_from_file_location("soak_fault_preflight", fault_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_jsonl_writer_keeps_every_success(tmp_path):
    output = tmp_path / "turns.jsonl"
    with soak.DurableJsonlWriter(output) as writer:
        for index in range(125):
            writer.append(
                soak.RequestRecord(
                    request_id=f"request-{index}",
                    worker=index % 50,
                    session_id=f"session-{index}",
                    started_at="start",
                    completed_at="end",
                    started_offset_seconds=float(index),
                    completed_offset_seconds=float(index + 1),
                    completion_phase="formal",
                    elapsed_seconds=1.0,
                    first_delta_seconds=0.5,
                    ok=True,
                    require_tool=True,
                    tool_uses=1,
                    tool_results=1,
                    tool_use_ids=[f"call-{index}"],
                    tool_result_ids=[f"call-{index}"],
                )
            )

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert len(rows) == 125
    assert [row["request_id"] for row in rows] == [
        f"request-{index}" for index in range(125)
    ]


def test_tool_success_requires_exact_use_result_id_match():
    good = [
        _event("agent.tool_use", id="call-1"),
        _event("agent.tool_result", tool_use_id="call-1", content=[]),
        _event("agent.message", content=[{"type": "text", "text": "mark"}]),
        _event("session.status_idle"),
    ]
    bad = [
        _event("agent.tool_use", id="call-1"),
        _event("agent.tool_result", tool_use_id="call-other", content=[]),
        _event("agent.message", content=[{"type": "text", "text": "mark"}]),
        _event("session.status_idle"),
    ]

    async def run(events):
        now = soak.time.monotonic()
        return await soak.run_one_turn(
            _client(events),
            "session",
            marker="mark",
            prompt="prompt",
            timeout=1,
            require_tool=True,
            worker=0,
            request_id="request",
            run_start=now,
            deadline=now + 10,
        )

    matched = asyncio.run(run(good))
    mismatched = asyncio.run(run(bad))
    assert matched.ok is True
    assert matched.tool_use_ids == matched.tool_result_ids == ["call-1"]
    assert mismatched.ok is False


def test_tool_error_result_is_a_failed_turn():
    events = [
        _event("agent.tool_use", id="call-1"),
        _event(
            "agent.tool_result",
            tool_use_id="call-1",
            is_error=True,
            content=[{"type": "text", "text": "command failed"}],
        ),
        _event("agent.message", content=[{"type": "text", "text": "mark"}]),
        _event("session.status_idle"),
    ]

    async def run():
        now = soak.time.monotonic()
        return await soak.run_one_turn(
            _client(events),
            "session",
            marker="mark",
            prompt="prompt",
            timeout=1,
            require_tool=True,
            worker=0,
            request_id="request",
            run_start=now,
            deadline=now + 10,
        )

    result = asyncio.run(run())
    assert result.ok is False
    assert result.tool_use_ids == result.tool_result_ids == ["call-1"]
    assert result.tool_error_ids == ["call-1"]
    assert result.error_category == "tool_result_error"


def test_error_record_keeps_redacted_detail_and_separate_category():
    now = soak.time.monotonic()
    record = soak._error_record(
        "request",
        0,
        "session",
        "start",
        now,
        RuntimeError("rate limit Authorization: Bearer abc123 token=secret-value"),
        require_tool=True,
        run_start=now,
        deadline=now + 10,
    )

    assert record.error_category == "rate_limit"
    assert "rate limit" in record.error_reason
    assert "abc123" not in record.error_reason
    assert "secret-value" not in record.error_reason
    assert "rate limit" in record.error_reason


@pytest.mark.parametrize(
    "detail,secrets",
    [
        ("secret_key=synthetic_secret request_id=req-1", ["synthetic_secret"]),
        (
            '{"secret_key":"synthetic_secret","request_id":"req-1"}',
            ["synthetic_secret"],
        ),
        ("{'api-key': 'synthetic-api', 'context': 'useful'}", ["synthetic-api"]),
        ('access_key = "synthetic-ak" status=429', ["synthetic-ak"]),
        ('secret_access_key: "synthetic-sk" path=/v1/work', ["synthetic-sk"]),
        (
            "client_secret=synthetic-client session_token=synthetic-token",
            ["synthetic-client", "synthetic-token"],
        ),
        (
            'private_key="-----BEGIN_PRIVATE_KEY-----" request-id=req-2',
            ["BEGIN_PRIVATE_KEY"],
        ),
        (
            "Authorization: Bearer synthetic-bearer request_id=req-3",
            ["synthetic-bearer"],
        ),
    ],
)
def test_sanitize_error_detail_redacts_credential_key_forms(detail, secrets):
    redacted = soak.sanitize_error_detail(detail)
    for secret in secrets:
        assert secret not in redacted
    assert "<redacted>" in redacted
    if "request_id" in detail:
        assert "request_id" in redacted
    if "status=429" in detail:
        assert "status=429" in redacted


def test_turn_exception_preserves_partial_tool_ids_category_and_redacted_detail():
    events = [
        _event("agent.tool_use", id="call-1"),
        TimeoutError("timed out token=secret-value"),
    ]
    now = soak.time.monotonic()
    record = asyncio.run(
        soak.run_one_turn(
            _client(events),
            "session",
            marker="mark",
            prompt="prompt",
            timeout=1,
            require_tool=True,
            worker=0,
            request_id="request",
            run_start=now,
            deadline=now + 10,
        )
    )
    assert record.ok is False
    assert record.tool_use_ids == ["call-1"]
    assert record.tool_result_ids == []
    assert record.error_category == "timeout"
    assert "timed out" in record.error_reason
    assert "secret-value" not in record.error_reason


def test_turn_exception_after_tool_error_preserves_error_evidence():
    events = [
        _event("agent.tool_use", id="call-1"),
        _event(
            "agent.tool_result",
            tool_use_id="call-1",
            is_error=True,
            content="failed token=secret-value",
        ),
        RuntimeError("terminal failure"),
    ]
    now = soak.time.monotonic()
    record = asyncio.run(
        soak.run_one_turn(
            _client(events),
            "session",
            marker="mark",
            prompt="prompt",
            timeout=1,
            require_tool=True,
            worker=0,
            request_id="request",
            run_start=now,
            deadline=now + 10,
        )
    )
    assert record.ok is False
    assert record.tool_error_ids == ["call-1"]
    assert "secret-value" not in record.tool_error_details[0]


def test_physical_lookup_is_filtered_to_run_sessions():
    calls = []

    class _Inspector:
        tool_id = "tool"

        class _Client:
            @staticmethod
            def call(action, body):
                calls.append((action, body))
                return {"SessionInfos": []}

        client = _Client()

    result = asyncio.run(
        soak.run_scoped_physical_sessions(_Inspector(), {"session-b", "session-a"})
    )

    assert result == []
    assert calls == [
        (
            "ListSessions",
            {
                "ToolId": "tool",
                "MaxResults": 100,
                "Filters": [
                    {
                        "Name": "UserSessionId",
                        "Values": ["session-a", "session-b"],
                    }
                ],
            },
        )
    ]


def test_physical_sample_records_same_instant_in_flight_mapping(tmp_path):
    output = tmp_path / "samples.jsonl"
    stop = asyncio.Event()

    class _Inspector:
        async def sessions_for_managed_sessions(self, managed_session_ids):
            assert managed_session_ids == {
                "session-a",
                "session-b",
                "session-completed-awaiting-reclaim",
            }
            stop.set()
            return [
                {
                    "session_id": "physical-a",
                    "user_session_id": "session-a",
                    "status": "Ready",
                    "created_at": "now",
                },
                {
                    "session_id": "physical-completed",
                    "user_session_id": "session-completed-awaiting-reclaim",
                    "status": "Ready",
                    "created_at": "now",
                },
            ]

    samples = []
    with soak.DurableJsonlWriter(output) as writer:
        asyncio.run(
            soak.sample_physical(
                _Inspector(),
                {"session-a", "session-b", "session-completed-awaiting-reclaim"},
                {"request-a": "session-a", "request-b": "session-b"},
                asyncio.Lock(),
                stop,
                samples,
                writer,
                30,
            )
        )

    assert len(samples) == 1
    assert samples[0]["in_flight_requests"] == 2
    assert samples[0]["in_flight"] == {
        "request-a": "session-a",
        "request-b": "session-b",
    }
    assert [row["session_id"] for row in samples[0]["physical_sessions"]] == [
        "physical-a",
        "physical-completed",
    ]
    assert samples[0]["snapshot_started_at"] <= samples[0]["snapshot_completed_at"]
    assert json.loads(output.read_text())["in_flight_requests"] == 2


def test_cleanup_confirms_physical_reclaim_and_records_query_window(tmp_path):
    class _Sessions:
        async def archive(self, session_id, *, timeout):
            assert session_id == "session-a"
            assert timeout == 7

    class _Inspector:
        async def sessions_for_managed_sessions(self, session_ids):
            assert session_ids == {"session-a"}
            return []

    record = soak.RequestRecord(
        request_id="request-a",
        worker=0,
        session_id="session-a",
        started_at="start",
        completed_at="end",
        started_offset_seconds=0,
        completed_offset_seconds=1,
        completion_phase="formal",
        elapsed_seconds=1,
        first_delta_seconds=0.5,
        ok=True,
        require_tool=True,
        tool_uses=1,
        tool_results=1,
    )
    active = {"session-a"}
    cleanup_records = []
    with soak.DurableJsonlWriter(tmp_path / "cleanup.jsonl") as writer:
        asyncio.run(
            soak.cleanup_session(
                SimpleNamespace(beta=SimpleNamespace(sessions=_Sessions())),
                "session-a",
                record,
                lock=asyncio.Lock(),
                active=active,
                cleanup_records=cleanup_records,
                cleanup_writer=writer,
                archive_timeout=7,
            )
        )
        asyncio.run(
            soak.confirm_physical_reclaims(
                _Inspector(),
                active,
                [record],
                cleanup_records,
                writer,
                timeout=7,
                interval=0,
            )
        )

    assert active == set()
    assert record.cleanup_status == "archived_physical_absent"
    assert record.physical_reclaimed is True
    assert record.physical_query_started_at <= record.physical_query_completed_at
    assert cleanup_records[0]["physical_reclaimed"] is True
    assert record.physical_query_count == 1


def test_physical_lookup_chunks_large_run_and_paginates():
    calls = []

    class _Inspector:
        tool_id = "tool"

        class _Client:
            @staticmethod
            def call(_action, body):
                calls.append(body)
                if (
                    body.get("NextToken") is None
                    and len(body["Filters"][0]["Values"]) == 50
                ):
                    return {"SessionInfos": [], "NextToken": "next"}
                return {"SessionInfos": []}

        client = _Client()

    session_ids = {f"session-{index:02d}" for index in range(51)}
    assert (
        asyncio.run(soak.run_scoped_physical_sessions(_Inspector(), session_ids)) == []
    )
    assert [len(call["Filters"][0]["Values"]) for call in calls] == [50, 50, 1]
    assert calls[1]["NextToken"] == "next"


def test_physical_lookup_fails_closed_on_wrong_owner_or_schema():
    class _Inspector:
        tool_id = "tool"

        class _Client:
            response = {"SessionInfos": {}}

            @classmethod
            def call(cls, _action, _body):
                return cls.response

        client = _Client()

    with pytest.raises(RuntimeError, match="SessionInfos list"):
        asyncio.run(soak.run_scoped_physical_sessions(_Inspector(), {"session"}))
    _Inspector._Client.response = {
        "SessionInfos": [{"SessionId": "physical", "UserSessionId": "other"}]
    }
    with pytest.raises(RuntimeError, match="unexpected UserSessionId"):
        asyncio.run(soak.run_scoped_physical_sessions(_Inspector(), {"session"}))


def test_physical_sample_error_log_redacts_json_credential(tmp_path):
    stop = asyncio.Event()

    class _Inspector:
        async def sessions_for_managed_sessions(self, _session_ids):
            stop.set()
            raise RuntimeError('{"secret_key":"synthetic_secret","request_id":"req-1"}')

    samples = []
    output = tmp_path / "samples.jsonl"
    with soak.DurableJsonlWriter(output) as writer:
        asyncio.run(
            soak.sample_physical(
                _Inspector(),
                {"session"},
                {"request": "session"},
                asyncio.Lock(),
                stop,
                samples,
                writer,
                30,
            )
        )
    error = samples[0]["error"]
    assert "synthetic_secret" not in error
    assert "request_id" in error
    assert "RuntimeError" in error
    assert "synthetic_secret" not in output.read_text()


def test_batch_reclaim_marks_remaining_session_unconfirmed(tmp_path):
    records = []
    cleanup_records = []
    for session_id in ("gone", "present"):
        record = soak.RequestRecord(
            request_id=session_id,
            worker=0,
            session_id=session_id,
            started_at="start",
            completed_at="end",
            started_offset_seconds=0,
            completed_offset_seconds=1,
            completion_phase="formal",
            elapsed_seconds=1,
            first_delta_seconds=0.5,
            ok=True,
            require_tool=True,
            tool_uses=1,
            tool_results=1,
            cleanup_status="archived",
        )
        records.append(record)
        cleanup_records.append(
            {"session_id": session_id, "status": "archived", "error": None}
        )

    class _Inspector:
        async def sessions_for_managed_sessions(self, _session_ids):
            return [
                {
                    "session_id": "physical",
                    "user_session_id": "present",
                    "status": "Ready",
                    "created_at": "now",
                }
            ]

    active = {"gone", "present"}
    with soak.DurableJsonlWriter(tmp_path / "cleanup.jsonl") as writer:
        asyncio.run(
            soak.confirm_physical_reclaims(
                _Inspector(),
                active,
                records,
                cleanup_records,
                writer,
                timeout=0.01,
                interval=0.02,
            )
        )
    assert active == {"present"}
    assert records[0].physical_reclaimed is True
    assert records[1].physical_reclaimed is False
    assert records[1].error_category is None
    assert "still present" in records[1].cleanup_error


def test_archive_timeout_is_recorded_before_physical_confirmation(tmp_path):
    class _Sessions:
        async def archive(self, _session_id, *, timeout):
            assert timeout == 0.01
            await asyncio.sleep(10)

    class _Inspector:
        async def sessions_for_managed_sessions(self, _session_ids):
            return [
                {
                    "session_id": "physical-a",
                    "user_session_id": "session-a",
                    "status": "Ready",
                    "created_at": "now",
                }
            ]

    record = soak.RequestRecord(
        request_id="request-a",
        worker=0,
        session_id="session-a",
        started_at="start",
        completed_at="end",
        started_offset_seconds=0,
        completed_offset_seconds=1,
        completion_phase="formal",
        elapsed_seconds=1,
        first_delta_seconds=0.5,
        ok=True,
        require_tool=True,
        tool_uses=1,
        tool_results=1,
        cleanup_status="pending",
    )
    active = {"session-a"}
    cleanup_records = []
    output = tmp_path / "cleanup.jsonl"
    with soak.DurableJsonlWriter(output) as writer:
        asyncio.run(
            soak.cleanup_session(
                SimpleNamespace(beta=SimpleNamespace(sessions=_Sessions())),
                "session-a",
                record,
                lock=asyncio.Lock(),
                active=active,
                cleanup_records=cleanup_records,
                cleanup_writer=writer,
                archive_timeout=0.01,
            )
        )
        asyncio.run(
            soak.confirm_physical_reclaims(
                _Inspector(),
                active,
                [record],
                cleanup_records,
                writer,
                timeout=0.01,
                interval=0.02,
            )
        )

    rows = [json.loads(line) for line in output.read_text().splitlines()]
    assert rows[0]["status"] == "archive_failed"
    assert rows[-1]["status"] == "archive_failed_physical_unconfirmed"
    assert record.physical_query_count >= 1
    assert active == {"session-a"}


def test_summary_schema_keeps_distinct_phase_and_latency_metrics():
    fields = soak.Summary.__dataclass_fields__
    assert "success_latency" in fields
    assert "latency_including_failures" in fields
    assert "first_text_event" in fields
    assert "formal_completions" in fields
    assert "drain_completions" in fields
    assert "peak_in_flight_requests" in fields
    assert "observed_peak_physical_sessions" in fields
    assert "physical_reclaim_unverified" in fields


def test_cli_result_fails_when_cleanup_or_physical_reclaim_is_incomplete(
    monkeypatch, tmp_path
):
    result = {
        "summary": {},
        "cleanup_records": [
            {"status": "archived_physical_unconfirmed", "physical_reclaimed": False}
        ],
        "unreclaimed_logical_session_ids": ["session-a"],
    }
    monkeypatch.setattr(soak, "_with_progress", lambda _args: _async_value(result))
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "soak_load_test.py",
            "--base-url",
            "https://example",
            "--agent-id",
            "agent",
            "--environment-id",
            "env",
            "--with-inspector",
            "--tool-id",
            "tool",
            "--output",
            str(tmp_path / "result.json"),
        ],
    )
    assert soak.main() == 1


async def _async_value(value):
    return value


def test_fault_preflight_requires_exact_tool_match():
    module = _fault_module()

    module.assert_tool_turn(
        {
            "tool_uses": ["call-1"],
            "tool_results": ["call-1"],
            "final": "marker",
            "types": ["agent.tool_use", "agent.tool_result", "session.status_idle"],
        },
        "marker",
    )
    with pytest.raises(AssertionError, match="tool IDs do not match"):
        module.assert_tool_turn(
            {
                "tool_uses": ["call-1"],
                "tool_results": ["call-2"],
                "final": "marker",
                "types": ["session.status_idle"],
            },
            "marker",
        )
    with pytest.raises(AssertionError, match="tool execution failed"):
        module.assert_tool_turn(
            {
                "tool_uses": ["call-1"],
                "tool_results": ["call-1"],
                "tool_error_ids": ["call-1"],
                "tool_error_details": ["command failed"],
                "final": "marker",
                "types": ["session.status_idle"],
            },
            "marker",
        )


def _fault_client(events):
    boundary = _event("user.message", id="new-input", seq=1)
    for index, event in enumerate(events, 2):
        event.seq = index
        if event.type == "session.status_idle":
            event.stop_reason = {"type": "end_turn"}
    sdk = _client([boundary, *events])

    async def send(*_args, **_kwargs):
        return {"data": [boundary]}

    sdk.beta.sessions.events.send = send
    return sdk


def test_fault_verified_turn_rejects_tool_is_error():
    module = _fault_module()
    events = [
        _event("agent.tool_use", id="call-1"),
        _event(
            "agent.tool_result", tool_use_id="call-1", is_error=True, content="failed"
        ),
        _event("agent.message", content=[{"type": "text", "text": "mark"}]),
        _event("session.status_idle"),
    ]
    result = asyncio.run(
        module.run_verified_tool_turn(
            _fault_client(events), "session", marker="mark", prompt="prompt", timeout=1
        )
    )
    assert result["tool_error_ids"] == ["call-1"]
    assert result["tool_error_details"] == ["failed"]
    with pytest.raises(AssertionError, match="tool execution failed"):
        module.assert_tool_turn(result, "mark")


def test_fault_error_detail_is_redacted():
    module = _fault_module()
    events = [
        _event("agent.tool_use", id="call-1"),
        _event(
            "agent.tool_result",
            tool_use_id="call-1",
            is_error=True,
            content="Authorization: Bearer abc token=secret-value",
        ),
        _event("session.status_idle"),
    ]
    result = asyncio.run(
        module.run_verified_tool_turn(
            _fault_client(events), "session", marker="mark", prompt="prompt", timeout=1
        )
    )
    detail = result["tool_error_details"][0]
    assert "abc" not in detail
    assert "secret-value" not in detail


def test_agentkit_inspector_uses_paginated_session_listing():
    module = _fault_module()
    calls = []
    inspector = module.AgentKitInspector.__new__(module.AgentKitInspector)
    inspector.tool_id = "tool"
    inspector.client = object()
    inspector.module = SimpleNamespace(
        list_all_sessions=lambda client, tool_id, max_results: (
            calls.append((client, tool_id, max_results))
            or [
                {
                    "SessionId": "physical",
                    "UserSessionId": "managed",
                    "Status": "Ready",
                    "CreatedAt": "now",
                }
            ]
        )
    )

    sessions = asyncio.run(inspector.sessions())

    assert calls == [(inspector.client, "tool", 100)]
    assert sessions == [
        {
            "session_id": "physical",
            "user_session_id": "managed",
            "status": "Ready",
            "created_at": "now",
        }
    ]


def test_fault_preflight_preserves_physical_lookup_error():
    module = _fault_module()

    class _Inspector:
        async def wait_present(self, _session_id, *, timeout):
            assert timeout == 120
            raise RuntimeError(
                "ListSessions failed Authorization: Bearer abc token=secret-value"
            )

    with pytest.raises(RuntimeError, match="physical lookup failed") as raised:
        asyncio.run(
            module.run_loss_during_active_tool(
                _client([_event("agent.tool_use", id="call-1")]),
                _Inspector(),
                "session",
                marker="mark",
                timeout=1,
            )
        )
    assert "abc" not in str(raised.value)
    assert "secret-value" not in str(raised.value)


def _work(work_id, session_id, *, environment_id="environment", state="queued"):
    return {
        "id": work_id,
        "work_id": work_id,
        "type": "work",
        "work_type": "session",
        "environment_id": environment_id,
        "data": {"id": session_id, "type": "session"},
        "state": state,
        "metadata": {},
        "created_at": "now",
    }


def test_work_snapshot_traverses_pages_and_filters_known_session(monkeypatch):
    module = _fault_module()
    responses = [
        {"data": [_work("other", "other-session")], "next_page": "page-2"},
        {"data": [_work("target", "session")], "next_page": None},
    ]

    class _Response:
        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class _HTTP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, _url, *, params, **_kwargs):
            expected_page = None if len(responses) == 2 else "page-2"
            assert params.get("page") == expected_page
            return _Response(responses.pop(0))

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_kwargs: _HTTP())
    snapshot = asyncio.run(
        module.session_work_snapshot(
            "https://gateway.example", "token", "environment", "session"
        )
    )
    assert snapshot["complete"] is True
    assert snapshot["page_count"] == 2
    assert snapshot["query_started_at"] <= snapshot["query_completed_at"]
    assert [row["work_id"] for row in snapshot["rows"]] == ["target"]


@pytest.mark.parametrize(
    "payload,match",
    [
        ({"data": {}, "next_page": None}, "data list"),
        ({"data": [{}], "next_page": None}, "work_id/id"),
        (
            {
                "data": [{**_work("target", "session"), "work_type": "other"}],
                "next_page": None,
            },
            "type/work_type",
        ),
        (
            {"data": [_work("target", "session")], "next_page": "same"},
            "repeated next_page",
        ),
    ],
)
def test_work_snapshot_fails_closed_on_schema_or_pagination(
    monkeypatch, payload, match
):
    module = _fault_module()

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    class _HTTP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_kwargs: _HTTP())
    with pytest.raises(RuntimeError, match=match):
        asyncio.run(
            module.session_work_snapshot(
                "https://gateway.example", "token", "environment", "session"
            )
        )


def test_work_snapshot_requires_previously_seen_work_ids(monkeypatch):
    module = _fault_module()

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"data": [], "next_page": None}

    class _HTTP:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, *_args, **_kwargs):
            return _Response()

    monkeypatch.setattr(module.httpx, "AsyncClient", lambda **_kwargs: _HTTP())
    with pytest.raises(RuntimeError, match="lost known IDs"):
        asyncio.run(
            module.session_work_snapshot(
                "https://gateway.example",
                "token",
                "environment",
                "session",
                expected_work_ids={"known-work"},
            )
        )


def test_async_main_keeps_all_success_records(monkeypatch, tmp_path):
    async def fake_worker(
        _client, worker, *, records, lock, in_flight, writer, peak_in_flight, **kwargs
    ):
        for index in range(25):
            request_id = f"{worker}-{index}"
            record = soak.RequestRecord(
                request_id=request_id,
                worker=worker,
                session_id=f"session-{request_id}",
                started_at="start",
                completed_at="end",
                started_offset_seconds=0.0,
                completed_offset_seconds=1.0,
                completion_phase="formal",
                elapsed_seconds=1.0,
                first_delta_seconds=0.5,
                ok=True,
                require_tool=True,
                tool_uses=1,
                tool_results=1,
                tool_use_ids=[f"call-{request_id}"],
                tool_result_ids=[f"call-{request_id}"],
                cleanup_status="archived",
            )
            async with lock:
                in_flight[request_id] = record.session_id
                peak_in_flight[0] = max(peak_in_flight[0], len(in_flight))
                records.append(record)
                writer.append(record)
                in_flight.pop(request_id)

    class _Client:
        kwargs = None

        def __init__(self, **kwargs):
            type(self).kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(soak, "worker_loop", fake_worker)
    monkeypatch.setattr(soak.anthropic, "AsyncAnthropic", _Client)
    output = tmp_path / "result.json"
    args = SimpleNamespace(
        base_url="https://gateway.example",
        auth_token="secret",
        agent_id="agent",
        environment_id="environment",
        concurrency=5,
        duration=1.0,
        turn_timeout=1.0,
        request_gap=0.0,
        require_tool=True,
        with_inspector=False,
        tool_id=None,
        sample_interval=30.0,
        physical_reclaim_timeout=1.0,
        output=output,
        records_output=None,
        samples_output=None,
        cleanup_output=None,
        progress_interval=60.0,
        run_id="test-run",
    )

    result = asyncio.run(soak.async_main(args))
    rows = [
        json.loads(line)
        for line in output.with_suffix(".records.jsonl").read_text().splitlines()
    ]
    assert result["summary"]["total_requests"] == 125
    assert result["summary"]["successes"] == 125
    assert len(result["records"]) == 125
    assert len(rows) == 125
    assert {row["request_id"] for row in rows} == {
        f"{worker}-{index}" for worker in range(5) for index in range(25)
    }
    assert _Client.kwargs["max_retries"] == 0
