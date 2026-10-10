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

import asyncio
import importlib
from types import SimpleNamespace
from typing import get_origin

import pytest

from google.adk.agents.run_config import StreamingMode


loop_module = importlib.import_module("veadk.runtime.managed_agents.loop")
ManagedAgentsLoop = loop_module.ManagedAgentsLoop
ManagedAgentEventState = loop_module.ManagedAgentEventState


def test_response_context_survives_fresh_worker_without_session_database():
    from google.adk.sessions import InMemorySessionService

    async def check():
        runner = _Runner([])
        runner.agent = SimpleNamespace(name="test_agent")
        runner.session_service = InMemorySessionService()
        loop = ManagedAgentsLoop(runner=runner, session_id="session-ark")
        loop._restore_completed_inputs(
            [
                {"type": "user.message", "id": "input-1"},
                {
                    "type": "span.model_request_end",
                    "metadata": {"ark_response_id": "resp-1"},
                },
                {"type": "session.status_idle"},
            ]
        )
        await loop._ensure_local_session()
        session = await runner.session_service.get_session(
            app_name=runner.app_name,
            user_id=loop.user_id,
            session_id=loop.session_id,
        )
        assert len(session.events) == 1
        assert session.events[0].interaction_id == "resp-1"
        assert session.events[0].author == "test_agent"
        assert session.events[0].content is None
        assert "input-1" in loop._completed_inputs

    asyncio.run(check())


def test_completed_turn_persists_response_reference():
    event = _event(_part("answer"))
    event.interaction_id = "resp-completed"
    runner = _Runner([event])
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=runner, session_id="session-ark")
    asyncio.run(loop._run_turn(sdk, {"content": [{"type": "text", "text": "hello"}]}))
    events = [event for _, batch in sdk.beta.sessions.events.batches for event in batch]
    end = next(event for event in events if event["type"] == "span.model_request_end")
    assert end["metadata"] == {"ark_response_id": "resp-completed"}


class _SessionService:
    def __init__(self, *, exists=True):
        self.session = object() if exists else None
        self.created = []

    async def get_session(self, **kwargs):
        return self.session

    async def create_session(self, **kwargs):
        self.created.append(kwargs)
        self.session = object()
        return self.session


class _Runner:
    app_name = "managed-agent-test"

    def __init__(self, events, *, session_exists=True):
        self.events = events
        self.session_service = _SessionService(exists=session_exists)
        self.calls = []

    async def run_async(self, **kwargs):
        self.calls.append(kwargs)
        for event in self.events:
            yield event


class _EventsAPI:
    def __init__(self):
        self.batches = []

    async def send(self, session_id, *, events):
        batch = list(events)
        self.batches.append((session_id, batch))
        data = []
        for event in batch:
            event_id = (
                "span-start-1"
                if event["type"] == "span.model_request_start"
                else "event"
            )
            data.append(SimpleNamespace(type=event["type"], id=event_id))
        return SimpleNamespace(data=data)


class _SDK:
    def __init__(self):
        self.transient = []
        self.beta = SimpleNamespace(
            sessions=SimpleNamespace(events=_EventsAPI()),
        )

    async def post(self, path, *, cast_to, body):
        self.transient.append((path, cast_to, body))
        return {"accepted": True}


class _SessionClient:
    session_id = "managed-session-1"

    @staticmethod
    def _event_seq(event):
        return int(event.get("_seq", 0))


class _AsyncPage:
    def __init__(self, events):
        self.events = events

    def __aiter__(self):
        async def iterate():
            for event in self.events:
                yield event

        return iterate()


class _EventPages:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def __call__(self, session_id, **kwargs):
        self.calls.append((session_id, kwargs))
        response = next(self.responses)
        if isinstance(response, BaseException):
            raise response
        return _AsyncPage(response)


def _event(*parts, usage=None, partial=False, function_calls=None):
    return SimpleNamespace(
        partial=partial,
        content=SimpleNamespace(parts=list(parts)),
        usage_metadata=usage,
        get_function_calls=lambda: list(function_calls or []),
    )


def _part(text, *, thought=False):
    return SimpleNamespace(text=text, thought=thought)


def test_debug_covers_runner_transient_and_persisted_events(monkeypatch, capsys):
    import json

    from google.adk.events import Event
    from google.genai import types

    monkeypatch.setenv("MA_DEBUG_EVENTS", "1")
    runner = _Runner(
        [
            Event(
                author="agent",
                partial=partial,
                content=types.Content(parts=[types.Part(text=text)]),
            )
            for partial, text in [(True, "hello"), (False, "hello world")]
        ]
    )
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=runner, session_id="session-debug")
    asyncio.run(loop._run_turn(sdk, {"content": [{"type": "text", "text": "hi"}]}))
    logged = [
        json.loads(line.removeprefix("MA_DEBUG_EVENT "))
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("MA_DEBUG_EVENT ")
    ]
    assert all(record["session_id"] == "session-debug" for record in logged)
    assert len([record for record in logged if record["source"] == "runner"]) == 2
    assert {
        record["event"]["type"] for record in logged if record["source"] == "transient"
    } == {"event_start", "event_delta"}
    assert [record["event"] for record in logged if record["source"] == "send"] == [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]


def test_debug_logs_sse_events_before_filtering(monkeypatch, capsys):
    import json
    from contextlib import asynccontextmanager

    monkeypatch.setenv("MA_DEBUG_EVENTS", "1")
    events = [
        SimpleNamespace(type="user.tool_result", content="tool output"),
        SimpleNamespace(type="session.status_terminated"),
    ]

    class Stream(_AsyncPage):
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

    async def stream(session_id):
        assert session_id == "session-sse"
        return Stream(events)

    @asynccontextmanager
    async def client_context():
        yield SimpleNamespace(
            beta=SimpleNamespace(
                sessions=SimpleNamespace(events=SimpleNamespace(stream=stream))
            )
        )

    client = SimpleNamespace(
        session_id="session-sse",
        list_events=lambda: [],
        create_async_client=client_context,
    )
    loop = ManagedAgentsLoop(runner=_Runner([]), session_client=client)

    async def run():
        return await asyncio.wait_for(loop.run(), timeout=5)

    assert asyncio.run(run()) == 0
    logged = [
        json.loads(line.removeprefix("MA_DEBUG_EVENT "))
        for line in capsys.readouterr().out.splitlines()
        if line.startswith("MA_DEBUG_EVENT ")
    ]
    assert [record["event"] for record in logged] == [vars(event) for event in events]
    assert all(record["source"] == "sse" for record in logged)


def test_turn_maps_veadk_events_to_managed_agent_events():
    usage = SimpleNamespace(
        prompt_token_count=3,
        candidates_token_count=2,
        cached_content_token_count=1,
    )
    runner = _Runner(
        [
            _event(_part("considering", thought=True)),
            _event(_part("ignored"), function_calls=[object()]),
            _event(_part("final answer"), usage=usage),
        ],
        session_exists=False,
    )
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=runner, session_client=_SessionClient())
    user_event = SimpleNamespace(
        content=[SimpleNamespace(type="text", text="hello")],
    )

    asyncio.run(loop._run_turn(sdk, user_event))

    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert [event["type"] for event in emitted] == [
        "session.status_running",
        "span.model_request_start",
        "agent.thinking",
        "agent.message",
        "span.model_request_end",
        "session.status_idle",
    ]
    assert emitted[2]["text"] == "considering"
    assert emitted[3]["content"] == [{"type": "text", "text": "final answer"}]
    assert emitted[4] == {
        "type": "span.model_request_end",
        "model_request_start_id": "span-start-1",
        "model_usage": {
            "input_tokens": 3,
            "output_tokens": 2,
            "cache_read_input_tokens": 1,
            "cache_creation_input_tokens": 0,
        },
    }
    assert runner.session_service.created == [
        {
            "app_name": "managed-agent-test",
            "user_id": "managed_agents_user",
            "session_id": "managed-session-1",
        }
    ]
    assert runner.calls[0]["session_id"] == "managed-session-1"
    assert runner.calls[0]["new_message"].parts[0].text == "hello"
    assert runner.calls[0]["run_config"].streaming_mode == StreamingMode.SSE


def test_turn_broadcasts_partial_text_before_persisting_the_final_message():
    runner = _Runner(
        [
            _event(_part("hel"), partial=True),
            _event(_part("lo"), partial=True),
            _event(_part("hello")),
        ]
    )
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=runner, session_client=_SessionClient())

    asyncio.run(
        loop._run_turn(sdk, SimpleNamespace(content=[{"type": "text", "text": "hi"}]))
    )

    transient = [call[2]["events"][0] for call in sdk.transient]
    assert all(get_origin(call[1]) is dict for call in sdk.transient)
    assert all(event["id"].startswith("transient-") for event in transient)
    assert all(event["processed_at"] for event in transient)
    assert all(call[0].endswith("/events") for call in sdk.transient)
    assert [event["type"] for event in transient] == [
        "event_start",
        "event_delta",
        "event_delta",
    ]
    assert [event["delta"]["content"]["text"] for event in transient[1:]] == [
        "hel",
        "lo",
    ]
    assert all(
        event["delta"]["type"] == "content_delta" and event["delta"]["index"] == 0
        for event in transient[1:]
    )
    message_id = transient[0]["event"]["id"]
    assert all(event["event_id"] == message_id for event in transient[1:])
    canonical = [
        event
        for _, batch in sdk.beta.sessions.events.batches
        for event in batch
        if event["type"] == "agent.message"
    ]
    assert canonical == [
        {
            "type": "agent.message",
            "message_id": message_id,
            "content": [{"type": "text", "text": "hello"}],
        }
    ]


def test_turn_closes_partial_stream_as_aborted_when_cancelled():
    class _CancelledRunner(_Runner):
        async def run_async(self, **kwargs):
            self.calls.append(kwargs)
            yield _event(_part("partial"), partial=True)
            raise asyncio.CancelledError

    sdk = _SDK()
    loop = ManagedAgentsLoop(
        runner=_CancelledRunner([]), session_client=_SessionClient()
    )

    async def run():
        try:
            await loop._run_turn(
                sdk, SimpleNamespace(content=[{"type": "text", "text": "hi"}])
            )
        except asyncio.CancelledError:
            return
        raise AssertionError("cancelled turn did not propagate cancellation")

    asyncio.run(run())

    transient = [call[2]["events"][0] for call in sdk.transient]
    assert transient[-1]["type"] == "event_delta"
    assert all(call[0].endswith("/events") for call in sdk.transient)
    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert emitted[-1]["type"] == "span.model_request_end"
    assert emitted[-1]["is_error"] is True
    assert [event["type"] for event in emitted].count("session.status_idle") == 0


def test_turn_failure_emits_span_error_and_session_error_without_idle():
    class _FailingRunner(_Runner):
        async def run_async(self, **kwargs):
            if False:
                yield None
            raise RuntimeError("model failed")

    sdk = _SDK()
    loop = ManagedAgentsLoop(
        runner=_FailingRunner([]),
        session_client=_SessionClient(),
    )

    with pytest.raises(RuntimeError, match="model failed"):
        asyncio.run(
            loop._run_turn(
                sdk,
                SimpleNamespace(content=[{"type": "text", "text": "hello"}]),
            )
        )

    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert [event["type"] for event in emitted] == [
        "session.status_running",
        "span.model_request_start",
        "span.model_request_end",
        "session.error",
    ]
    assert emitted[-1]["error"] == "Managed Agents turn failed"


def test_invalid_user_message_emits_session_error_without_starting_runner():
    runner = _Runner([])
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=runner, session_client=_SessionClient())

    with pytest.raises(ValueError):
        asyncio.run(
            loop._run_turn(
                sdk,
                SimpleNamespace(content=[{"type": "image", "source": "ignored"}]),
            )
        )

    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert emitted == [
        {
            "type": "session.error",
            "error": "Managed Agents turn failed",
        }
    ]
    assert runner.calls == []


def test_recovery_only_marks_user_messages_followed_by_terminal_event_complete():
    loop = ManagedAgentsLoop(runner=_Runner([]), session_client=_SessionClient())

    loop._restore_completed_inputs(
        [
            {"_seq": 1, "id": "old", "type": "user.message"},
            {"_seq": 2, "type": "session.status_running"},
            {"_seq": 3, "type": "session.status_idle"},
            {"_seq": 4, "id": "pending", "type": "user.message"},
            {"_seq": 5, "type": "session.status_running"},
        ]
    )

    assert loop._completed_inputs == {"old"}


def test_recovery_pairs_one_terminal_with_one_queued_user_message():
    loop = ManagedAgentsLoop(runner=_Runner([]), session_client=_SessionClient())

    loop._restore_completed_inputs(
        [
            {"id": "first", "type": "user.message"},
            {"id": "second", "type": "user.message"},
            {"id": "running", "type": "session.status_running"},
            {"id": "idle", "type": "session.status_idle"},
        ]
    )

    assert loop._completed_inputs == {"first"}


def test_requires_action_does_not_mark_turn_complete_during_recovery():
    loop = ManagedAgentsLoop(runner=_Runner([]), session_client=_SessionClient())

    loop._restore_completed_inputs(
        [
            {"id": "pending", "type": "user.message"},
            {
                "id": "waiting",
                "type": "session.status_idle",
                "stop_reason": {"type": "requires_action"},
            },
        ]
    )

    assert loop._completed_inputs == set()


def test_claimed_session_keeps_processing_after_idle():
    async def run():
        loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session-1")
        sdk = _SDK()
        statuses = iter(["idle", "idle", "running", "terminated"])
        heartbeats = []
        polls = []

        async def retrieve(_session_id):
            return {"status": next(statuses)}

        async def heartbeat(work_id, **kwargs):
            heartbeats.append((work_id, kwargs))
            return SimpleNamespace(lease_extended=True, last_heartbeat="hb-2")

        async def pending(_sdk, *, max_turns):
            polls.append(max_turns)
            return 0 if len(polls) == 2 else 1

        sdk.beta.sessions.retrieve = retrieve
        sdk.beta.environments = SimpleNamespace(
            work=SimpleNamespace(heartbeat=heartbeat)
        )
        loop.run_pending = pending
        turns = await loop.run_claimed(
            sdk,
            environment_id="env-1",
            work_id="work-1",
            last_heartbeat="hb-1",
            poll_interval=0,
        )
        assert turns == 2
        assert polls == [None, None, None]
        assert heartbeats[0][1]["expected_last_heartbeat"] == "hb-1"

    asyncio.run(run())


def test_claimed_session_cancels_tools_when_lease_is_lost():
    async def run():
        loop = ManagedAgentsLoop(runner=_Runner([]), session_id="session-1")
        sdk = _SDK()
        cancelled = asyncio.Event()

        async def retrieve(_session_id):
            return {"status": "running"}

        async def heartbeat(*_args, **_kwargs):
            return SimpleNamespace(lease_extended=False)

        async def pending(_sdk, *, max_turns):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        sdk.beta.sessions.retrieve = retrieve
        sdk.beta.environments = SimpleNamespace(
            work=SimpleNamespace(heartbeat=heartbeat)
        )
        loop.run_pending = pending
        try:
            await loop.run_claimed(sdk, environment_id="env-1", work_id="work-1")
        except RuntimeError as error:
            assert "lease" in str(error)
        else:
            raise AssertionError("lost lease did not stop the session")
        assert cancelled.is_set()

    asyncio.run(run())


def test_claimed_work_processes_only_pending_message_from_durable_log():
    runner = _Runner([])
    sdk = _SDK()
    sdk.beta.sessions.events.list = lambda *args, **kwargs: _AsyncPage(
        [
            {
                "id": "old",
                "type": "user.message",
                "content": [{"type": "text", "text": "old"}],
            },
            {"id": "idle", "type": "session.status_idle"},
            {
                "id": "pending",
                "type": "user.message",
                "content": [{"type": "text", "text": "new"}],
            },
        ]
    )
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    turns = asyncio.run(loop.run_pending(sdk))

    assert turns == 1
    assert len(runner.calls) == 1
    assert runner.calls[0]["new_message"].parts[0].text == "new"
    emitted = [
        event for _, batch in sdk.beta.sessions.events.batches for event in batch
    ]
    assert [event["type"] for event in emitted] == [
        "session.status_running",
        "span.model_request_start",
        "span.model_request_end",
        "session.status_idle",
    ]


def test_claimed_work_reconciles_full_history_once_then_uses_seq_cursor():
    runner = _Runner([])
    sdk = _SDK()
    history = [
        {"seq": index, "id": f"system-{index}", "type": "system.message"}
        for index in range(1, 1005)
    ]
    history.append(
        {
            "seq": 1005,
            "id": "first",
            "type": "user.message",
            "content": [{"type": "text", "text": "first"}],
        }
    )
    pages = _EventPages(
        [
            history,
            [
                {
                    "seq": 1006,
                    "id": "second",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "second"}],
                }
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    async def run():
        assert await loop.run_pending(sdk) == 1
        assert await loop.run_pending(sdk) == 1

    asyncio.run(run())

    assert pages.calls == [
        (
            "managed-session-1",
            {"limit": 100, "order": "asc"},
        ),
        (
            "managed-session-1",
            {"limit": 100, "order": "asc", "page": "1005"},
        ),
    ]
    assert [call["new_message"].parts[0].text for call in runner.calls] == [
        "first",
        "second",
    ]
    assert loop._event_cursor_seq == 1006


def test_separate_work_handlers_share_the_session_event_cursor():
    first_runner = _Runner([])
    second_runner = _Runner([])
    sdk = _SDK()
    pages = _EventPages(
        [
            [
                {
                    "seq": 1,
                    "id": "first",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "first"}],
                }
            ],
            [
                {
                    "seq": 2,
                    "id": "second",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "second"}],
                }
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    state = ManagedAgentEventState()
    first = ManagedAgentsLoop(
        runner=first_runner, session_id="managed-session-1", event_state=state
    )
    second = ManagedAgentsLoop(
        runner=second_runner, session_id="managed-session-1", event_state=state
    )

    async def run():
        assert await first.run_pending(sdk) == 1
        assert await second.run_pending(sdk) == 1

    asyncio.run(run())

    assert "page" not in pages.calls[0][1]
    assert pages.calls[1][1]["page"] == "1"
    assert first_runner.calls[0]["new_message"].parts[0].text == "first"
    assert second_runner.calls[0]["new_message"].parts[0].text == "second"
    assert state.cursor_seq == 2


def test_claimed_work_does_not_advance_cursor_past_unprocessed_message():
    runner = _Runner([])
    sdk = _SDK()
    pages = _EventPages(
        [
            [
                {
                    "seq": 1,
                    "id": "first",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "first"}],
                },
                {
                    "seq": 2,
                    "id": "second",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "second"}],
                },
            ],
            [
                {
                    "seq": 2,
                    "id": "second",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "second"}],
                }
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    async def run():
        assert await loop.run_pending(sdk, max_turns=1) == 1
        assert loop._event_cursor_seq == 1
        assert await loop.run_pending(sdk, max_turns=1) == 1

    asyncio.run(run())

    assert pages.calls[1][1]["page"] == "1"
    assert [call["new_message"].parts[0].text for call in runner.calls] == [
        "first",
        "second",
    ]
    assert loop._event_cursor_seq == 2


def test_claimed_work_falls_back_to_one_full_reconcile_when_cursor_fails():
    runner = _Runner([])
    sdk = _SDK()
    pages = _EventPages(
        [
            [
                {"seq": 1, "id": "old", "type": "user.message"},
                {"seq": 2, "id": "idle", "type": "session.status_idle"},
            ],
            RuntimeError("invalid cursor"),
            [
                {"seq": 1, "id": "old", "type": "user.message"},
                {"seq": 2, "id": "idle", "type": "session.status_idle"},
                {
                    "seq": 3,
                    "id": "new",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "new"}],
                },
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    async def run():
        assert await loop.run_pending(sdk) == 0
        assert await loop.run_pending(sdk) == 1

    asyncio.run(run())

    assert pages.calls[1][1]["page"] == "2"
    assert "page" not in pages.calls[2][1]
    assert [call["new_message"].parts[0].text for call in runner.calls] == ["new"]
    assert loop._event_cursor_seq == 3


def test_claimed_work_falls_back_when_server_ignores_cursor():
    runner = _Runner([])
    sdk = _SDK()
    pages = _EventPages(
        [
            [
                {"seq": 1, "id": "old", "type": "user.message"},
                {"seq": 2, "id": "idle", "type": "session.status_idle"},
            ],
            [
                {"seq": 1, "id": "old", "type": "user.message"},
                {"seq": 2, "id": "idle", "type": "session.status_idle"},
                {
                    "seq": 3,
                    "id": "new",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "new"}],
                },
            ],
            [
                {"seq": 1, "id": "old", "type": "user.message"},
                {"seq": 2, "id": "idle", "type": "session.status_idle"},
                {
                    "seq": 3,
                    "id": "new",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "new"}],
                },
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    async def run():
        assert await loop.run_pending(sdk) == 0
        assert await loop.run_pending(sdk) == 1

    asyncio.run(run())

    assert pages.calls[1][1]["page"] == "2"
    assert "page" not in pages.calls[2][1]
    assert [call["new_message"].parts[0].text for call in runner.calls] == ["new"]
    assert loop._event_cursor_seq == 3


def test_claimed_work_without_event_sequences_stays_on_full_reconciliation():
    runner = _Runner([])
    sdk = _SDK()
    pages = _EventPages(
        [
            [
                {"id": "old", "type": "user.message"},
                {"id": "idle", "type": "session.status_idle"},
            ],
            [
                {"id": "old", "type": "user.message"},
                {"id": "idle", "type": "session.status_idle"},
                {
                    "id": "new",
                    "type": "user.message",
                    "content": [{"type": "text", "text": "new"}],
                },
            ],
        ]
    )
    sdk.beta.sessions.events.list = pages
    loop = ManagedAgentsLoop(runner=runner, session_id="managed-session-1")

    async def run():
        assert await loop.run_pending(sdk) == 0
        assert await loop.run_pending(sdk) == 1

    asyncio.run(run())

    assert all("page" not in kwargs for _, kwargs in pages.calls)
    assert [call["new_message"].parts[0].text for call in runner.calls] == ["new"]


def test_thinking_previews_are_start_only():
    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=_Runner([]), session_client=_SessionClient())

    async def run():
        for typ in (
            "agent.thinking_stream_start",
            "agent.thinking_chunk",
            "agent.thinking_stream_end",
        ):
            await loop._publish_transient(
                sdk, {"type": typ, "thinking_id": "thinking", "delta": "private"}
            )

    asyncio.run(run())
    assert len(sdk.transient) == 1
    path, _, body = sdk.transient[0]
    assert path.endswith("/events")
    assert body["events"][0]["type"] == "event_start"
    assert body["events"][0]["event"] == {"type": "agent.thinking", "id": "thinking"}


def test_failed_turn_does_not_complete_input_or_leak_provider_secret(caplog):
    class FailingRunner(_Runner):
        async def run_async(self, **kwargs):
            if False:
                yield None
            raise RuntimeError("provider secret-must-not-escape")

    sdk = _SDK()
    loop = ManagedAgentsLoop(runner=FailingRunner([]), session_client=_SessionClient())
    with pytest.raises(RuntimeError):
        asyncio.run(
            loop._run_turn(
                sdk, {"id": "failed", "content": [{"type": "text", "text": "hello"}]}
            )
        )
    events = [event for _, batch in sdk.beta.sessions.events.batches for event in batch]
    assert "secret-must-not-escape" not in str(events)
    assert "secret-must-not-escape" not in caplog.text
    loop._restore_completed_inputs([{"id": "failed", "type": "user.message"}, *events])
    assert "failed" not in loop._completed_inputs


def test_reporting_failure_preserves_original_turn_exception(monkeypatch):
    class FailingRunner(_Runner):
        async def run_async(self, **kwargs):
            if False:
                yield None
            raise RuntimeError("original model failure")

    sdk = _SDK()
    original_send = loop_module.send_session_events

    async def send(client, session_id, *, events):
        if any(event["type"] == "session.error" for event in events):
            raise OSError("reporting failed")
        return await original_send(client, session_id, events=events)

    monkeypatch.setattr(loop_module, "send_session_events", send)
    loop = ManagedAgentsLoop(runner=FailingRunner([]), session_client=_SessionClient())
    with pytest.raises(RuntimeError, match="original model failure"):
        asyncio.run(
            loop._run_turn(sdk, {"content": [{"type": "text", "text": "hello"}]})
        )
