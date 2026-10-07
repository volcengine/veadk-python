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


def _mpa_artifact(event_type, payload, *, task_id="task-1", event_id=None):
    return {
        "kind": "artifact-update",
        "taskId": task_id,
        "lastChunk": False,
        "artifact": {
            "artifactId": "sandbox-artifact",
            "parts": [
                {
                    "kind": "data",
                    "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                    "data": {
                        "eventId": event_id or event_type,
                        "invocationId": "sandbox-invocation",
                        "eventType": event_type,
                        "payload": payload,
                    },
                }
            ],
        },
    }


def _outer_result(text="Final answer.", *, task_id="task-1"):
    return {
        "kind": "artifact-update",
        "taskId": task_id,
        "lastChunk": True,
        "artifact": {
            "artifactId": "outer-result",
            "parts": [
                {
                    "kind": "data",
                    "metadata": {"adk_type": "function_response"},
                    "data": {"name": "sandbox_task", "response": {"result": text}},
                }
            ],
        },
    }


def test_mpa_a2a_final_replaces_sandbox_preview_and_owns_outer_result():
    decoder = A2AStreamDecoder()
    delta = decoder.project(
        _mpa_artifact("message.delta", {"text": "Final answer."}), author="default"
    )
    final = decoder.project(
        _mpa_artifact("invocation.completed", {"finalMessage": "Final answer."}),
        author="default",
    )
    assert len(final) == 1
    assert final[0]["invocationId"] == delta[0]["invocationId"]
    assert final[0]["partial"] is False
    assert final[0]["turnComplete"] is True
    assert final[0]["content"]["parts"] == [{"text": "Final answer."}]
    assert decoder.project(_outer_result(), author="default") == []
    extra = decoder.project(_outer_result("Outer reformulation."), author="default")
    assert extra[0]["content"]["parts"] == [{"text": "Outer reformulation."}]
    decoder.project(
        {
            "kind": "status-update",
            "taskId": "task-1",
            "final": True,
            "status": {"state": "completed"},
        },
        author="default",
    )
    assert decoder.finalize_projection(author="default") == []


def test_mpa_final_keeps_usage_tools_and_distinct_outer_reasoning():
    decoder = A2AStreamDecoder()
    decoder.project(
        _mpa_artifact("invocation.completed", {"finalMessage": "Done."}),
        author="default",
    )
    late_thought = {
        "kind": "status-update",
        "taskId": "task-1",
        "metadata": {"adk_usage_metadata": {"totalTokenCount": 12}},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "messageId": "outer-thought",
                "parts": [
                    {
                        "kind": "text",
                        "text": "Outer reasoning.",
                        "metadata": {"adk_thought": True},
                    }
                ],
            },
        },
    }
    projected = decoder.project(late_thought, author="default")
    assert len(projected) == 2
    assert projected[0]["content"]["parts"] == [
        {"text": "Outer reasoning.", "thought": True}
    ]
    assert projected[1]["usageMetadata"]["totalTokenCount"] == 12
    assert projected[1]["content"]["parts"] == []
    for kind in ("tool.result", "tool.error"):
        tool = decoder.project(
            _mpa_artifact(kind, {"name": "exec_command", "commandId": "cmd-1"}),
            author="default",
        )
        assert (
            tool[0]["content"]["parts"][0]["functionResponse"]["name"] == "exec_command"
        )


def test_mpa_sandbox_replay_does_not_append_delta_or_final_again():
    decoder = A2AStreamDecoder()
    delta = _mpa_artifact("message.delta", {"text": "Final answer."})
    final = _mpa_artifact("invocation.completed", {"finalMessage": "Final answer."})
    assert decoder.project(delta, author="default")
    assert decoder.project(delta, author="default") == []
    assert decoder.project(final, author="default")
    snapshot = {
        "kind": "task",
        "id": "task-1",
        "status": {"state": "completed"},
        "artifacts": [
            delta["artifact"],
            final["artifact"],
            _outer_result()["artifact"],
        ],
    }
    assert decoder.project(snapshot, author="default") == []
    assert decoder.finalize_projection(author="default") == []
    assert decoder.project(_outer_result(task_id="task-2"), author="default")
    assert decoder.project(
        _mpa_artifact("message.delta", {"text": "Other task."}, task_id="task-2"),
        author="default",
    )


@pytest.mark.parametrize("field", ["text", "message"])
def test_sandbox_completed_legacy_text_fields_remain_supported(field):
    projected = A2AStreamDecoder().project(
        _mpa_artifact("invocation.completed", {field: "Legacy final."}),
        author="default",
    )
    assert projected[0]["content"]["parts"] == [{"text": "Legacy final."}]
    assert projected[0]["turnComplete"] is True


def test_missing_task_id_does_not_claim_an_unrelated_outer_answer():
    decoder = A2AStreamDecoder()
    final = _mpa_artifact("invocation.completed", {"finalMessage": "Done."})
    final.pop("taskId")
    assert decoder.project(final, author="default")
    unrelated = _outer_result("Unscoped answer.")
    unrelated.pop("taskId")
    assert decoder.project(unrelated, author="default")


@pytest.mark.parametrize(
    "event_type,payload",
    [
        ("invocation.completed", {"finalMessage": ""}),
        ("invocation.completed", {"finalMessage": "   "}),
        ("invocation.failed", {"message": "Failed."}),
        ("invocation.cancelled", {"message": "Cancelled."}),
    ],
)
def test_empty_or_unsuccessful_sandbox_final_does_not_own_outer_result(
    event_type, payload
):
    decoder = A2AStreamDecoder()
    decoder.project(_mpa_artifact(event_type, payload), author="default")
    assert decoder.project(_outer_result("Fallback response."), author="default")


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


@pytest.mark.parametrize("through_feed", [False, True])
@pytest.mark.parametrize("usage_first", [False, True])
def test_mpa_shared_source_id_preserves_usage_and_final(through_feed, usage_first):
    decoder = A2AStreamDecoder(mpa_a2a=True)
    usage = _mpa_artifact("usage.updated", {"totalTokens": 100}, event_id="shared")
    final = _mpa_artifact(
        "invocation.completed", {"finalMessage": "Final answer."}, event_id="shared"
    )
    events = [usage, final] if usage_first else [final, usage]
    output = []
    for event in events * 2:
        frames = decoder.feed(_frame(event)) if through_feed else [{"result": event}]
        for frame in frames:
            output.extend(decoder.project(frame["result"], author="default"))
    assert [item["customMetadata"]["eventType"] for item in output] == [
        event["artifact"]["parts"][0]["data"]["eventType"] for event in events
    ]
    assert len({item["id"] for item in output}) == 2
    assert (
        sum(item.get("usageMetadata", {}).get("totalTokenCount", 0) for item in output)
        == 100
    )
    assert decoder.project(_outer_result(), author="default") == []


def test_mpa_multipart_replay_retains_new_part_and_invocation():
    decoder = A2AStreamDecoder(mpa_a2a=True)

    def consume(event):
        return [
            item
            for frame in decoder.feed(_frame(event))
            for item in decoder.project(frame["result"], author="default")
        ]

    first = _mpa_artifact(
        "tool.call", {"name": "read", "commandId": "cmd"}, event_id="shared"
    )
    final = _mpa_artifact(
        "invocation.completed", {"finalMessage": "Done."}, event_id="shared"
    )
    assert len(consume(first)) == 1
    combined = {
        **first,
        "artifact": {
            **first["artifact"],
            "parts": first["artifact"]["parts"] + final["artifact"]["parts"],
        },
    }
    assert consume(combined)[0]["turnComplete"] is True
    assert consume(combined) == []
    final["artifact"]["parts"][0]["data"]["invocationId"] = "another-invocation"
    assert len(consume(final)) == 1
    assert len(consume({**final, "taskId": "another-task"})) == 1


@pytest.mark.parametrize("event_type", ["invocation.failed", "invocation.cancelled"])
def test_mpa_usage_does_not_hide_same_id_terminal_failure(event_type):
    decoder = A2AStreamDecoder(mpa_a2a=True)
    output = []
    for event in [
        _mpa_artifact("usage.updated", {"totalTokens": 10}, event_id="shared"),
        _mpa_artifact(event_type, {"message": "Interrupted"}, event_id="shared"),
    ]:
        for frame in decoder.feed(_frame(event)):
            output.extend(decoder.project(frame["result"], author="default"))
    assert [item["customMetadata"]["eventType"] for item in output] == [
        "usage.updated",
        event_type,
    ]


def test_mpa_missing_source_ids_are_not_deduplicated():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    event = _mpa_artifact("message.delta", {"text": "Repeat"})
    event["artifact"]["parts"][0]["data"]["eventId"] = ""
    for _ in range(2):
        frames = decoder.feed(_frame(event))
        assert len(frames) == 1
        assert len(decoder.project(frames[0]["result"], author="default")) == 1


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


def test_maps_sandbox_usage_to_existing_studio_usage_fields():
    event = {
        "kind": "artifact-update",
        "lastChunk": False,
        "artifact": {
            "artifactId": "sandbox-e-1",
            "parts": [
                {
                    "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                    "data": {
                        "eventId": "usage-1",
                        "invocationId": "e-1",
                        "eventType": "usage.updated",
                        "payload": {
                            "modelId": "model-a",
                            "inputTokens": 10,
                            "outputTokens": 4,
                            "totalTokens": 14,
                            "cachedTokens": 3,
                        },
                    },
                }
            ],
        },
    }

    projected = A2AStreamDecoder().project(event, author="default")

    assert projected == [
        {
            "id": "usage-1",
            "author": "default",
            "invocationId": "e-1",
            "partial": True,
            "content": {"role": "model", "parts": []},
            "modelVersion": "model-a",
            "usageMetadata": {
                "promptTokenCount": 10,
                "candidatesTokenCount": 4,
                "totalTokenCount": 14,
                "cachedContentTokenCount": 3,
            },
            "customMetadata": {
                "source": "sandbox",
                "eventType": "usage.updated",
                "sourceEventId": "usage-1",
            },
        }
    ]


def test_decoder_emits_only_positive_delta_for_replayed_sandbox_usage():
    decoder = A2AStreamDecoder()

    def usage_event(total: int, event_id: str):
        return {
            "kind": "artifact-update",
            "artifact": {
                "artifactId": "sandbox-e-1",
                "parts": [
                    {
                        "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                        "data": {
                            "eventId": event_id,
                            "invocationId": "e-1",
                            "eventType": "usage.updated",
                            "payload": {
                                "requestId": "request-1",
                                "inputTokens": total - 4,
                                "outputTokens": 4,
                                "totalTokens": total,
                            },
                        },
                    }
                ],
            },
        }

    first = decoder.project(usage_event(14, "usage-1"), author="default")
    replay = decoder.project(usage_event(14, "usage-2"), author="default")
    advanced = decoder.project(usage_event(20, "usage-3"), author="default")

    assert first[0]["usageMetadata"]["totalTokenCount"] == 14
    assert replay == []
    assert advanced[0]["usageMetadata"]["totalTokenCount"] == 6


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


def test_projection_suppresses_reasoning_replayed_across_status_and_artifact():
    decoder = A2AStreamDecoder()
    status = {
        "kind": "status-update",
        "taskId": "task-1",
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [
                    {
                        "kind": "text",
                        "text": "inspect then compare",
                        "metadata": {"adk_thought": True},
                    }
                ],
            },
        },
    }
    artifact = {
        "kind": "artifact-update",
        "taskId": "task-1",
        "artifact": {
            "artifactId": "thought-1",
            "parts": [
                {
                    "kind": "text",
                    "text": "inspect then compare",
                    "metadata": {"adk_thought": True},
                }
            ],
        },
    }

    first = decoder.project(status, author="default")
    replay = decoder.project(artifact, author="default")

    assert first[0]["customMetadata"]["thoughtKind"] == "reasoning"
    assert replay == []


def test_projection_keeps_equal_reasoning_for_different_tasks():
    decoder = A2AStreamDecoder()

    def artifact(task_id):
        return {
            "kind": "artifact-update",
            "taskId": task_id,
            "artifact": {
                "artifactId": f"{task_id}-thought",
                "parts": [
                    {
                        "kind": "text",
                        "text": "same deliberate thought",
                        "metadata": {"adk_thought": True},
                    }
                ],
            },
        }

    first = decoder.project(artifact("task-1"), author="default")
    second = decoder.project(artifact("task-2"), author="default")

    assert len(first) == 1
    assert len(second) == 1


def test_projection_suppresses_completed_reasoning_replayed_after_deltas():
    decoder = A2AStreamDecoder()

    def artifact(text, event_id):
        return {
            "kind": "artifact-update",
            "taskId": "task-1",
            "artifact": {
                "artifactId": "sandbox-invocation-1",
                "parts": [
                    {
                        "kind": "data",
                        "metadata": {"schemaVersion": "mpa.sandbox-event.v1"},
                        "data": {
                            "eventId": event_id,
                            "invocationId": "invocation-1",
                            "eventType": "thought.delta",
                            "payload": {"text": text},
                        },
                    }
                ],
            },
        }

    first = decoder.project(artifact("inspect ", "10"), author="default")
    second = decoder.project(artifact("the repository", "11"), author="default")
    replay = decoder.project(artifact("inspect the repository", "12"), author="default")

    assert first[0]["content"]["parts"][0]["text"] == "inspect "
    assert second[0]["content"]["parts"][0]["text"] == "the repository"
    assert replay == []


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
    assert len(cumulative) == 1
    assert cumulative[0]["content"]["parts"] == []
    assert cumulative[0]["usageMetadata"] == {"totalTokenCount": 1}


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


@pytest.mark.parametrize(
    "text", ["Result; additional warning.", "Different answer.", "Res"]
)
def test_mpa_final_preserves_distinct_outer_complete_text(text):
    decoder = A2AStreamDecoder()
    decoder.project(
        _mpa_artifact("invocation.completed", {"finalMessage": "Result"}),
        author="default",
    )
    projected = decoder.project(_outer_result(text), author="default")
    assert projected[0]["content"]["parts"] == [{"text": text}]


def test_mpa_final_preserves_partial_mirror_until_its_meaning_is_complete():
    decoder = A2AStreamDecoder()
    decoder.project(
        _mpa_artifact("invocation.completed", {"finalMessage": "Result"}),
        author="default",
    )
    for index, text in enumerate(["Result", "; additional warning."]):
        event = {
            "kind": "status-update",
            "taskId": "task-1",
            "status": {
                "state": "working",
                "message": {
                    "role": "agent",
                    "messageId": f"extra-{index}",
                    "parts": [{"kind": "text", "text": text}],
                },
            },
        }
        projected = decoder.project(event, author="default")
        assert projected[0]["content"]["parts"] == [{"text": text}]


def test_mpa_exact_outer_mirror_keeps_other_artifact_parts():
    decoder = A2AStreamDecoder()
    decoder.project(
        _mpa_artifact("invocation.completed", {"finalMessage": "Result"}),
        author="default",
    )
    event = _outer_result(" Result ")
    event["artifact"]["parts"].append({"kind": "text", "text": "Additional warning."})
    projected = decoder.project(event, author="default")
    assert [item["content"]["parts"] for item in projected] == [
        [{"text": "Additional warning."}]
    ]


def _thought_status(parts, *, complete=False):
    return {
        "kind": "status-update",
        "taskId": "task-1",
        "metadata": {"adk_usage_metadata": {"totalTokenCount": 1}} if complete else {},
        "status": {
            "state": "working",
            "message": {
                "role": "agent",
                "parts": [
                    {"kind": "text", "text": text, "metadata": {"adk_thought": True}}
                    for text in parts
                ],
            },
        },
    }


def _thought_text(events):
    return "".join(
        p["text"]
        for e in events
        for p in e.get("content", {}).get("parts", [])
        if p.get("thought")
    )


def test_mpa_outer_multipart_snapshot_and_worker_replay_are_independent():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    events = []
    for part in ["Plan", " again", "."]:
        events += decoder.project(_thought_status([part]), author="outer")
    events += decoder.project(_thought_status(["Plan", " again", "."]), author="outer")
    for index, part in enumerate(["Read ", "skill", ".", "Read skill."]):
        events += decoder.project(
            _mpa_artifact("thought.delta", {"text": part}, event_id=str(index)),
            author="outer",
        )
    assert _thought_text(events) == "Plan again.Read skill."


def test_mpa_reasoning_keeps_repeated_tokens_and_separates_phases_and_invocations():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    first = decoder.project(
        _mpa_artifact("thought.delta", {"text": "ha"}, event_id="1"), author="outer"
    )
    repeat = decoder.project(
        _mpa_artifact("thought.delta", {"text": "ha"}, event_id="2"), author="outer"
    )
    assert _thought_text(first + repeat) == "haha"
    decoder.project(_mpa_artifact("tool.call", {"name": "inspect"}), author="outer")
    tail = decoder.project(
        _mpa_artifact("thought.delta", {"text": "."}, event_id="3"), author="outer"
    )
    assert (
        first[0]["customMetadata"]["reasoningSegmentId"]
        == tail[0]["customMetadata"]["reasoningSegmentId"]
    )
    assert (
        decoder.project(
            _mpa_artifact("thought.delta", {"text": "haha."}, event_id="4"),
            author="outer",
        )
        == []
    )
    decoder.project(_mpa_artifact("tool.result", {"name": "inspect"}), author="outer")
    later = decoder.project(
        _mpa_artifact("thought.delta", {"text": "haha."}, event_id="5"), author="outer"
    )
    assert _thought_text(later) == "haha."
    assert (
        later[0]["customMetadata"]["reasoningSegmentId"]
        != first[0]["customMetadata"]["reasoningSegmentId"]
    )
    other = _mpa_artifact("thought.delta", {"text": "haha."}, event_id="6")
    other["artifact"]["parts"][0]["data"]["invocationId"] = "other-worker"
    assert _thought_text(decoder.project(other, author="outer")) == "haha."


def test_mpa_cumulative_thought_extension_and_default_compatibility():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    first = decoder.project(_thought_status(["Plan"]), author="outer")
    more = decoder.project(
        _thought_status(["Plan then act"], complete=True), author="outer"
    )
    assert _thought_text(first + more) == "Plan then act"
    generic = A2AStreamDecoder()
    assert (
        "reasoningSegmentId"
        not in generic.project(_thought_status(["Plan"]), author="outer")[0][
            "customMetadata"
        ]
    )


def test_mpa_mixed_status_parts_and_cancelled_partial_remain_visible():
    event = _thought_status(["new thought"])
    event["status"]["message"]["parts"].insert(0, {"text": "Answer", "metadata": None})
    decoder = A2AStreamDecoder(mpa_a2a=True)
    projected = decoder.project(event, author="outer")
    assert _thought_text(projected) == "new thought"
    assert projected[0]["content"]["parts"][0]["text"] == "Answer"
    decoder.project(
        {
            "kind": "status-update",
            "taskId": "task-1",
            "final": True,
            "status": {"state": "canceled"},
        },
        author="outer",
    )
    assert _thought_text(projected) == "new thought"


def _outer_thought_artifact(
    chunks, *, kind="artifact-update", append=False, final=True
):
    artifact = {
        "artifactId": "outer-final",
        "parts": [
            {"kind": "text", "text": text, "metadata": {"adk_thought": True}}
            for text in chunks
        ]
        + [{"kind": "text", "text": "2"}],
    }
    if kind == "task":
        return {
            "kind": "task",
            "id": "task-1",
            "status": {"state": "completed"},
            "artifacts": [artifact],
        }
    return {
        "kind": kind,
        "taskId": "task-1",
        "append": append,
        "lastChunk": final,
        "artifact": artifact,
    }


@pytest.mark.parametrize("kind", ["artifact-update", "task"])
@pytest.mark.parametrize("stream_first", [False, True])
def test_mpa_final_tokenized_thought_artifact_is_one_snapshot(kind, stream_first):
    chunks = [
        "The",
        " user",
        " asks",
        " a",
        " question",
        ".",
        "\n\n",
        "Answer",
        " directly",
        ".",
        " ",
    ]
    decoder = A2AStreamDecoder(mpa_a2a=True)
    output = []
    if stream_first:
        for chunk in chunks:
            output += decoder.project(_thought_status([chunk]), author="outer")
    event = _outer_thought_artifact(chunks, kind=kind)
    before = json.dumps(event)
    final = decoder.project(event, author="outer")
    output += final
    assert _thought_text(output) == "".join(chunks)
    assert (
        len(
            {
                e["customMetadata"]["reasoningSegmentId"]
                for e in output
                if _thought_text([e])
            }
        )
        == 1
    )
    assert len([e for e in final if _thought_text([e])]) == (0 if stream_first else 1)
    assert final[-1]["content"]["parts"] == [{"text": "2"}]
    assert json.dumps(event) == before


def test_mpa_tokenized_extended_snapshot_emits_only_suffix():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    first = decoder.project(_thought_status(["The user"]), author="outer")
    more = decoder.project(
        _outer_thought_artifact(["The", " user", " asks", "."]), author="outer"
    )
    assert _thought_text(first + more) == "The user asks."
    assert _thought_text(more) == " asks."


def test_mpa_artifact_append_chunks_keep_whitespace_and_repeated_deltas():
    decoder = A2AStreamDecoder(mpa_a2a=True)
    first = _outer_thought_artifact(["ha", " "], append=True, final=False)
    first["artifact"]["parts"].pop()
    a = decoder.project(first, author="outer")
    b = decoder.project(first, author="outer")
    assert _thought_text(a + b) == "ha ha "
    assert (
        a[0]["customMetadata"]["reasoningSegmentId"]
        == b[0]["customMetadata"]["reasoningSegmentId"]
    )


def test_mpa_thought_coalescing_keeps_non_thought_boundaries_and_default_behavior():
    event = _outer_thought_artifact(["First", " thought"])
    event["artifact"]["parts"] += [
        {"kind": "text", "text": "Second", "metadata": {"adk_thought": True}}
    ]
    mpa = A2AStreamDecoder(mpa_a2a=True).project(event, author="outer")
    assert [bool(e["content"]["parts"][0].get("thought")) for e in mpa] == [
        True,
        False,
        True,
    ]
    generic = A2AStreamDecoder().project(event, author="outer")
    assert [e["content"]["parts"][0]["text"] for e in generic] == [
        "First",
        "thought",
        "2",
        "Second",
    ]
