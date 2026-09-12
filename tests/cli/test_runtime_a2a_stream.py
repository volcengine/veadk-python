import json

import pytest

from veadk.cli.runtime_a2a_stream import (
    A2AStreamDecoder,
    a2a_error_message,
    a2a_event_to_studio_events,
    is_method_not_supported,
)


def _frame(result):
    return (
        "data: "
        + json.dumps(
            {"jsonrpc": "2.0", "id": "rpc-1", "result": result},
            ensure_ascii=False,
        )
        + "\n\n"
    )


def test_decoder_handles_fragmented_and_multiple_sse_frames():
    decoder = A2AStreamDecoder()
    first = _frame({"kind": "status-update", "status": {"state": "working"}})
    second = _frame(
        {"kind": "status-update", "status": {"state": "completed"}, "final": True}
    )

    assert decoder.feed(first[:13]) == []
    events = decoder.feed(first[13:] + second)

    assert [event["result"]["status"]["state"] for event in events] == [
        "working",
        "completed",
    ]
    assert decoder.finish() == []


def test_decoder_handles_utf8_split_across_byte_chunks():
    decoder = A2AStreamDecoder()
    frame = _frame(
        {"kind": "message", "parts": [{"kind": "text", "text": "中文"}]}
    ).encode()
    split = frame.index("中".encode()) + 1

    assert decoder.feed(frame[:split]) == []
    events = decoder.feed(frame[split:])

    assert events[0]["result"]["parts"][0]["text"] == "中文"


def test_decoder_deduplicates_replayed_a2a_events():
    decoder = A2AStreamDecoder()
    event = {
        "kind": "artifact-update",
        "taskId": "task-1",
        "artifact": {
            "artifactId": "sandbox-e-1",
            "parts": [
                {
                    "kind": "data",
                    "data": {"eventId": "worker-7", "eventType": "tool.call"},
                }
            ],
        },
    }
    frame = _frame(event)

    assert len(decoder.feed(frame)) == 1
    assert decoder.feed(frame) == []


def test_maps_sandbox_tool_and_text_delta_to_studio_events():
    envelope = {
        "kind": "artifact-update",
        "taskId": "task-1",
        "artifact": {
            "artifactId": "sandbox-e-1",
            "parts": [
                {
                    "kind": "data",
                    "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                    "data": {
                        "eventId": "worker-7",
                        "invocationId": "e-1",
                        "eventType": "tool.call",
                        "payload": {
                            "name": "exec_command",
                            "commandId": "cmd-1",
                            "status": "started",
                        },
                    },
                },
                {
                    "kind": "data",
                    "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                    "data": {
                        "eventId": "worker-8",
                        "invocationId": "e-1",
                        "eventType": "message.delta",
                        "payload": {"text": "hello"},
                    },
                },
            ],
        },
    }

    events = a2a_event_to_studio_events(envelope, author="default")

    assert events[0]["content"]["parts"][0]["functionCall"]["name"] == "exec_command"
    assert events[0]["content"]["parts"][0]["functionCall"]["id"] == "cmd-1"
    assert events[1]["partial"] is True
    assert events[1]["content"]["parts"][0]["text"] == "hello"


def test_maps_final_function_response_artifact_to_text_once():
    event = {
        "kind": "artifact-update",
        "taskId": "task-1",
        "lastChunk": True,
        "artifact": {
            "artifactId": "final-1",
            "parts": [
                {
                    "kind": "data",
                    "metadata": {"adk_type": "function_response"},
                    "data": {
                        "name": "sandbox_task",
                        "response": {"result": "sandbox output"},
                    },
                }
            ],
        },
    }

    events = a2a_event_to_studio_events(event, author="default")

    assert events == [
        {
            "id": "final-1-0",
            "author": "default",
            "partial": False,
            "turnComplete": True,
            "content": {"role": "model", "parts": [{"text": "sandbox output"}]},
        }
    ]


def test_maps_reasoning_artifact_to_thinking_event():
    event = {
        "kind": "artifact-update",
        "taskId": "task-1",
        "artifact": {
            "artifactId": "thought-1",
            "parts": [
                {
                    "kind": "text",
                    "text": "inspect the request",
                    "metadata": {"adk_thought": True},
                }
            ],
        },
    }

    events = a2a_event_to_studio_events(event, author="default")

    assert events[0]["partial"] is True
    assert events[0]["content"]["parts"][0] == {
        "text": "inspect the request",
        "thought": True,
    }


def test_maps_each_artifact_text_part_with_a_unique_event_id():
    event = {
        "kind": "artifact-update",
        "lastChunk": True,
        "artifact": {
            "artifactId": "artifact-1",
            "parts": [
                {
                    "kind": "text",
                    "text": "thinking",
                    "metadata": {"adk_thought": True},
                },
                {"kind": "text", "text": "final answer"},
            ],
        },
    }

    events = a2a_event_to_studio_events(event, author="default")

    assert [item["id"] for item in events] == [
        "artifact-1-0",
        "artifact-1-1",
    ]
    assert events[0]["content"]["parts"][0]["thought"] is True
    assert events[1]["content"]["parts"][0]["text"] == "final answer"


def test_decoder_uniquifies_ids_across_appends_to_the_same_artifact():
    decoder = A2AStreamDecoder()

    def artifact(text, *, thought=False, final=False):
        return {
            "kind": "artifact-update",
            "lastChunk": final,
            "artifact": {
                "artifactId": "artifact-1",
                "parts": [
                    {
                        "kind": "text",
                        "text": text,
                        **({"metadata": {"adk_thought": True}} if thought else {}),
                    }
                ],
            },
        }

    first = decoder.project(artifact("thinking", thought=True), author="default")
    second = decoder.project(artifact("more", thought=True), author="default")
    final = decoder.project(artifact("answer", final=True), author="default")

    assert [first[0]["id"], second[0]["id"], final[0]["id"]] == [
        "artifact-1-0",
        "artifact-1-0-1",
        "artifact-1-0-2",
    ]


def test_maps_working_status_message_to_partial_text_and_reasoning():
    event = {
        "kind": "status-update",
        "taskId": "task-1",
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [
                    {"kind": "text", "text": "streamed answer"},
                    {
                        "kind": "text",
                        "text": "hidden thought",
                        "metadata": {"adk_thought": True},
                    },
                ],
            },
        },
    }

    events = a2a_event_to_studio_events(event, author="default")

    assert len(events) == 2
    assert events[0]["partial"] is True
    assert events[0].get("turnComplete") is not True
    assert events[0]["content"]["parts"][0]["text"] == "streamed answer"
    assert events[1]["partial"] is True
    assert events[1]["content"]["parts"][0]["text"] == "hidden thought"
    assert events[1]["content"]["parts"][0]["thought"] is True


def test_projection_tracks_cumulative_reasoning_separately_from_answer():
    decoder = A2AStreamDecoder()

    def working(text, *, thought=False):
        return {
            "kind": "status-update",
            "metadata": {"adk_usage_metadata": {"totalTokenCount": 1}},
            "status": {
                "state": "working",
                "message": {
                    "role": "agent",
                    "parts": [
                        {
                            "kind": "text",
                            "text": text,
                            **({"metadata": {"adk_thought": True}} if thought else {}),
                        }
                    ],
                },
            },
        }

    reasoning = decoder.project(working("think", thought=True), author="default")
    reasoning_delta = decoder.project(
        working("think-more", thought=True), author="default"
    )
    answer = decoder.project(working("answer"), author="default")

    assert reasoning[0]["content"]["parts"][0]["text"] == "think"
    assert reasoning_delta[0]["content"]["parts"][0]["text"] == "-more"
    assert answer[0]["content"]["parts"][0]["text"] == "answer"


def test_decoder_finalizes_received_answer_when_a2a_terminal_has_no_message():
    decoder = A2AStreamDecoder()
    event = {
        "kind": "status-update",
        "metadata": {},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [{"kind": "text", "text": "final answer"}],
            },
        },
    }

    assert decoder.project(event, author="default")[0]["partial"] is True
    decoder.project(
        {
            "kind": "status-update",
            "final": True,
            "status": {"state": "completed"},
        },
        author="default",
    )
    terminal = decoder.finalize_projection(author="default")

    assert terminal == [
        {
            "id": "a2a-final-answer",
            "author": "default",
            "partial": False,
            "turnComplete": True,
            "content": {"role": "model", "parts": [{"text": "final answer"}]},
        }
    ]
    assert decoder.finalize_projection(author="default") == []


def test_decoder_does_not_promote_reasoning_to_final_answer():
    decoder = A2AStreamDecoder()
    event = {
        "kind": "status-update",
        "metadata": {},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [
                    {
                        "kind": "text",
                        "text": "private reasoning",
                        "metadata": {"adk_thought": True},
                    }
                ],
            },
        },
    }

    decoder.project(event, author="default")

    assert decoder.finalize_projection(author="default") == []


def test_decoder_does_not_finalize_answer_after_failed_terminal():
    decoder = A2AStreamDecoder()
    working = {
        "kind": "status-update",
        "metadata": {},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [{"kind": "text", "text": "partial answer"}],
            },
        },
    }
    failed = {
        "kind": "status-update",
        "final": True,
        "status": {"state": "failed"},
    }

    decoder.project(working, author="default")
    decoder.project(failed, author="default")

    assert decoder.finalize_projection(author="default") == []


def test_decoder_does_not_duplicate_an_explicit_final_answer():
    decoder = A2AStreamDecoder()
    decoder.project(
        {
            "kind": "status-update",
            "metadata": {},
            "status": {
                "state": "working",
                "message": {
                    "role": "agent",
                    "parts": [{"kind": "text", "text": "answer"}],
                },
            },
        },
        author="default",
    )
    explicit_final = decoder.project(
        {
            "kind": "artifact-update",
            "lastChunk": True,
            "artifact": {
                "artifactId": "final-1",
                "parts": [{"kind": "text", "text": "answer"}],
            },
        },
        author="default",
    )

    assert explicit_final[0]["partial"] is False
    assert decoder.finalize_projection(author="default") == []


@pytest.mark.parametrize("state", ["submitted", "working"])
def test_maps_non_final_empty_status_to_transport_heartbeat(state):
    event = {
        "kind": "status-update",
        "taskId": "task-1",
        "status": {"state": state},
    }

    events = a2a_event_to_studio_events(event, author="default")

    assert events == [
        {
            "id": f"a2a-task-1-{state}",
            "author": "default",
            "partial": True,
            "content": {"role": "model", "parts": []},
            "customMetadata": {"a2aStatus": state},
        }
    ]


def test_decoder_suppresses_repeated_transport_heartbeats():
    decoder = A2AStreamDecoder()
    submitted = {
        "kind": "status-update",
        "taskId": "task-1",
        "status": {"state": "submitted"},
    }
    working = {
        "kind": "status-update",
        "taskId": "task-1",
        "status": {"state": "working"},
    }

    assert len(decoder.project(submitted, author="default")) == 1
    assert decoder.project(submitted, author="default") == []
    assert len(decoder.project(working, author="default")) == 1
    assert decoder.project(working, author="default") == []


def test_does_not_map_submitted_user_echo_or_terminal_status_message():
    submitted = {
        "kind": "status-update",
        "status": {
            "state": "submitted",
            "message": {"role": "user", "parts": [{"kind": "text", "text": "hello"}]},
        },
    }
    completed = {
        "kind": "status-update",
        "final": True,
        "status": {
            "state": "completed",
            "message": {"role": "agent", "parts": [{"kind": "text", "text": "done"}]},
        },
    }

    assert a2a_event_to_studio_events(submitted, author="default") == []
    assert a2a_event_to_studio_events(completed, author="default") == []


def test_projection_suppresses_cumulative_working_message_after_deltas():
    decoder = A2AStreamDecoder()

    def working(text):
        return {
            "kind": "status-update",
            "metadata": {"adk_usage_metadata": {"totalTokenCount": 1}},
            "status": {
                "state": "working",
                "message": {
                    "role": "agent",
                    "parts": [{"kind": "text", "text": text}],
                },
            },
        }

    first_event = working("hello")
    first_event["metadata"] = {}
    second_event = working("-stream")
    second_event["metadata"] = {}
    first = decoder.project(first_event, author="default")
    second = decoder.project(second_event, author="default")
    cumulative = decoder.project(working("hello-stream"), author="default")

    assert first[0]["content"]["parts"][0]["text"] == "hello"
    assert second[0]["content"]["parts"][0]["text"] == "-stream"
    assert cumulative == []


def test_projection_preserves_identical_non_cumulative_deltas():
    decoder = A2AStreamDecoder()
    event = {
        "kind": "status-update",
        "metadata": {},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [{"kind": "text", "text": "ha"}],
            },
        },
    }

    first = decoder.project(event, author="default")
    second = decoder.project(event, author="default")

    assert first[0]["content"]["parts"][0]["text"] == "ha"
    assert second[0]["content"]["parts"][0]["text"] == "ha"


@pytest.mark.parametrize("code", [-32601, -32004])
def test_method_not_supported_detection(code):
    assert is_method_not_supported({"error": {"code": code}}) is True


def test_other_errors_do_not_allow_fallback():
    assert is_method_not_supported({"error": {"code": -32603}}) is False
    assert (
        a2a_error_message({"error": {"code": -32603, "message": "failed"}}) == "failed"
    )
