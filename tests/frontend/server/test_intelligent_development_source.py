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

import hashlib
import io
import json
import stat
import struct
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from frontend.server import intelligent_development_source as source_module
from frontend.server.deployment_source import DeploymentSourceError
from frontend.server.intelligent_development import release_path
from frontend.server.intelligent_development_source import (
    IntelligentDevelopmentSourceNotFound,
    load_intelligent_development_artifact,
    materialize_intelligent_development_preview,
    materialize_intelligent_development_source,
)
from veadk.cli.frontend_sandbox import (
    SandboxCloudSession,
    SandboxConversationService,
)


SESSION_ID = "session-1"
OWNER_ID = "owner-1"
REPORT_DIGEST_FIELD = "validationReportSha256"
REQUIRED_GATES = (
    "local-checks",
    "service-probe",
    "ak-config",
    "ak-build",
    "ak-deploy",
    "runtime-ready",
    "acceptance-invoke",
    "runtime-logs",
    "runtime-cleanup",
)


def _digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _zip(
    entries: list[tuple[str | zipfile.ZipInfo, bytes]] | None = None,
) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in entries or [
            (
                "agentkit.yaml",
                b"common:\n  agent_name: trusted-agent\n  entry_point: app.py\n",
            ),
            ("app.py", b"root_agent = object()\n"),
            ("pkg/helper.py", b"VALUE = 1\n"),
        ]:
            archive.writestr(name, content)
    return output.getvalue()


def _encrypted_zip() -> bytes:
    value = bytearray(_zip([("app.py", b"root_agent = object()\n")]))
    local = value.index(b"PK\x03\x04")
    central = value.index(b"PK\x01\x02")
    local_flags = struct.unpack_from("<H", value, local + 6)[0]
    central_flags = struct.unpack_from("<H", value, central + 8)[0]
    struct.pack_into("<H", value, local + 6, local_flags | 1)
    struct.pack_into("<H", value, central + 8, central_flags | 1)
    return bytes(value)


def _report(
    *,
    session_id: str = SESSION_ID,
    status: str = "passed",
    artifact_gate: bool = True,
    artifact_sha256: str | None = None,
    gates: tuple[str, ...] = REQUIRED_GATES,
    failed_gate: str | None = None,
) -> bytes:
    value = {
        "status": status,
        "sessionId": session_id,
        "artifactGate": artifact_gate,
        "agentName": "trusted-agent",
        "entryPoint": "app.py",
        "fileCount": 3,
        "steps": [{"name": name, "passed": name != failed_gate} for name in gates],
    }
    if artifact_sha256 is not None:
        value["artifactSha256"] = artifact_sha256
    return _json_bytes(value)


def _release_files(
    artifact: bytes | None = None,
    report: bytes | None = None,
    *,
    entry_point: object = "app.py",
    agent_name: object = "trusted-agent",
    file_count: object | None = None,
    artifact_size: object | None = None,
    descriptor_updates: dict[str, object] | None = None,
    pointer_updates: dict[str, object] | None = None,
) -> tuple[dict[str, object], dict[str, bytes]]:
    artifact = artifact if artifact is not None else _zip()
    artifact_digest = _digest(artifact)
    if report is None:
        report = _report(artifact_sha256=artifact_digest)
    else:
        report_value = json.loads(report)
        if isinstance(report_value, dict):
            report_value.setdefault("artifactSha256", artifact_digest)
            report = _json_bytes(report_value)
    report_digest = _digest(report)
    release = release_path(artifact_digest, report_digest)
    if file_count is None:
        try:
            with zipfile.ZipFile(io.BytesIO(artifact)) as archive:
                file_count = sum(not info.is_dir() for info in archive.infolist())
        except zipfile.BadZipFile:
            file_count = 1
    descriptor: dict[str, object] = {
        "sessionId": SESSION_ID,
        "artifactSha256": artifact_digest,
        REPORT_DIGEST_FIELD: report_digest,
        "releasePath": release,
        "artifactPath": f"{release}/artifact.zip",
        "descriptorPath": f"{release}/descriptor.json",
        "validationReportPath": f"{release}/validation/{report_digest}.json",
        "entryPoint": entry_point,
        "agentName": agent_name,
        "fileCount": file_count,
        "artifactSize": len(artifact) if artifact_size is None else artifact_size,
    }
    descriptor.update(descriptor_updates or {})
    report_value = json.loads(report)
    if isinstance(report_value, dict) and not (
        descriptor_updates
        and (
            REPORT_DIGEST_FIELD in descriptor_updates
            or "validationReportPath" in descriptor_updates
        )
    ):
        report_value["agentName"] = descriptor["agentName"]
        report_value["entryPoint"] = descriptor["entryPoint"]
        report_value["fileCount"] = descriptor["fileCount"]
        report = _json_bytes(report_value)
        report_digest = _digest(report)
        descriptor[REPORT_DIGEST_FIELD] = report_digest
    release = release_path(artifact_digest, report_digest)
    descriptor.update(
        {
            "releasePath": release,
            "artifactPath": f"{release}/artifact.zip",
            "descriptorPath": f"{release}/descriptor.json",
            "validationReportPath": f"{release}/validation/{report_digest}.json",
        }
    )
    descriptor.update(descriptor_updates or {})
    pointer: dict[str, object] = {
        "artifactSha256": artifact_digest,
        REPORT_DIGEST_FIELD: report_digest,
        "releasePath": release,
    }
    pointer.update(pointer_updates or {})
    request: dict[str, object] = {
        "kind": "intelligentDevelopment",
        "sessionId": SESSION_ID,
        "artifactSha256": artifact_digest,
        REPORT_DIGEST_FIELD: report_digest,
    }
    downloads = {
        "/home/gem/.intelligent-development/published.json": _json_bytes(pointer),
        f"{release}/descriptor.json": _json_bytes(descriptor),
        f"{release}/artifact.zip": artifact,
        f"{release}/validation/{report_digest}.json": report,
    }
    return request, downloads


class FakeTransport:
    downloads: dict[str, bytes] = {}
    instances: list["FakeTransport"] = []

    def __init__(self, endpoint: str) -> None:
        self.endpoint = endpoint
        self.requests: list[tuple[str, int]] = []
        type(self).instances.append(self)

    async def download(self, path: str, *, max_bytes: int) -> bytes:
        self.requests.append((path, max_bytes))
        value = self.downloads[path]
        if len(value) > max_bytes:
            raise ValueError("download exceeds limit")
        return value


class FakeService:
    def __init__(self, cloud: SandboxCloudSession) -> None:
        self.cloud = cloud
        self.requested: list[str] = []

    async def _cloud_session(self, session_id: str) -> SandboxCloudSession:
        self.requested.append(session_id)
        return self.cloud


def _cloud(**updates: object) -> SandboxCloudSession:
    value = SandboxCloudSession(
        tool_id="tool-1",
        instance_id=SESSION_ID,
        user_session_id="workspace-1",
        endpoint="https://sandbox.example",
        status="Ready",
        expire_at="2099-01-01T00:00:00Z",
        created_by=OWNER_ID,
        agent_kind="intelligent-development",
    )
    return replace(value, **updates)


@pytest.fixture(autouse=True)
def _transport(monkeypatch: pytest.MonkeyPatch) -> None:
    FakeTransport.downloads = {}
    FakeTransport.instances = []
    monkeypatch.setattr(source_module, "SandboxRemoteTransport", FakeTransport)


async def _materialize(
    tmp_path: Path,
    request: dict[str, object],
    downloads: dict[str, bytes],
    *,
    cloud: SandboxCloudSession | None = None,
    owner_id: str = OWNER_ID,
):
    FakeTransport.downloads = downloads
    return await materialize_intelligent_development_source(
        tmp_path,
        request,
        owner_id=owner_id,
        service=cast(SandboxConversationService, FakeService(cloud or _cloud())),
    )


async def _preview(
    tmp_path: Path,
    request: dict[str, object],
    downloads: dict[str, bytes],
):
    FakeTransport.downloads = downloads
    return await materialize_intelligent_development_preview(
        tmp_path,
        request,
        owner_id=OWNER_ID,
        service=cast(SandboxConversationService, FakeService(_cloud())),
    )


@pytest.mark.asyncio
async def test_materializes_only_server_downloaded_verified_source(
    tmp_path: Path,
) -> None:
    request, downloads = _release_files()

    result = await _materialize(tmp_path, request, downloads)

    assert result.entry_point == "app.py"
    assert result.agent_name == "trusted-agent"
    assert result.artifact_sha256 == request["artifactSha256"]
    assert result.validation_report_sha256 == request[REPORT_DIGEST_FIELD]
    assert result.file_count == 3
    assert result.verified is True
    assert [(item.path, item.content) for item in result.files] == [
        (
            "agentkit.yaml",
            "common:\n  agent_name: trusted-agent\n  entry_point: app.py\n",
        ),
        ("app.py", "root_agent = object()\n"),
        ("pkg/helper.py", "VALUE = 1\n"),
    ]
    assert result.artifact_size == len(
        downloads[
            f"{release_path(result.artifact_sha256, result.validation_report_sha256)}/artifact.zip"
        ]
    )
    assert (tmp_path / "app.py").read_bytes() == b"root_agent = object()\n"
    assert (tmp_path / "pkg/helper.py").read_bytes() == b"VALUE = 1\n"
    transport = FakeTransport.instances[0]
    assert transport.endpoint == "https://sandbox.example"
    assert [maximum for _, maximum in transport.requests] == [
        256 * 1024,
        256 * 1024,
        20 * 1024 * 1024,
        2 * 1024 * 1024,
    ]


@pytest.mark.asyncio
async def test_source_preview_omits_binary_files_without_rejecting_delivery(
    tmp_path: Path,
) -> None:
    artifact = _zip(
        [
            (
                "agentkit.yaml",
                b"common:\n  agent_name: trusted-agent\n  entry_point: app.py\n",
            ),
            ("app.py", b"root_agent = object()\n"),
            ("logo.png", b"\x89PNG\x00\x01\xff"),
        ]
    )
    request, downloads = _release_files(artifact=artifact)

    result = await _materialize(tmp_path, request, downloads)

    assert [item.path for item in result.files] == ["agentkit.yaml", "app.py"]
    assert result.file_count == 3


@pytest.mark.asyncio
async def test_download_keeps_exact_artifact_including_binary_files(
    tmp_path: Path,
) -> None:
    artifact = _zip(
        [
            (
                "agentkit.yaml",
                b"common:\n  agent_name: trusted-agent\n  entry_point: app.py\n",
            ),
            ("app.py", b"root_agent = object()\n"),
            ("logo.png", b"\x89PNG\x00\x01\xff"),
        ]
    )
    request, downloads = _release_files(artifact=artifact)
    FakeTransport.downloads = downloads

    result = await load_intelligent_development_artifact(
        tmp_path,
        request,
        owner_id=OWNER_ID,
        service=cast(SandboxConversationService, FakeService(_cloud())),
    )

    assert result.content == artifact
    assert result.agent_name == "trusted-agent"
    assert result.artifact_sha256 == request["artifactSha256"]
    assert result.file_count == 3
    assert result.artifact_size == len(artifact)


@pytest.mark.asyncio
async def test_unverified_snapshot_requires_explicit_deployment_acknowledgement(
    tmp_path: Path,
) -> None:
    report = _report(status="unverified", failed_gate="runtime-cleanup")
    report_value = json.loads(report)
    report_value["validationSummary"] = "未收到完整验证结果"
    request, downloads = _release_files(report=_json_bytes(report_value))

    preview = await _preview(tmp_path / "preview", request, downloads)

    assert preview.verified is False
    assert preview.validation_summary == "未收到完整验证结果"
    assert [item.path for item in preview.files] == [
        "agentkit.yaml",
        "app.py",
        "pkg/helper.py",
    ]
    with pytest.raises(DeploymentSourceError, match="未通过全部门禁"):
        await _materialize(tmp_path / "deploy", request, downloads)
    with pytest.raises(DeploymentSourceError, match="未通过全部门禁"):
        await _materialize(
            tmp_path / "unacknowledged-deploy",
            {**request, "acknowledgeUnverified": False},
            downloads,
        )

    acknowledged = {**request, "acknowledgeUnverified": True}
    deployable = await _materialize(
        tmp_path / "acknowledged-deploy", acknowledged, downloads
    )

    assert deployable.verified is False
    assert deployable.artifact_sha256 == request["artifactSha256"]


@pytest.mark.asyncio
async def test_unverified_acknowledgement_cannot_bypass_artifact_integrity(
    tmp_path: Path,
) -> None:
    report = _report(status="unverified", failed_gate="runtime-cleanup")
    request, downloads = _release_files(report=report)
    release = release_path(
        str(request["artifactSha256"]), str(request[REPORT_DIGEST_FIELD])
    )
    downloads[f"{release}/artifact.zip"] += b"tampered"

    with pytest.raises(DeploymentSourceError, match="完整性校验失败"):
        await _materialize(
            tmp_path,
            {**request, "acknowledgeUnverified": True},
            downloads,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("owner_id", "cloud", "error"),
    [
        ("admin-1", _cloud(), IntelligentDevelopmentSourceNotFound),
        (
            "owner-1",
            _cloud(created_by="foreign-1"),
            IntelligentDevelopmentSourceNotFound,
        ),
        ("owner-1", _cloud(agent_kind="codex"), IntelligentDevelopmentSourceNotFound),
        ("owner-1", _cloud(agent_kind="other"), IntelligentDevelopmentSourceNotFound),
        ("owner-1", _cloud(status="Expired"), IntelligentDevelopmentSourceNotFound),
    ],
    ids=(
        "admin-no-bypass",
        "foreign",
        "ordinary-agent-kind",
        "wrong-agent-kind",
        "expired",
    ),
)
async def test_rejects_unowned_or_ineligible_sessions_before_remote_access(
    tmp_path: Path,
    owner_id: str,
    cloud: SandboxCloudSession,
    error: type[Exception],
) -> None:
    request, downloads = _release_files()
    with pytest.raises(error):
        await _materialize(tmp_path, request, downloads, cloud=cloud, owner_id=owner_id)
    assert FakeTransport.instances == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "request_update",
    [
        {},
        {"extra": "field"},
        {"kind": "files"},
        {"sessionId": ""},
        {"artifactSha256": "A" * 64},
        {REPORT_DIGEST_FIELD: "not-a-digest"},
        {"acknowledgeUnverified": "true"},
    ],
    ids=(
        "missing-field",
        "extra-field",
        "wrong-kind",
        "empty-session",
        "uppercase-digest",
        "bad-report-digest",
        "invalid-acknowledgement",
    ),
)
async def test_rejects_malformed_source_before_session_resolution(
    tmp_path: Path, request_update: dict[str, object]
) -> None:
    request, downloads = _release_files()
    if not request_update:
        request.pop(REPORT_DIGEST_FIELD)
    else:
        request.update(request_update)
    service = FakeService(_cloud())
    FakeTransport.downloads = downloads
    with pytest.raises(DeploymentSourceError):
        await materialize_intelligent_development_source(
            tmp_path,
            request,
            owner_id=OWNER_ID,
            service=cast(SandboxConversationService, service),
        )
    assert service.requested == []
    assert FakeTransport.instances == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifactSha256", "f" * 64),
        (REPORT_DIGEST_FIELD, "e" * 64),
        ("releasePath", "/stale/release"),
    ],
)
async def test_rejects_stale_current_pointer_before_release_downloads(
    tmp_path: Path, field: str, value: str
) -> None:
    request, downloads = _release_files(pointer_updates={field: value})
    with pytest.raises(DeploymentSourceError, match="当前发布版本"):
        await _materialize(tmp_path, request, downloads)
    assert len(FakeTransport.instances[0].requests) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("pointer", [b"not-json", b"[]"])
async def test_rejects_invalid_current_pointer_format(
    tmp_path: Path, pointer: bytes
) -> None:
    request, downloads = _release_files()
    downloads["/home/gem/.intelligent-development/published.json"] = pointer
    with pytest.raises(DeploymentSourceError, match="published.json 格式无效"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize("target", ["artifact", "report"])
async def test_rejects_each_download_digest_mismatch(
    tmp_path: Path, target: str
) -> None:
    request, downloads = _release_files()
    release = release_path(
        str(request["artifactSha256"]),
        str(request[REPORT_DIGEST_FIELD]),
    )
    path = (
        f"{release}/artifact.zip"
        if target == "artifact"
        else f"{release}/validation/{request[REPORT_DIGEST_FIELD]}.json"
    )
    downloads[path] += b"tampered"
    with pytest.raises(DeploymentSourceError, match="完整性校验失败"):
        await _materialize(tmp_path, request, downloads)
    assert not list(tmp_path.rglob("*"))


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("artifactSha256", "f" * 64),
        (REPORT_DIGEST_FIELD, "e" * 64),
        ("releasePath", "/tmp/release"),
        ("artifactPath", "/tmp/artifact.zip"),
        ("descriptorPath", "/tmp/descriptor.json"),
        ("validationReportPath", "/tmp/report.json"),
    ],
)
async def test_descriptor_binds_artifact_report_and_every_release_path(
    tmp_path: Path, field: str, value: object
) -> None:
    request, downloads = _release_files(descriptor_updates={field: value})
    with pytest.raises(DeploymentSourceError, match="描述与请求不一致"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing_gate", REQUIRED_GATES)
async def test_validation_report_requires_every_named_gate(
    tmp_path: Path, missing_gate: str
) -> None:
    gates = tuple(name for name in REQUIRED_GATES if name != missing_gate)
    request, downloads = _release_files(report=_report(gates=gates))
    with pytest.raises(DeploymentSourceError, match="未通过全部门禁"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "report",
    [
        _report(status="failed"),
        _report(session_id="other-session"),
        _report(artifact_gate=False),
        _report(artifact_sha256="f" * 64),
        _report(failed_gate="acceptance-invoke"),
        _json_bytes(
            {
                "status": "passed",
                "sessionId": SESSION_ID,
                "artifactGate": True,
                "steps": {},
            }
        ),
    ],
    ids=(
        "status",
        "session-binding",
        "artifact-gate",
        "artifact-digest-binding",
        "failed-step",
        "steps-shape",
    ),
)
async def test_validation_report_fails_closed_for_each_report_binding(
    tmp_path: Path, report: bytes
) -> None:
    request, downloads = _release_files(report=report)
    with pytest.raises(DeploymentSourceError, match="未通过全部门禁"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("fileCount", True),
        ("fileCount", 0),
        ("artifactSize", True),
        ("artifactSize", 0),
        ("agentName", ""),
        ("agentName", 1),
        ("entryPoint", ""),
        ("entryPoint", 1),
    ],
)
async def test_rejects_invalid_descriptor_metadata(
    tmp_path: Path, field: str, value: object
) -> None:
    request, downloads = _release_files(descriptor_updates={field: value})
    with pytest.raises(DeploymentSourceError, match="描述元数据无效"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("artifact", "message"),
    [
        (b"not a zip", "ZIP 格式无效"),
        (_zip([("../app.py", b"root_agent = object()\n")]), "安全"),
        (_zip([("/app.py", b"root_agent = object()\n")]), "安全"),
        (_encrypted_zip(), "ZIP 格式无效"),
    ],
    ids=("corrupt", "traversal", "absolute-path", "encrypted"),
)
async def test_rejects_corrupt_path_and_encrypted_archives(
    tmp_path: Path, artifact: bytes, message: str
) -> None:
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    with pytest.raises(DeploymentSourceError, match=message):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_symlink_zip_member(tmp_path: Path) -> None:
    link = zipfile.ZipInfo("app.py")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    artifact = _zip([(link, b"target.py")])
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    with pytest.raises(DeploymentSourceError, match="不安全文件"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_duplicate_zip_member(tmp_path: Path) -> None:
    artifact = _zip(
        [
            ("app.py", b"root_agent = object()\n"),
            ("app.py", b"root_agent = object()\n"),
        ]
    )
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    with pytest.raises(DeploymentSourceError, match="文件清单格式无效|不安全文件"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_file_directory_collision(tmp_path: Path) -> None:
    artifact = _zip([("app.py", b"root_agent = object()\n"), ("app.py/config", b"bad")])
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    with pytest.raises(DeploymentSourceError, match="文件与目录路径冲突"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_expanded_size_before_reading_zip_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _zip([("app.py", b"root_agent = object()\n")])
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    monkeypatch.setattr(source_module, "_MAX_EXPANDED_BYTES", 4)
    with pytest.raises(DeploymentSourceError, match="解压后超过"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_file_count_limit_before_reading_zip_members(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = _zip(
        [("app.py", b"root_agent = object()\n"), ("other.py", b"VALUE = 1\n")]
    )
    request, downloads = _release_files(artifact=artifact, entry_point="app.py")
    monkeypatch.setattr(source_module, "_MAX_FILE_COUNT", 1)
    with pytest.raises(DeploymentSourceError, match="文件过多"):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("entry_point", "file_count", "message"),
    [
        ("missing.py", 3, "启动文件不在文件清单"),
        ("app.py", 4, "文件清单不一致"),
    ],
    ids=("entrypoint", "file-count"),
)
async def test_descriptor_entrypoint_and_file_count_must_match_archive(
    tmp_path: Path, entry_point: str, file_count: int, message: str
) -> None:
    request, downloads = _release_files(entry_point=entry_point, file_count=file_count)
    with pytest.raises(DeploymentSourceError, match=message):
        await _materialize(tmp_path, request, downloads)


@pytest.mark.asyncio
async def test_rejects_download_over_each_server_limit(tmp_path: Path) -> None:
    request, downloads = _release_files()
    pointer_path = "/home/gem/.intelligent-development/published.json"
    downloads[pointer_path] = b" " * (256 * 1024 + 1)
    with pytest.raises(ValueError, match="download exceeds limit"):
        await _materialize(tmp_path, request, downloads)
