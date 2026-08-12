from __future__ import annotations

from datetime import datetime, timedelta, timezone

from frontend.server.vibe_task.runner import (
    CommandResult,
    build_codex_command,
    build_context_prompt,
    may_start_cloud_attempt,
    redacted_evidence,
    validation_commands,
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


def test_context_and_commands_express_terminal_contract() -> None:
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
    command = build_codex_command(prompt, workspace="/home/gem/work space")
    assert "codex exec" in command
    assert "'/home/gem/work space'" in command
    commands = validation_commands("runtime-name")
    assert any("ak deploy build" in item for item in commands)
    assert any("ak invoke runtime-name" in item for item in commands)
    assert all("eval" not in item for item in commands)


def test_evidence_redacts_secret_markers_and_bounds_output() -> None:
    result = CommandResult(
        1,
        stdout="VOLCENGINE_ACCESS_KEY=value",
        stderr="Authorization=token",
    )
    evidence = redacted_evidence(result, limit=100)
    assert "VOLCENGINE_ACCESS_KEY" not in evidence["stdout"]
    assert "Authorization" not in evidence["stderr"]
    assert evidence["exit_code"] == 1
