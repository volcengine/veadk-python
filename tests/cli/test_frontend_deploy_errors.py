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
import queue
import threading

from veadk.cli.cli_frontend import (
    _advance_deploy_phase,
    _build_log_tail_has_error_marker,
    _cp_metadata_from_reporter_message,
    _deployment_target_key,
    _extract_build_error_excerpt,
    _finalize_deploy_task,
    _has_active_deployment_target,
    _next_deploy_stream_event,
    _sanitize_build_log_snapshot,
    _wait_for_cp_build_error_log_snapshot,
)


def test_extract_build_error_excerpt_keeps_dependency_resolution_cause() -> None:
    lines = [
        "#10 0.1 Using Python 3.12",
        "\x1b[31m× No solution found when resolving dependencies:\x1b[0m",
        "╰─▶ Because only veadk-python<=1.0.4 is available",
        "    and you require veadk-python>=1.0.5,",
        "    your requirements are unsatisfiable.",
        "#10 ERROR: process did not complete successfully",
    ]

    excerpt = _extract_build_error_excerpt(lines)

    assert "\x1b" not in excerpt
    assert "veadk-python<=1.0.4" in excerpt
    assert "veadk-python>=1.0.5" in excerpt
    assert "requirements are unsatisfiable" in excerpt


def test_extract_build_error_excerpt_removes_credentials() -> None:
    lines = [
        "VOLCENGINE_ACCESS_KEY=temporary-access-key",
        "VOLCENGINE_SECRET_KEY=temporary-secret-key",
        "Authorization: Bearer temporary.jwt.token",
        "X-Tos-Security-Token=temporary-session-token",
        "CR_TOKEN=temporary-registry-token",
        "API_KEY=temporary-api-key",
        "No solution found when resolving dependencies:",
        "Because only veadk-python<=1.0.4 is available",
        "and you require veadk-python>=1.0.5",
        "docker login --password temporary-registry-token registry.example.com",
    ]

    excerpt = _extract_build_error_excerpt(lines)

    assert "temporary" not in excerpt
    assert "veadk-python>=1.0.5" in excerpt


def test_extract_build_error_excerpt_ignores_successful_logs() -> None:
    lines = [
        "Step 1/2: Building image",
        "Successfully built image",
        "Step 2/2: Deploying service",
        "Runtime status: Ready",
    ]

    assert _extract_build_error_excerpt(lines) == ""


def test_advance_deploy_phase_classifies_runtime_initialization_failure() -> None:
    message = (
        "Deploy failed: Runtime status is Error. Initialization failed "
        "ErrorCode.RUNTIME_NOT_READY"
    )

    assert _advance_deploy_phase("build", message) == "deploy"
    assert _advance_deploy_phase("deploy", "Step 1/2: Building image") == "deploy"


def test_advance_deploy_phase_classifies_slow_runtime_ready_timeout() -> None:
    message = "Timed out waiting for Runtime to reach Ready (last status: Releasing)."

    assert _advance_deploy_phase("build", message) == "deploy"


def test_advance_deploy_phase_classifies_stuck_runtime_reconciliation() -> None:
    message = (
        "Harness Sidecar runtime is stuck in a status that cannot be updated; "
        "explicit reconciliation is required before any delete or recreate"
    )

    assert _advance_deploy_phase("build", message) == "deploy"


def test_next_deploy_stream_event_emits_heartbeat_without_blocking_executor() -> None:
    events: queue.Queue[object] = queue.Queue()

    has_event, event = asyncio.run(
        _next_deploy_stream_event(
            events,
            heartbeat_seconds=0.01,
            poll_seconds=0.001,
        )
    )

    assert not has_event
    assert event is None
    events.put({"phase": "deploy"})
    has_event, event = asyncio.run(
        _next_deploy_stream_event(
            events,
            heartbeat_seconds=0.01,
            poll_seconds=0.001,
        )
    )
    assert has_event
    assert event == {"phase": "deploy"}


def test_active_deployment_target_is_scoped_by_owner_runtime_and_region() -> None:
    target = _deployment_target_key("owner-a", "agent-a", "cn-shanghai")
    tasks = {"task-a": {"target_key": target}}

    assert _has_active_deployment_target(tasks, target)
    assert not _has_active_deployment_target(
        tasks,
        _deployment_target_key("owner-b", "agent-a", "cn-shanghai"),
    )
    assert not _has_active_deployment_target(
        tasks,
        _deployment_target_key("owner-a", "agent-a", "cn-beijing"),
    )


def test_worker_finalizer_cleans_source_without_stream_consumer(tmp_path) -> None:
    work_dir = tmp_path / "deployment-source"
    work_dir.mkdir()
    (work_dir / "main.py").write_text("app = object()\n", encoding="utf-8")
    stop_event = threading.Event()
    task_state = {"cp_log_stop_event": stop_event}
    tasks = {"task-a": task_state}
    events: queue.Queue[object] = queue.Queue()

    _finalize_deploy_task(
        task_id="task-a",
        task_state=task_state,
        tasks=tasks,
        tasks_lock=threading.Lock(),
        events=events,
        temp_dir=str(work_dir),
    )

    assert stop_event.is_set()
    assert tasks == {}
    assert not work_dir.exists()
    assert events.get_nowait() is None


def test_build_log_tail_error_marker_checks_retained_tail() -> None:
    text = "error: failed to solve\n" + ("progress line\n" * 20)

    assert not _build_log_tail_has_error_marker(text, tail_chars=20)
    assert _build_log_tail_has_error_marker(text, tail_chars=len(text))


def test_wait_for_cp_build_error_log_snapshot_retries_until_tail_has_marker() -> None:
    snapshots = iter(
        [
            {"text": "downloading base image"},
            {"text": "extracting base image"},
            {"text": "error: failed to solve: exit code: 1"},
        ]
    )
    sleeps: list[float] = []

    snapshot = _wait_for_cp_build_error_log_snapshot(
        lambda: next(snapshots),
        attempts=5,
        interval_seconds=2.0,
        sleep_fn=sleeps.append,
    )

    assert snapshot["text"].startswith("error: failed to solve")
    assert sleeps == [2.0, 2.0]


def test_wait_for_cp_build_error_log_snapshot_returns_last_snapshot_on_timeout() -> (
    None
):
    snapshots = iter(
        [
            {"text": "downloading base image"},
            {"text": "extracting base image"},
        ]
    )
    sleeps: list[float] = []

    snapshot = _wait_for_cp_build_error_log_snapshot(
        lambda: next(snapshots),
        attempts=2,
        interval_seconds=0.5,
        sleep_fn=sleeps.append,
    )

    assert snapshot == {"text": "extracting base image"}
    assert sleeps == [0.5]


def test_wait_for_cp_build_error_log_snapshot_keeps_last_success_on_later_error() -> (
    None
):
    calls = 0
    sleeps: list[float] = []

    def read_snapshot() -> dict[str, str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            return {"text": "extracting base image"}
        raise RuntimeError("temporary log download failure")

    snapshot = _wait_for_cp_build_error_log_snapshot(
        read_snapshot,
        attempts=2,
        interval_seconds=0.5,
        sleep_fn=sleeps.append,
    )

    assert snapshot == {"text": "extracting base image"}
    assert sleeps == [0.5]


def test_sanitize_build_log_snapshot_redacts_and_bounds_logs() -> None:
    text = """Authorization: Bearer temporary.jwt.token
installing dependencies
API_KEY=temporary-api-key
No solution found when resolving dependencies:
Because veadk-python>=1.0.5 is unavailable
Traceback (most recent call last):"""

    snapshot = _sanitize_build_log_snapshot(text, max_chars=500, max_lines=4)

    assert "temporary" not in snapshot["text"]
    assert "Authorization" not in snapshot["text"]
    assert "API_KEY" not in snapshot["text"]
    assert "veadk-python>=1.0.5" in snapshot["text"]
    assert snapshot["lineCount"] == 4
    assert snapshot["truncated"] is True


def test_sanitize_build_log_snapshot_removes_camel_case_credentials() -> None:
    text = """requesting temporary upload credentials
Resp {"sessionToken":"temporary-session-token","accessKeyId":"temporary-access-key","secretAccessKey":"temporary-secret-key"}
credentials received"""

    snapshot = _sanitize_build_log_snapshot(text)

    assert "temporary-session-token" not in snapshot["text"]
    assert "temporary-access-key" not in snapshot["text"]
    assert "temporary-secret-key" not in snapshot["text"]
    assert "requesting temporary upload credentials" in snapshot["text"]
    assert "credentials received" in snapshot["text"]
    assert snapshot["truncated"] is True


def test_cp_metadata_from_reporter_message_extracts_pipeline_and_run_ids() -> None:
    assert _cp_metadata_from_reporter_message(
        "Pipeline created successfully: agentkit-cli-demo-abcd (ID: pl-123)"
    ) == {
        "pipeline_name": "agentkit-cli-demo-abcd",
        "pipeline_id": "pl-123",
    }
    assert _cp_metadata_from_reporter_message(
        "Reusing pipeline by name: agentkit-cli-demo-abcd"
    ) == {"pipeline_name": "agentkit-cli-demo-abcd"}
    assert _cp_metadata_from_reporter_message(
        "Pipeline triggered successfully, run ID: pr-456"
    ) == {"pipeline_run_id": "pr-456"}
    assert _cp_metadata_from_reporter_message(
        "triggering build (pipeline=pipe-sidecar-cache)"
    ) == {"pipeline_id": "pipe-sidecar-cache"}
    assert _cp_metadata_from_reporter_message("run id run-sidecar-cache; waiting…") == {
        "pipeline_run_id": "run-sidecar-cache"
    }
