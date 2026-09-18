# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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

"""Behavior tests for ``veadk mpa control`` (VC-22)."""

from __future__ import annotations

import json
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

import pytest

from click.testing import CliRunner

from veadk.cli import cli_mpa


@contextmanager
def _bff_server(
    *,
    status: int = 200,
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    first_response_delay: float = 0.0,
) -> Iterator[tuple[str, list[dict[str, Any]]]]:
    requests: list[dict[str, Any]] = []
    response_payload = payload or {}
    response_headers = headers or {}

    class Handler(BaseHTTPRequestHandler):
        def _record(self, method: str) -> None:
            content_length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(content_length) if content_length else b""
            requests.append(
                {
                    "method": method,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization", ""),
                    "idempotency_key": self.headers.get("Idempotency-Key", ""),
                    "if_match": self.headers.get("If-Match", ""),
                    "body": json.loads(raw_body) if raw_body else None,
                }
            )
            if first_response_delay and len(requests) == 1:
                time.sleep(first_response_delay)
            body = json.dumps(response_payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            for key, value in response_headers.items():
                self.send_header(key, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                return

        def do_GET(self) -> None:  # noqa: N802
            self._record("GET")

        def do_POST(self) -> None:  # noqa: N802
            self._record("POST")

        def do_PATCH(self) -> None:  # noqa: N802
            self._record("PATCH")

        def do_PUT(self) -> None:  # noqa: N802
            self._record("PUT")

        def log_message(self, _format: str, *args: Any) -> None:
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_control_group_preserves_the_provisioning_create_command() -> None:
    result = CliRunner().invoke(cli_mpa.mpa, ["--help"])

    assert result.exit_code == 0
    assert "control" in result.output
    assert "create" in result.output


def test_nested_help_does_not_require_a_studio_connection() -> None:
    runner = CliRunner()

    for command in ("operation", "profile", "session"):
        result = runner.invoke(cli_mpa.mpa, ["control", command, "--help"])
        assert result.exit_code == 0, result.output


def test_command_without_studio_url_is_a_local_usage_error() -> None:
    result = CliRunner().invoke(
        cli_mpa.mpa, ["control", "view", "--mpa-instance-id", "mi-123"]
    )

    assert result.exit_code == 2
    assert "invalid_control_request" in result.output


def test_view_calls_only_studio_bff_and_outputs_json() -> None:
    view = {
        "mpaInstanceId": "mi-123",
        "bindingStatus": "bound",
        "capabilities": {
            "canRead": True,
            "canWrite": True,
            "canDebug": True,
        },
    }
    with _bff_server(payload=view, headers={"ETag": '"profile-7"'}) as (
        studio_url,
        requests,
    ):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "--token",
                "studio-bearer",
                "view",
                "--mpa-instance-id",
                "mi-123",
                "--runtime-id",
                "r-123",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == {**view, "etag": '"profile-7"'}
    assert requests == [
        {
            "method": "GET",
            "path": "/web/mpa/agents/mi-123/view?runtimeId=r-123&region=all",
            "authorization": "Bearer studio-bearer",
            "idempotency_key": "",
            "if_match": "",
            "body": None,
        }
    ]
    assert "studio-bearer" not in result.output


def test_create_reads_json_file_and_forwards_stable_idempotency_key(tmp_path) -> None:
    request_file = tmp_path / "create.json"
    request_file.write_text(
        json.dumps(
            {
                "operationKind": "create",
                "runtimeId": "r-123",
                "sourceProfileId": "agent-123",
                "profile": {
                    "name": "Research agent",
                    "system": "Research the requested topic.",
                    "model": {"modelId": "model-1"},
                },
            }
        )
    )
    operation = {
        "operationId": "op-123",
        "operationKind": "create",
        "stage": "accepted",
        "status": "pending",
    }
    with _bff_server(status=202, payload=operation) as (studio_url, requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "create",
                "--request",
                str(request_file),
                "--idempotency-key",
                "create-mi-123-profile-7",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["operationId"] == "op-123"
    assert requests[0]["method"] == "POST"
    assert requests[0]["path"] == "/web/mpa/agents"
    assert requests[0]["idempotency_key"] == "create-mi-123-profile-7"
    assert requests[0]["body"]["profile"]["model"] == {"modelId": "model-1"}


def test_create_accepts_request_json_from_stdin() -> None:
    request = {
        "operationKind": "create",
        "runtimeId": "r-stdin",
        "sourceProfileId": "agent-stdin",
        "profile": {
            "name": "stdin agent",
            "system": "Read safely.",
            "model": {"modelId": "model-1"},
        },
    }
    operation = {
        "operationId": "op-stdin",
        "operationKind": "create",
        "stage": "accepted",
        "status": "pending",
    }
    with _bff_server(status=202, payload=operation) as (studio_url, requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "create",
                "--request",
                "-",
                "--idempotency-key",
                "create-stdin",
            ],
            input=json.dumps(request),
        )

    assert result.exit_code == 0, result.output
    assert requests[0]["body"]["runtimeId"] == "r-stdin"


def test_create_rejects_secret_like_profile_before_network(tmp_path) -> None:
    request_file = tmp_path / "unsafe.json"
    request_file.write_text(
        json.dumps(
            {
                "operationKind": "create",
                "runtimeId": "r-123",
                "sourceProfileId": "agent-123",
                "profile": {
                    "name": "unsafe",
                    "system": "unsafe",
                    "model": {"apiKey": "must-not-leak"},
                },
            }
        )
    )

    result = CliRunner().invoke(
        cli_mpa.mpa,
        [
            "control",
            "--studio-url",
            "http://127.0.0.1:1",
            "create",
            "--request",
            str(request_file),
            "--idempotency-key",
            "create-unsafe",
        ],
    )

    assert result.exit_code == 2
    assert "invalid_request_payload" in result.output
    assert "must-not-leak" not in result.output


def test_update_forwards_runtime_revision_and_idempotency_key(tmp_path) -> None:
    request_file = tmp_path / "update.json"
    request_file.write_text(
        json.dumps(
            {
                "operationKind": "update",
                "runtimeId": "r-123",
                "sourceProfileId": "agent-123",
                "runtimeRevision": '"profile-7"',
                "profile": {
                    "name": "Research agent",
                    "system": "Use the revised instructions.",
                    "model": {"modelId": "model-1"},
                },
            }
        )
    )
    operation = {
        "operationId": "op-update",
        "operationKind": "update",
        "stage": "accepted",
        "status": "pending",
    }
    with _bff_server(status=202, payload=operation) as (studio_url, requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "update",
                "--mpa-instance-id",
                "mi-123",
                "--request",
                str(request_file),
                "--idempotency-key",
                "update-mi-123-profile-8",
            ],
        )

    assert result.exit_code == 0, result.output
    assert requests[0]["method"] == "PATCH"
    assert requests[0]["path"] == "/web/mpa/agents/mi-123"
    assert requests[0]["idempotency_key"] == "update-mi-123-profile-8"
    assert requests[0]["body"]["runtimeRevision"] == '"profile-7"'


def test_operation_list_get_and_retry_use_studio_lifecycle_endpoints(tmp_path) -> None:
    operation = {
        "operationId": "op-123",
        "operationKind": "create",
        "stage": "complete",
        "status": "succeeded",
    }
    with _bff_server(payload={"operations": [operation]}) as (
        studio_url,
        list_requests,
    ):
        listed = CliRunner().invoke(
            cli_mpa.mpa,
            ["control", "--studio-url", studio_url, "operation", "list"],
        )
    with _bff_server(payload=operation) as (studio_url, get_requests):
        fetched = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "operation",
                "get",
                "--operation-id",
                "op-123",
            ],
        )

    retry_file = tmp_path / "retry.json"
    retry_file.write_text(
        json.dumps(
            {
                "operationKind": "create",
                "runtimeId": "r-123",
                "sourceProfileId": "agent-123",
                "profile": {
                    "name": "Research agent",
                    "system": "Research carefully.",
                    "model": {"modelId": "model-1"},
                },
            }
        )
    )
    with _bff_server(status=202, payload=operation) as (studio_url, retry_requests):
        retried = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "operation",
                "retry",
                "--operation-id",
                "op-123",
                "--request",
                str(retry_file),
            ],
        )

    assert listed.exit_code == fetched.exit_code == retried.exit_code == 0
    assert json.loads(listed.output)[0]["operationId"] == "op-123"
    assert json.loads(fetched.output)["status"] == "succeeded"
    assert json.loads(retried.output)["operationId"] == "op-123"
    assert list_requests[0]["path"] == "/web/mpa/agent-operations?status=active"
    assert get_requests[0]["path"] == "/web/mpa/agent-operations/op-123"
    assert retry_requests[0]["path"] == ("/web/mpa/agent-operations/op-123/retry")
    assert retry_requests[0]["idempotency_key"] == ""


def test_profile_status_and_apply_preserve_etag_and_revision(tmp_path) -> None:
    status_payload = {
        "status": "applied",
        "profileRevision": 7,
        "runtimeRevision": '"runtime-7"',
    }
    with _bff_server(payload=status_payload, headers={"ETag": '"runtime-7"'}) as (
        studio_url,
        status_requests,
    ):
        status_result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "profile",
                "status",
                "--mpa-instance-id",
                "mi-123",
                "--runtime-id",
                "r-123",
            ],
        )

    profile_file = tmp_path / "profile.json"
    profile_file.write_text(
        json.dumps(
            {
                "name": "Research agent",
                "system": "Use the revised instructions.",
                "model": {"modelId": "model-1"},
                "tools": [{"toolId": "tool-1"}],
            }
        )
    )
    applied_payload = {
        "operationId": "op-profile",
        "status": "succeeded",
        "profileRevision": 8,
        "runtimeRevision": '"runtime-8"',
    }
    with _bff_server(
        status=202,
        payload=applied_payload,
        headers={"ETag": '"runtime-8"'},
    ) as (studio_url, apply_requests):
        apply_result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "profile",
                "apply",
                "--mpa-instance-id",
                "mi-123",
                "--runtime-id",
                "r-123",
                "--source-profile-id",
                "agent-123",
                "--profile",
                str(profile_file),
                "--runtime-revision",
                '"runtime-7"',
                "--idempotency-key",
                "profile-mi-123-8",
            ],
        )

    assert status_result.exit_code == apply_result.exit_code == 0
    assert json.loads(status_result.output)["etag"] == '"runtime-7"'
    assert json.loads(apply_result.output)["etag"] == '"runtime-8"'
    assert status_requests[0]["path"] == (
        "/web/mpa/agents/mi-123/profile-status?runtimeId=r-123&region=cn-beijing"
    )
    assert apply_requests[0]["method"] == "PUT"
    assert apply_requests[0]["path"] == "/web/mpa/agents/mi-123/profile"
    assert apply_requests[0]["idempotency_key"] == "profile-mi-123-8"
    assert apply_requests[0]["body"]["runtimeRevision"] == '"runtime-7"'
    assert apply_requests[0]["body"]["profile"]["tools"] == [{"toolId": "tool-1"}]


def test_session_config_commands_enforce_cas_and_profile_upgrade(tmp_path) -> None:
    config = {
        "appName": "app-1",
        "sessionId": "session-1",
        "revision": 3,
        "mpaInstanceId": "mi-123",
        "profileRevision": 7,
        "profileDefaultRevision": 8,
    }
    with _bff_server(payload=config, headers={"ETag": '"config-3"'}) as (
        studio_url,
        get_requests,
    ):
        get_result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "session",
                "config-get",
                "--session-id",
                "session-1",
                "--runtime-id",
                "r-123",
            ],
        )

    changes_file = tmp_path / "changes.json"
    changes_file.write_text(
        json.dumps(
            [
                {
                    "category": "model",
                    "mode": "replace",
                    "value": {"modelId": "model-2"},
                }
            ]
        )
    )
    patched = {**config, "revision": 4}
    with _bff_server(payload=patched, headers={"ETag": '"config-4"'}) as (
        studio_url,
        patch_requests,
    ):
        patch_result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "session",
                "config-patch",
                "--session-id",
                "session-1",
                "--runtime-id",
                "r-123",
                "--etag",
                '"config-3"',
                "--changes",
                str(changes_file),
            ],
        )

    upgraded = {**config, "revision": 5, "profileRevision": 8}
    with _bff_server(payload=upgraded, headers={"ETag": '"config-5"'}) as (
        studio_url,
        upgrade_requests,
    ):
        upgrade_result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "session",
                "profile-upgrade",
                "--session-id",
                "session-1",
                "--runtime-id",
                "r-123",
                "--etag",
                '"config-4"',
                "--target-profile-revision",
                "8",
                "--idempotency-key",
                "upgrade-session-1-profile-8",
            ],
        )

    assert (
        get_result.exit_code == patch_result.exit_code == upgrade_result.exit_code == 0
    )
    assert json.loads(get_result.output)["etag"] == '"config-3"'
    assert get_requests[0]["path"] == (
        "/web/mpa/sessions/session-1/execution-config?runtimeId=r-123&region=cn-beijing"
    )
    assert patch_requests[0]["method"] == "PATCH"
    assert patch_requests[0]["if_match"] == '"config-3"'
    assert patch_requests[0]["body"]["changes"][0]["category"] == "model"
    assert upgrade_requests[0]["method"] == "POST"
    assert upgrade_requests[0]["if_match"] == '"config-4"'
    assert upgrade_requests[0]["idempotency_key"] == ("upgrade-session-1-profile-8")
    assert upgrade_requests[0]["body"]["targetProfileRevision"] == 8


def test_delete_preview_is_read_only_and_reports_blockers() -> None:
    preview = {
        "mpaInstanceId": "mi-123",
        "bindingStatus": "bound",
        "canDelete": False,
        "blockers": ["active_sessions"],
        "sessionCounts": {"active": 1},
        "activeSessions": [{"sessionId": "session-1"}],
        "cleanupPlan": [],
    }
    with _bff_server(payload=preview) as (studio_url, requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "delete-preview",
                "--mpa-instance-id",
                "mi-123",
                "--runtime-id",
                "r-123",
            ],
        )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output)["blockers"] == ["active_sessions"]
    assert requests[0]["method"] == "GET"
    assert requests[0]["path"] == (
        "/web/mpa/agents/mi-123/delete-preview?runtimeId=r-123&region=cn-beijing"
    )


@pytest.mark.parametrize(
    ("status", "detail", "expected_code", "expected_exit"),
    [
        (401, {"code": "authentication_required"}, "authentication_required", 3),
        (403, {"code": "runtime_action_forbidden"}, "runtime_action_forbidden", 3),
        (409, {"code": "idempotency_mismatch"}, "idempotency_mismatch", 4),
        (
            412,
            {
                "code": "profile_changed",
                "currentState": {"profileRevision": 8},
            },
            "profile_changed",
            4,
        ),
        (428, {"code": "precondition_required"}, "precondition_required", 4),
        (503, {"code": "control_plane_unavailable"}, "control_plane_unavailable", 5),
        (500, "private upstream failure with secret material", "http_500", 5),
        (404, {"code": "mpa_agent_not_found"}, "mpa_agent_not_found", 1),
    ],
)
def test_control_plane_errors_are_redacted_json_with_stable_exit_codes(
    status: int, detail: Any, expected_code: str, expected_exit: int
) -> None:
    with _bff_server(
        status=status,
        payload={"detail": detail},
        headers={"X-Request-Id": "request-123"},
    ) as (studio_url, _requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "view",
                "--mpa-instance-id",
                "mi-123",
            ],
        )

    assert result.exit_code == expected_exit
    payload = json.loads(result.output)
    assert payload["error"]["code"] == expected_code
    assert payload["error"]["statusCode"] == status
    assert payload["error"]["requestId"] == "request-123"
    assert payload["error"]["retryable"] is (status >= 500)
    assert "private upstream failure" not in result.output


def test_view_uses_controlled_environment_and_reports_old_runtime_read_only() -> None:
    view = {
        "mpaInstanceId": "mi-old",
        "bindingStatus": "unsupported_runtime",
        "capabilities": {
            "canRead": True,
            "canWrite": False,
            "canDebug": False,
        },
        "safeError": {"code": "runtime_capability_unsupported"},
    }
    with _bff_server(payload=view) as (studio_url, requests):
        result = CliRunner().invoke(
            cli_mpa.mpa,
            ["control", "view", "--mpa-instance-id", "mi-old"],
            env={
                "VEADK_MPA_STUDIO_URL": studio_url,
                "VEADK_MPA_STUDIO_TOKEN": "environment-bearer",
            },
        )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["bindingStatus"] == "unsupported_runtime"
    assert output["capabilities"]["canWrite"] is False
    assert requests[0]["authorization"] == "Bearer environment-bearer"
    assert "environment-bearer" not in result.output


def test_timeout_retry_reuses_the_caller_persisted_idempotency_key(tmp_path) -> None:
    request_file = tmp_path / "create.json"
    request_file.write_text(
        json.dumps(
            {
                "operationKind": "create",
                "runtimeId": "r-123",
                "sourceProfileId": "agent-123",
                "profile": {
                    "name": "Research agent",
                    "system": "Research carefully.",
                    "model": {"modelId": "model-1"},
                },
            }
        )
    )
    operation = {
        "operationId": "op-replayed",
        "operationKind": "create",
        "stage": "accepted",
        "status": "pending",
    }
    key = "create-mi-123-profile-7"
    with _bff_server(status=202, payload=operation, first_response_delay=0.2) as (
        studio_url,
        requests,
    ):
        command = [
            "control",
            "--studio-url",
            studio_url,
            "create",
            "--request",
            str(request_file),
            "--idempotency-key",
            key,
        ]
        timed_out = CliRunner().invoke(
            cli_mpa.mpa,
            [
                "control",
                "--studio-url",
                studio_url,
                "--timeout",
                "0.05",
                *command[3:],
            ],
        )
        deadline = time.monotonic() + 1
        while not requests and time.monotonic() < deadline:
            time.sleep(0.01)
        assert requests, "the BFF must observe the write before timeout replay"
        replayed = CliRunner().invoke(cli_mpa.mpa, command)

    assert timed_out.exit_code == 5
    assert json.loads(timed_out.output)["error"]["code"] == ("control_plane_timeout")
    assert replayed.exit_code == 0, replayed.output
    assert json.loads(replayed.output)["operationId"] == "op-replayed"
    assert [request["idempotency_key"] for request in requests] == [key, key]
