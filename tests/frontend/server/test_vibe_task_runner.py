from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from frontend.server.vibe_task.runner import (
    CommandResult,
    CompletionGates,
    build_context_prompt,
    invoke_succeeded,
    logs_have_blockers,
    may_start_cloud_attempt,
    redacted_evidence,
    runtime_is_ready,
    validate_runtime_name,
    validation_policy,
)


def test_cloud_attempt_limits_rounds_and_remaining_time() -> None:
    now = datetime.now(timezone.utc)
    assert may_start_cloud_attempt(
        attempt=0, now=now, expires_at=now + timedelta(hours=1)
    ).allowed
    assert not may_start_cloud_attempt(
        attempt=3, now=now, expires_at=now + timedelta(hours=1)
    ).allowed
    decision = may_start_cloud_attempt(
        attempt=1, now=now, expires_at=now + timedelta(minutes=29)
    )
    assert not decision.allowed
    assert "30 minutes" in decision.reason


def test_context_expresses_terminal_contract() -> None:
    prompt = build_context_prompt(
        goal="build",
        summary={"goal": "build"},
        versions={"ak": "0.52.1"},
        evidence=[],
        attempt=1,
        expires_at="later",
    )
    assert "Context over Control" in prompt
    assert "intent-summary.json" in prompt
    assert "do not create evaluation resources" in prompt


def test_validation_policy_separates_typed_argv_steps() -> None:
    policy = validation_policy(
        runtime_name="vibe-task-a1b2c3", project_root="/home/gem/work space"
    )

    assert policy.project_root == "/home/gem/work space"
    assert policy.local_steps[0].argv == (
        "python",
        "-m",
        "compileall",
        "-q",
        ".",
    )
    assert all(step.stage == "local" for step in policy.local_steps)
    assert all(step.stage == "cloud" for step in policy.cloud_steps)
    assert all(
        isinstance(step.argv, tuple) for step in policy.local_steps + policy.cloud_steps
    )
    assert ("ak", "deploy", "build") in (step.argv for step in policy.cloud_steps)
    assert (
        "ak",
        "invoke",
        "vibe-task-a1b2c3",
        "--message",
        "VIBE_VALIDATION_SMOKE",
        "--json",
    ) in (step.argv for step in policy.cloud_steps)
    assert not any(
        "eval" in argument.lower()
        for step in policy.local_steps + policy.cloud_steps
        for argument in step.argv
    )


@pytest.mark.parametrize(
    "runtime_name",
    [
        "Uppercase",
        "-leading",
        "trailing-",
        "has spaces",
        "has_underscore",
        "a" * 65,
        "",
    ],
)
def test_runtime_name_rejects_noncanonical_values(runtime_name: str) -> None:
    with pytest.raises(ValueError, match="runtime name"):
        validate_runtime_name(runtime_name)


def test_validation_policy_requires_absolute_project_root() -> None:
    with pytest.raises(ValueError, match="absolute"):
        validation_policy(runtime_name="runtime-1", project_root="relative/path")


def test_evidence_redacts_values_assignments_bearer_and_jwt() -> None:
    secret = "actual-super-secret"
    jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
    result = CommandResult(
        1,
        stdout=(
            f'api={secret} API_TOKEN=other-secret Authorization: auth-secret '
            '{"accessToken":"json-secret","secretAccessKey":"json-access"}'
        ),
        stderr=f"Bearer bearer-token response token: {jwt}",
    )

    evidence = redacted_evidence(result, secrets=(secret,), limit=1_000)

    combined = f"{evidence['stdout']} {evidence['stderr']}"
    assert secret not in combined
    assert "other-secret" not in combined
    assert "auth-secret" not in combined
    assert "json-secret" not in combined
    assert "json-access" not in combined
    assert "bearer-token" not in combined
    assert jwt not in combined
    assert "API_TOKEN=<redacted>" in evidence["stdout"]
    assert "Authorization: <redacted>" in evidence["stdout"]
    assert "Bearer <redacted>" in evidence["stderr"]
    assert evidence["exit_code"] == 1


def test_evidence_bounds_output_after_redaction() -> None:
    evidence = redacted_evidence(CommandResult(0, stdout="x" * 200), limit=20)
    assert evidence["stdout"] == "x" * 20


def test_parse_helpers_fail_closed() -> None:
    assert runtime_is_ready(CommandResult(0, stdout='{"status": "Ready"}'))
    assert runtime_is_ready(CommandResult(0, stdout='{"status": {"phase": "Ready"}}'))
    assert not runtime_is_ready(CommandResult(0, stdout='{"status": "Pending"}'))
    assert not runtime_is_ready(CommandResult(1, stdout='{"status": "Ready"}'))
    assert not runtime_is_ready(CommandResult(0, stdout="not-json"))

    assert invoke_succeeded(CommandResult(0, stdout='{"success": true}'))
    assert invoke_succeeded(CommandResult(0, stdout='{"status": "succeeded"}'))
    assert not invoke_succeeded(CommandResult(0, stdout='{"success": false}'))
    assert not invoke_succeeded(CommandResult(1, stdout='{"success": true}'))

    assert not logs_have_blockers(CommandResult(0, stdout="request completed"))
    assert logs_have_blockers(CommandResult(0, stderr="Traceback: startup failed"))
    assert logs_have_blockers(CommandResult(1, stdout=""))


def test_completion_requires_every_gate() -> None:
    complete = CompletionGates(True, True, True, True, True, True)
    assert complete.completed

    values = [True] * 6
    for index in range(len(values)):
        incomplete = values.copy()
        incomplete[index] = False
        assert not CompletionGates(*incomplete).completed
