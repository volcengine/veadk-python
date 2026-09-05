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

from datetime import datetime, timezone
import hashlib
import io
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from frontend.server import intelligent_development_source as source_module
from frontend.server.intelligent_development_projects import (
    IntelligentDevelopmentProjectConflict,
    IntelligentDevelopmentProjectNotFound,
    IntelligentDevelopmentProjectService,
    IntelligentDevelopmentProjectStorageUnavailable,
    IntelligentDevelopmentSessionBinding,
    IntelligentDevelopmentVersion,
    IntelligentDevelopmentVersionIntegrityError,
    TosIntelligentDevelopmentProjectRepository,
)
from frontend.server.intelligent_development_projects import service as service_module
from frontend.server.intelligent_development_projects import (
    repository as repository_module,
)
from frontend.server.intelligent_development_source import TrustedDevelopmentArtifact
from veadk.cli.frontend_sandbox import SandboxSessionUnavailableError


class _TosError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"TOS {status_code}")


class FakeTos:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.fail = False
        self.fail_put_suffix = ""
        self.fail_delete_suffix = ""

    def put_object(self, *, key, content, forbid_overwrite=False, **_kwargs):
        if self.fail or (self.fail_put_suffix and key.endswith(self.fail_put_suffix)):
            raise _TosError(503)
        if forbid_overwrite and key in self.objects:
            raise _TosError(409)
        self.objects[key] = bytes(content)

    def get_object(self, *, key, **_kwargs):
        if self.fail:
            raise _TosError(503)
        if key not in self.objects:
            raise _TosError(404)
        return io.BytesIO(self.objects[key])

    def delete_object(self, *, key, **_kwargs):
        if self.fail or (
            self.fail_delete_suffix and key.endswith(self.fail_delete_suffix)
        ):
            raise _TosError(503)
        self.objects.pop(key, None)

    def list_objects_type2(self, *, prefix, **_kwargs):
        if self.fail:
            raise _TosError(503)
        return SimpleNamespace(
            contents=[
                SimpleNamespace(key=key)
                for key in sorted(self.objects)
                if key.startswith(prefix)
            ],
            is_truncated=False,
            next_continuation_token="",
        )


def _repository(tos: FakeTos) -> TosIntelligentDevelopmentProjectRepository:
    return TosIntelligentDevelopmentProjectRepository(
        bucket="studio",
        client_factory=lambda: tos,
    )


def _version(
    *,
    version_id: str,
    artifact: bytes,
    report: bytes,
    created_at: datetime,
    parent: str | None = None,
) -> IntelligentDevelopmentVersion:
    return IntelligentDevelopmentVersion(
        projectId="a" * 32,
        versionId=version_id,
        parentVersionId=parent,
        sourceSessionId="session-1",
        createdAt=created_at,
        intentSummary="生成销售周报",
        acceptanceCriteria=["可以生成结构化周报"],
        artifactSha256=hashlib.sha256(artifact).hexdigest(),
        validationReportSha256=hashlib.sha256(report).hexdigest(),
        artifactSize=len(artifact),
        fileCount=1,
        agentName="sales_report_agent",
        entryPoint="agent.py",
        verified=True,
        validationSummary="验证通过",
        gateSummary=["local-checks"],
        validatedAt=created_at.isoformat(),
    )


def test_version_metadata_enforces_shared_project_limits() -> None:
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    payload = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    ).model_dump(by_alias=True)

    IntelligentDevelopmentVersion.model_validate(
        {**payload, "artifactSize": 20 * 1024 * 1024, "fileCount": 2_000}
    )
    for updates in (
        {"artifactSize": 20 * 1024 * 1024 + 1},
        {"fileCount": 2_001},
    ):
        with pytest.raises(ValidationError):
            IntelligentDevelopmentVersion.model_validate({**payload, **updates})

    assert repository_module._MAX_ARTIFACT_BYTES == 20 * 1024 * 1024
    assert repository_module._MAX_REPORT_BYTES == 2 * 1024 * 1024


@pytest.mark.asyncio
async def test_commit_list_load_and_bind_project_version() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )

    project = await repository.commit_version(
        "owner@example.com", "销售周报 Agent", version, artifact, report
    )
    binding = IntelligentDevelopmentSessionBinding(
        ownerId="owner@example.com",
        sessionId="session/1",
        projectId=project.project_id,
        projectName=project.name,
        baseVersionId=version.version_id,
        createdAt=now,
        updatedAt=now,
    )
    await repository.put_binding(binding)

    assert [
        item.project_id for item in await repository.list_projects("owner@example.com")
    ] == ["a" * 32]
    assert [
        item.version_id
        for item in await repository.list_versions("owner@example.com", "a" * 32)
    ] == ["b" * 32]
    stored = await repository.load_version("owner@example.com", "a" * 32, "b" * 32)
    assert stored.artifact == artifact
    assert stored.validation_report == report
    assert (
        await repository.get_binding("owner@example.com", "session/1")
    ).base_version_id == "b" * 32


@pytest.mark.asyncio
async def test_uncommitted_version_objects_are_not_listed() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    await repository.commit_version("owner", "Agent", version, artifact, report)
    marker = next(key for key in tos.objects if key.endswith("/version.json"))
    tos.objects.pop(marker)

    assert await repository.list_versions("owner", "a" * 32) == []


@pytest.mark.asyncio
async def test_project_list_reconciles_a_stale_summary_from_committed_markers() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    first_time = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    second_time = datetime(2026, 8, 26, 9, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    first = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=first_time,
    )
    second = _version(
        version_id="c" * 32,
        artifact=artifact,
        report=report,
        created_at=second_time,
        parent=first.version_id,
    )
    stale = await repository.commit_version("owner", "Agent", first, artifact, report)
    await repository.commit_version("owner", "Agent", second, artifact, report)
    summary_key = next(key for key in tos.objects if key.endswith("/summary.json"))
    tos.objects[summary_key] = stale.model_dump_json(by_alias=True).encode()

    projects = await repository.list_projects("owner")

    assert len(projects) == 1
    assert projects[0].latest_version_id == second.version_id
    assert projects[0].version_count == 2


@pytest.mark.asyncio
async def test_corrupt_source_is_rejected() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    await repository.commit_version("owner", "Agent", version, artifact, report)
    source_key = next(key for key in tos.objects if key.endswith("/source.zip"))
    tos.objects[source_key] += b"tampered"

    with pytest.raises(IntelligentDevelopmentVersionIntegrityError):
        await repository.load_version("owner", "a" * 32, "b" * 32)


@pytest.mark.asyncio
async def test_delete_latest_falls_back_then_removes_empty_project() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    first_time = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    second_time = datetime(2026, 8, 26, 9, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    first = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=first_time,
    )
    second = _version(
        version_id="c" * 32,
        artifact=artifact,
        report=report,
        created_at=second_time,
        parent=first.version_id,
    )
    await repository.commit_version("owner", "Agent", first, artifact, report)
    await repository.commit_version("owner", "Agent", second, artifact, report)

    project = await repository.delete_version("owner", "a" * 32, "c" * 32)
    assert project is not None
    assert project.latest_version_id == "b" * 32
    assert project.version_count == 1
    assert await repository.delete_version("owner", "a" * 32, "b" * 32) is None
    with pytest.raises(IntelligentDevelopmentProjectNotFound):
        await repository.get_project("owner", "a" * 32)


@pytest.mark.asyncio
async def test_tos_failures_are_exposed_as_retryable_storage_errors() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    tos.fail = True

    with pytest.raises(IntelligentDevelopmentProjectStorageUnavailable):
        await repository.list_projects("owner")


@pytest.mark.asyncio
async def test_commit_is_idempotent_and_never_overwrites_an_immutable_version() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )

    first = await repository.commit_version("owner", "Agent", version, artifact, report)
    repeated = await repository.commit_version(
        "owner", "Agent", version, artifact, report
    )

    assert first.version_count == repeated.version_count == 1
    different_artifact = b"different source"
    conflicting = _version(
        version_id=version.version_id,
        artifact=different_artifact,
        report=report,
        created_at=now,
    )
    with pytest.raises(IntelligentDevelopmentProjectConflict):
        await repository.commit_version(
            "owner",
            "Agent",
            conflicting,
            different_artifact,
            report,
        )
    assert (
        await repository.load_version("owner", "a" * 32, "b" * 32)
    ).artifact == artifact


@pytest.mark.asyncio
async def test_summary_failure_rolls_back_the_version_commit_marker() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    tos.fail_put_suffix = "/summary.json"

    with pytest.raises(IntelligentDevelopmentProjectStorageUnavailable):
        await repository.commit_version("owner", "Agent", version, artifact, report)

    assert not any(key.endswith("/version.json") for key in tos.objects)
    assert not any(key.endswith("/source.zip") for key in tos.objects)
    assert not any(key.endswith("/validation.json") for key in tos.objects)


@pytest.mark.asyncio
async def test_partial_version_write_cleans_only_new_uncommitted_objects() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    tos.fail_put_suffix = "/validation.json"

    with pytest.raises(IntelligentDevelopmentProjectStorageUnavailable):
        await repository.commit_version("owner", "Agent", version, artifact, report)

    assert not any(key.endswith("/source.zip") for key in tos.objects)
    assert not any(key.endswith("/validation.json") for key in tos.objects)
    assert not any(key.endswith("/version.json") for key in tos.objects)


@pytest.mark.asyncio
async def test_delete_summary_failure_restores_version_visibility() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    await repository.commit_version("owner", "Agent", version, artifact, report)
    tos.fail_delete_suffix = "/summary.json"

    with pytest.raises(IntelligentDevelopmentProjectStorageUnavailable):
        await repository.delete_version("owner", "a" * 32, "b" * 32)

    tos.fail_delete_suffix = ""
    assert (
        await repository.get_version("owner", "a" * 32, "b" * 32)
    ).version_id == "b" * 32


@pytest.mark.asyncio
async def test_delete_keeps_logical_state_consistent_when_blob_cleanup_fails() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    await repository.commit_version("owner", "Agent", version, artifact, report)
    tos.fail_delete_suffix = "/source.zip"

    assert await repository.delete_version("owner", "a" * 32, "b" * 32) is None
    assert not any(key.endswith("/version.json") for key in tos.objects)
    with pytest.raises(IntelligentDevelopmentProjectNotFound):
        await repository.get_project("owner", "a" * 32)


@pytest.mark.asyncio
async def test_service_repairs_a_binding_after_post_commit_update_failure() -> None:
    tos = FakeTos()
    repository = _repository(tos)
    service = IntelligentDevelopmentProjectService(repository)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    binding = IntelligentDevelopmentSessionBinding(
        ownerId="owner",
        sessionId="session-1",
        projectId="a" * 32,
        projectName="Agent",
        baseVersionId=None,
        createdAt=now,
        updatedAt=now,
    )
    await repository.put_binding(binding)
    await repository.commit_version("owner", "Agent", version, artifact, report)

    resolved = await service.base_metadata("owner", "session-1")

    assert resolved is not None
    assert resolved.version_id == version.version_id
    assert (
        await repository.get_binding("owner", "session-1")
    ).base_version_id == version.version_id


@pytest.mark.asyncio
async def test_service_restores_the_bound_version_atomically(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tos = FakeTos()
    repository = _repository(tos)
    service = IntelligentDevelopmentProjectService(repository)
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"PK\x03\x04"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    await repository.commit_version("owner", "Agent", version, artifact, report)
    await repository.put_binding(
        IntelligentDevelopmentSessionBinding(
            ownerId="owner",
            sessionId="session-1",
            projectId="a" * 32,
            projectName="Agent",
            baseVersionId="b" * 32,
            createdAt=now,
            updatedAt=now,
        )
    )
    load = AsyncMock(
        return_value=TrustedDevelopmentArtifact(
            content=artifact,
            artifact_sha256=version.artifact_sha256,
            agent_name=version.agent_name,
            file_count=version.file_count,
            artifact_size=version.artifact_size,
        )
    )
    monkeypatch.setattr(
        source_module,
        "load_intelligent_development_artifact",
        load,
    )
    remote = SimpleNamespace(
        upload=AsyncMock(),
        exec_text=AsyncMock(return_value=""),
    )
    monkeypatch.setattr(
        service_module,
        "SandboxRemoteTransport",
        lambda endpoint: remote if endpoint == "https://sandbox.example" else None,
    )

    restored = await service.restore_base_version(
        owner_id="owner",
        session_id="session-1",
        endpoint="https://sandbox.example",
        workspace="/home/gem/workspace/session-1",
    )

    assert restored is True
    load_call = load.await_args
    assert load_call is not None
    source = load_call.args[1]
    assert source["projectId"] == "a" * 32
    assert source["versionId"] == "b" * 32
    assert load_call.kwargs["service"] is None
    assert load_call.kwargs["project_service"] is service
    assert remote.upload.await_args.args[1] == artifact
    assert remote.upload.await_args.kwargs == {
        "media_type": "application/zip",
        "mode": 0o600,
    }
    command = remote.exec_text.await_args.args[0]
    assert "os.replace(staging,root)" in command
    assert "workspace/session-1" in command
    assert "len(files)>2000" in command
    assert "sum(item.file_size for item in files)>20971520" in command
    assert remote.exec_text.await_args.kwargs["timeout"] == 60


@pytest.mark.asyncio
async def test_service_maps_restore_transport_failure_to_a_retryable_session_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = IntelligentDevelopmentProjectService(_repository(FakeTos()))
    now = datetime(2026, 8, 26, 8, tzinfo=timezone.utc)
    artifact = b"PK\x03\x04"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=now,
    )
    monkeypatch.setattr(
        service,
        "base_metadata",
        AsyncMock(return_value=version),
    )
    monkeypatch.setattr(
        source_module,
        "load_intelligent_development_artifact",
        AsyncMock(
            return_value=TrustedDevelopmentArtifact(
                content=artifact,
                artifact_sha256=version.artifact_sha256,
                agent_name=version.agent_name,
                file_count=version.file_count,
                artifact_size=version.artifact_size,
            )
        ),
    )
    remote = SimpleNamespace(
        upload=AsyncMock(side_effect=RuntimeError("transport unavailable")),
        exec_text=AsyncMock(),
    )
    monkeypatch.setattr(
        service_module,
        "SandboxRemoteTransport",
        lambda _endpoint: remote,
    )

    with pytest.raises(SandboxSessionUnavailableError, match="项目版本恢复失败"):
        await service.restore_base_version(
            owner_id="owner",
            session_id="session-1",
            endpoint="https://sandbox.example",
            workspace="/home/gem/workspace/session-1",
        )

    remote.exec_text.assert_not_awaited()
