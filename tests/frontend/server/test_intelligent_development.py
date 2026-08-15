from __future__ import annotations

import asyncio
import base64
import hashlib
from datetime import datetime, timezone
import json
import re
import shlex
from types import SimpleNamespace
from typing import Callable

import pytest

from frontend.server import intelligent_development as module
from frontend.server.intelligent_development import (
    RELEASE_ROOT,
    CommandResult,
    DevSession,
    DevelopmentEvent,
    DevelopmentStage,
    DevelopmentStatus,
    IntelligentDevelopmentVerifier,
    StudioCredentials,
    redact,
    verification_commands,
)


NOW = datetime(2026, 8, 15, tzinfo=timezone.utc)
SESSION = DevSession(
    owner_id="owner-1",
    session_id="session-1",
    endpoint="https://sandbox.example",
    project_root="/home/gem/workspace/project-1",
)
ARCHIVE = "/tmp/tmp-agentkit-build/project-1_20260815_deadbeef.tar.gz"
DIGEST = "a" * 64


def _argv(command: str) -> tuple[str, ...] | None:
    if not command.startswith("python3 -c "):
        return None
    source = shlex.split(command)[2]
    match = re.search(r"argv=json.loads\(base64\.b64decode\('([^']+)'\)\)", source)
    if match is None:
        return None
    return tuple(json.loads(base64.b64decode(match.group(1))))


class FakeTransport:
    def __init__(
        self,
        results: dict[str, list[dict[str, object]]] | None = None,
        *,
        delivery_value: dict[str, object] | None = None,
    ) -> None:
        self.results = results or {}
        self.delivery_value = delivery_value or self.valid_delivery()
        self.uploads: list[tuple[str, bytes, str, int | None]] = []
        self.exec_commands: list[tuple[str, tuple[str, ...] | None]] = []
        self.unlinks: list[str] = []
        self.raise_delivery = False

    @staticmethod
    def valid_delivery() -> dict[str, object]:
        release = f"{RELEASE_ROOT}/{DIGEST}"
        return {
            "artifactSha256": DIGEST,
            "artifactSize": 42,
            "agentName": "test-agent",
            "entryPoint": "app.py",
            "fileCount": 3,
            "releasePath": release,
            "artifactPath": f"{release}/artifact.zip",
            "descriptorPath": f"{release}/descriptor.json",
            "validationReportPath": f"{release}/validation/{'b' * 64}.json",
            "validationReportSha256": "b" * 64,
        }

    async def upload(
        self,
        path: str,
        content: bytes,
        *,
        media_type: str = "application/octet-stream",
        max_bytes: int = 20 * 1024 * 1024,
        mode: int | None = None,
    ) -> None:
        assert max_bytes == 20 * 1024 * 1024
        self.uploads.append((path, content, media_type, mode))

    async def exec_json(self, command: str, *, timeout: int = 12) -> dict[str, object]:
        argv = _argv(command)
        self.exec_commands.append((command, argv))
        if argv is None:
            if "/delivery-" in command:
                if self.raise_delivery:
                    raise RuntimeError("remote leaked SECRET")
                return self.delivery_value
            raise AssertionError(command)
        name = self._name(argv)
        values = self.results.get(name)
        if values:
            return values.pop(0)
        return self.default_result(name)

    async def exec_text(self, command: str, *, timeout: int = 12) -> str:
        source = shlex.split(command)[2]
        match = re.search(r"path='([^']+)'", source)
        if match:
            self.unlinks.append(match.group(1))
        return ""

    @staticmethod
    def _name(argv: tuple[str, ...]) -> str:
        if argv[:3] == ("python", "-m", "compileall"):
            return "compile"
        if argv[:2] == ("python", "-c"):
            return "service-contract"
        if argv[:2] == ("ak", "config"):
            return "ak-config"
        if argv[:2] == ("ak", "build"):
            return "ak-build"
        if argv[:2] == ("ak", "deploy"):
            return "ak-deploy"
        if argv[:3] == ("ak", "runtime", "update"):
            return "runtime-tag"
        if argv[:3] == ("ak", "runtime", "show"):
            return "runtime-ready"
        if argv[:3] == ("ak", "invoke", "run"):
            return "invoke"
        if argv[:3] == ("ak", "runtime", "logs"):
            return "logs"
        if argv == ("__studio_runtime__", "tag"):
            return "runtime-tag"
        if argv == ("__studio_runtime__", "get"):
            return "runtime-ready"
        if argv == ("__studio_runtime__", "logs"):
            return "logs"
        if argv == ("__studio_runtime__", "delete"):
            return "runtime-delete"
        raise AssertionError(argv)

    @staticmethod
    def default_result(name: str) -> dict[str, object]:
        stdout = ""
        if name == "ak-build":
            stdout = f"Project archive created: {ARCHIVE}\n"
        elif name == "runtime-ready":
            stdout = '{"id":"runtime-1","status":{"phase":"Ready"}}'
        elif name == "invoke":
            stdout = '{"success":true}'
        elif name == "logs":
            stdout = "[]"
        return {"exitCode": 0, "stdout": stdout, "stderr": ""}


def credentials() -> StudioCredentials:
    return StudioCredentials("ACCESS_EXACT", "SECRET_EXACT", "TOKEN_EXACT")


def verifier(
    transport: FakeTransport,
    *,
    resolver: Callable[[], StudioCredentials] = credentials,
    **kwargs,
) -> IntelligentDevelopmentVerifier:
    async def runtime_operation(
        operation: str,
        runtime_name: str,
        resolved: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        del runtime_name, resolved, arguments
        name = {
            "tag": "runtime-tag",
            "get": "runtime-ready",
            "logs": "logs",
            "delete": "runtime-delete",
        }[operation]
        transport.exec_commands.append(
            (f"studio:{operation}", ("__studio_runtime__", operation))
        )
        values = transport.results.get(name)
        value = values.pop(0) if values else transport.default_result(name)
        return CommandResult(
            int(value.get("exitCode", 1)),
            str(value.get("stdout", "")),
            str(value.get("stderr", "")),
        )

    supplied_runtime_operation = kwargs.pop("runtime_operation", runtime_operation)
    options = {"ready_interval_seconds": 0, "clock": lambda: NOW, **kwargs}
    return IntelligentDevelopmentVerifier(
        resolver,
        runtime_operation=supplied_runtime_operation,
        transport_factory=lambda endpoint: transport,
        **options,
    )


def result(exit_code: int, stdout: str = "", stderr: str = "") -> dict[str, object]:
    return {"exitCode": exit_code, "stdout": stdout, "stderr": stderr}


def test_dev_session_and_credentials_reject_untrusted_values() -> None:
    with pytest.raises(ValueError, match="endpoint"):
        DevSession("owner", "session", "http://sandbox", "/home/gem/workspace/project")
    with pytest.raises(ValueError, match="project root"):
        DevSession("owner", "session", "https://sandbox", "/tmp/project")
    with pytest.raises(ValueError, match="identity"):
        DevSession(
            "owner", "../session", "https://sandbox", "/home/gem/workspace/project"
        )
    with pytest.raises(ValueError, match="incomplete"):
        StudioCredentials("", "secret")
    with pytest.raises(ValueError, match="invalid"):
        StudioCredentials("access", "secret\x00")


def test_command_plan_is_typed_fixed_and_tags_validation_runtime() -> None:
    plan = verification_commands("idv-session-a1b2c3")
    assert [step.name for step in plan] == [
        "compile",
        "service-contract",
        "ak-config",
        "ak-build",
        "ak-deploy",
        "runtime-tag",
        "runtime-ready",
        "invoke",
        "logs",
    ]
    assert plan[0].credential_scope == "local"
    assert plan[1].credential_scope == "local"
    assert all(step.credential_scope == "cloud" for step in plan[2:])
    assert plan[2].argv == (
        "ak",
        "config",
        "--runtime_name",
        "idv-session-a1b2c3",
    )
    tags = json.loads(plan[5].argv[-1])
    assert {item["Key"] for item in tags} == {
        "veadk:lifecycle",
        "veadk:owner-hash",
        "veadk:session-hash",
    }
    assert plan[5].argv[:2] == ("__studio_runtime__", "tag")
    assert plan[6].argv[:2] == ("__studio_runtime__", "get")
    assert plan[-1].argv[:2] == ("__studio_runtime__", "logs")
    with pytest.raises(ValueError, match="name"):
        verification_commands("INVALID")


def test_redaction_handles_exact_and_generic_secrets() -> None:
    text = (
        "ACCESS_EXACT SECRET_KEY=generic Authorization: Bearer abc.def-_= "
        "eyJhbGciOiJIUzI1NiJ9.payload.signature"
    )
    cleaned = redact(text, exact_secrets=("ACCESS_EXACT",))
    assert "ACCESS_EXACT" not in cleaned
    assert "generic" not in cleaned
    assert "abc.def" not in cleaned
    assert "eyJhbGci" not in cleaned
    assert cleaned.count("<redacted>") >= 3


def test_sse_event_serialization_is_typed_and_ready() -> None:
    event = DevelopmentEvent(
        1,
        "verification.started",
        DevelopmentStage.CLOUD_BUILD,
        NOW.isoformat(),
        {"ok": True},
    )
    value = event.as_sse()
    assert value.startswith("id: 1\nevent: verification.started\ndata: ")
    assert '"stage":"cloud_build"' in value
    assert value.endswith("\n\n")


@pytest.mark.asyncio
async def test_success_runs_all_gates_with_fresh_one_shot_credentials_and_delivery(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module, "uuid4", lambda: SimpleNamespace(hex="a1b2c3d4e5f67890")
    )
    transport = FakeTransport()
    calls = 0

    def resolve() -> StudioCredentials:
        nonlocal calls
        calls += 1
        return credentials()

    emitted: list[DevelopmentEvent] = []
    run = verifier(transport, resolver=resolve, event_sink=emitted.append)
    outcome = await run.run(owner_id="owner-1", session=SESSION)

    assert outcome.status is DevelopmentStatus.SUCCEEDED
    assert outcome.failure is None
    assert outcome.delivery is not None
    assert outcome.delivery.artifact_sha256 == DIGEST
    assert outcome.delivery.validation_report_sha256 == "b" * 64
    assert outcome.delivery.session_id == SESSION.session_id
    assert outcome.delivery.agent_name == "test-agent"
    assert outcome.delivery.entry_point == "app.py"
    assert outcome.delivery.file_count == 3
    commands = [
        FakeTransport._name(argv) for _, argv in transport.exec_commands if argv
    ]
    assert commands == [
        "compile",
        "service-contract",
        "ak-config",
        "ak-build",
        "ak-deploy",
        "runtime-tag",
        "runtime-ready",
        "invoke",
        "logs",
        "runtime-delete",
    ]
    assert calls == 8
    credential_uploads = [
        item for item in transport.uploads if "/credentials-" in item[0]
    ]
    assert len(credential_uploads) == 4
    assert all(item[3] == 0o600 for item in credential_uploads)
    assert all(item[0] in transport.unlinks for item in credential_uploads)
    cloud_sources = [
        command for command, argv in transport.exec_commands if argv and argv[0] == "ak"
    ]
    assert all("O_NOFOLLOW" in shlex.split(command)[2] for command in cloud_sources)
    assert all(
        "os.unlink(secret)" in shlex.split(command)[2] for command in cloud_sources
    )
    assert all(
        "BYTEPLUS_ACCESS_KEY" in shlex.split(command)[2] for command in cloud_sources
    )
    assert emitted == list(outcome.events)
    assert outcome.events[-1].event_type == "development.succeeded"
    assert outcome.events[-3].event_type == "validation-runtime.cleanup.started"
    delivery_request = next(
        content
        for path, content, _, _ in transport.uploads
        if "/delivery-" in path and path.endswith(".json")
    )
    request = json.loads(delivery_request)
    assert request["sourceArchive"] == ARCHIVE
    assert request["report"]["status"] == "passed"
    assert request["report"]["sessionId"] == SESSION.session_id
    assert (
        request["report"]["runtimeNameHash"] != hashlib.sha256(b"compile").hexdigest()
    )
    assert [step["name"] for step in request["report"]["steps"]] == [
        "compile",
        "service-contract",
        "ak-config",
        "ak-build",
        "ak-deploy",
        "runtime-tag",
        "runtime-ready",
        "invoke",
        "logs",
    ]


@pytest.mark.asyncio
async def test_cancelled_run_finishes_validation_runtime_cleanup(monkeypatch) -> None:
    monkeypatch.setattr(
        module, "uuid4", lambda: SimpleNamespace(hex="a1b2c3d4e5f67890")
    )
    started = asyncio.Event()
    release = asyncio.Event()

    transport = FakeTransport()

    async def blocking_runtime_operation(
        operation: str,
        runtime_name: str,
        resolved: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        del runtime_name, resolved, arguments
        transport.exec_commands.append(
            (f"studio:{operation}", ("__studio_runtime__", operation))
        )
        if operation == "get":
            started.set()
            await release.wait()
            return CommandResult(0, '{"status":"Ready"}')
        return CommandResult(0)

    task = asyncio.create_task(
        verifier(transport, runtime_operation=blocking_runtime_operation).run(
            owner_id="owner-1", session=SESSION
        )
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    names = [FakeTransport._name(argv) for _, argv in transport.exec_commands if argv]
    assert names[-1] == "runtime-delete"


@pytest.mark.asyncio
async def test_owner_mismatch_fails_before_remote_access() -> None:
    transport = FakeTransport()
    with pytest.raises(PermissionError, match="ownership"):
        await verifier(transport).run(owner_id="other", session=SESSION)
    assert transport.exec_commands == []


@pytest.mark.asyncio
async def test_local_failure_stops_before_credentials_and_needs_no_remote_cleanup() -> (
    None
):
    transport = FakeTransport({"compile": [result(1, stderr="syntax failure")]})
    calls = 0

    def resolve() -> StudioCredentials:
        nonlocal calls
        calls += 1
        return credentials()

    outcome = await verifier(transport, resolver=resolve).run(
        owner_id="owner-1", session=SESSION
    )
    assert outcome.status is DevelopmentStatus.FAILED
    assert outcome.failure is not None
    assert outcome.failure.stage is DevelopmentStage.LOCAL_COMPILE
    assert calls == 0
    assert [argv for _, argv in transport.exec_commands if argv] == [
        ("python", "-m", "compileall", "-q", ".")
    ]
    assert outcome.events[-2].payload == {"deleted": False}


@pytest.mark.asyncio
async def test_build_requires_installed_agentkit_tmp_archive_contract() -> None:
    transport = FakeTransport(
        {
            "ak-build": [
                result(
                    0,
                    "Project archive created: /home/gem/workspace/other/archive.tar.gz",
                )
            ]
        }
    )
    outcome = await verifier(transport).run(owner_id="owner-1", session=SESSION)
    assert outcome.status is DevelopmentStatus.FAILED
    assert outcome.failure.stage is DevelopmentStage.CLOUD_BUILD
    assert outcome.report[-1].name == "ak-build"
    assert outcome.report[-1].passed is False
    assert "runtime-delete" not in [
        FakeTransport._name(argv) for _, argv in transport.exec_commands if argv
    ]


@pytest.mark.asyncio
async def test_deploy_ambiguous_failure_still_attempts_idempotent_cleanup() -> None:
    transport = FakeTransport(
        {
            "ak-deploy": [result(1, stderr="request timeout")],
            "runtime-delete": [result(1, stderr="runtime not found")],
        }
    )
    outcome = await verifier(transport).run(owner_id="owner-1", session=SESSION)
    assert outcome.status is DevelopmentStatus.FAILED
    names = [FakeTransport._name(argv) for _, argv in transport.exec_commands if argv]
    assert names[-1] == "runtime-delete"
    cleanup = next(
        event
        for event in outcome.events
        if event.event_type == "validation-runtime.cleanup.finished"
    )
    assert cleanup.payload == {"deleted": False, "alreadyAbsent": True}


@pytest.mark.asyncio
async def test_cleanup_failure_overrides_success_and_suppresses_delivery_reference() -> (
    None
):
    transport = FakeTransport(
        {
            "runtime-delete": [
                result(1, stderr="permission denied"),
                result(1, stderr="permission denied"),
                result(1, stderr="permission denied"),
            ]
        }
    )
    delays: list[float] = []

    async def sleep(delay: float) -> None:
        delays.append(delay)

    outcome = await verifier(transport, sleep=sleep).run(
        owner_id="owner-1", session=SESSION
    )
    assert delays == [1, 2]
    assert outcome.status is DevelopmentStatus.FAILED
    assert outcome.delivery is None
    assert outcome.failure is not None
    assert outcome.failure.code == "VALIDATION_RUNTIME_CLEANUP_FAILED"
    assert outcome.failure.stage is DevelopmentStage.CLEANUP


@pytest.mark.asyncio
async def test_ready_polls_until_ready_and_times_out_at_fixed_attempt_limit() -> None:
    transport = FakeTransport(
        {
            "runtime-ready": [
                result(0, '{"status":"Creating"}'),
                result(0, '{"status":{"phase":"Ready"}}'),
            ]
        }
    )
    sleeps: list[float] = []

    async def sleep(delay: float) -> None:
        sleeps.append(delay)

    outcome = await verifier(
        transport,
        ready_attempts=2,
        ready_interval_seconds=0.25,
        sleep=sleep,
    ).run(owner_id="owner-1", session=SESSION)
    assert outcome.status is DevelopmentStatus.SUCCEEDED
    assert sleeps == [0.25]

    never_ready = FakeTransport(
        {"runtime-ready": [result(0, '{"status":"Creating"}')] * 2}
    )
    outcome = await verifier(never_ready, ready_attempts=2).run(
        owner_id="owner-1", session=SESSION
    )
    assert outcome.status is DevelopmentStatus.FAILED
    assert outcome.failure.stage is DevelopmentStage.RUNTIME_READY


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "step, bad_result, expected_stage",
    [
        ("runtime-tag", result(1), DevelopmentStage.RUNTIME_TAG),
        ("invoke", result(0, "{}"), DevelopmentStage.RUNTIME_INVOKE),
        ("logs", result(0, "Traceback: boom"), DevelopmentStage.RUNTIME_LOGS),
    ],
)
async def test_semantic_cloud_gates_fail_closed(
    step, bad_result, expected_stage
) -> None:
    transport = FakeTransport({step: [bad_result]})
    outcome = await verifier(transport).run(owner_id="owner-1", session=SESSION)
    assert outcome.status is DevelopmentStatus.FAILED
    assert outcome.failure.stage is expected_stage
    assert outcome.report[-1].passed is False
    assert outcome.delivery is None


@pytest.mark.asyncio
async def test_exact_and_generic_secrets_are_redacted_from_report() -> None:
    transport = FakeTransport(
        {
            "ak-config": [
                result(
                    1,
                    "ACCESS_EXACT SECRET_KEY=generic",
                    "Authorization=Bearer bearer-value",
                )
            ]
        }
    )
    outcome = await verifier(transport).run(owner_id="owner-1", session=SESSION)
    report = outcome.report[-1]
    assert "ACCESS_EXACT" not in report.stdout
    assert "generic" not in report.stdout
    assert "bearer-value" not in report.stderr
    assert "<redacted>" in report.stdout


@pytest.mark.asyncio
async def test_invalid_remote_result_and_delivery_failure_return_minimal_failure() -> (
    None
):
    malformed = FakeTransport({"compile": [{"exitCode": "zero", "stdout": "SECRET"}]})
    outcome = await verifier(malformed).run(owner_id="owner-1", session=SESSION)
    assert outcome.failure is not None
    assert outcome.failure.as_dict() == {
        "code": "INTELLIGENT_DEVELOPMENT_FAILED",
        "stage": "local_compile",
        "message": "Foreground verification could not be completed",
    }
    assert "SECRET" not in json.dumps(outcome.failure.as_dict())

    delivery = FakeTransport()
    delivery.raise_delivery = True
    outcome = await verifier(delivery).run(owner_id="owner-1", session=SESSION)
    assert outcome.failure is not None
    assert outcome.failure.stage is DevelopmentStage.ARTIFACT
    assert "SECRET" not in outcome.failure.message
    assert any("delivery-secrets-" in value for value in delivery.unlinks)
    assert any(
        "/delivery-" in value and value.endswith(".json") for value in delivery.unlinks
    )
    assert any(
        "/delivery-" in value and value.endswith(".py") for value in delivery.unlinks
    )


def test_delivery_reference_rejects_digest_size_metadata_and_remote_path() -> None:
    valid = FakeTransport.valid_delivery()
    verifier_instance = verifier(FakeTransport())
    reports = ()
    reference = verifier_instance._delivery_reference(valid, SESSION, reports)
    assert reference.artifact_sha256 == DIGEST
    assert "artifactPath" not in reference.as_dict()
    for field, value in (
        ("artifactSha256", "bad"),
        ("artifactSize", True),
        ("validationReportSha256", "bad"),
        ("agentName", ""),
        ("entryPoint", ""),
        ("fileCount", 0),
        ("releasePath", "/tmp/release"),
        ("artifactPath", "/tmp/artifact.zip"),
    ):
        changed = dict(valid)
        changed[field] = value
        with pytest.raises(ValueError, match="Delivery descriptor"):
            verifier_instance._delivery_reference(changed, SESSION, reports)


def test_remote_worker_contains_immutable_atomic_and_safety_gates() -> None:
    source = module.REMOTE_DELIVERY_WORKER
    assert "RELEASES / digest" in source
    assert "os.rename(staging, release)" in source
    assert "os.replace(temporary, path)" in source
    assert "O_NOFOLLOW" in source
    assert "stat.S_ISREG" in source
    assert "secret_path.unlink(missing_ok=True)" in source
    assert "Delivery source contains supplied credentials" in source
    assert 'read_regular(release / "descriptor.json") != descriptor_bytes' in source
    assert (
        'read_regular(release / "validation" / f"{report_digest}.json") != report_bytes'
        in source
    )
    assert "artifact.zip" in source
    assert "descriptor.json" in source
    assert 'validation_dir = staging / "validation"' in source
    assert "published.json" in source


def test_value_objects_reject_remaining_invalid_boundaries() -> None:
    with pytest.raises(ValueError, match="owner"):
        DevSession("", "session", "https://sandbox", "/home/gem/workspace/project")
    with pytest.raises(ValueError, match="project root"):
        DevSession("owner", "session", "https://sandbox", "/home/gem/workspace/../")
    with pytest.raises(ValueError, match="command"):
        module.VerificationCommand(
            "",
            DevelopmentStage.LOCAL_COMPILE,
            ("python",),
            1,
            "local",
        )
    with pytest.raises(ValueError, match="argv"):
        module.VerificationCommand(
            "compile",
            DevelopmentStage.LOCAL_COMPILE,
            ("python", ""),
            1,
            "local",
        )


def test_semantic_helpers_cover_malformed_and_alternate_outputs() -> None:
    assert module._runtime_ready(CommandResult(1, '{"status":"Ready"}')) is False
    assert module._runtime_ready(CommandResult(0, "[]")) is False
    assert module._invoke_succeeded(CommandResult(1, '"answer"')) is False
    assert module._invoke_succeeded(CommandResult(0, 'noise\n"answer"')) is True
    assert module._json_output('noise\n{"status":"Ready"}') == {"status": "Ready"}
    assert module._json_output("noise\nstill noise") is None
    assert (
        module._archive_path(CommandResult(1, f"Project archive created: {ARCHIVE}"))
        == ""
    )
    with pytest.raises(ValueError, match="cannot be derived"):
        module._runtime_name(SESSION, "INVALID")


def test_verifier_rejects_invalid_ready_polling_policy() -> None:
    with pytest.raises(ValueError, match="polling policy"):
        verifier(FakeTransport(), ready_attempts=0)
    with pytest.raises(ValueError, match="polling policy"):
        verifier(FakeTransport(), ready_interval_seconds=-0.1)


@pytest.mark.asyncio
async def test_cancelled_run_fails_closed_when_runtime_cleanup_fails(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        module, "uuid4", lambda: SimpleNamespace(hex="a1b2c3d4e5f67890")
    )
    started = asyncio.Event()
    release = asyncio.Event()

    async def runtime_operation(
        operation: str,
        runtime_name: str,
        resolved: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        del runtime_name, resolved, arguments
        if operation == "get":
            started.set()
            await release.wait()
            return CommandResult(0, '{"status":"Ready"}')
        if operation == "delete":
            return CommandResult(1, stderr="permission denied")
        return CommandResult(0)

    task = asyncio.create_task(
        verifier(FakeTransport(), runtime_operation=runtime_operation).run(
            owner_id="owner-1", session=SESSION
        )
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(RuntimeError, match="cleanup could not be confirmed"):
        await task


@pytest.mark.asyncio
async def test_execute_requires_runtime_adapter_and_typed_fresh_credentials() -> None:
    runtime_command = verification_commands("idv-session-a1b2c3")[5]
    cloud_command = verification_commands("idv-session-a1b2c3")[2]
    transport = FakeTransport()
    exact_secrets: set[str] = set()

    no_adapter = verifier(transport, runtime_operation=None)
    with pytest.raises(RuntimeError, match="not configured"):
        await no_adapter._execute(transport, SESSION, runtime_command, exact_secrets)

    bad_runtime_credentials = verifier(
        transport,
        resolver=lambda: None,  # type: ignore[return-value]
    )
    with pytest.raises(TypeError, match="StudioCredentials"):
        await bad_runtime_credentials._execute(
            transport, SESSION, runtime_command, exact_secrets
        )

    bad_cloud_credentials = verifier(
        transport,
        resolver=lambda: None,  # type: ignore[return-value]
    )
    with pytest.raises(TypeError, match="StudioCredentials"):
        await bad_cloud_credentials._execute(
            transport, SESSION, cloud_command, exact_secrets
        )


@pytest.mark.asyncio
async def test_failed_credential_upload_still_removes_one_shot_file() -> None:
    class UploadFailureTransport(FakeTransport):
        async def upload(
            self,
            path: str,
            content: bytes,
            *,
            media_type: str = "application/octet-stream",
            max_bytes: int = 20 * 1024 * 1024,
            mode: int | None = None,
        ) -> None:
            del content, media_type, max_bytes, mode
            raise RuntimeError(f"upload failed for {path}")

    transport = UploadFailureTransport()
    command = verification_commands("idv-session-a1b2c3")[2]
    with pytest.raises(RuntimeError, match="upload failed"):
        await verifier(transport)._execute(transport, SESSION, command, set())
    assert len(transport.unlinks) == 1
    assert "/credentials-" in transport.unlinks[0]


@pytest.mark.asyncio
async def test_publish_rejects_missing_verified_archive() -> None:
    transport = FakeTransport()
    with pytest.raises(ValueError, match="archive is unavailable"):
        await verifier(transport)._publish(
            transport,
            SESSION,
            "",
            (),
            set(),
            "idv-session-a1b2c3",
        )
    assert transport.uploads == []


@pytest.mark.asyncio
async def test_cleanup_reports_runtime_adapter_exception() -> None:
    async def runtime_operation(
        operation: str,
        runtime_name: str,
        resolved: StudioCredentials,
        arguments: tuple[str, ...],
    ) -> CommandResult:
        del operation, runtime_name, resolved, arguments
        raise RuntimeError("runtime service unavailable")

    run = verifier(FakeTransport(), runtime_operation=runtime_operation)
    failure = await run._cleanup_runtime_once(
        FakeTransport(), SESSION, "idv-session-a1b2c3", True, set()
    )
    assert failure is not None
    assert failure.code == "VALIDATION_RUNTIME_CLEANUP_FAILED"


@pytest.mark.asyncio
async def test_cleanup_waits_for_shielded_task_after_caller_cancellation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def event_sink(event: DevelopmentEvent) -> None:
        if event.event_type == "validation-runtime.cleanup.started":
            started.set()
            await release.wait()

    run = verifier(FakeTransport(), event_sink=event_sink)
    task = asyncio.create_task(
        run._cleanup_runtime(
            FakeTransport(), SESSION, "idv-session-a1b2c3", False, set()
        )
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert any(
        event.event_type == "validation-runtime.cleanup.finished"
        for event in run._events
    )


@pytest.mark.asyncio
async def test_cleanup_cancels_failed_shielded_task_after_caller_cancellation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    async def event_sink(event: DevelopmentEvent) -> None:
        if event.event_type == "validation-runtime.cleanup.started":
            started.set()
            await release.wait()
            raise asyncio.CancelledError

    run = verifier(FakeTransport(), event_sink=event_sink)
    task = asyncio.create_task(
        run._cleanup_runtime(
            FakeTransport(), SESSION, "idv-session-a1b2c3", False, set()
        )
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_unlink_waits_for_shielded_delete_after_caller_cancellation() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class BlockingTransport(FakeTransport):
        async def exec_text(self, command: str, *, timeout: int = 12) -> str:
            del command, timeout
            started.set()
            await release.wait()
            return ""

    task = asyncio.create_task(
        module.IntelligentDevelopmentVerifier._unlink(BlockingTransport(), "/tmp/file")
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task


@pytest.mark.asyncio
async def test_unlink_cancels_failed_delete_and_translates_transport_errors() -> None:
    started = asyncio.Event()
    release = asyncio.Event()

    class CancelledTransport(FakeTransport):
        async def exec_text(self, command: str, *, timeout: int = 12) -> str:
            del command, timeout
            started.set()
            await release.wait()
            raise asyncio.CancelledError

    task = asyncio.create_task(
        module.IntelligentDevelopmentVerifier._unlink(CancelledTransport(), "/tmp/file")
    )
    await started.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task

    class FailedTransport(FakeTransport):
        async def exec_text(self, command: str, *, timeout: int = 12) -> str:
            del command, timeout
            raise OSError("sandbox unavailable")

    with pytest.raises(RuntimeError, match="one-shot file cleanup failed"):
        await module.IntelligentDevelopmentVerifier._unlink(
            FailedTransport(), "/tmp/file"
        )


@pytest.mark.asyncio
async def test_async_event_sink_is_awaited() -> None:
    received: list[DevelopmentEvent] = []

    async def event_sink(event: DevelopmentEvent) -> None:
        await asyncio.sleep(0)
        received.append(event)

    run = verifier(FakeTransport(), event_sink=event_sink)
    await run._emit("test.event", DevelopmentStage.DONE)
    assert received == run._events
