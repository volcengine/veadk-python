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

"""Public text is safe at every transport boundary and storage grows linearly."""

from frontend.server.intelligent_development_runs.output import TaskTextProjection
from veadk.cli.codex_app_server import CodexAppServerEvent


def test_split_secret_never_reaches_a_public_frame():
    secret = "credential-boundary-value"
    for split in range(1, len(secret)):
        projection = TaskTextProjection((secret,))
        frames = []
        for text in ("safe prefix " + secret[:split], secret[split:] + " safe suffix"):
            frames.append(
                projection.apply(
                    CodexAppServerEvent(kind="text", item_id="i", text=text), "t"
                )
            )
        frames.extend(projection.finish("t"))
        visible = ""
        for event in frames:
            visible = visible + event.text if event.kind == "text" else event.text
            assert secret not in visible
            assert "credential-" not in visible
        assert visible == "safe prefix *** safe suffix"


def test_stream_storage_is_linear_and_snapshot_does_not_duplicate_text():
    projection = TaskTextProjection(())
    frames = [
        projection.apply(
            CodexAppServerEvent(kind="text", item_id="i", text="x" * 100), "t"
        )
        for _ in range(100)
    ]
    assert sum(len(event.text) for event in frames) <= 10_000
    duplicate = projection.apply(
        CodexAppServerEvent(kind="text_snapshot", item_id="i", text="x" * 10_000), "t"
    )
    assert duplicate.kind == "text" and duplicate.text == ""


def test_commentary_final_updates_one_item_and_thinking_redacts_partial_secrets():
    projection = TaskTextProjection(("credential-boundary-value",))
    prefix = projection.apply(
        CodexAppServerEvent(
            kind="thinking",
            item_id="reason",
            text="safe credential-boundary-",
            status="running",
        ),
        "t",
        snapshot_only=True,
    )
    assert "credential-" not in prefix.text
    final = projection.apply(
        CodexAppServerEvent(
            kind="thinking",
            item_id="reason",
            text="safe credential-boundary-value",
            status="done",
        ),
        "t",
        snapshot_only=True,
    )
    assert final.text == "safe ***" and final.kind == "thinking"
    projection = TaskTextProjection(())
    first = projection.apply(
        CodexAppServerEvent(kind="text", item_id="i", text="plan"), "t"
    )
    completed = projection.apply(
        CodexAppServerEvent(kind="commentary", item_id="i", text="plan", status="done"),
        "t",
    )
    assert first.text == "plan" and completed.text == ""


def test_tool_output_redacts_split_credentials_and_retains_its_native_channel():
    secret = "credential-boundary-value"
    for split in range(1, len(secret)):
        projection = TaskTextProjection((secret,))
        frames = [
            projection.apply(
                CodexAppServerEvent(
                    kind="tool_output",
                    item_id="command",
                    item_type="commandExecution",
                    text=text,
                ),
                "turn",
            )
            for text in ("safe " + secret[:split], secret[split:] + " result")
        ]
        assert all(event.kind == "tool_output" for event in frames)
        frames.extend(projection.finish("turn"))
        visible = ""
        for event in frames:
            visible = (
                visible + event.text if event.kind == "tool_output" else event.text
            )
            assert secret not in visible and "credential-" not in visible
            assert event.item_type == "commandExecution" and event.turn_id == "turn"
        assert visible == "safe *** result"


def test_final_flush_preserves_assistant_phase_and_identity():
    projection = TaskTextProjection(())
    projection.apply(
        CodexAppServerEvent(
            kind="text",
            item_id="answer",
            item_type="agentMessage",
            phase="final_answer",
            text="done",
        ),
        "turn",
    )
    final = projection.finish("turn")[0]
    assert final.item_id == "answer" and final.phase == "final_answer"
    assert final.item_type == "agentMessage" and final.text == "done"
