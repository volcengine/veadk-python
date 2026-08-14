# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from typing_extensions import Self

from frontend.server.migration import service as service_module
from frontend.server.migration.gateway import (
    MigrationGatewayError,
)
from frontend.server.migration.models import (
    ConfirmMigrationBody,
    CreateMigrationTaskBody,
    SubmitAnalysisAnswersBody,
)
from frontend.server.migration.service import (
    MIGRATION_ROOT,
    MigrationError,
    MigrationService,
    _timestamp,
    validate_source_archive,
)
from tests.frontend.test_migration_server import (
    FakeMigrationGateway,
    analysis_result,
    confirmation_body,
    create_uploaded_task,
    mark_analysis_ready,
    source_zip,
)


def zip_bytes(files: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for path, content in files.items():
            archive.writestr(path, content)
    return output.getvalue()


def assert_code(error: pytest.ExceptionInfo[MigrationError], code: str) -> None:
    assert error.value.code == code


def test_source_archive_validation_covers_size_structure_and_encryption(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with pytest.raises(MigrationError) as empty:
        validate_source_archive(b"")
    assert_code(empty, "MIGRATION_SOURCE_EMPTY")

    monkeypatch.setattr(service_module, "MIGRATION_UPLOAD_MAX_BYTES", 0)
    with pytest.raises(MigrationError) as upload_size:
        validate_source_archive(b"x")
    assert_code(upload_size, "MIGRATION_SOURCE_TOO_LARGE")
    monkeypatch.setattr(service_module, "MIGRATION_UPLOAD_MAX_BYTES", 50 * 1024 * 1024)

    with pytest.raises(MigrationError) as duplicate:
        validate_source_archive(zip_bytes({"A.py": b"a", "a.py": b"b"}))
    assert_code(duplicate, "MIGRATION_SOURCE_DUPLICATE_PATH")

    assert (
        validate_source_archive(
            zip_bytes({"folder/": b"", "folder/app.py": b"x"})
        ).file_count
        == 1
    )

    monkeypatch.setattr(service_module, "_MAX_ARCHIVE_FILES", 0)
    with pytest.raises(MigrationError) as file_count:
        validate_source_archive(zip_bytes({"app.py": b"x"}))
    assert_code(file_count, "MIGRATION_SOURCE_FILE_COUNT")
    monkeypatch.setattr(service_module, "_MAX_ARCHIVE_FILES", 20_000)

    monkeypatch.setattr(service_module, "_MAX_EXPANDED_BYTES", 0)
    with pytest.raises(MigrationError) as expanded:
        validate_source_archive(zip_bytes({"app.py": b"x"}))
    assert_code(expanded, "MIGRATION_SOURCE_EXPANDED_TOO_LARGE")

    with pytest.raises(MigrationError) as invalid:
        validate_source_archive(b"not-a-zip")
    assert_code(invalid, "MIGRATION_SOURCE_INVALID")
    with pytest.raises(MigrationError) as no_files:
        validate_source_archive(zip_bytes({}))
    assert_code(no_files, "MIGRATION_SOURCE_EMPTY")

    class EncryptedInfo:
        filename = "app.py"
        external_attr = 0
        flag_bits = 1
        file_size = 1

        @staticmethod
        def is_dir() -> bool:
            return False

    class FakeZip:
        def __enter__(self) -> Self:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        @staticmethod
        def infolist() -> list[EncryptedInfo]:
            return [EncryptedInfo()]

    monkeypatch.setattr(service_module.zipfile, "ZipFile", lambda *_args: FakeZip())
    with pytest.raises(MigrationError) as encrypted:
        validate_source_archive(b"zip")
    assert_code(encrypted, "MIGRATION_SOURCE_ENCRYPTED")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (True, None),
        (1, 1.0),
        ("", None),
        ("invalid", None),
        ("2026-08-13T08:00:00", 1786608000.0),
    ],
)
def test_timestamp_normalization(value: object, expected: float | None) -> None:
    assert _timestamp(value) == expected


def test_service_maps_gateway_and_remote_state_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    sandbox_session = gateway.create_session(
        task_id="migration-v1-" + "1" * 32,
        owner_id="owner-1",
        creator_name="Owner",
        display_name="存量迁移",
        ttl_seconds=3600,
    )

    gateway.capabilities = lambda: {"enabled": True, "model": "invalid"}  # type: ignore[method-assign]
    assert service.capabilities()["model"] == {"configured": False, "id": ""}

    with pytest.raises(MigrationError) as invalid_id:
        service.get_task("invalid", "owner-1")
    assert_code(invalid_id, "MIGRATION_TASK_NOT_FOUND")

    upstream = MigrationGatewayError(
        "UPSTREAM",
        "upstream failed",
        status_code=503,
        retryable=True,
    )
    monkeypatch.setattr(
        gateway,
        "find_session",
        lambda *_args: (_ for _ in ()).throw(upstream),
    )
    with pytest.raises(MigrationError) as translated_session:
        service._session(sandbox_session.task_id, "owner-1")
    assert_code(translated_session, "UPSTREAM")
    assert translated_session.value.retryable is True

    monkeypatch.setattr(
        gateway,
        "put_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(upstream),
    )
    with pytest.raises(MigrationError) as translated_put:
        service._put(sandbox_session, "path", b"x", media_type="text/plain")
    assert_code(translated_put, "UPSTREAM")

    monkeypatch.setattr(
        gateway,
        "get_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(upstream),
    )
    with pytest.raises(MigrationError) as translated_read:
        service._read(sandbox_session, "path")
    assert_code(translated_read, "UPSTREAM")

    monkeypatch.setattr(gateway, "get_file", lambda *_args, **_kwargs: b"{")
    with pytest.raises(MigrationError) as invalid_json:
        service._read_json(sandbox_session, "path")
    assert_code(invalid_json, "MIGRATION_REMOTE_STATE_INVALID")
    monkeypatch.setattr(gateway, "get_file", lambda *_args, **_kwargs: b"[]")
    with pytest.raises(MigrationError) as non_object:
        service._read_json(sandbox_session, "path")
    assert_code(non_object, "MIGRATION_REMOTE_STATE_INVALID")

    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: None)
    with pytest.raises(MigrationError) as missing_analysis:
        service._read_analysis(
            sandbox_session,
            expected_attempt=1,
            expected_input_sha256="1" * 64,
        )
    assert_code(missing_analysis, "MIGRATION_ANALYSIS_MISSING")


def test_runtime_capability_validation_and_unavailable_task_creation() -> None:
    with pytest.raises(MigrationError) as not_object:
        MigrationService._validated_runtime_capabilities(None)
    assert_code(not_object, "MIGRATION_SANDBOX_CAPABILITY_INVALID")

    with pytest.raises(MigrationError) as malformed:
        MigrationService._validated_runtime_capabilities({"schema_version": 1})
    assert_code(malformed, "MIGRATION_SANDBOX_CAPABILITY_INVALID")

    with pytest.raises(MigrationError) as unavailable:
        MigrationService._require_runtime_ready(
            {"ready": False, "failures": ["AK_VERSION_TOO_OLD"]}
        )
    assert_code(unavailable, "MIGRATION_SANDBOX_CAPABILITY_UNAVAILABLE")

    gateway = FakeMigrationGateway()
    gateway.enabled = False
    service = MigrationService(gateway)
    with pytest.raises(MigrationError) as disabled:
        service.create_task(
            CreateMigrationTaskBody(sourceFileName="source.zip"),
            "owner-1",
            "Owner",
        )
    assert_code(disabled, "MIGRATION_DEVENV_UNAVAILABLE")


def test_create_task_maps_missing_request_and_gateway_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    original_get = gateway.get_file

    def missing_request(
        sandbox_session: object,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes | None:
        if path.endswith("/request/task.json"):
            return None
        return original_get(sandbox_session, path, max_bytes=max_bytes)  # type: ignore[arg-type]

    monkeypatch.setattr(gateway, "get_file", missing_request)
    with pytest.raises(MigrationError) as missing:
        service.create_task(
            CreateMigrationTaskBody(sourceFileName="source.zip"),
            "owner-1",
            "Owner",
        )
    assert_code(missing, "MIGRATION_REQUEST_MISSING")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    monkeypatch.setattr(
        gateway,
        "create_session",
        lambda **_kwargs: (_ for _ in ()).throw(
            MigrationGatewayError("CREATE_FAILED", "create failed")
        ),
    )
    with pytest.raises(MigrationError) as create_failed:
        service.create_task(
            CreateMigrationTaskBody(sourceFileName="source.zip"),
            "owner-1",
            "Owner",
        )
    assert_code(create_failed, "CREATE_FAILED")


def test_analysis_reference_rejects_source_mismatch_and_stale_result() -> None:
    source = {"sha256": "1" * 64}
    analysis = {"attempt": 1, "input_sha256": "1" * 64}
    with pytest.raises(MigrationError) as mismatch:
        MigrationService._validate_analysis_reference(
            analysis_attempt=1,
            analysis_sha256="2" * 64,
            input_sha256="3" * 64,
            analysis=analysis,
            actual_analysis_sha256="2" * 64,
            source=source,
        )
    assert_code(mismatch, "MIGRATION_ANALYSIS_SOURCE_MISMATCH")

    with pytest.raises(MigrationError) as stale:
        MigrationService._validate_analysis_reference(
            analysis_attempt=2,
            analysis_sha256="2" * 64,
            input_sha256="1" * 64,
            analysis=analysis,
            actual_analysis_sha256="2" * 64,
            source=source,
        )
    assert_code(stale, "MIGRATION_ANALYSIS_STALE")


def test_upload_rejects_locked_source_and_missing_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    with pytest.raises(MigrationError) as locked:
        service.upload_source(
            task_id,
            "owner-1",
            source_zip({"different.py": b"different"}),
        )
    assert_code(locked, "MIGRATION_SOURCE_LOCKED")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    accepted = source_zip()
    gateway.files[(task_id, f"{MIGRATION_ROOT}/request/source.json")] = json.dumps(
        {
            "schema_version": 1,
            "sha256": hashlib.sha256(accepted).hexdigest(),
            "size": len(accepted),
            "file_count": 2,
            "expanded_bytes": 1,
        }
    ).encode()
    with pytest.raises(MigrationError) as immutable_source:
        service.upload_source(
            task_id,
            "owner-1",
            source_zip({"different.py": b"different"}),
        )
    assert_code(immutable_source, "MIGRATION_SOURCE_LOCKED")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    original_execute = gateway.execute_bash
    original_get = gateway.get_file
    request_removed = False

    def execute(*args: object, **kwargs: object) -> dict[str, object]:
        nonlocal request_removed
        result = original_execute(*args, **kwargs)  # type: ignore[arg-type]
        if kwargs.get("operation") == "prepare_source":
            gateway.files.pop((task_id, f"{MIGRATION_ROOT}/request/task.json"))
            request_removed = True
        return result

    monkeypatch.setattr(gateway, "execute_bash", execute)

    def get_file(
        sandbox_session: object,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes | None:
        if request_removed and path.endswith("/request/task.json"):
            return None
        return original_get(sandbox_session, path, max_bytes=max_bytes)  # type: ignore[arg-type]

    monkeypatch.setattr(gateway, "get_file", get_file)
    with pytest.raises(MigrationError) as missing_request:
        service.upload_source(task_id, "owner-1", source_zip())
    assert_code(missing_request, "MIGRATION_REQUEST_MISSING")


def test_list_tasks_maps_gateway_and_invalid_request_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    monkeypatch.setattr(
        gateway,
        "list_sessions",
        lambda _owner: (_ for _ in ()).throw(
            MigrationGatewayError("LIST_FAILED", "list failed")
        ),
    )
    with pytest.raises(MigrationError) as list_failed:
        service.list_tasks("owner-1")
    assert_code(list_failed, "LIST_FAILED")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    gateway.files[(task_id, f"{MIGRATION_ROOT}/request/task.json")] = b"{}"
    listed = service.list_tasks("owner-1")["items"]
    assert listed[0]["state"] == "failed"
    assert listed[0]["sourceFileName"] == "项目 ZIP"


def test_task_recovery_handles_failed_and_missing_analysis_status() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/task-status.json")] = json.dumps(
        {
            "schema_version": 1,
            "attempt": 1,
            "state": "failed",
            "message": "项目分析未完成",
            "error": {
                "code": "MIGRATION_ANALYSIS_FAILED",
                "message": "Codex 分析失败。",
                "retryable": False,
            },
        }
    ).encode()

    failed = service.get_task(task_id, "owner-1")

    assert failed["state"] == "failed"
    assert failed["error"]["code"] == "MIGRATION_ANALYSIS_FAILED"

    gateway.files.pop((task_id, f"{MIGRATION_ROOT}/control/task-status.json"))
    uploaded = service.get_task(task_id, "owner-1")
    assert uploaded["state"] == "awaiting_upload"
    assert uploaded["canUpload"] is True

    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="new-source.zip"),
        "owner-1",
        "Owner",
    )
    created_id = str(created["id"])
    gateway.files.pop((created_id, f"{MIGRATION_ROOT}/control/task-status.json"))
    empty = service.get_task(created_id, "owner-1")
    assert empty["state"] == "awaiting_upload"
    assert empty["sourceFileName"] == "new-source.zip"


def mark_needs_input(
    gateway: FakeMigrationGateway,
    task_id: str,
    *,
    attempt: int = 1,
) -> tuple[dict[str, object], bytes]:
    source = json.loads(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/request/source.json")]
    )
    analysis = analysis_result(
        input_sha256=source["sha256"],
        attempt=attempt,
        status="needs_input",
    )
    analysis["questions"] = [{"id": "question", "prompt": "补充信息", "required": True}]
    content = json.dumps(analysis, ensure_ascii=False).encode()
    gateway.files[(task_id, f"{MIGRATION_ROOT}/analysis/route.json")] = content
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/task-status.json")] = json.dumps(
        {
            "schema_version": 1,
            "attempt": attempt,
            "state": "needs_input",
            "message": "请补充信息",
        }
    ).encode()
    return source, content


def answers_body(
    source: dict[str, object],
    content: bytes,
    *,
    attempt: int = 1,
) -> SubmitAnalysisAnswersBody:
    return SubmitAnalysisAnswersBody(
        analysisAttempt=attempt,
        analysisSha256=hashlib.sha256(content).hexdigest(),
        inputSha256=str(source["sha256"]),
        answers={"question": "保持现有行为"},
    )


def test_submit_answers_success_missing_state_and_attempt_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    source, content = mark_needs_input(gateway, task_id)

    result = service.submit_answers(
        task_id,
        "owner-1",
        answers_body(source, content),
    )
    assert result["state"] == "analyzing"
    assert [operation for _, operation, _ in gateway.commands].count(
        "start_analysis"
    ) == 2

    with pytest.raises(MigrationError) as locked:
        service.submit_answers(
            task_id,
            "owner-1",
            answers_body(source, content),
        )
    assert_code(locked, "MIGRATION_ANALYSIS_ANSWERS_LOCKED")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    source, content = mark_needs_input(gateway, task_id)
    original_read_json = service._read_json
    reads = 0

    def read_json(*args: object, **kwargs: object) -> dict[str, object] | None:
        nonlocal reads
        path = str(args[1])
        if path.endswith("/request/task.json"):
            reads += 1
            if reads > 1:
                return None
        return original_read_json(*args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(service, "_read_json", read_json)
    with pytest.raises(MigrationError) as missing:
        service.submit_answers(task_id, "owner-1", answers_body(source, content))
    assert_code(missing, "MIGRATION_ANALYSIS_MISSING")

    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    source, content = mark_needs_input(gateway, task_id, attempt=100)
    with pytest.raises(MigrationError) as limit:
        service.submit_answers(
            task_id,
            "owner-1",
            answers_body(source, content, attempt=100),
        )
    assert_code(limit, "MIGRATION_ANALYSIS_ATTEMPT_LIMIT")


def test_submit_answers_rechecks_analysis_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    source, content = mark_needs_input(gateway, task_id)
    original_task = service._task_from_session
    task = original_task(gateway.sessions[task_id])
    analysis = json.loads(content)
    analysis["status"] = "recommendation_ready"
    analysis["questions"] = []
    gateway.files[(task_id, f"{MIGRATION_ROOT}/analysis/route.json")] = json.dumps(
        analysis
    ).encode()
    monkeypatch.setattr(service, "_task_from_session", lambda _session: task)
    updated = gateway.files[(task_id, f"{MIGRATION_ROOT}/analysis/route.json")]
    with pytest.raises(MigrationError) as locked:
        service.submit_answers(
            task_id,
            "owner-1",
            answers_body(source, updated),
        )
    assert_code(locked, "MIGRATION_ANALYSIS_ANSWERS_LOCKED")


def test_confirm_rejects_analysis_route_capability_and_entry_mismatches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)

    unsupported = confirmation_body(
        gateway,
        task_id,
        framework="dify",
        entry=None,
    )
    with pytest.raises(MigrationError) as route:
        service.confirm(task_id, "owner-1", unsupported)
    assert_code(route, "MIGRATION_ROUTE_UNSUPPORTED")

    unavailable_runtime = json.loads(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/control/capabilities.json")]
    )
    unavailable_runtime["structured"]["available"] = False
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/capabilities.json")] = (
        json.dumps(unavailable_runtime).encode()
    )
    with pytest.raises(MigrationError) as capability:
        service.confirm(task_id, "owner-1", confirmation_body(gateway, task_id))
    assert_code(capability, "MIGRATION_ROUTE_CAPABILITY_UNAVAILABLE")

    unavailable_runtime["structured"]["available"] = True
    gateway.files[(task_id, f"{MIGRATION_ROOT}/control/capabilities.json")] = (
        json.dumps(unavailable_runtime).encode()
    )
    invalid_entry = confirmation_body(gateway, task_id)
    invalid_entry = ConfirmMigrationBody(
        **{
            **invalid_entry.model_dump(by_alias=True),
            "entry": "other.py:agent",
        }
    )
    with pytest.raises(MigrationError) as entry:
        service.confirm(task_id, "owner-1", invalid_entry)
    assert_code(entry, "MIGRATION_ENTRY_UNSUPPORTED")


def test_confirm_allows_any_override_for_structured_recommendation() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id, framework="langchain")

    task = service.confirm(
        task_id,
        "owner-1",
        confirmation_body(
            gateway,
            task_id,
            framework="any",
            entry=None,
        ),
    )

    assert task["state"] == "migrating"
    assert task["confirmation"]["framework"] == "any"
    assert task["confirmation"]["execution_model"] == "agentic"


def test_confirm_rechecks_analysis_status_after_task_read(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    task = service.get_task(task_id, "owner-1")
    analysis_path = (task_id, f"{MIGRATION_ROOT}/analysis/route.json")
    analysis = json.loads(gateway.files[analysis_path])
    analysis["status"] = "needs_input"
    analysis["questions"] = [{"id": "question", "prompt": "补充信息", "required": True}]
    changed = json.dumps(analysis).encode()
    gateway.files[analysis_path] = changed
    task["analysisRef"]["sha256"] = hashlib.sha256(changed).hexdigest()
    monkeypatch.setattr(service, "_task_from_session", lambda _session: task)
    source = json.loads(
        gateway.files[(task_id, f"{MIGRATION_ROOT}/request/source.json")]
    )
    body = ConfirmMigrationBody(
        framework="langchain",
        entry="agent.py:agent",
        appName="support-agent",
        analysisAttempt=1,
        analysisSha256=hashlib.sha256(changed).hexdigest(),
        inputSha256=source["sha256"],
        boundaryConfirmed=True,
    )
    with pytest.raises(MigrationError) as not_ready:
        service.confirm(task_id, "owner-1", body)
    assert_code(not_ready, "MIGRATION_ANALYSIS_NOT_READY")


@pytest.mark.parametrize(
    ("missing_path", "expected_code"),
    [
        ("request/task.json", "MIGRATION_REQUEST_MISSING"),
        ("request/source.json", "MIGRATION_SOURCE_STATE_INVALID"),
    ],
)
def test_confirm_rejects_state_files_removed_after_task_read(
    monkeypatch: pytest.MonkeyPatch,
    missing_path: str,
    expected_code: str,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    body = confirmation_body(gateway, task_id)
    task = service.get_task(task_id, "owner-1")
    monkeypatch.setattr(service, "_task_from_session", lambda _session: task)
    gateway.files.pop((task_id, f"{MIGRATION_ROOT}/{missing_path}"))

    with pytest.raises(MigrationError) as missing:
        service.confirm(task_id, "owner-1", body)

    assert_code(missing, expected_code)


def test_ready_analysis_requires_source_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    gateway.files.pop((task_id, f"{MIGRATION_ROOT}/request/source.json"))
    original_get = gateway.get_file

    def get_file(
        sandbox_session: object,
        path: str,
        *,
        max_bytes: int,
    ) -> bytes | None:
        if path.endswith("/request/source.json"):
            return None
        return original_get(sandbox_session, path, max_bytes=max_bytes)  # type: ignore[arg-type]

    monkeypatch.setattr(gateway, "get_file", get_file)
    with pytest.raises(MigrationError) as source_state:
        service.get_task(task_id, "owner-1")
    assert_code(source_state, "MIGRATION_SOURCE_STATE_INVALID")


def test_ready_analysis_rejects_a_needs_input_result() -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    task_id, _ = create_uploaded_task(service)
    mark_analysis_ready(gateway, task_id)
    analysis_path = (task_id, f"{MIGRATION_ROOT}/analysis/route.json")
    analysis = json.loads(gateway.files[analysis_path])
    analysis["status"] = "needs_input"
    analysis["questions"] = [
        {"id": "entry", "prompt": "请确认项目入口", "required": True}
    ]
    gateway.files[analysis_path] = json.dumps(analysis).encode()

    with pytest.raises(MigrationError) as mismatch:
        service.get_task(task_id, "owner-1")

    assert_code(mismatch, "MIGRATION_ANALYSIS_INVALID")


def test_artifact_binding_requires_confirmation_state() -> None:
    provenance_sha256 = "1" * 64

    with pytest.raises(MigrationError) as missing:
        MigrationService._validate_result_binding(
            {
                "migration": {
                    "provenance_sha256": provenance_sha256,
                }
            },
            expected_provenance_sha256=provenance_sha256,
            expected_source_archive_sha256="2" * 64,
            confirmation=None,
        )

    assert_code(missing, "MIGRATION_CONFIRMATION_INVALID")


def test_terminal_actions_reject_invalid_state_and_delete_sessions(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])

    with pytest.raises(MigrationError) as not_running:
        service.stop(task_id, "owner-1")
    assert_code(not_running, "MIGRATION_NOT_RUNNING")

    with pytest.raises(MigrationError) as not_ready:
        service.artifact(task_id, "owner-1")
    assert_code(not_ready, "MIGRATION_ARTIFACT_NOT_READY")

    with pytest.raises(MigrationError) as not_deployable:
        service.materialize_deployment(task_id, "owner-1", tmp_path)
    assert_code(not_deployable, "MIGRATION_ARTIFACT_NOT_DEPLOYABLE")

    service.delete(task_id, "owner-1")
    assert gateway.deleted == [task_id]

    failed = service.create_task(
        CreateMigrationTaskBody(sourceFileName="failed.zip"),
        "owner-1",
        "Owner",
    )

    def fail_delete(_session: object) -> None:
        raise MigrationGatewayError(
            "MIGRATION_REMOTE_DELETE_FAILED",
            "delete failed",
            retryable=True,
        )

    monkeypatch.setattr(gateway, "delete_session", fail_delete)
    with pytest.raises(MigrationError) as delete_failed:
        service.delete(str(failed["id"]), "owner-1")
    assert_code(delete_failed, "MIGRATION_REMOTE_DELETE_FAILED")
    assert delete_failed.value.retryable is True


def test_artifact_result_rejects_missing_state_and_decision_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    session = gateway.sessions[str(created["id"])]
    ready_task = {
        "state": "succeeded",
        "artifact": {"previewReady": True},
    }

    monkeypatch.setattr(service, "_read_json", lambda *_args, **_kwargs: None)
    with pytest.raises(MigrationError) as missing_result:
        service._artifact_result(session, ready_task, readiness="previewReady")
    assert_code(missing_result, "MIGRATION_ARTIFACT_MISSING")

    states = iter([{}, None])
    monkeypatch.setattr(
        service,
        "_read_json",
        lambda *_args, **_kwargs: next(states),
    )
    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: b"confirmation")
    with pytest.raises(MigrationError) as missing_source:
        service._artifact_result(session, ready_task, readiness="previewReady")
    assert_code(missing_source, "MIGRATION_SOURCE_STATE_INVALID")

    with pytest.raises(MigrationError) as decision:
        MigrationService._validate_result_binding(
            {
                "migration": {
                    "provenance_sha256": "1" * 64,
                    "framework": "any",
                    "engine": "structured",
                }
            },
            expected_provenance_sha256="1" * 64,
            expected_source_archive_sha256="2" * 64,
            confirmation={
                "input_sha256": "2" * 64,
                "framework": "any",
                "entry": None,
            },
        )
    assert_code(decision, "MIGRATION_ARTIFACT_DECISION_MISMATCH")


def test_artifact_preview_and_download_reject_missing_or_tampered_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gateway = FakeMigrationGateway()
    service = MigrationService(gateway)
    created = service.create_task(
        CreateMigrationTaskBody(sourceFileName="source.zip"),
        "owner-1",
        "Owner",
    )
    task_id = str(created["id"])
    session = gateway.sessions[task_id]
    ready_task = {
        "state": "succeeded",
        "artifact": {"previewReady": True, "downloadReady": True},
    }
    monkeypatch.setattr(service, "_task_from_session", lambda _session: ready_task)

    monkeypatch.setattr(
        service,
        "_artifact_result",
        lambda *_args, **_kwargs: {"files": None},
    )
    with pytest.raises(MigrationError) as invalid_files:
        service.preview_file(task_id, "owner-1", "app.py")
    assert_code(invalid_files, "MIGRATION_ARTIFACT_INVALID")

    large_result = {
        "files": [
            {
                "path": "app.py",
                "size": 2 * 1024 * 1024 + 1,
                "sha256": "0" * 64,
            }
        ]
    }
    monkeypatch.setattr(
        service,
        "_artifact_result",
        lambda *_args, **_kwargs: large_result,
    )
    with pytest.raises(MigrationError) as too_large:
        service.preview_file(task_id, "owner-1", "app.py")
    assert_code(too_large, "MIGRATION_ARTIFACT_FILE_TOO_LARGE")

    preview_result = {
        "files": [
            {
                "path": "app.py",
                "size": 4,
                "sha256": hashlib.sha256(b"good").hexdigest(),
            }
        ]
    }
    monkeypatch.setattr(
        service,
        "_artifact_result",
        lambda *_args, **_kwargs: preview_result,
    )
    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: None)
    with pytest.raises(MigrationError) as missing_preview:
        service.preview_file(task_id, "owner-1", "app.py")
    assert_code(missing_preview, "MIGRATION_ARTIFACT_FILE_NOT_FOUND")

    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: b"bad")
    with pytest.raises(MigrationError) as tampered_preview:
        service.preview_file(task_id, "owner-1", "app.py")
    assert_code(tampered_preview, "MIGRATION_ARTIFACT_INTEGRITY_FAILED")

    artifact_result = {
        "artifact": {
            "size": 4,
            "sha256": hashlib.sha256(b"good").hexdigest(),
        }
    }
    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: None)
    with pytest.raises(MigrationError) as missing_artifact:
        service._verified_artifact_content(session, artifact_result)
    assert_code(missing_artifact, "MIGRATION_ARTIFACT_MISSING")

    monkeypatch.setattr(service, "_read", lambda *_args, **_kwargs: b"bad")
    with pytest.raises(MigrationError) as tampered_artifact:
        service._verified_artifact_content(session, artifact_result)
    assert_code(tampered_artifact, "MIGRATION_ARTIFACT_INTEGRITY_FAILED")

    monkeypatch.setattr(
        service,
        "_artifact_result",
        lambda *_args, **_kwargs: artifact_result,
    )
    monkeypatch.setattr(
        service,
        "_verified_artifact_content",
        lambda *_args, **_kwargs: b"zip",
    )
    monkeypatch.setattr(service, "_read_json", lambda *_args, **_kwargs: None)
    with pytest.raises(MigrationError) as missing_request:
        service.download(task_id, "owner-1")
    assert_code(missing_request, "MIGRATION_REQUEST_INVALID")
