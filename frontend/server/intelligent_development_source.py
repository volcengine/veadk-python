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

"""Server-authoritative preview and deployment materialization of source snapshots."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from frontend.server.deployment_source import (
    DeploymentSourceError,
    extract_migration_source,
)
from frontend.server.intelligent_development import release_path
from frontend.server.intelligent_development_projects import (
    IntelligentDevelopmentProjectService,
    IntelligentDevelopmentVersion,
    IntelligentDevelopmentVersionIntegrityError,
    IntelligentDevelopmentVersionNotFound,
)
from frontend.server.sandbox_remote import SandboxRemoteTransport
from frontend.server.source_project_limits import (
    SOURCE_PROJECT_MAX_BYTES,
    SOURCE_PROJECT_MAX_FILES,
    SOURCE_PROJECT_MAX_REPORT_BYTES,
)
from veadk.cli.frontend_sandbox import (
    SandboxConversationService,
    SandboxSessionNotFoundError,
    SandboxSessionUnavailableError,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_EXPANDED_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_FILE_COUNT = SOURCE_PROJECT_MAX_FILES
_MAX_REPORT_BYTES = SOURCE_PROJECT_MAX_REPORT_BYTES
_MAX_DESCRIPTOR_BYTES = 256 * 1024
_CURRENT_POINTER_BYTES = 4 * 1024
_MAX_PREVIEW_FILE_BYTES = 2 * 1024 * 1024
_MAX_PREVIEW_TOTAL_BYTES = SOURCE_PROJECT_MAX_BYTES
_MAX_PREVIEW_FILES = SOURCE_PROJECT_MAX_FILES
_REQUIRED_GATES = {
    "local-checks",
    "service-probe",
    "ak-config",
    "ak-build",
    "ak-deploy",
    "runtime-ready",
    "acceptance-invoke",
    "runtime-logs",
    "runtime-cleanup",
}


class IntelligentDevelopmentSourceNotFound(DeploymentSourceError):
    """The Dev Session is unavailable or not owned by the caller."""


class IntelligentDevelopmentSourceStale(DeploymentSourceError):
    """The requested release is no longer current or consistently bound."""


class IntelligentDevelopmentSourceIntegrityError(DeploymentSourceError):
    """Server-side release bytes fail cryptographic or package validation."""


@dataclass(frozen=True)
class TrustedSourceFile:
    path: str
    content: str


@dataclass(frozen=True)
class TrustedDeploymentSource:
    entry_point: str
    agent_name: str
    artifact_sha256: str
    validation_report_sha256: str
    file_count: int
    artifact_size: int
    validated_at: str
    gate_summary: tuple[str, ...]
    verified: bool
    validation_summary: str
    files: tuple[TrustedSourceFile, ...]
    project_id: str = ""
    version_id: str = ""
    environment_required: tuple[str, ...] = ()
    environment_optional: tuple[str, ...] = ()
    environment_defaults: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class TrustedDevelopmentArtifact:
    content: bytes
    artifact_sha256: str
    agent_name: str
    file_count: int
    artifact_size: int


@dataclass(frozen=True)
class _MaterializedDevelopmentRelease:
    source: TrustedDeploymentSource
    artifact: bytes


def _text_source_files(
    destination: Path,
    *,
    max_file_bytes: int | None = None,
    max_total_bytes: int | None = None,
    max_files: int | None = None,
) -> tuple[TrustedSourceFile, ...]:
    files: list[TrustedSourceFile] = []
    total_bytes = 0
    for path in sorted(destination.rglob("*")):
        if path.is_symlink() or not path.is_file():
            continue
        if max_files is not None and len(files) >= max_files:
            break
        size = path.stat().st_size
        if (max_file_bytes is not None and size > max_file_bytes) or (
            max_total_bytes is not None and total_bytes + size > max_total_bytes
        ):
            continue
        content = path.read_bytes()
        if b"\x00" in content:
            continue
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError:
            continue
        files.append(TrustedSourceFile(path.relative_to(destination).as_posix(), text))
        total_bytes += len(content)
    return tuple(files)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _object(value: bytes, name: str) -> dict[str, object]:
    try:
        parsed = json.loads(value)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise DeploymentSourceError(f"{name} 格式无效。") from error
    if not isinstance(parsed, dict):
        raise DeploymentSourceError(f"{name} 格式无效。")
    return parsed


def _request_digest(source: Mapping[str, object], field: str) -> str:
    value = source.get(field)
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise DeploymentSourceError(f"{field} 格式无效。")
    return value


async def _materialize_intelligent_development_source(
    destination: Path,
    source: Mapping[str, object],
    *,
    owner_id: str,
    service: SandboxConversationService | None,
    project_service: IntelligentDevelopmentProjectService | None,
    require_verified: bool,
) -> _MaterializedDevelopmentRelease:
    """Authorize, verify both digests, and safely materialize one immutable snapshot."""
    from frontend.server.intelligent_development_routes import (
        resolve_intelligent_development_session,
    )

    live_fields = {
        "kind",
        "sessionId",
        "artifactSha256",
        "validationReportSha256",
    }
    stored_fields = {*live_fields, "projectId", "versionId"}
    if (
        set(source)
        not in {
            frozenset(live_fields),
            frozenset({*live_fields, "acknowledgeUnverified"}),
            frozenset(stored_fields),
            frozenset({*stored_fields, "acknowledgeUnverified"}),
        }
        or source.get("kind") != "intelligentDevelopment"
    ):
        raise DeploymentSourceError("智能开发部署来源格式无效。")
    acknowledge_unverified = source.get("acknowledgeUnverified", False)
    if not isinstance(acknowledge_unverified, bool):
        raise DeploymentSourceError("智能开发部署来源格式无效。")
    session_id = source.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise DeploymentSourceError("sessionId 格式无效。")
    artifact_digest = _request_digest(source, "artifactSha256")
    report_digest = _request_digest(source, "validationReportSha256")
    project_id = source.get("projectId")
    version_id = source.get("versionId")
    stored = isinstance(project_id, str) or isinstance(version_id, str)
    metadata: IntelligentDevelopmentVersion | None = None
    if stored:
        if (
            not isinstance(project_id, str)
            or not project_id
            or not isinstance(version_id, str)
            or not version_id
        ):
            raise DeploymentSourceError("智能开发项目版本格式无效。")
        if project_service is None:
            raise IntelligentDevelopmentSourceNotFound("项目存储尚未配置。")
        try:
            bundle = await project_service.load_version(
                owner_id, project_id, version_id
            )
        except IntelligentDevelopmentVersionNotFound as error:
            raise IntelligentDevelopmentSourceNotFound(str(error)) from error
        except IntelligentDevelopmentVersionIntegrityError as error:
            raise IntelligentDevelopmentSourceIntegrityError(str(error)) from error
        metadata = bundle.metadata
        if (
            metadata.source_session_id != session_id
            or metadata.artifact_sha256 != artifact_digest
            or metadata.validation_report_sha256 != report_digest
        ):
            raise IntelligentDevelopmentSourceStale("项目版本与请求不一致。")
        descriptor = {
            "sessionId": session_id,
            "artifactSha256": artifact_digest,
            "validationReportSha256": report_digest,
            "agentName": metadata.agent_name,
            "entryPoint": metadata.entry_point,
            "fileCount": metadata.file_count,
            "artifactSize": metadata.artifact_size,
        }
        artifact = bundle.artifact
        report = bundle.validation_report
    else:
        if service is None:
            raise IntelligentDevelopmentSourceNotFound("开发环境已结束或不可用。")
        try:
            cloud = await resolve_intelligent_development_session(
                service, session_id, owner_id
            )
        except (SandboxSessionNotFoundError, SandboxSessionUnavailableError) as error:
            raise IntelligentDevelopmentSourceNotFound(str(error)) from error
        transport = SandboxRemoteTransport(cloud.endpoint)
        release = release_path(artifact_digest, report_digest)
        pointer = _object(
            await transport.download(
                "/home/gem/.intelligent-development/published.json",
                max_bytes=_MAX_DESCRIPTOR_BYTES,
            ),
            "published.json",
        )
        if (
            pointer.get("artifactSha256") != artifact_digest
            or pointer.get("validationReportSha256") != report_digest
            or pointer.get("releasePath") != release
        ):
            raise IntelligentDevelopmentSourceStale("交付物已不是当前发布版本。")
        descriptor_bytes = await transport.download(
            f"{release}/descriptor.json",
            max_bytes=_MAX_DESCRIPTOR_BYTES,
        )
        descriptor = _object(descriptor_bytes, "descriptor.json")
        artifact = await transport.download(
            f"{release}/artifact.zip",
            max_bytes=_MAX_ARTIFACT_BYTES,
        )
        report = await transport.download(
            f"{release}/validation/{report_digest}.json",
            max_bytes=_MAX_REPORT_BYTES,
        )
    if _digest(artifact) != artifact_digest or _digest(report) != report_digest:
        raise IntelligentDevelopmentSourceIntegrityError("交付物完整性校验失败。")
    stored_metadata = metadata if stored else None
    if stored_metadata is not None and stored_metadata.producer == "migration":
        from frontend.server.migration.contracts import (
            MigrationContractError,
            validate_delivery_result,
        )

        migration_report = _object(report, "migration result")
        try:
            migration_result = validate_delivery_result(
                migration_report,
                expected_run_id=session_id,
                expected_status=str(migration_report.get("status") or ""),
            )
        except MigrationContractError as error:
            raise IntelligentDevelopmentSourceIntegrityError(
                "已保存迁移版本的交付清单无效。"
            ) from error
        artifact_descriptor = migration_result.get("artifact")
        files_descriptor = migration_result.get("files")
        startup = migration_result.get("startup")
        if (
            not isinstance(artifact_descriptor, dict)
            or artifact_descriptor.get("sha256") != artifact_digest
            or artifact_descriptor.get("size") != len(artifact)
            or not isinstance(files_descriptor, list)
            or len(files_descriptor) != stored_metadata.file_count
            or not isinstance(startup, dict)
            or startup.get("module") != stored_metadata.entry_point
        ):
            raise IntelligentDevelopmentSourceIntegrityError(
                "已保存迁移版本与交付清单不一致。"
            )
        if (
            require_verified
            and not stored_metadata.verified
            and not acknowledge_unverified
        ):
            raise DeploymentSourceError("迁移版本的校验结果尚未确认。")
        resolved_entry = extract_migration_source(
            destination,
            artifact,
            migration_result,
        )
        return _MaterializedDevelopmentRelease(
            TrustedDeploymentSource(
                resolved_entry,
                stored_metadata.agent_name,
                artifact_digest,
                report_digest,
                stored_metadata.file_count,
                stored_metadata.artifact_size,
                stored_metadata.validated_at,
                tuple(stored_metadata.gate_summary),
                stored_metadata.verified,
                stored_metadata.validation_summary,
                _text_source_files(
                    destination,
                    max_file_bytes=_MAX_PREVIEW_FILE_BYTES,
                    max_total_bytes=_MAX_PREVIEW_TOTAL_BYTES,
                    max_files=_MAX_PREVIEW_FILES,
                ),
                project_id if isinstance(project_id, str) else "",
                version_id if isinstance(version_id, str) else "",
                tuple(stored_metadata.environment.required),
                tuple(stored_metadata.environment.optional),
                tuple(sorted(stored_metadata.environment.defaults.items())),
            ),
            artifact,
        )
    if not stored:
        release = release_path(artifact_digest, report_digest)
        expected_paths = {
            "artifactSha256": artifact_digest,
            "validationReportSha256": report_digest,
            "releasePath": release,
            "artifactPath": f"{release}/artifact.zip",
            "descriptorPath": f"{release}/descriptor.json",
            "validationReportPath": f"{release}/validation/{report_digest}.json",
        }
        if any(descriptor.get(key) != value for key, value in expected_paths.items()):
            raise IntelligentDevelopmentSourceStale("交付物描述与请求不一致。")
    report_value = _object(report, "validation report")
    steps = report_value.get("steps")
    passed = (
        {
            item.get("name")
            for item in steps
            if isinstance(item, dict) and item.get("passed") is True
        }
        if isinstance(steps, list)
        else set()
    )
    if (
        report_value.get("sessionId") != session_id
        or report_value.get("artifactSha256") != artifact_digest
        or descriptor.get("sessionId") != session_id
        or report_value.get("agentName") != descriptor.get("agentName")
        or report_value.get("entryPoint") != descriptor.get("entryPoint")
        or report_value.get("fileCount") != descriptor.get("fileCount")
        or report_value.get("artifactGate") is not True
    ):
        raise DeploymentSourceError("交付物验证报告未通过全部门禁。")
    verified = report_value.get("status") == "passed" and _REQUIRED_GATES.issubset(
        passed
    )
    if require_verified and not verified and not acknowledge_unverified:
        raise DeploymentSourceError("交付物验证报告未通过全部门禁。")
    validation_summary = report_value.get("validationSummary")
    if not isinstance(validation_summary, str) or not validation_summary.strip():
        validation_summary = "云端验证已通过" if verified else "验证结果尚未确认"
    file_count = descriptor.get("fileCount")
    artifact_size = descriptor.get("artifactSize")
    agent_name = descriptor.get("agentName")
    entry_point = descriptor.get("entryPoint")
    if (
        isinstance(file_count, bool)
        or not isinstance(file_count, int)
        or file_count < 1
        or isinstance(artifact_size, bool)
        or not isinstance(artifact_size, int)
        or artifact_size != len(artifact)
        or not isinstance(agent_name, str)
        or not agent_name
        or not isinstance(entry_point, str)
        or not entry_point
    ):
        raise DeploymentSourceError("交付物描述元数据无效。")
    manifest = {
        "files": [],
        "startup": {"module": entry_point},
    }
    # Reuse the hardened archive verifier by deriving its exact manifest from ZIP bytes.
    import io

    try:
        with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
            files = [info for info in archive.infolist() if not info.is_dir()]
            if len(files) != file_count:
                raise DeploymentSourceError("交付物文件清单不一致。")
            if len(files) > _MAX_FILE_COUNT:
                raise DeploymentSourceError("交付物 ZIP 文件过多。")
            if sum(info.file_size for info in files) > _MAX_EXPANDED_BYTES:
                raise DeploymentSourceError("交付物 ZIP 解压后超过限制。")
            manifest["files"] = [
                {
                    "path": info.filename,
                    "size": info.file_size,
                    "sha256": _digest(archive.read(info)),
                }
                for info in files
            ]
    except (zipfile.BadZipFile, RuntimeError) as error:
        raise DeploymentSourceError("交付物 ZIP 格式无效。") from error
    resolved_entry = extract_migration_source(destination, artifact, manifest)
    source_files = _text_source_files(destination)
    return _MaterializedDevelopmentRelease(
        TrustedDeploymentSource(
            resolved_entry,
            agent_name,
            artifact_digest,
            report_digest,
            file_count,
            artifact_size,
            str(report_value.get("validatedAt") or ""),
            tuple(sorted(str(name) for name in passed)),
            verified,
            validation_summary.strip(),
            source_files,
            project_id if isinstance(project_id, str) else "",
            version_id if isinstance(version_id, str) else "",
        ),
        artifact,
    )


async def materialize_intelligent_development_source(
    destination: Path,
    source: Mapping[str, object],
    *,
    owner_id: str,
    service: SandboxConversationService | None,
    project_service: IntelligentDevelopmentProjectService | None = None,
) -> TrustedDeploymentSource:
    """Materialize a verified snapshot or an explicitly acknowledged one."""
    release = await _materialize_intelligent_development_source(
        destination,
        source,
        owner_id=owner_id,
        service=service,
        project_service=project_service,
        require_verified=True,
    )
    return release.source


async def materialize_intelligent_development_preview(
    destination: Path,
    source: Mapping[str, object],
    *,
    owner_id: str,
    service: SandboxConversationService | None,
    project_service: IntelligentDevelopmentProjectService | None = None,
) -> TrustedDeploymentSource:
    """Materialize a digest-bound snapshot without authorizing deployment."""
    release = await _materialize_intelligent_development_source(
        destination,
        source,
        owner_id=owner_id,
        service=service,
        project_service=project_service,
        require_verified=False,
    )
    return release.source


async def materialize_current_intelligent_development_preview(
    destination: Path,
    session_id: str,
    *,
    owner_id: str,
    service: SandboxConversationService,
) -> TrustedDeploymentSource | None:
    """Return the current owner-scoped release, or None before first delivery."""
    from frontend.server.intelligent_development import CURRENT_POINTER
    from frontend.server.intelligent_development_routes import (
        resolve_intelligent_development_session,
    )

    cloud = await resolve_intelligent_development_session(service, session_id, owner_id)
    source = (
        "import json,os,stat\n"
        f"path={CURRENT_POINTER!r}; limit={_CURRENT_POINTER_BYTES}\n"
        "try:\n"
        " fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))\n"
        "except FileNotFoundError:\n"
        " print(json.dumps({'exists':False},separators=(',',':')))\n"
        "else:\n"
        " try:\n"
        "  metadata=os.fstat(fd)\n"
        "  if not stat.S_ISREG(metadata.st_mode): raise ValueError('not regular')\n"
        "  with os.fdopen(fd,'rb',closefd=False) as stream: content=stream.read(limit+1)\n"
        " finally:\n"
        "  os.close(fd)\n"
        " if len(content)>limit: raise ValueError('pointer too large')\n"
        " pointer=json.loads(content)\n"
        " print(json.dumps({'exists':True,'pointer':pointer},separators=(',',':')))\n"
    )
    envelope = await SandboxRemoteTransport(cloud.endpoint).exec_json(
        f"python3 -c {shlex.quote(source)}", timeout=12
    )
    if envelope == {"exists": False}:
        return None
    pointer = envelope.get("pointer")
    if set(envelope) != {"exists", "pointer"} or envelope.get("exists") is not True:
        raise DeploymentSourceError("当前交付物索引格式无效。")
    if not isinstance(pointer, dict) or set(pointer) != {
        "artifactSha256",
        "validationReportSha256",
        "releasePath",
    }:
        raise DeploymentSourceError("当前交付物索引格式无效。")
    artifact_digest = _request_digest(pointer, "artifactSha256")
    report_digest = _request_digest(pointer, "validationReportSha256")
    if pointer.get("releasePath") != release_path(artifact_digest, report_digest):
        raise IntelligentDevelopmentSourceStale("交付物索引与当前发布版本不一致。")
    return await materialize_intelligent_development_preview(
        destination,
        {
            "kind": "intelligentDevelopment",
            "sessionId": session_id,
            "artifactSha256": artifact_digest,
            "validationReportSha256": report_digest,
        },
        owner_id=owner_id,
        service=service,
        project_service=None,
    )


async def load_intelligent_development_artifact(
    destination: Path,
    source: Mapping[str, object],
    *,
    owner_id: str,
    service: SandboxConversationService | None,
    project_service: IntelligentDevelopmentProjectService | None = None,
) -> TrustedDevelopmentArtifact:
    """Load an exact archive only after the preview trust checks succeed."""
    release = await _materialize_intelligent_development_source(
        destination,
        source,
        owner_id=owner_id,
        service=service,
        project_service=project_service,
        require_verified=False,
    )
    trusted = release.source
    return TrustedDevelopmentArtifact(
        release.artifact,
        trusted.artifact_sha256,
        trusted.agent_name,
        trusted.file_count,
        trusted.artifact_size,
    )


__all__ = [
    "IntelligentDevelopmentSourceIntegrityError",
    "IntelligentDevelopmentSourceNotFound",
    "IntelligentDevelopmentSourceStale",
    "TrustedDeploymentSource",
    "TrustedDevelopmentArtifact",
    "TrustedSourceFile",
    "load_intelligent_development_artifact",
    "materialize_current_intelligent_development_preview",
    "materialize_intelligent_development_preview",
    "materialize_intelligent_development_source",
]
