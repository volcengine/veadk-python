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

"""Server-authoritative materialization of verified intelligent-development source."""

from __future__ import annotations

import hashlib
import json
import re
import zipfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from frontend.server.deployment_source import DeploymentSourceError, extract_migration_source
from veadk.cli.frontend_sandbox import (
    SandboxSessionNotFoundError,
    SandboxSessionUnavailableError,
)
from frontend.server.intelligent_development import RELEASE_ROOT
from frontend.server.sandbox_remote import SandboxRemoteTransport
from veadk.cli.frontend_sandbox import SandboxConversationService

_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_ARTIFACT_BYTES = 20 * 1024 * 1024
_MAX_EXPANDED_BYTES = 20 * 1024 * 1024
_MAX_FILE_COUNT = 2_000
_MAX_REPORT_BYTES = 2 * 1024 * 1024
_MAX_DESCRIPTOR_BYTES = 256 * 1024
_REQUIRED_GATES = {
    "compile",
    "service-contract",
    "ak-config",
    "ak-build",
    "ak-deploy",
    "runtime-tag",
    "runtime-ready",
    "invoke",
    "logs",
}


class IntelligentDevelopmentSourceNotFound(DeploymentSourceError):
    """The Dev Session is unavailable or not owned by the caller."""


class IntelligentDevelopmentSourceStale(DeploymentSourceError):
    """The requested release is no longer current or consistently bound."""


class IntelligentDevelopmentSourceIntegrityError(DeploymentSourceError):
    """Server-side release bytes fail cryptographic or package validation."""


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


async def materialize_intelligent_development_source(
    destination: Path,
    source: Mapping[str, object],
    *,
    owner_id: str,
    service: SandboxConversationService,
) -> TrustedDeploymentSource:
    """Authorize, verify both digests, and safely materialize one immutable release."""
    from frontend.server.intelligent_development_routes import (
        resolve_intelligent_development_session,
    )

    if set(source) != {
        "kind",
        "sessionId",
        "artifactSha256",
        "validationReportSha256",
    } or source.get("kind") != "intelligentDevelopment":
        raise DeploymentSourceError("智能开发部署来源格式无效。")
    session_id = source.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        raise DeploymentSourceError("sessionId 格式无效。")
    artifact_digest = _request_digest(source, "artifactSha256")
    report_digest = _request_digest(source, "validationReportSha256")
    try:
        cloud = await resolve_intelligent_development_session(
            service, session_id, owner_id
        )
    except (SandboxSessionNotFoundError, SandboxSessionUnavailableError) as error:
        raise IntelligentDevelopmentSourceNotFound(str(error)) from error
    transport = SandboxRemoteTransport(cloud.endpoint)
    release = f"{RELEASE_ROOT}/{artifact_digest}"
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
    passed = {
        item.get("name")
        for item in steps
        if isinstance(item, dict) and item.get("passed") is True
    } if isinstance(steps, list) else set()
    if (
        report_value.get("status") != "passed"
        or report_value.get("sessionId") != session_id
        or report_value.get("artifactSha256") != artifact_digest
        or descriptor.get("sessionId") != session_id
        or report_value.get("agentName") != descriptor.get("agentName")
        or report_value.get("entryPoint") != descriptor.get("entryPoint")
        or report_value.get("fileCount") != descriptor.get("fileCount")
        or not _REQUIRED_GATES.issubset(passed)
        or report_value.get("artifactGate") is not True
    ):
        raise DeploymentSourceError("交付物验证报告未通过全部门禁。")
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
    return TrustedDeploymentSource(
        resolved_entry,
        agent_name,
        artifact_digest,
        report_digest,
        file_count,
        artifact_size,
        str(report_value.get("validatedAt") or ""),
        tuple(sorted(str(name) for name in passed)),
    )


__all__ = [
    "IntelligentDevelopmentSourceIntegrityError",
    "IntelligentDevelopmentSourceNotFound",
    "IntelligentDevelopmentSourceStale",
    "TrustedDeploymentSource",
    "materialize_intelligent_development_source",
]
