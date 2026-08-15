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

"""Foreground verification and immutable delivery for an owned Dev Session.

This module deliberately has no task repository, event replay, or background-job
API. One caller owns one foreground invocation and supplies the already-authorized
Dev Session plus a fresh Studio credential resolver.
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import re
import shlex
from typing import Literal, Protocol
from uuid import uuid4

from .sandbox_remote import SandboxRemoteTransport


RELEASE_ROOT = "/home/gem/.intelligent-development/releases"
CURRENT_POINTER = "/home/gem/.intelligent-development/published.json"
_MAX_EVIDENCE_CHARS = 8_000
_MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_SAFE_SEGMENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_RUNTIME_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,62}[a-z0-9])?$")
_ARCHIVE = re.compile(
    r"Project archive created:\s*(?P<path>/tmp/[^\s/]+/[A-Za-z0-9._-]+\.tar\.gz)"
)
_ASSIGNMENT = re.compile(
    r"(?i)([\"']?(?:[A-Z][A-Z0-9_]*(?:KEY|SECRET|TOKEN|PASSWORD|CREDENTIAL)[A-Z0-9_]*)[\"']?)"
    r"(\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)([\"']?)"
)
_AUTHORIZATION = re.compile(
    r"(?i)([\"']?AUTHORIZATION[\"']?\s*[:=]\s*)(?:Bearer\s+)?[^\s,;}]+"
)
_BEARER = re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]+")
_JWT = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+(?![A-Za-z0-9_-])"
)
_BLOCKING_LOG = re.compile(
    r"(?i)(traceback|\b(?:fatal|panic)\b|\b(?:error|exception)\b|"
    r"authentication failed|permission denied|crashloop|out of memory)"
)
_NOT_FOUND = re.compile(r"(?i)(not found|does not exist|404)")


class DevelopmentStage(StrEnum):
    LOCAL_COMPILE = "local_compile"
    CLOUD_CONFIG = "cloud_config"
    CLOUD_BUILD = "cloud_build"
    CLOUD_DEPLOY = "cloud_deploy"
    RUNTIME_TAG = "runtime_tag"
    RUNTIME_READY = "runtime_ready"
    RUNTIME_INVOKE = "runtime_invoke"
    RUNTIME_LOGS = "runtime_logs"
    ARTIFACT = "artifact"
    CLEANUP = "cleanup"
    DONE = "done"


class DevelopmentStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


@dataclass(frozen=True)
class DevSession:
    """Caller-authorized, fixed Sandbox session and project workspace."""

    owner_id: str
    session_id: str
    endpoint: str
    project_root: str

    def __post_init__(self) -> None:
        if not self.owner_id or len(self.owner_id) > 512:
            raise ValueError("Dev Session owner is invalid")
        if not _SAFE_SEGMENT.fullmatch(self.session_id):
            raise ValueError("Dev Session identity is invalid")
        if not self.endpoint.startswith("https://"):
            raise ValueError("Dev Session endpoint must use HTTPS")
        expected_prefix = "/home/gem/workspace/"
        if not self.project_root.startswith(expected_prefix):
            raise ValueError("Dev Session project root is invalid")
        leaf = self.project_root.removeprefix(expected_prefix)
        if not _SAFE_SEGMENT.fullmatch(leaf):
            raise ValueError("Dev Session project root is invalid")


@dataclass(frozen=True)
class StudioCredentials:
    access_key_id: str
    secret_access_key: str
    session_token: str | None = None

    def __post_init__(self) -> None:
        if not self.access_key_id or not self.secret_access_key:
            raise ValueError("Studio credentials are incomplete")
        if any("\x00" in value for value in self.secret_values):
            raise ValueError("Studio credentials are invalid")

    @property
    def secret_values(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (
                self.access_key_id,
                self.secret_access_key,
                self.session_token,
            )
            if value
        )

    def as_remote_json(self) -> bytes:
        return json.dumps(
            {
                "accessKeyId": self.access_key_id,
                "secretAccessKey": self.secret_access_key,
                "sessionToken": self.session_token,
            },
            separators=(",", ":"),
        ).encode()


@dataclass(frozen=True)
class VerificationCommand:
    name: str
    stage: DevelopmentStage
    argv: tuple[str, ...]
    timeout_seconds: int
    credential_scope: Literal["local", "cloud"]

    def __post_init__(self) -> None:
        if not self.name or not self.argv or self.timeout_seconds < 1:
            raise ValueError("Verification command is invalid")
        if any(not item or "\x00" in item for item in self.argv):
            raise ValueError("Verification command argv is invalid")


@dataclass(frozen=True)
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""

    @property
    def succeeded(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class StepReport:
    name: str
    stage: DevelopmentStage
    passed: bool
    exit_code: int
    stdout: str
    stderr: str
    recorded_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "stage": self.stage.value,
            "passed": self.passed,
            "exitCode": self.exit_code,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "recordedAt": self.recorded_at,
        }


@dataclass(frozen=True)
class DeliveryReference:
    artifact_sha256: str
    artifact_size: int
    validation_report_sha256: str
    session_id: str
    agent_name: str
    entry_point: str
    file_count: int
    validated_at: str
    gate_summary: tuple[str, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "sessionId": self.session_id,
            "artifactSha256": self.artifact_sha256,
            "artifactSize": self.artifact_size,
            "validationReportSha256": self.validation_report_sha256,
            "agentName": self.agent_name,
            "entryPoint": self.entry_point,
            "fileCount": self.file_count,
            "validatedAt": self.validated_at,
            "gateSummary": list(self.gate_summary),
        }


@dataclass(frozen=True)
class FailureReport:
    code: str
    stage: DevelopmentStage
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "stage": self.stage.value, "message": self.message}


@dataclass(frozen=True)
class DevelopmentEvent:
    sequence: int
    event_type: str
    stage: DevelopmentStage
    timestamp: str
    payload: Mapping[str, object] = field(default_factory=dict)

    def as_dict(self) -> dict[str, object]:
        return {
            "sequence": self.sequence,
            "eventType": self.event_type,
            "stage": self.stage.value,
            "timestamp": self.timestamp,
            "payload": dict(self.payload),
        }

    def as_sse(self) -> str:
        return (
            f"id: {self.sequence}\n"
            f"event: {self.event_type}\n"
            f"data: {json.dumps(self.as_dict(), ensure_ascii=False, separators=(',', ':'))}\n\n"
        )


@dataclass(frozen=True)
class DevelopmentResult:
    status: DevelopmentStatus
    events: tuple[DevelopmentEvent, ...]
    report: tuple[StepReport, ...]
    delivery: DeliveryReference | None = None
    failure: FailureReport | None = None


CredentialResolver = Callable[[], StudioCredentials]
EventSink = Callable[[DevelopmentEvent], Awaitable[None] | None]
Sleep = Callable[[float], Awaitable[None]]
Clock = Callable[[], datetime]


class RemoteTransport(Protocol):
    async def exec_json(
        self, command: str, *, timeout: int = 12
    ) -> dict[str, object]: ...

    async def exec_text(self, command: str, *, timeout: int = 12) -> str: ...

    async def upload(
        self,
        path: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        max_bytes: int = _MAX_ARTIFACT_BYTES,
        mode: int | None = None,
    ) -> None: ...


TransportFactory = Callable[[str], RemoteTransport]
RuntimeOperation = Callable[
    [str, str, StudioCredentials, tuple[str, ...]], Awaitable[CommandResult]
]


def verification_commands(
    runtime_name: str,
    *,
    owner_hash: str = "unknown",
    session_hash: str = "unknown",
) -> tuple[VerificationCommand, ...]:
    """Return the fixed typed AgentKit verification plan."""
    if not _RUNTIME_NAME.fullmatch(runtime_name):
        raise ValueError("Validation Runtime name is invalid")
    tags = json.dumps(
        [
            {"Key": "veadk:lifecycle", "Value": "validation"},
            {"Key": "veadk:owner-hash", "Value": owner_hash},
            {"Key": "veadk:session-hash", "Value": session_hash},
        ],
        separators=(",", ":"),
    )
    return (
        VerificationCommand(
            "compile",
            DevelopmentStage.LOCAL_COMPILE,
            ("python", "-m", "compileall", "-q", "."),
            120,
            "local",
        ),
        VerificationCommand(
            "service-contract",
            DevelopmentStage.LOCAL_COMPILE,
            (
                "python",
                "-c",
                "import pathlib,runpy,yaml; data=yaml.safe_load(pathlib.Path('agentkit.yaml').read_text()) or {}; entry=(data.get('common') or {}).get('entry_point','app.py'); runpy.run_path(entry,run_name='agentkit_validation')",
            ),
            120,
            "local",
        ),
        VerificationCommand(
            "ak-config",
            DevelopmentStage.CLOUD_CONFIG,
            ("ak", "config", "--runtime_name", runtime_name),
            120,
            "cloud",
        ),
        VerificationCommand(
            "ak-build",
            DevelopmentStage.CLOUD_BUILD,
            ("ak", "build"),
            1_800,
            "cloud",
        ),
        VerificationCommand(
            "ak-deploy",
            DevelopmentStage.CLOUD_DEPLOY,
            ("ak", "deploy"),
            900,
            "cloud",
        ),
        VerificationCommand(
            "runtime-tag",
            DevelopmentStage.RUNTIME_TAG,
            (
                "__studio_runtime__",
                "tag",
                runtime_name,
                tags,
            ),
            180,
            "cloud",
        ),
        VerificationCommand(
            "runtime-ready",
            DevelopmentStage.RUNTIME_READY,
            (
                "__studio_runtime__",
                "get",
                runtime_name,
            ),
            120,
            "cloud",
        ),
        VerificationCommand(
            "invoke",
            DevelopmentStage.RUNTIME_INVOKE,
            (
                "ak",
                "invoke",
                "run",
                "--payload",
                '{"messages":"INTELLIGENT_DEVELOPMENT_VALIDATION_SMOKE"}',
                "--config-file",
                "agentkit.yaml",
                "--raw",
            ),
            300,
            "cloud",
        ),
        VerificationCommand(
            "logs",
            DevelopmentStage.RUNTIME_LOGS,
            ("__studio_runtime__", "logs", runtime_name),
            120,
            "cloud",
        ),
    )


def redact(value: str, *, exact_secrets: Sequence[str] = ()) -> str:
    for secret in sorted(
        (item for item in exact_secrets if item), key=len, reverse=True
    ):
        value = value.replace(secret, "<redacted>")
    value = _AUTHORIZATION.sub(r"\1<redacted>", value)
    value = _ASSIGNMENT.sub(r"\1\2\3<redacted>\5", value)
    value = _BEARER.sub("Bearer <redacted>", value)
    value = _JWT.sub("<redacted>", value)
    return value[-_MAX_EVIDENCE_CHARS:]


def _runtime_ready(result: CommandResult) -> bool:
    if not result.succeeded:
        return False
    payload = _json_output(result.stdout)
    if not isinstance(payload, dict):
        return False
    status = payload.get("status") or payload.get("Status")
    if isinstance(status, dict):
        status = status.get("phase") or status.get("state") or status.get("Phase")
    return status == "Ready"


def _invoke_succeeded(result: CommandResult) -> bool:
    if not result.succeeded:
        return False
    for candidate in (result.stdout, *reversed(result.stdout.splitlines())):
        try:
            value = json.loads(candidate)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(value, str) and value.strip():
            return True
        if isinstance(value, dict) and (
            value.get("success") is True
            or value.get("status") in {"success", "succeeded", "Success", "Succeeded"}
        ):
            return True
    return False


def _json_output(value: str) -> object | None:
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        for line in reversed(value.splitlines()):
            try:
                return json.loads(line)
            except (TypeError, json.JSONDecodeError):
                continue
    return None


def _archive_path(result: CommandResult) -> str:
    if not result.succeeded:
        return ""
    matches = list(_ARCHIVE.finditer(result.stdout))
    return matches[-1].group("path") if matches else ""


def _runtime_name(session: DevSession, token: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", session.session_id.lower()).strip("-")
    normalized = normalized[:40].rstrip("-") or "dev"
    value = f"idv-{normalized}-{token}"
    if not _RUNTIME_NAME.fullmatch(value):
        raise ValueError("Validation Runtime name cannot be derived")
    return value


REMOTE_DELIVERY_WORKER = r"""import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import stat
import sys
import tarfile
import tempfile
import zipfile

ROOT = Path("/home/gem/.intelligent-development")
RELEASES = ROOT / "releases"
CURRENT = ROOT / "published.json"
MAX_BYTES = 20 * 1024 * 1024
MAX_FILES = 2000
ZIP_TIME = (1980, 1, 1, 0, 0, 0)

def fail(message):
    raise ValueError(message)

def atomic_json(path, value):
    fd, temporary = tempfile.mkstemp(prefix=".pointer-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.lexists(temporary):
            os.unlink(temporary)

def read_regular(path, expected_mode=None):
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            fail("Delivery input is not a regular file")
        if expected_mode is not None and stat.S_IMODE(metadata.st_mode) != expected_mode:
            fail("Delivery secret mode is invalid")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            return stream.read(MAX_BYTES + 1)
    finally:
        os.close(descriptor)

def zip_member(archive, name, content):
    info = zipfile.ZipInfo(name, ZIP_TIME)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (stat.S_IFREG | 0o644) << 16
    archive.writestr(info, content, compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

def main():
    if len(sys.argv) != 2:
        fail("Delivery request is invalid")
    request_path = Path(sys.argv[1])
    request = json.loads(read_regular(request_path).decode("utf-8"))
    if set(request) != {"projectRoot", "sourceArchive", "report", "secretPath"}:
        fail("Delivery request fields are invalid")
    project = request["projectRoot"]
    source = request["sourceArchive"]
    secret_path = Path(request["secretPath"])
    if not isinstance(project, str) or not project.startswith("/home/gem/workspace/"):
        fail("Delivery project is invalid")
    if not isinstance(source, str) or not source.startswith("/tmp/") or not source.endswith(".tar.gz"):
        fail("Delivery source archive is invalid")
    source_relative = PurePosixPath(source).relative_to("/tmp")
    if len(source_relative.parts) != 2 or any(part in {"", ".", ".."} for part in source_relative.parts):
        fail("Delivery source archive is invalid")
    try:
        secrets_value = json.loads(read_regular(secret_path, 0o600).decode("utf-8"))
    finally:
        secret_path.unlink(missing_ok=True)
    if not isinstance(secrets_value, list) or any(not isinstance(value, str) for value in secrets_value):
        fail("Delivery secrets are invalid")
    secrets = tuple(value.encode() for value in secrets_value if value)
    source_path = Path(source)
    try:
        resolved_source = source_path.resolve(strict=True)
        resolved_source.relative_to(Path("/tmp").resolve(strict=True))
        if resolved_source != source_path:
            fail("Delivery source archive is invalid")
    except (OSError, ValueError) as error:
        raise ValueError("Delivery source archive is unavailable") from error
    content = read_regular(source_path)
    if len(content) > MAX_BYTES:
        fail("Delivery source archive exceeds the limit")
    files = []
    total = 0
    try:
        with tarfile.open(fileobj=io.BytesIO(content), mode="r:gz") as source_tar:
            members = source_tar.getmembers()
            if len(members) > MAX_FILES:
                fail("Delivery source has too many files")
            for member in members:
                name = member.name
                relative = PurePosixPath(name)
                if not name or name.startswith(("/", "\\")) or "\\" in name or name != relative.as_posix() or any(part in {"", ".", ".."} for part in relative.parts) or not member.isfile():
                    fail("Delivery source contains an unsafe entry")
                total += member.size
                if member.size < 0 or total > MAX_BYTES:
                    fail("Delivery expanded source exceeds the limit")
                stream = source_tar.extractfile(member)
                if stream is None:
                    fail("Delivery source member cannot be read")
                member_content = stream.read(member.size + 1)
                if len(member_content) != member.size:
                    fail("Delivery source member size is invalid")
                if any(secret in member_content for secret in secrets):
                    fail("Delivery source contains supplied credentials")
                files.append((name, member_content))
    except (tarfile.TarError, OSError) as error:
        raise ValueError("Delivery source archive is invalid") from error
    ROOT.mkdir(mode=0o700, parents=True, exist_ok=True)
    RELEASES.mkdir(mode=0o700, parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".release-", dir=RELEASES))
    try:
        artifact = staging / "artifact.zip"
        with open(artifact, "w+b") as output:
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
                for name, member_content in files:
                    zip_member(archive, name, member_content)
            output.flush()
            os.fsync(output.fileno())
            size = output.tell()
        if size > MAX_BYTES:
            fail("Delivery artifact exceeds the limit")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        release = RELEASES / digest
        report = dict(request["report"])
        report["artifactGate"] = True
        report["artifactSha256"] = digest
        report_bytes = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        report_digest = hashlib.sha256(report_bytes).hexdigest()
        agentkit_yaml = next((content for name, content in files if name == "agentkit.yaml"), b"")
        try:
            import yaml
            manifest = yaml.safe_load(agentkit_yaml) if agentkit_yaml else {}
        except Exception as error:
            raise ValueError("Delivery agentkit.yaml is invalid") from error
        common = manifest.get("common", {}) if isinstance(manifest, dict) else {}
        if not isinstance(common, dict):
            fail("Delivery agentkit.yaml common is invalid")
        agent_name = common.get("agent_name") or common.get("name") or "agent"
        entry_point = common.get("entry_point") or "app.py"
        if not isinstance(agent_name, str) or not agent_name.strip():
            fail("Delivery agent name is invalid")
        if not isinstance(entry_point, str) or entry_point not in {name for name, _ in files}:
            fail("Delivery entry point is invalid")
        descriptor = {
            "sessionId": report.get("sessionId"),
            "artifactSha256": digest,
            "artifactSize": size,
            "agentName": agent_name.strip(),
            "entryPoint": entry_point,
            "fileCount": len(files),
            "artifactPath": str(release / "artifact.zip"),
            "descriptorPath": str(release / "descriptor.json"),
            "validationReportPath": str(release / "validation" / f"{report_digest}.json"),
            "validationReportSha256": report_digest,
            "releasePath": str(release),
        }
        report["agentName"] = descriptor["agentName"]
        report["entryPoint"] = descriptor["entryPoint"]
        report["fileCount"] = descriptor["fileCount"]
        report_bytes = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
        report_digest = hashlib.sha256(report_bytes).hexdigest()
        descriptor["validationReportSha256"] = report_digest
        descriptor["validationReportPath"] = str(
            release / "validation" / f"{report_digest}.json"
        )
        descriptor_bytes = (json.dumps(descriptor, sort_keys=True, separators=(",", ":")) + "\n").encode()
        validation_dir = staging / "validation"
        validation_dir.mkdir(mode=0o700)
        (validation_dir / f"{report_digest}.json").write_bytes(report_bytes)
        (staging / "descriptor.json").write_bytes(descriptor_bytes)
        for child in (artifact, staging / "descriptor.json", validation_dir / f"{report_digest}.json"):
            with open(child, "rb") as stream:
                os.fsync(stream.fileno())
        if release.exists():
            if (
                read_regular(release / "artifact.zip") != artifact.read_bytes()
                or read_regular(release / "descriptor.json") != descriptor_bytes
                or read_regular(release / "validation" / f"{report_digest}.json") != report_bytes
            ):
                fail("Immutable release conflicts with existing content")
        else:
            os.rename(staging, release)
        atomic_json(CURRENT, {
            "artifactSha256": digest,
            "validationReportSha256": report_digest,
            "releasePath": str(release),
        })
        print(json.dumps(descriptor, sort_keys=True, separators=(",", ":")))
    finally:
        if staging.exists():
            for child in sorted(staging.rglob("*"), reverse=True):
                if child.is_dir():
                    child.rmdir()
                else:
                    child.unlink()
            staging.rmdir()

if __name__ == "__main__":
    main()
"""


class IntelligentDevelopmentVerifier:
    """Run one foreground verification and delivery transaction."""

    def __init__(
        self,
        resolve_credentials: CredentialResolver,
        *,
        event_sink: EventSink | None = None,
        runtime_operation: RuntimeOperation | None = None,
        transport_factory: TransportFactory = SandboxRemoteTransport,
        ready_attempts: int = 20,
        ready_interval_seconds: float = 3.0,
        sleep: Sleep = asyncio.sleep,
        clock: Clock | None = None,
    ) -> None:
        if ready_attempts < 1 or ready_interval_seconds < 0:
            raise ValueError("Ready polling policy is invalid")
        self._resolve_credentials = resolve_credentials
        self._event_sink = event_sink
        self._runtime_operation = runtime_operation
        self._transport_factory = transport_factory
        self._ready_attempts = ready_attempts
        self._ready_interval_seconds = ready_interval_seconds
        self._sleep = sleep
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._events: list[DevelopmentEvent] = []

    async def run(self, *, owner_id: str, session: DevSession) -> DevelopmentResult:
        """Verify and deliver from the caller-owned session; never persists run state."""
        if owner_id != session.owner_id:
            raise PermissionError("Dev Session ownership does not match caller")
        self._events = []
        transport = self._transport_factory(session.endpoint)
        runtime_name = _runtime_name(session, uuid4().hex[:12])
        reports: list[StepReport] = []
        exact_secrets: set[str] = set()
        runtime_may_exist = False
        current_stage = DevelopmentStage.LOCAL_COMPILE
        failure: FailureReport | None = None
        delivery: DeliveryReference | None = None
        source_archive = ""
        try:
            await self._prepare_remote_root(transport)
            for command in verification_commands(
                runtime_name,
                owner_hash=hashlib.sha256(session.owner_id.encode()).hexdigest()[:32],
                session_hash=hashlib.sha256(session.session_id.encode()).hexdigest()[:32],
            ):
                current_stage = command.stage
                await self._emit(
                    "verification.stage.started", current_stage, {"name": command.name}
                )
                if command.name == "ak-deploy":
                    # A timeout or malformed response can still mean deploy reached the
                    # server. From this point cleanup must be attempted, fail closed.
                    runtime_may_exist = True
                if command.name == "runtime-ready":
                    result, report = await self._wait_ready(
                        transport, session, command, exact_secrets
                    )
                else:
                    result, report = await self._execute(
                        transport, session, command, exact_secrets
                    )
                reports.append(report)
                passed = self._passes(command, result)
                await self._emit(
                    "verification.step.finished",
                    current_stage,
                    {"name": command.name, "passed": passed},
                )
                if command.name == "ak-build":
                    source_archive = _archive_path(result)
                    passed = passed and bool(source_archive)
                    if passed != report.passed:
                        reports[-1] = self._report(
                            command, result, passed, exact_secrets
                        )
                if not passed:
                    evidence = reports[-1]
                    detail = evidence.stderr.strip() or evidence.stdout.strip()
                    failure = FailureReport(
                        "VERIFICATION_FAILED",
                        current_stage,
                        (
                            f"Required verification step failed: {command.name}"
                            + (f"\n{detail}" if detail else "")
                        )[:2_000],
                    )
                    break
            if failure is None:
                current_stage = DevelopmentStage.ARTIFACT
                await self._emit("delivery.started", current_stage)
                delivery = await self._publish(
                    transport,
                    session,
                    source_archive,
                    reports,
                    exact_secrets,
                    runtime_name,
                )
                await self._emit(
                    "delivery.published", current_stage, delivery.as_dict()
                )
        except asyncio.CancelledError:
            cleanup_failure = await self._cleanup_runtime(
                transport, session, runtime_name, runtime_may_exist, exact_secrets
            )
            if cleanup_failure is not None:
                raise RuntimeError(cleanup_failure.message)
            raise
        except Exception:
            failure = FailureReport(
                "INTELLIGENT_DEVELOPMENT_FAILED",
                current_stage,
                "Foreground verification could not be completed",
            )
        cleanup_failure = await self._cleanup_runtime(
            transport, session, runtime_name, runtime_may_exist, exact_secrets
        )
        if cleanup_failure is not None and failure is None:
            failure = cleanup_failure
            delivery = None
        if failure is not None:
            await self._emit(
                "development.failed", DevelopmentStage.DONE, failure.as_dict()
            )
            return DevelopmentResult(
                DevelopmentStatus.FAILED,
                tuple(self._events),
                tuple(reports),
                failure=failure,
            )
        await self._emit(
            "development.succeeded",
            DevelopmentStage.DONE,
            {"delivery": delivery.as_dict() if delivery else {}},
        )
        return DevelopmentResult(
            DevelopmentStatus.SUCCEEDED,
            tuple(self._events),
            tuple(reports),
            delivery=delivery,
        )

    async def _execute(
        self,
        transport: RemoteTransport,
        session: DevSession,
        command: VerificationCommand,
        exact_secrets: set[str],
    ) -> tuple[CommandResult, StepReport]:
        if command.argv[0] == "__studio_runtime__":
            if self._runtime_operation is None:
                raise RuntimeError("Studio Runtime operation is not configured")
            credentials = self._resolve_credentials()
            if not isinstance(credentials, StudioCredentials):
                raise TypeError("Credential resolver must return StudioCredentials")
            exact_secrets.update(credentials.secret_values)
            result = await self._runtime_operation(
                command.argv[1], command.argv[2], credentials, command.argv[3:]
            )
            passed = self._passes(command, result)
            return result, self._report(command, result, passed, exact_secrets)

        secret_path: str | None = None
        if command.credential_scope == "cloud":
            credentials = self._resolve_credentials()
            if not isinstance(credentials, StudioCredentials):
                raise TypeError("Credential resolver must return StudioCredentials")
            exact_secrets.update(credentials.secret_values)
            secret_path = (
                f"/home/gem/.intelligent-development/tmp/credentials-{uuid4().hex}.json"
            )
            try:
                await transport.upload(
                    secret_path,
                    credentials.as_remote_json(),
                    media_type="application/json",
                    mode=0o600,
                )
            except BaseException:
                await self._unlink(transport, secret_path)
                raise
        encoded = base64.b64encode(json.dumps(command.argv).encode()).decode()
        source = (
            "import base64,json,os,stat,subprocess\n"
            f"argv=json.loads(base64.b64decode({encoded!r}))\n"
            "env=os.environ.copy()\n"
            f"secret={secret_path!r}\n"
            "values={}\n"
            "if secret is not None:\n"
            " fd=os.open(secret,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))\n"
            " try:\n"
            "  metadata=os.fstat(fd)\n"
            "  if not stat.S_ISREG(metadata.st_mode) or stat.S_IMODE(metadata.st_mode)!=0o600: raise PermissionError('invalid credential file')\n"
            "  with os.fdopen(fd,encoding='utf-8',closefd=False) as stream: values=json.load(stream)\n"
            " finally:\n"
            "  os.close(fd)\n"
            "  os.unlink(secret)\n"
            "env.update({key:value for key,value in {"
            "'VOLCENGINE_ACCESS_KEY':values.get('accessKeyId'),"
            "'VOLCENGINE_SECRET_KEY':values.get('secretAccessKey'),"
            "'VOLCENGINE_SESSION_TOKEN':values.get('sessionToken'),"
            "'BYTEPLUS_ACCESS_KEY':values.get('accessKeyId'),"
            "'BYTEPLUS_SECRET_KEY':values.get('secretAccessKey'),"
            "'BYTEPLUS_SESSION_TOKEN':values.get('sessionToken')}.items() if value})\n"
            f"result=subprocess.run(argv,cwd={session.project_root!r},env=env,capture_output=True,text=True,timeout={command.timeout_seconds!r},check=False)\n"
            "print(json.dumps({'exitCode':result.returncode,'stdout':result.stdout,'stderr':result.stderr},ensure_ascii=False))\n"
        )
        try:
            value = await transport.exec_json(
                f"python3 -c {shlex.quote(source)}",
                timeout=command.timeout_seconds + 10,
            )
        finally:
            if secret_path is not None:
                await self._unlink(transport, secret_path)
        result = self._command_result(value)
        passed = self._passes(command, result)
        return result, self._report(command, result, passed, exact_secrets)

    async def _wait_ready(
        self,
        transport: RemoteTransport,
        session: DevSession,
        command: VerificationCommand,
        exact_secrets: set[str],
    ) -> tuple[CommandResult, StepReport]:
        result = CommandResult(1)
        for attempt in range(self._ready_attempts):
            result, report = await self._execute(
                transport, session, command, exact_secrets
            )
            if report.passed:
                return result, report
            if attempt + 1 < self._ready_attempts:
                await self._sleep(self._ready_interval_seconds)
        return result, report

    @staticmethod
    def _command_result(value: Mapping[str, object]) -> CommandResult:
        exit_code = value.get("exitCode")
        stdout = value.get("stdout", "")
        stderr = value.get("stderr", "")
        if (
            isinstance(exit_code, bool)
            or not isinstance(exit_code, int)
            or not isinstance(stdout, str)
            or not isinstance(stderr, str)
        ):
            raise ValueError("Verification command returned an invalid result")
        return CommandResult(exit_code, stdout, stderr)

    @staticmethod
    def _passes(command: VerificationCommand, result: CommandResult) -> bool:
        if command.name == "runtime-ready":
            return _runtime_ready(result)
        if command.name == "invoke":
            return _invoke_succeeded(result)
        if command.name == "logs":
            return (
                result.succeeded
                and _BLOCKING_LOG.search(f"{result.stdout}\n{result.stderr}") is None
            )
        return result.succeeded

    def _report(
        self,
        command: VerificationCommand,
        result: CommandResult,
        passed: bool,
        exact_secrets: set[str],
    ) -> StepReport:
        return StepReport(
            command.name,
            command.stage,
            passed,
            result.exit_code,
            redact(result.stdout, exact_secrets=tuple(exact_secrets)),
            redact(result.stderr, exact_secrets=tuple(exact_secrets)),
            self._clock().isoformat(),
        )

    async def _publish(
        self,
        transport: RemoteTransport,
        session: DevSession,
        source_archive: str,
        reports: Sequence[StepReport],
        exact_secrets: set[str],
        runtime_name: str,
    ) -> DeliveryReference:
        if not source_archive:
            raise ValueError("Verified build archive is unavailable")
        token = uuid4().hex
        root = "/home/gem/.intelligent-development/tmp"
        worker_path = f"{root}/delivery-{token}.py"
        request_path = f"{root}/delivery-{token}.json"
        secret_path = f"{root}/delivery-secrets-{token}.json"
        report = {
            "status": "passed",
            "sessionId": session.session_id,
            "validatedAt": self._clock().isoformat(),
            "runtimeNameHash": hashlib.sha256(runtime_name.encode()).hexdigest(),
            "steps": [item.as_dict() for item in reports],
        }
        request = {
            "projectRoot": session.project_root,
            "sourceArchive": source_archive,
            "report": report,
            "secretPath": secret_path,
        }
        await transport.upload(
            worker_path, REMOTE_DELIVERY_WORKER.encode(), media_type="text/x-python"
        )
        await transport.upload(
            request_path,
            json.dumps(request, separators=(",", ":")).encode(),
            media_type="application/json",
        )
        try:
            await transport.upload(
                secret_path,
                json.dumps(sorted(exact_secrets), separators=(",", ":")).encode(),
                media_type="application/json",
                mode=0o600,
            )
            value = await transport.exec_json(
                f"python3 {shlex.quote(worker_path)} {shlex.quote(request_path)}",
                timeout=180,
            )
            return self._delivery_reference(value, session, reports)
        finally:
            await self._unlink(transport, secret_path)
            await self._unlink(transport, request_path)
            await self._unlink(transport, worker_path)

    def _delivery_reference(
        self,
        value: Mapping[str, object],
        session: DevSession,
        reports: Sequence[StepReport],
    ) -> DeliveryReference:
        digest = value.get("artifactSha256")
        size = value.get("artifactSize")
        if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
            raise ValueError("Delivery descriptor digest is invalid")
        if (
            isinstance(size, bool)
            or not isinstance(size, int)
            or not 0 <= size <= _MAX_ARTIFACT_BYTES
        ):
            raise ValueError("Delivery descriptor size is invalid")
        release = f"{RELEASE_ROOT}/{digest}"
        expected = {
            "releasePath": release,
            "artifactPath": f"{release}/artifact.zip",
            "descriptorPath": f"{release}/descriptor.json",
            "validationReportPath": f"{release}/validation/{value.get('validationReportSha256')}.json",
        }
        if any(value.get(key) != path for key, path in expected.items()):
            raise ValueError("Delivery descriptor path is invalid")
        report_digest = value.get("validationReportSha256")
        agent_name = value.get("agentName")
        entry_point = value.get("entryPoint")
        file_count = value.get("fileCount")
        if (
            not isinstance(report_digest, str)
            or re.fullmatch(r"[0-9a-f]{64}", report_digest) is None
            or not isinstance(agent_name, str)
            or not agent_name.strip()
            or not isinstance(entry_point, str)
            or not entry_point
            or isinstance(file_count, bool)
            or not isinstance(file_count, int)
            or file_count < 1
        ):
            raise ValueError("Delivery descriptor metadata is invalid")
        return DeliveryReference(
            digest,
            size,
            report_digest,
            session.session_id,
            agent_name.strip(),
            entry_point,
            file_count,
            self._clock().isoformat(),
            tuple(item.name for item in reports if item.passed),
        )

    async def _cleanup_runtime(
        self,
        transport: RemoteTransport,
        session: DevSession,
        runtime_name: str,
        runtime_may_exist: bool,
        exact_secrets: set[str],
    ) -> FailureReport | None:
        task = asyncio.create_task(
            self._cleanup_runtime_once(
                transport, session, runtime_name, runtime_may_exist, exact_secrets
            )
        )
        try:
            return await asyncio.shield(task)
        except asyncio.CancelledError:
            try:
                await asyncio.shield(task)
            except BaseException:
                task.cancel()
            raise

    async def _cleanup_runtime_once(
        self,
        transport: RemoteTransport,
        session: DevSession,
        runtime_name: str,
        runtime_may_exist: bool,
        exact_secrets: set[str],
    ) -> FailureReport | None:
        await self._emit("validation-runtime.cleanup.started", DevelopmentStage.CLEANUP)
        if not runtime_may_exist:
            await self._emit(
                "validation-runtime.cleanup.finished",
                DevelopmentStage.CLEANUP,
                {"deleted": False},
            )
            return None
        command = VerificationCommand(
            "runtime-delete",
            DevelopmentStage.CLEANUP,
            ("__studio_runtime__", "delete", runtime_name),
            180,
            "cloud",
        )
        result: CommandResult | None = None
        for attempt in range(3):
            try:
                result, _ = await self._execute(
                    transport, session, command, exact_secrets
                )
            except Exception:
                result = None
            if result is not None and (
                result.succeeded
                or _NOT_FOUND.search(f"{result.stdout}\n{result.stderr}") is not None
            ):
                break
            if attempt < 2:
                await self._sleep(min(2**attempt, 2))
        if result is None:
            return FailureReport(
                "VALIDATION_RUNTIME_CLEANUP_FAILED",
                DevelopmentStage.CLEANUP,
                "Validation Runtime cleanup could not be confirmed",
            )
        deleted = result.succeeded
        absent = _NOT_FOUND.search(f"{result.stdout}\n{result.stderr}") is not None
        await self._emit(
            "validation-runtime.cleanup.finished",
            DevelopmentStage.CLEANUP,
            {"deleted": deleted, "alreadyAbsent": absent},
        )
        if not deleted and not absent:
            return FailureReport(
                "VALIDATION_RUNTIME_CLEANUP_FAILED",
                DevelopmentStage.CLEANUP,
                "Validation Runtime cleanup could not be confirmed",
            )
        return None

    @staticmethod
    async def _prepare_remote_root(transport: RemoteTransport) -> None:
        source = (
            "import os,stat\n"
            "root='/home/gem/.intelligent-development'\n"
            "temporary=root+'/tmp'\n"
            "for path in (root,temporary):\n"
            " os.makedirs(path,mode=0o700,exist_ok=True)\n"
            " metadata=os.stat(path,follow_symlinks=False)\n"
            " if not stat.S_ISDIR(metadata.st_mode): raise ValueError('invalid development root')\n"
            " os.chmod(path,0o700)\n"
        )
        await transport.exec_text(f"python3 -c {shlex.quote(source)}", timeout=12)

    @staticmethod
    async def _unlink(transport: RemoteTransport, path: str) -> None:
        source = (
            "import os\n"
            f"path={path!r}\n"
            "if os.path.lexists(path): os.unlink(path)\n"
            "if os.path.lexists(path): raise RuntimeError('one-shot file remains')\n"
        )
        task = asyncio.create_task(
            transport.exec_text(f"python3 -c {shlex.quote(source)}", timeout=10)
        )
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=11)
        except asyncio.CancelledError:
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=11)
            except BaseException:
                task.cancel()
            raise
        except BaseException as error:
            task.cancel()
            raise RuntimeError("Remote one-shot file cleanup failed") from error

    async def _emit(
        self,
        event_type: str,
        stage: DevelopmentStage,
        payload: Mapping[str, object] | None = None,
    ) -> None:
        event = DevelopmentEvent(
            len(self._events) + 1,
            event_type,
            stage,
            self._clock().isoformat(),
            payload or {},
        )
        self._events.append(event)
        if self._event_sink is not None:
            result = self._event_sink(event)
            if result is not None:
                await result
