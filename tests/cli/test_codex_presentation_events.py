"""Presentation contracts for the Codex 0.154.0 notification boundary."""

import asyncio

from veadk.cli.codex_app_server import CodexAppServerSession, _event_from_item


def test_command_item_preserves_native_actions_and_duration():
    event = _event_from_item(
        {
            "id": "read-1",
            "type": "commandExecution",
            "command": "cat agent.py",
            "cwd": "/workspace",
            "commandActions": [
                {
                    "type": "read",
                    "command": "cat agent.py",
                    "name": "agent.py",
                    "path": "/workspace/agent.py",
                }
            ],
            "status": "failed",
            "exitCode": 1,
            "aggregatedOutput": "missing file",
            "durationMs": 321,
        },
        completed=True,
    )
    assert event is not None
    assert event.item_type == "commandExecution"
    assert event.arguments["commandActions"][0]["type"] == "read"
    assert event.duration_ms == 321
    assert event.status == "error"


def test_native_progress_plan_and_diff_are_forwarded_with_item_identity():
    session = CodexAppServerSession("https://sandbox.invalid")
    session.thread_id = "thread-1"
    session._active_turn_id = "turn-1"
    session._turn_events = asyncio.Queue()
    for method, payload in [
        (
            "item/commandExecution/outputDelta",
            {"itemId": "command-1", "delta": "test passed\n"},
        ),
        ("item/mcpToolCall/progress", {"itemId": "mcp-1", "message": "Reading result"}),
        (
            "turn/plan/updated",
            {
                "explanation": "Implement and verify",
                "plan": [{"step": "Implement", "status": "inProgress"}],
            },
        ),
        ("turn/diff/updated", {"diff": "diff --git a/a.py b/a.py\n+fixed\n"}),
    ]:
        session._handle_notification(
            method, {"threadId": "thread-1", "turnId": "turn-1", **payload}
        )
    events = []
    while not session._turn_events.empty():
        events.append(session._turn_events.get_nowait())
    assert [event.kind for event in events] == [
        "tool_output",
        "tool_progress",
        "plan",
        "diff",
    ]
    assert [event.turn_id for event in events] == ["turn-1"] * 4
    assert events[0].item_id == "command-1"
    assert events[0].text == "test passed\n"
    assert events[1].item_id == "mcp-1"


def test_recovered_messages_keep_phase_and_thinking_start_is_visible():
    events = CodexAppServerSession.turn_snapshot_events(
        {
            "id": "turn-1",
            "status": "inProgress",
            "items": [
                {
                    "id": "message-1",
                    "type": "agentMessage",
                    "phase": "commentary",
                    "text": "Checking the project",
                },
                {"id": "thinking-1", "type": "reasoning", "summary": [], "content": []},
            ],
        }
    )
    assert events[0].phase == "commentary"
    assert events[0].item_type == "agentMessage"
    assert events[1].kind == "thinking"
    assert events[1].item_type == "reasoning"


def test_reasoning_summary_parts_do_not_duplicate_raw_content():
    session = CodexAppServerSession("https://sandbox.invalid")
    session.thread_id = "thread-1"
    session._turn_events = asyncio.Queue()
    for method, payload in [
        ("item/reasoning/textDelta", {"contentIndex": 0, "delta": "raw text"}),
        (
            "item/reasoning/summaryTextDelta",
            {"summaryIndex": 0, "delta": "First summary"},
        ),
        (
            "item/reasoning/summaryTextDelta",
            {"summaryIndex": 1, "delta": "Second summary"},
        ),
    ]:
        session._handle_notification(
            method, {"threadId": "thread-1", "itemId": "reasoning-1", **payload}
        )
    events = []
    while not session._turn_events.empty():
        events.append(session._turn_events.get_nowait())
    assert events[-1].text == "First summary\n\nSecond summary"


def test_native_turn_timing_uses_reported_values_and_never_fabricates_missing_time():
    session = CodexAppServerSession("https://sandbox.invalid")
    session.model = "test-model"
    event = session.turn_lifecycle_event(
        "turn_completed",
        {
            "id": "t",
            "status": "interrupted",
            "startedAt": 100,
            "completedAt": 102,
            "durationMs": 2123,
        },
    )
    assert event.response == {
        "startedAt": 100,
        "completedAt": 102,
        "durationMs": 2123,
        "model": "test-model",
    }
    event = session.turn_lifecycle_event(
        "turn_completed", {"id": "t", "durationMs": -1}
    )
    assert event.response == {"model": "test-model"}
