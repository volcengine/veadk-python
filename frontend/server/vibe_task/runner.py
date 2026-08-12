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

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import shlex
from typing import Protocol

from .models import (
    INTENT_SUMMARY_PATH,
    MAX_CLOUD_ATTEMPTS,
    MIN_CLOUD_ATTEMPT_REMAINING_SECONDS,
)


class CommandRunner(Protocol):
    def run(self, command: str, *, cwd: str, timeout: int) -> "CommandResult": ...


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class ValidationDecision:
    allowed: bool
    reason: str = ""


def may_start_cloud_attempt(
    *, attempt: int, now: datetime, expires_at: datetime
) -> ValidationDecision:
    if attempt >= MAX_CLOUD_ATTEMPTS:
        return ValidationDecision(False, "cloud attempt limit reached")
    remaining = (expires_at - now).total_seconds()
    if remaining < MIN_CLOUD_ATTEMPT_REMAINING_SECONDS:
        return ValidationDecision(False, "less than 30 minutes remain")
    return ValidationDecision(True)


def build_context_prompt(
    *,
    goal: str,
    summary: dict[str, object],
    versions: dict[str, str],
    evidence: list[dict[str, object]],
    attempt: int,
    expires_at: str,
) -> str:
    package = {
        "goal": goal,
        "intent_summary_path": INTENT_SUMMARY_PATH,
        "intent_summary": summary,
        "versions": versions,
        "recent_evidence": evidence[-10:],
        "cloud_attempt": attempt,
        "max_cloud_attempts": MAX_CLOUD_ATTEMPTS,
        "sandbox_expires_at": expires_at,
        "hard_gates": [
            "never expose credentials",
            "do not create evaluation resources",
            "cloud completion requires Ready, invoke, logs, and Artifact",
            "do not modify a production Runtime",
        ],
    }
    return (
        "Use Context over Control. Plan and adapt best effort from this Context Package. "
        "Maintain the Intent Summary atomically at its fixed path.\n"
        + json.dumps(package, ensure_ascii=False, indent=2)
    )


def build_codex_command(prompt: str, *, workspace: str) -> str:
    return " ".join(
        [
            "codex",
            "exec",
            "--ephemeral",
            "--skip-git-repo-check",
            "--sandbox",
            "workspace-write",
            "--json",
            "--cwd",
            shlex.quote(workspace),
            shlex.quote(prompt),
        ]
    )


def validation_commands(runtime_name: str) -> tuple[str, ...]:
    target = shlex.quote(runtime_name)
    return (
        "python -m compileall -q .",
        "ak deploy config --force",
        "ak deploy build",
        "ak deploy apply",
        f"ak runtime show {target} --json",
        f"ak invoke {target} --message 'VIBE_VALIDATION_SMOKE' --json",
        f"ak runtime logs {target} --limit 200 --json",
    )


def redacted_evidence(result: CommandResult, *, limit: int = 8_000) -> dict[str, object]:
    def clean(value: str) -> str:
        for marker in (
            "VOLCENGINE_ACCESS_KEY",
            "VOLCENGINE_SECRET_KEY",
            "Authorization",
        ):
            value = value.replace(marker, "<redacted>")
        return value[-limit:]

    return {
        "exit_code": result.exit_code,
        "stdout": clean(result.stdout),
        "stderr": clean(result.stderr),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
