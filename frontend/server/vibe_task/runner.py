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
from pathlib import PurePath
import re
from typing import Literal, Protocol

from .models import (
    INTENT_SUMMARY_PATH,
    MAX_CLOUD_ATTEMPTS,
    MIN_CLOUD_ATTEMPT_REMAINING_SECONDS,
)


class CommandRunner(Protocol):
    def run(
        self, command: tuple[str, ...], *, cwd: str, timeout: int
    ) -> "CommandResult": ...


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


@dataclass(frozen=True)
class ValidationStep:
    name: str
    argv: tuple[str, ...]
    stage: Literal["local", "cloud"]
    timeout: int


@dataclass(frozen=True)
class ValidationPolicy:
    project_root: str
    local_steps: tuple[ValidationStep, ...]
    cloud_steps: tuple[ValidationStep, ...]


@dataclass(frozen=True)
class CompletionGates:
    local_ok: bool
    build_ok: bool
    runtime_ready: bool
    invoke_ok: bool
    logs_checked: bool
    artifact_ready: bool

    @property
    def completed(self) -> bool:
        return all(
            (
                self.local_ok,
                self.build_ok,
                self.runtime_ready,
                self.invoke_ok,
                self.logs_checked,
                self.artifact_ready,
            )
        )


_RUNTIME_NAME = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?\Z")
_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:AUTHORIZATION|"
    r"[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z0-9_]*"
    r")[\"']?)(\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)([\"']?)"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"
    r"(?![A-Za-z0-9_-])"
)
_BLOCKING_LOG = re.compile(
    r"(?i)(traceback|\b(?:fatal|panic)\b|\b(?:error|exception)\b|"
    r"authentication failed|permission denied|crashloop|out of memory)"
)


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


def validate_runtime_name(runtime_name: str) -> str:
    if not _RUNTIME_NAME.fullmatch(runtime_name):
        raise ValueError(
            "runtime name must be 1-64 lowercase letters, digits, or hyphens, "
            "and must start and end with a letter or digit"
        )
    return runtime_name


def validation_policy(*, runtime_name: str, project_root: str) -> ValidationPolicy:
    target = validate_runtime_name(runtime_name)
    if not project_root or not PurePath(project_root).is_absolute():
        raise ValueError("project root must be an absolute path")

    local_steps = (
        ValidationStep(
            "compile", ("python", "-m", "compileall", "-q", "."), "local", 120
        ),
    )
    cloud_steps = (
        ValidationStep(
            "deploy-config",
            (
                "ak",
                "config",
                "--runtime_name",
                target,
            ),
            "cloud",
            120,
        ),
        ValidationStep("deploy-build", ("ak", "build"), "cloud", 1_800),
        ValidationStep("deploy-apply", ("ak", "deploy"), "cloud", 900),
        ValidationStep(
            "runtime-ready", ("ak", "runtime", "show", target, "--json"), "cloud", 120
        ),
        ValidationStep(
            "invoke",
            (
                "ak",
                "invoke",
                "run",
                "VIBE_VALIDATION_SMOKE",
                "--config-file",
                "agentkit.yaml",
                "--raw",
            ),
            "cloud",
            300,
        ),
        ValidationStep(
            "logs",
            ("ak", "runtime", "logs", target, "--limit", "200", "--json"),
            "cloud",
            120,
        ),
    )
    return ValidationPolicy(project_root, local_steps, cloud_steps)


def parse_json_result(result: CommandResult) -> object | None:
    if not result.succeeded:
        return None
    try:
        return json.loads(result.stdout)
    except (json.JSONDecodeError, TypeError):
        return None


def runtime_is_ready(result: CommandResult) -> bool:
    payload = parse_json_result(result)
    if not isinstance(payload, dict):
        return False
    status = payload.get("status")
    if isinstance(status, dict):
        status = status.get("phase") or status.get("state")
    return status == "Ready"


def invoke_succeeded(result: CommandResult) -> bool:
    payload = parse_json_result(result)
    if isinstance(payload, str):
        return bool(payload.strip())
    if not isinstance(payload, dict):
        return False
    if payload.get("success") is True:
        return True
    return payload.get("status") in {"success", "succeeded", "Success", "Succeeded"}


def logs_have_blockers(result: CommandResult) -> bool:
    if not result.succeeded:
        return True
    return _BLOCKING_LOG.search(f"{result.stdout}\n{result.stderr}") is not None


def redacted_evidence(
    result: CommandResult, *, secrets: tuple[str, ...] = (), limit: int = 8_000
) -> dict[str, object]:
    if limit < 0:
        raise ValueError("limit must not be negative")

    def clean(value: str) -> str:
        for secret in sorted((item for item in secrets if item), key=len, reverse=True):
            value = value.replace(secret, "<redacted>")
        value = _ASSIGNMENT.sub(r"\1\2\3<redacted>\5", value)
        value = _BEARER.sub("Bearer <redacted>", value)
        value = _JWT.sub("<redacted>", value)
        return value[-limit:] if limit else ""

    return {
        "exit_code": result.exit_code,
        "stdout": clean(result.stdout),
        "stderr": clean(result.stderr),
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
