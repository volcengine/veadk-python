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

"""Tests for the authenticated Studio release service."""

from __future__ import annotations

import hashlib
import importlib.machinery
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import zipfile
from collections.abc import Callable
from concurrent.futures import Executor, Future
from contextlib import nullcontext
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient

from frontend.service.studio_release_server import (
    BuildResult,
    ReleaseRequest,
    ReleaseServerSettings,
    ReleaseService,
    ReleaseStatus,
    SourceUpload,
    StudioReleaseBuilder,
    create_app,
)
from frontend.service.studio_release_server import app as release_app
from frontend.service.studio_release_server import builder as release_builder
from frontend.service.studio_release_server import deploy as release_deploy
from frontend.service.studio_release_server import publisher as release_publisher
from frontend.service.studio_release_server.tos_store import (
    TosDependencyStore,
    TosJobStore,
)


def _write_test_wheel(
    path: Path,
    *,
    name: str,
    version: str,
    license_expression: str = "MIT",
    marker: str = "",
) -> None:
    """Write a minimal deterministic wheel with auditable license metadata."""

    distribution = name.replace("-", "_")
    metadata = (
        "Metadata-Version: 2.4\n"
        f"Name: {name}\n"
        f"Version: {version}\n"
        f"License-Expression: {license_expression}\n"
    )
    with zipfile.ZipFile(path, "w") as archive:
        for filename, content in (
            (f"{distribution}/__init__.py", marker),
            (f"{distribution}-{version}.dist-info/METADATA", metadata),
        ):
            info = zipfile.ZipInfo(filename, date_time=(2025, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)


def _pypi_lock(*items: tuple[str, str, Path]) -> str:
    return "".join(
        "[[package]]\n"
        f'name = "{name}"\n'
        f'version = "{version}"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        'wheels = [{ url = "https://files.pythonhosted.org/packages/'
        f'{wheel.name}", hash = "sha256:'
        f'{hashlib.sha256(wheel.read_bytes()).hexdigest()}", size = '
        f"{wheel.stat().st_size} }}]\n"
        for name, version, wheel in items
    )


class _InlineExecutor(Executor):
    def submit(self, function: Any, *args: Any, **kwargs: Any) -> Future[None]:
        future: Future[None] = Future()
        try:
            function(*args, **kwargs)
        except Exception as error:  # noqa: BLE001  # pragma: no cover
            future.set_exception(error)
        else:
            future.set_result(None)
        return future


class _MemoryStore:
    def __init__(self) -> None:
        self.statuses: dict[str, ReleaseStatus] = {}

    def get(self, job_id: str) -> ReleaseStatus | None:
        return self.statuses.get(job_id)

    def put(self, status: ReleaseStatus) -> None:
        self.statuses[status.job_id] = status


class _MemorySourceStore:
    def expected_key(self, job_id: str) -> str:
        return f"veadk/studio/release-server/jobs/sources/{job_id}.tar.gz"

    def prepare_upload(self, job_id: str) -> SourceUpload:
        return SourceUpload(
            sourceKey=self.expected_key(job_id),
            uploadUrl="https://example.com/private-source-upload",
            expiresIn=900,
        )

    def download_and_delete(
        self,
        source_key: str,
        destination: Path,
        *,
        max_bytes: int,
        on_progress: Callable[[int], None],
    ) -> None:
        raise AssertionError("Unexpected source download")


class _ArchiveSourceStore(_MemorySourceStore):
    def __init__(self, archive: Path) -> None:
        self.archive = archive
        self.consumed_key = ""

    def download_and_delete(
        self,
        source_key: str,
        destination: Path,
        *,
        max_bytes: int,
        on_progress: Callable[[int], None],
    ) -> None:
        assert self.archive.stat().st_size <= max_bytes
        shutil.copyfile(self.archive, destination)
        on_progress(destination.stat().st_size)
        self.consumed_key = source_key


class _SuccessfulBuilder:
    def build(self, request: ReleaseRequest, on_progress: Any) -> BuildResult:
        on_progress("building", "building")
        return BuildResult(
            version="20260724235959",
            gitSha=request.git_sha,
            sha256="b" * 64,
            size=123,
            createdAt="2026-07-24T23:59:59+08:00",
            timings={"totalSeconds": 1.25},
        )


class _NotFoundError(Exception):
    status_code = 404


class _DependencyCacheClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        try:
            return [self.objects[(bucket, key)]]
        except KeyError as error:
            raise _NotFoundError(key) from error

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        assert content_type == "application/octet-stream"
        self.objects[(bucket, key)] = content


class _MemoryDependencyStore:
    def __init__(self) -> None:
        self.manifest: Path | None = None

    def materialize(
        self,
        manifest: Path,
        destination: Path,
    ) -> tuple[Path, ...]:
        self.manifest = manifest
        destination.mkdir(parents=True)
        wheel = destination / "dependency.whl"
        wheel.write_bytes(b"wheel")
        return (wheel,)


def _settings(
    *,
    provider: str = "volcengine",
    thin_releases: bool = False,
) -> ReleaseServerSettings:
    return ReleaseServerSettings(
        api_key="release-key-with-at-least-thirty-two-characters",
        bucket="veadk-studio",
        region="ap-southeast-1" if provider == "byteplus" else "cn-beijing",
        release_prefix="veadk/studio/main",
        job_prefix="veadk/studio/release-server/jobs",
        repository="volcengine/veadk-python",
        provider=provider,  # type: ignore[arg-type]
        thin_releases=thin_releases,
    )


def _request(request_id: str = "12345-1") -> ReleaseRequest:
    return ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId=request_id,
        changelog=("发布 Studio 更新",),
    )


def test_release_request_accepts_one_shared_version_for_all_providers() -> None:
    request = ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId="shared-version",
        version="20260828123045",
    )

    assert request.version == "20260828123045"
    assert request.thin_bundle is False
    with pytest.raises(ValueError, match="YYYYMMDDHHMMSS"):
        ReleaseRequest(
            repository="volcengine/veadk-python",
            gitSha="a" * 40,
            requestId="invalid-version",
            version="latest",
        )


def test_release_request_accepts_explicit_thin_bundle_opt_in() -> None:
    request = ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId="thin-release",
        thinBundle=True,
    )

    assert request.thin_bundle is True
    with pytest.raises(ValueError):
        ReleaseRequest(
            repository="volcengine/veadk-python",
            gitSha="a" * 40,
            requestId="coerced-thin-release",
            thinBundle="true",  # type: ignore[arg-type]
        )


def test_release_server_settings_load_byteplus_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_RELEASE_SERVER_API_KEY", "x" * 32)
    monkeypatch.setenv("STUDIO_RELEASE_BUCKET", "veadk-studio")
    monkeypatch.setenv("STUDIO_RELEASE_REGION", "ap-southeast-1")
    monkeypatch.setenv("STUDIO_RELEASE_PROVIDER", "byteplus")

    settings = ReleaseServerSettings.from_env()

    assert settings.provider == "byteplus"
    assert settings.region == "ap-southeast-1"


def test_release_server_settings_reject_ambiguous_thin_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("STUDIO_RELEASE_SERVER_API_KEY", "x" * 32)
    monkeypatch.setenv("STUDIO_RELEASE_BUCKET", "veadk-studio")
    monkeypatch.setenv("STUDIO_RELEASE_THIN_BUNDLES", "enabled")

    with pytest.raises(ValueError, match="explicit boolean"):
        ReleaseServerSettings.from_env()


def _service() -> ReleaseService:
    settings = _settings()
    source_store = _MemorySourceStore()
    return ReleaseService(
        settings=settings,
        store=_MemoryStore(),
        builder=_SuccessfulBuilder(),
        source_store=source_store,
        executor=_InlineExecutor(),
    )


def test_submit_is_idempotent_and_persists_success() -> None:
    service = _service()

    first = service.submit(_request())
    second = service.submit(_request())
    status = service.get(first.job_id)

    assert first.state == "queued"
    assert second.state == "succeeded"
    assert status.state == "succeeded"
    assert status.result is not None
    assert status.result.git_sha == "a" * 40


def test_api_requires_key_and_returns_durable_status() -> None:
    settings = _settings()
    app = create_app(settings=settings, service=_service())

    with TestClient(app) as client:
        unauthorized = client.post(
            "/release", json=_request().model_dump(by_alias=True)
        )
        accepted = client.post(
            "/release",
            headers={"X-API-Key": settings.api_key},
            json=_request("12346-1").model_dump(by_alias=True),
        )
        current = client.get(
            "/status/12346-1",
            headers={"X-API-Key": settings.api_key},
        )

    assert unauthorized.status_code == 401
    assert accepted.status_code == 202
    events = [
        json.loads(line.removeprefix("data: "))
        for line in accepted.text.splitlines()
        if line.startswith("data: ")
    ]
    assert current.status_code == 200
    assert current.json()["state"] == "succeeded"
    assert current.json()["result"]["gitSha"] == "a" * 40
    assert events[-1]["state"] == "succeeded"


def test_readiness_requires_the_active_revision_api_key() -> None:
    settings = _settings()
    app = create_app(settings=settings, service=_service())

    with TestClient(app) as client:
        unauthorized = client.get("/readyz")
        ready = client.get(
            "/readyz",
            headers={"X-API-Key": settings.api_key},
        )

    assert unauthorized.status_code == 401
    assert ready.json() == {"status": "ready"}


def test_release_stream_emits_terminal_change_with_same_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    timestamp = "2026-07-26T16:00:00+08:00"
    queued = ReleaseStatus(
        jobId="12345-1",
        state="queued",
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        stage="queued",
        message="queued",
        createdAt=timestamp,
        updatedAt=timestamp,
    )
    succeeded = queued.model_copy(
        update={
            "state": "succeeded",
            "stage": "complete",
            "message": "complete",
        }
    )

    class _SameTimestampService:
        def __init__(self) -> None:
            self.reads = 0

        def submit(self, _request: ReleaseRequest) -> ReleaseStatus:
            return queued

        def get(self, _job_id: str) -> ReleaseStatus:
            self.reads += 1
            return queued if self.reads == 1 else succeeded

    monkeypatch.setattr(release_app.time, "sleep", lambda _seconds: None)
    app = create_app(settings=_settings(), service=_SameTimestampService())

    with TestClient(app) as client:
        response = client.post(
            "/release",
            headers={"X-API-Key": _settings().api_key},
            json=_request().model_dump(by_alias=True),
        )

    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert [event["state"] for event in events] == ["queued", "succeeded"]


def test_api_rejects_another_repository() -> None:
    settings = _settings()
    app = create_app(settings=settings, service=_service())
    payload = _request().model_dump(by_alias=True)
    payload["repository"] = "another/repository"

    with TestClient(app) as client:
        response = client.post(
            "/release",
            headers={"X-API-Key": settings.api_key},
            json=payload,
        )

    assert response.status_code == 400
    assert (
        response.json()["detail"] == "repository is not allowed by this release server"
    )


def test_source_upload_requires_key_and_returns_job_bound_key() -> None:
    settings = _settings()
    app = create_app(settings=settings, service=_service())

    with TestClient(app) as client:
        unauthorized = client.post(
            "/source-upload",
            json={"requestId": "12347-1"},
        )
        prepared = client.post(
            "/source-upload",
            headers={"X-API-Key": settings.api_key},
            json={"requestId": "12347-1"},
        )

    assert unauthorized.status_code == 401
    assert prepared.status_code == 200
    assert prepared.json() == {
        "sourceKey": ("veadk/studio/release-server/jobs/sources/12347-1.tar.gz"),
        "uploadUrl": "https://example.com/private-source-upload",
        "expiresIn": 900,
    }


def test_release_rejects_source_key_for_another_job() -> None:
    settings = _settings()
    app = create_app(settings=settings, service=_service())
    payload = _request("12348-1").model_dump(by_alias=True)
    payload["sourceKey"] = "veadk/studio/release-server/jobs/sources/another-job.tar.gz"

    with TestClient(app) as client:
        response = client.post(
            "/release",
            headers={"X-API-Key": settings.api_key},
            json=payload,
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "sourceKey does not belong to requestId"


def test_builder_consumes_staged_source_archive(tmp_path: Path) -> None:
    git_sha = "a" * 40
    source_root = tmp_path / f"veadk-python-{git_sha}"
    frontend = source_root / "frontend"
    frontend.mkdir(parents=True)
    (frontend / "package.json").write_text("{}\n", encoding="utf-8")
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        output.add(source_root, arcname=source_root.name)

    source_store = _ArchiveSourceStore(archive)
    request = _request("12349-1").model_copy(
        update={"source_key": source_store.expected_key("12349-1")}
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    builder = StudioReleaseBuilder(_settings(), source_store=source_store)

    extracted = builder._download_source(
        request,
        workspace,
        lambda _stage, _message: None,
    )

    assert (extracted / "frontend" / "package.json").is_file()
    assert source_store.consumed_key == request.source_key


def test_builder_prefers_domestic_source_and_node_mirrors() -> None:
    request = _request()
    builder = StudioReleaseBuilder(_settings())

    assert builder._source_clone_urls(request) == (
        "https://github.com/volcengine/veadk-python.git",
        "https://ghfast.top/https://github.com/volcengine/veadk-python.git",
    )
    assert builder._source_urls(request) == (
        (
            "https://ghfast.top/https://github.com/volcengine/veadk-python/"
            f"archive/{request.git_sha}.tar.gz"
        ),
        (
            "https://codeload.github.com/volcengine/veadk-python/tar.gz/"
            f"{request.git_sha}"
        ),
    )
    assert builder._node_download_urls("node.tar.xz") == (
        "https://registry.npmmirror.com/-/binary/node/v22.17.0/node.tar.xz",
        "https://nodejs.org/dist/v22.17.0/node.tar.xz",
    )


def test_builder_passes_only_publisher_runtime_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request().model_copy(update={"thin_bundle": True})
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        release_builder,
        "resolve_credentials",
        lambda _provider: SimpleNamespace(
            access_key="release-ak",
            secret_key="release-sk",
            session_token="release-sts",
        ),
    )

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(release_builder.subprocess, "run", _run)
    monkeypatch.setenv(
        "NODE_OPTIONS",
        "--trace-warnings --max-old-space-size=1024",
    )
    monkeypatch.setattr(release_builder, "_node_heap_limit_mb", lambda: 24_576)
    builder = StudioReleaseBuilder(_settings(thin_releases=True))

    builder._run_publisher(
        request=request,
        source_root=tmp_path,
        output_dir=tmp_path / "dist",
        version="20260805170000",
        node_bin=None,
        uv=Path("/bin/uv"),
        frontend_assets=None,
        dependency_wheels=tmp_path,
    )

    assert "VEADK_STUDIO_APMPLUS_AID" not in captured["env"]
    assert "VEADK_STUDIO_APMPLUS_TOKEN" not in captured["env"]
    assert captured["env"]["VOLCENGINE_ACCESS_KEY"] == "release-ak"
    assert captured["env"]["NODE_OPTIONS"] == (
        "--trace-warnings --max-old-space-size=24576"
    )
    assert captured["command"][1].endswith("studio_release_server/publisher.py")
    assert (
        captured["command"][captured["command"].index("--release-contract") + 1]
        == "agentkit-cli-v1"
    )
    assert "--thin" in captured["command"]
    assert "veadk.cli.studio_release" not in captured["command"]
    assert str(tmp_path) not in captured["env"].get("PYTHONPATH", "").split(os.pathsep)


def test_builder_rejects_thin_request_without_server_opt_in(tmp_path: Path) -> None:
    request = _request().model_copy(update={"thin_bundle": True})
    builder = StudioReleaseBuilder(_settings(thin_releases=False))

    with pytest.raises(RuntimeError, match="not enabled"):
        builder._run_publisher(
            request=request,
            source_root=tmp_path,
            output_dir=tmp_path / "dist",
            version="20260805170000",
            node_bin=None,
            uv=Path("/bin/uv"),
            frontend_assets=None,
            dependency_wheels=tmp_path,
        )


def test_byteplus_builder_uses_local_tos_endpoint_and_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        release_builder,
        "resolve_credentials",
        lambda provider: SimpleNamespace(
            access_key=f"{provider}-ak",
            secret_key=f"{provider}-sk",
            session_token="",
        ),
    )

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(release_builder.subprocess, "run", _run)
    builder = StudioReleaseBuilder(_settings(provider="byteplus"))
    builder._run_publisher(
        request=_request(),
        source_root=tmp_path,
        output_dir=tmp_path / "dist",
        version="20260828123045",
        node_bin=None,
        uv=Path("/bin/uv"),
        frontend_assets=None,
        dependency_wheels=tmp_path,
    )

    assert captured["command"][captured["command"].index("--provider") + 1] == (
        "byteplus"
    )
    assert captured["env"]["BYTEPLUS_ACCESS_KEY"] == "byteplus-ak"
    assert captured["env"]["BYTEPLUS_SECRET_KEY"] == "byteplus-sk"
    assert "--thin" not in captured["command"]


def test_byteplus_runtime_store_uses_byteplus_tos_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "frontend.service.studio_release_server.tos_store.resolve_credentials",
        lambda provider: SimpleNamespace(
            access_key=f"{provider}-ak",
            secret_key=f"{provider}-sk",
            session_token="",
        ),
    )

    def _client(*args: Any, **kwargs: Any) -> object:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("tos.TosClientV2", _client)

    TosJobStore(_settings(provider="byteplus"))._new_client()

    assert captured["args"][:2] == ("byteplus-ak", "byteplus-sk")
    assert captured["kwargs"]["endpoint"] == ("tos-ap-southeast-1.bytepluses.com")


def test_standalone_publisher_uses_byteplus_tos_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def _client(*args: Any, **kwargs: Any) -> object:
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr("tos.TosClientV2", _client)

    release_publisher.StudioReleaseStore(
        bucket="veadk-studio",
        region="ap-southeast-1",
        provider="byteplus",
        access_key="ak",
        secret_key="sk",
        session_token="",
        prefix="veadk/studio/main",
    )

    assert captured["kwargs"]["endpoint"] == ("tos-ap-southeast-1.bytepluses.com")


def test_builder_sizes_node_heap_from_cgroup_memory(tmp_path: Path) -> None:
    cgroup_v2 = tmp_path / "memory.max"
    cgroup_v2.write_text(str(32 * 1024**3), encoding="utf-8")

    memory_limit = release_builder._memory_limit_bytes(
        cgroup_paths=(cgroup_v2,),
        physical_memory=64 * 1024**3,
    )

    assert memory_limit == 32 * 1024**3
    assert release_builder._node_heap_limit_mb(memory_limit) == 24_576


def test_builder_ignores_unlimited_cgroup_memory(tmp_path: Path) -> None:
    cgroup_v1 = tmp_path / "memory.limit_in_bytes"
    cgroup_v1.write_text("9223372036854771712", encoding="utf-8")

    memory_limit = release_builder._memory_limit_bytes(
        cgroup_paths=(cgroup_v1,),
        physical_memory=16 * 1024**3,
    )

    assert memory_limit == 16 * 1024**3
    assert release_builder._node_heap_limit_mb(memory_limit) == 12_288


def test_builder_replaces_node_heap_option_aliases() -> None:
    assert (
        release_builder._node_options(
            "--max_old_space_size 1024 --trace-warnings",
            8192,
        )
        == "--trace-warnings --max-old-space-size=8192"
    )


def test_standalone_publisher_starts_without_importing_veadk() -> None:
    publisher = Path(release_builder.__file__).with_name("publisher.py")

    completed = subprocess.run(
        [sys.executable, "-I", str(publisher), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_standalone_publisher_exposes_release_changelog_to_vite(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_dir = tmp_path / "frontend-output"
    captured: list[str] = []

    monkeypatch.setattr(
        release_publisher, "_validate_source_checkout", lambda _root: None
    )
    monkeypatch.setattr(
        release_publisher.shutil,
        "which",
        lambda _name, path=None: "/bin/npm",
    )

    def _run(command: list[str], **kwargs: Any) -> None:
        environment = kwargs["env"]
        captured.append(environment["VITE_STUDIO_RELEASE_CHANGELOG"])
        if "build" in command:
            output_dir.mkdir()
            (output_dir / "index.html").write_text("studio", encoding="utf-8")

    monkeypatch.setattr(release_publisher.subprocess, "run", _run)

    release_publisher._build_frontend_assets(
        tmp_path,
        output_dir,
        {"PATH": os.environ["PATH"]},
        changelog=("新增能力;修复问题", "优化体验"),
    )

    assert captured == [
        '["新增能力;修复问题", "优化体验"]',
        '["新增能力;修复问题", "优化体验"]',
    ]


def test_standalone_publisher_builds_bundle_from_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend_assets = tmp_path / "frontend-assets"
    frontend_assets.mkdir()
    (frontend_assets / "index.html").write_text("studio", encoding="utf-8")
    dependency_wheels = tmp_path / "dependencies"
    dependency_wheels.mkdir()
    _write_test_wheel(
        dependency_wheels / "six-1.17.0-py2.py3-none-any.whl",
        name="six",
        version="1.17.0",
    )
    cli_archive = dependency_wheels / "agentkit-linux-x64.tar.gz"
    cli_archive.write_bytes(b"pinned-cli")
    monkeypatch.setattr(
        release_publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(cli_archive.read_bytes()).hexdigest(),
    )

    def _run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[Any]:
        output_dir = Path(command[command.index("-o") + 1])
        with zipfile.ZipFile(
            output_dir / "veadk_python-1.0.0-py3-none-any.whl", "w"
        ) as wheel:
            for name in release_publisher.studio_runtime_modules(
                Path(__file__).parents[1]
            ):
                wheel.writestr(name, "")
            wheel.writestr(
                "veadk_python-1.0.0.dist-info/METADATA",
                "Metadata-Version: 2.4\nName: veadk-python\nVersion: 1.0.0\n"
                "License-Expression: Apache-2.0\n",
            )
        return subprocess.CompletedProcess(command, 0)

    def _offline_runtime(
        _source_root: Path,
        package_dir: Path,
        *,
        veadk_wheel: Path,
        **_kwargs: Any,
    ) -> str:
        target = package_dir / veadk_wheel.name
        target.write_bytes(veadk_wheel.read_bytes())
        _write_test_wheel(
            package_dir / "six-1.17.0-py2.py3-none-any.whl",
            name="six",
            version="1.17.0",
        )
        (package_dir / "studio-runtime.lock").write_text(
            "dependency==1.0\n",
            encoding="utf-8",
        )
        return (
            "--no-index\n"
            "--require-hashes\n"
            "./six-1.17.0-py2.py3-none-any.whl --hash=sha256:test\n"
            f"./{target.name} --hash=sha256:test\n"
        )

    monkeypatch.setattr(release_publisher.subprocess, "run", _run)
    monkeypatch.setattr(
        release_publisher,
        "build_studio_offline_runtime",
        _offline_runtime,
    )
    output_dir = tmp_path / "output"
    bundle, manifest = release_publisher.build_studio_release(
        source_root=Path(__file__).parents[1],
        output_dir=output_dir,
        version="20260805190000",
        git_sha="a" * 40,
        changelog=("发布 Studio 更新",),
        frontend_assets=frontend_assets,
        dependency_wheels=dependency_wheels,
        env={"PATH": os.environ["PATH"]},
    )

    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("requirements.txt").decode() == (
            "--no-index\n"
            "--require-hashes\n"
            "./six-1.17.0-py2.py3-none-any.whl --hash=sha256:test\n"
            "./veadk_python-1.0.0-py3-none-any.whl --hash=sha256:test\n"
        )
        assert not any(name.startswith("wheelhouse/") for name in archive.namelist())
        assert len([name for name in archive.namelist() if name.endswith(".whl")]) == 2
        assert archive.read("agentkit-linux-x64.tar.gz") == b"pinned-cli"
        assert ".studio-release-environment.json" not in archive.namelist()
        assert (
            b'--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}"'
            in archive.read("run.sh")
        )
        assert (
            b'export PYTHONPATH="./site-packages${PYTHONPATH:+:$PYTHONPATH}"'
            in archive.read("run.sh")
        )
        assert b"python3 -m veadk.cli.studio_companion" in archive.read("run.sh")
    assert manifest.git_sha == "a" * 40
    assert manifest.sha256 == hashlib.sha256(bundle.read_bytes()).hexdigest()

    monkeypatch.setattr(
        release_publisher,
        "validate_public_runtime_provenance",
        lambda _source_root, _wheels: None,
    )
    thin_output = tmp_path / "thin-output"
    full_bundle, thin_manifest = release_publisher.build_studio_release(
        source_root=Path(__file__).parents[1],
        output_dir=thin_output,
        version="20260805190001",
        git_sha="a" * 40,
        changelog=("发布 Studio 瘦包",),
        frontend_assets=frontend_assets,
        dependency_wheels=dependency_wheels,
        env={"PATH": os.environ["PATH"]},
        thin=True,
        provider="volcengine",
    )
    thin_bundle = thin_output / "studio-bundle-20260805190001-thin.zip"
    assert thin_manifest.runtime_epoch
    assert thin_manifest.sha256 == hashlib.sha256(full_bundle.read_bytes()).hexdigest()
    assert thin_manifest.size == full_bundle.stat().st_size
    assert thin_manifest.thin_size == thin_bundle.stat().st_size
    assert (
        thin_manifest.thin_sha256
        == hashlib.sha256(thin_bundle.read_bytes()).hexdigest()
    )
    with zipfile.ZipFile(thin_bundle) as archive:
        names = archive.namelist()
        assert "studio-runtime.json" in names
        assert "agentkit-linux-x64.tar.gz" not in names
        assert not any(name.startswith("wheelhouse/") for name in names)
        assert b"--runtime-manifest" in archive.read("run.sh")
    with zipfile.ZipFile(full_bundle) as archive:
        assert archive.read("agentkit-linux-x64.tar.gz") == b"pinned-cli"
        assert not any(name.startswith("wheelhouse/") for name in archive.namelist())
        assert len([name for name in archive.namelist() if name.endswith(".whl")]) == 2
    extracted = tmp_path / "thin-extracted"
    with zipfile.ZipFile(thin_bundle) as archive:
        archive.extractall(extracted)
    assert release_publisher.validate_studio_bundle_dependencies(extracted) == (
        extracted / "studio-runtime.json"
    )


def test_publisher_repairs_missing_agentkit_cli_before_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_wheels = tmp_path / "dependencies"
    dependency_wheels.mkdir()
    cli_archive = dependency_wheels / "agentkit-linux-x64.tar.gz"
    cli_archive.write_bytes(b"pinned-cli")
    monkeypatch.setattr(
        release_publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(cli_archive.read_bytes()).hexdigest(),
    )
    bundle = tmp_path / "studio-bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("run.sh", "")

    release_publisher.ensure_studio_bundle_agentkit_cli(
        bundle,
        dependency_wheels,
    )

    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("agentkit-linux-x64.tar.gz") == b"pinned-cli"


def test_publisher_rejects_bad_agentkit_cli_in_final_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dependency_wheels = tmp_path / "dependencies"
    dependency_wheels.mkdir()
    monkeypatch.setattr(
        release_publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(b"pinned-cli").hexdigest(),
    )
    bundle = tmp_path / "studio-bundle.zip"
    with zipfile.ZipFile(bundle, "w") as archive:
        archive.writestr("agentkit-linux-x64.tar.gz", b"wrong-cli")

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="checksum is invalid",
    ):
        release_publisher.ensure_studio_bundle_agentkit_cli(
            bundle,
            dependency_wheels,
        )


def test_standalone_release_store_reuses_identical_immutable_objects(
    tmp_path: Path,
) -> None:
    content = b"full-bundle"
    bundle = tmp_path / "bundle.zip"
    bundle.write_bytes(content)
    manifest = release_publisher.StudioReleaseManifest(
        version="20260805190100",
        git_sha="a" * 40,
        sha256=hashlib.sha256(content).hexdigest(),
        size=len(content),
        created_at="2026-08-05T19:01:00+08:00",
    )

    class _Client:
        def __init__(self) -> None:
            self.objects: dict[tuple[str, str], bytes] = {}
            self.puts = 0

        def get_object(self, *, bucket: str, key: str) -> list[bytes]:
            return [self.objects[(bucket, key)]]

        def put_object(self, **kwargs: Any) -> None:
            identity = (kwargs["bucket"], kwargs["key"])
            if kwargs.get("forbid_overwrite") and identity in self.objects:
                raise FileExistsError(kwargs["key"])
            self.objects[identity] = kwargs["content"]
            self.puts += 1

    client = _Client()
    store = release_publisher.StudioReleaseStore(
        bucket="studio-releases",
        region="cn-beijing",
        access_key="ak",
        secret_key="sk",
        session_token="",
        prefix="veadk/studio/main",
    )
    store._client = client

    store.publish(bundle, manifest)
    first_puts = client.puts
    store.publish(bundle, manifest)

    assert client.puts == first_puts


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_publisher_stages_provider_local_thin_runtime(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    provider: str,
) -> None:
    source_root = tmp_path / "source"
    contract = source_root / "veadk" / "cli" / "studio_artifacts.py"
    contract.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).parents[1] / "veadk/cli/studio_artifacts.py", contract)
    (source_root / "uv.lock").write_text(
        '[[package]]\nname = "dependency"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    package_dir = tmp_path / "package"
    package_dir.mkdir(parents=True)
    dependency_wheel = package_dir / "dependency-1.0-py3-none-any.whl"
    _write_test_wheel(
        dependency_wheel,
        name="dependency",
        version="1.0",
    )
    (source_root / "uv.lock").write_text(
        _pypi_lock(("dependency", "1.0", dependency_wheel)),
        encoding="utf-8",
    )
    veadk_wheel = package_dir / "veadk_python-1.0.0-py3-none-any.whl"
    _write_test_wheel(
        veadk_wheel,
        name="veadk-python",
        version="1.0.0",
        license_expression="Apache-2.0",
    )
    cli_archive = package_dir / "agentkit-linux-x64.tar.gz"
    cli_archive.write_bytes(b"cli")
    (package_dir / "requirements.txt").write_text("local\n", encoding="utf-8")
    (package_dir / "run.sh").write_text("local\n", encoding="utf-8")
    monkeypatch.setattr(
        release_publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(cli_archive.read_bytes()).hexdigest(),
    )

    epoch, artifact_dir = release_publisher.stage_studio_thin_runtime(
        source_root,
        package_dir,
        tmp_path / "output",
        provider=provider,
    )

    manifest = json.loads((package_dir / "studio-runtime.json").read_text())
    assert manifest["runtimeEpoch"] == epoch
    assert manifest["provider"] == provider
    assert len(list(artifact_dir.iterdir())) == 2
    assert not (package_dir / "wheelhouse").exists()
    assert not dependency_wheel.exists()
    assert not cli_archive.exists()
    assert len(list(package_dir.glob("veadk*.whl"))) == 1
    assert (
        package_dir.joinpath("requirements.txt")
        .read_text()
        .startswith("--no-index\nhttps://")
    )
    assert (
        "./veadk_python-1.0.0-py3-none-any.whl --hash=sha256:"
        in (package_dir / "requirements.txt").read_text()
    )
    assert "--runtime-manifest" in package_dir.joinpath("run.sh").read_text()


def test_public_artifact_store_uploads_once_and_reuses_by_digest(
    tmp_path: Path,
) -> None:
    from veadk.cli import studio_artifacts as contract

    wheel = tmp_path / "dependency.whl"
    wheel.write_bytes(b"wheel")
    cli = tmp_path / "agentkit-linux-x64.tar.gz"
    cli.write_bytes(b"cli")
    manifest = contract.StudioRuntimeManifest.create(
        "volcengine",
        (
            contract.StudioArtifact.from_path(
                wheel,
                provider="volcengine",
                kind="wheel",
            ),
            contract.StudioArtifact.from_path(
                cli,
                provider="volcengine",
                kind="agentkit-cli",
            ),
        ),
    )

    class _Client:
        def __init__(self) -> None:
            self.objects: dict[tuple[str, str], tuple[bytes, dict[str, str]]] = {}
            self.puts = 0
            self.fail_file = ""
            self.failed_once = False

        def head_object(self, *, bucket: str, key: str) -> SimpleNamespace:
            if (bucket, key) not in self.objects:
                raise _NotFoundError(key)
            content, metadata = self.objects[(bucket, key)]
            return SimpleNamespace(content_length=len(content), meta=metadata)

        def put_object_from_file(self, **kwargs: Any) -> None:
            if (
                Path(kwargs["file_path"]).name == self.fail_file
                and not self.failed_once
            ):
                self.failed_once = True
                raise RuntimeError("injected upload failure")
            content = Path(kwargs["file_path"]).read_bytes()
            self.objects[(kwargs["bucket"], kwargs["key"])] = (
                content,
                dict(kwargs["meta"]),
            )
            self.puts += 1

    client = _Client()
    artifact_sizes = {item.url: item.size for item in manifest.artifacts}

    class _PublicResponse:
        status = 200

        def __init__(self, url: str) -> None:
            self._url = url
            self.headers = {"Content-Length": str(artifact_sizes[url])}

        def __enter__(self) -> _PublicResponse:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return self._url

    store = release_publisher.StudioPublicArtifactStore(
        contract=contract,
        provider="volcengine",
        access_key="",
        secret_key="",
        session_token="",
        client=client,
        public_opener=lambda request, **_kwargs: _PublicResponse(request.full_url),
    )

    assert store.publish(manifest, tmp_path) == (2, 0)
    assert store.publish(manifest, tmp_path) == (0, 2)
    assert client.puts == 2

    first_key = next(iter(client.objects))
    content, _metadata = client.objects[first_key]
    client.objects[first_key] = (content, {"sha256": "0" * 64})
    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="conflict",
    ):
        store.publish(manifest, tmp_path)

    retry_client = _Client()
    retry_client.fail_file = manifest.artifacts[1].filename
    retry_store = release_publisher.StudioPublicArtifactStore(
        contract=contract,
        provider="volcengine",
        access_key="",
        secret_key="",
        session_token="",
        client=retry_client,
        public_opener=lambda request, **_kwargs: _PublicResponse(request.full_url),
    )
    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="upload failed",
    ):
        retry_store.publish(manifest, tmp_path)
    assert len(retry_client.objects) == 1
    assert retry_store.publish(manifest, tmp_path) == (1, 1)
    assert retry_client.puts == 2


@pytest.mark.parametrize(
    ("status", "length", "redirect"),
    [
        (403, 5, False),
        (200, 0, False),
        (200, 5, True),
    ],
)
def test_public_artifact_store_rejects_anonymous_head_failures(
    tmp_path: Path,
    status: int,
    length: int,
    redirect: bool,
) -> None:
    from veadk.cli import studio_artifacts as contract

    wheel = tmp_path / "dependency.whl"
    wheel.write_bytes(b"wheel")
    artifact = contract.StudioArtifact.from_path(
        wheel,
        provider="volcengine",
        kind="wheel",
    )

    class _Response:
        headers = {"Content-Length": str(length)}

        def __enter__(self) -> _Response:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://redirect.invalid/artifact" if redirect else artifact.url

    response = _Response()
    response.status = status
    store = release_publisher.StudioPublicArtifactStore(
        contract=contract,
        provider="volcengine",
        access_key="",
        secret_key="",
        session_token="",
        client=object(),
        public_opener=lambda *_args, **_kwargs: response,
    )

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="anonymous-read verification failed",
    ):
        store._verify_public(artifact)


def test_public_runtime_rejects_wheel_without_public_pypi_provenance(
    tmp_path: Path,
) -> None:
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "private-dependency"\nversion = "1.0"\n'
        'source = { git = "https://example.com/private.git" }\n',
        encoding="utf-8",
    )
    wheel = tmp_path / "private_dependency-1.0-py3-none-any.whl"
    wheel.write_bytes(b"wheel")

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="non-PyPI",
    ):
        release_publisher.validate_public_runtime_provenance(tmp_path, [wheel])


def test_public_runtime_requires_exact_locked_wheel_bytes(tmp_path: Path) -> None:
    wheel = tmp_path / "dependency-1.0-py3-none-any.whl"
    _write_test_wheel(wheel, name="dependency", version="1.0")
    (tmp_path / "uv.lock").write_text(
        _pypi_lock(("dependency", "1.0", wheel)),
        encoding="utf-8",
    )
    with wheel.open("ab") as output:
        output.write(b"tampered")

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="does not match uv.lock",
    ):
        release_publisher.validate_public_runtime_provenance(tmp_path, [wheel])


def test_source_built_wheel_stays_in_private_bundle(tmp_path: Path) -> None:
    wheel = tmp_path / "dependency-1.0-py3-none-any.whl"
    _write_test_wheel(wheel, name="dependency", version="1.0")
    (tmp_path / "uv.lock").write_text(
        '[[package]]\nname = "dependency"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n'
        'sdist = { url = "https://files.pythonhosted.org/packages/dependency-1.0.tar.gz", '
        'hash = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", '
        "size = 100 }\n",
        encoding="utf-8",
    )

    public, bundled = release_publisher.partition_public_runtime_wheels(
        tmp_path,
        [wheel],
    )

    assert public == []
    assert bundled == [wheel]


def test_public_runtime_requires_allowlisted_wheel_license(tmp_path: Path) -> None:
    wheel = tmp_path / "dependency-1.0-py3-none-any.whl"
    _write_test_wheel(
        wheel,
        name="dependency",
        version="1.0",
        license_expression="LicenseRef-Proprietary",
    )
    (tmp_path / "uv.lock").write_text(
        _pypi_lock(("dependency", "1.0", wheel)),
        encoding="utf-8",
    )

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match="license is not allowlisted",
    ):
        release_publisher.validate_public_runtime_provenance(tmp_path, [wheel])

    _write_test_wheel(
        wheel,
        name="dependency",
        version="1.0",
        license_expression="MIT OR Apache-2.0",
    )
    (tmp_path / "uv.lock").write_text(
        _pypi_lock(("dependency", "1.0", wheel)),
        encoding="utf-8",
    )
    release_publisher.validate_public_runtime_provenance(tmp_path, [wheel])


def test_non_allowlisted_wheel_stays_in_private_bundle(tmp_path: Path) -> None:
    public_wheel = tmp_path / "public_dependency-1.0-py3-none-any.whl"
    private_wheel = tmp_path / "private_dependency-1.0-py3-none-any.whl"
    _write_test_wheel(public_wheel, name="public-dependency", version="1.0")
    _write_test_wheel(
        private_wheel,
        name="private-dependency",
        version="1.0",
        license_expression="LicenseRef-Proprietary",
    )
    (tmp_path / "uv.lock").write_text(
        _pypi_lock(
            ("public-dependency", "1.0", public_wheel),
            ("private-dependency", "1.0", private_wheel),
        ),
        encoding="utf-8",
    )

    public, bundled = release_publisher.partition_public_runtime_wheels(
        tmp_path,
        [private_wheel, public_wheel],
    )

    assert public == [public_wheel]
    assert bundled == [private_wheel]


def test_runtime_epoch_reuses_dependencies_across_veadk_releases(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = tmp_path / "source"
    contract = source_root / "veadk" / "cli" / "studio_artifacts.py"
    contract.parent.mkdir(parents=True)
    shutil.copy2(Path(__file__).parents[1] / "veadk/cli/studio_artifacts.py", contract)
    (source_root / "uv.lock").write_text(
        '[[package]]\nname = "dependency"\nversion = "1.0"\n'
        'source = { registry = "https://pypi.org/simple" }\n',
        encoding="utf-8",
    )
    cli_content = b"same-cli"
    monkeypatch.setattr(
        release_publisher,
        "_AGENTKIT_CLI_ARCHIVE_SHA256",
        hashlib.sha256(cli_content).hexdigest(),
    )
    epochs: list[str] = []
    artifact_names: list[set[str]] = []
    for version, content in (("1.0.0", b"app-one"), ("1.0.1", b"app-two")):
        package = tmp_path / f"package-{version}"
        package.mkdir(parents=True)
        _write_test_wheel(
            package / "dependency-1.0-py3-none-any.whl",
            name="dependency",
            version="1.0",
        )
        (source_root / "uv.lock").write_text(
            _pypi_lock(
                (
                    "dependency",
                    "1.0",
                    package / "dependency-1.0-py3-none-any.whl",
                )
            ),
            encoding="utf-8",
        )
        veadk_name = f"veadk_python-{version}-py3-none-any.whl"
        _write_test_wheel(
            package / veadk_name,
            name="veadk-python",
            version=version,
            license_expression="Apache-2.0",
            marker=content.decode(),
        )
        (package / "agentkit-linux-x64.tar.gz").write_bytes(cli_content)
        (package / "requirements.txt").write_text("local\n", encoding="utf-8")
        (package / "run.sh").write_text("local\n", encoding="utf-8")

        epoch, artifacts = release_publisher.stage_studio_thin_runtime(
            source_root,
            package,
            tmp_path / f"output-{version}",
            provider="volcengine",
        )
        epochs.append(epoch)
        artifact_names.append({path.name for path in artifacts.iterdir()})

    assert epochs[0] == epochs[1]
    assert artifact_names == [
        {"dependency-1.0-py3-none-any.whl", "agentkit-linux-x64.tar.gz"},
        {"dependency-1.0-py3-none-any.whl", "agentkit-linux-x64.tar.gz"},
    ]


def test_standalone_publisher_stages_scheduler_backend(tmp_path: Path) -> None:
    source_root = tmp_path / "source"
    (source_root / "veadk").mkdir(parents=True)
    (source_root / "veadk" / "__init__.py").write_text("", encoding="utf-8")
    for filename in ("pyproject.toml", "README.md", "LICENSE"):
        (source_root / filename).write_text("", encoding="utf-8")
    (source_root / "frontend" / "server").mkdir(parents=True)
    (source_root / "frontend" / "server" / "__init__.py").write_text(
        "", encoding="utf-8"
    )
    future_runtime = source_root / "frontend" / "future_runtime"
    future_runtime.mkdir()
    (future_runtime / "__init__.py").write_text("", encoding="utf-8")
    (future_runtime / "handler.py").write_text("HANDLER = True\n", encoding="utf-8")
    (source_root / "frontend" / "__init__.py").write_text("", encoding="utf-8")
    scheduler = source_root / "frontend" / "service" / "studio_scheduler"
    scheduler.mkdir(parents=True)
    (scheduler.parent / "__init__.py").write_text("", encoding="utf-8")
    release_server = scheduler.parent / "studio_release_server"
    release_server.mkdir()
    (release_server / "__init__.py").write_text("", encoding="utf-8")
    (scheduler / "__init__.py").write_text("", encoding="utf-8")
    (scheduler / "models.py").write_text("MODEL = True\n", encoding="utf-8")
    frontend_assets = tmp_path / "frontend-assets"
    frontend_assets.mkdir()
    (frontend_assets / "index.html").write_text("studio", encoding="utf-8")

    wheel_source = tmp_path / "wheel-source"
    release_publisher.stage_studio_wheel_source(
        source_root, frontend_assets, wheel_source
    )

    assert (
        wheel_source / "frontend" / "service" / "studio_scheduler" / "models.py"
    ).read_text(encoding="utf-8") == "MODEL = True\n"
    assert (wheel_source / "frontend" / "future_runtime" / "handler.py").read_text(
        encoding="utf-8"
    ) == "HANDLER = True\n"
    assert (wheel_source / "frontend" / "service" / "studio_release_server").is_dir()


@pytest.mark.parametrize(
    "missing_module",
    (
        "frontend/service/studio_scheduler/models.py",
        "veadk/cli/studio_update.py",
    ),
)
def test_standalone_publisher_rejects_wheel_without_runtime_module(
    tmp_path: Path,
    missing_module: str,
) -> None:
    wheel = tmp_path / "veadk.whl"
    source_root = Path(__file__).parents[1]
    with zipfile.ZipFile(wheel, "w") as archive:
        for name in release_publisher.studio_runtime_modules(source_root):
            if name != missing_module:
                archive.writestr(name, "")

    with pytest.raises(
        release_publisher.StudioPublisherError,
        match=missing_module,
    ):
        release_publisher.validate_studio_wheel(wheel, source_root)


def test_builder_shallow_clones_only_main_build_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _request()
    commands: list[list[str]] = []

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
        commands.append(command)
        if command[1] == "clone":
            destination = Path(command[-1])
            (destination / "frontend").mkdir(parents=True)
            (destination / "frontend" / "package.json").write_text(
                "{}\n", encoding="utf-8"
            )
        output: str | bytes = f"{request.git_sha}\n" if kwargs.get("text") else b""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr=b"")

    monkeypatch.setattr(release_builder.shutil, "which", lambda name: f"/bin/{name}")
    monkeypatch.setattr(release_builder.subprocess, "run", _run)
    builder = StudioReleaseBuilder(_settings())

    source = builder._clone_source(
        request,
        tmp_path,
        lambda _stage, _message: None,
    )

    assert source == tmp_path / "source-clone-0"
    clone = commands[0]
    assert clone[1:10] == [
        "clone",
        "--quiet",
        "--depth",
        "1",
        "--single-branch",
        "--branch",
        "main",
        "--filter=blob:none",
        "--sparse",
    ]
    sparse = next(command for command in commands if "sparse-checkout" in command)
    assert "/frontend/" in sparse
    assert "/veadk/" in sparse
    assert "!/veadk/webui/" in sparse
    assert not any("fetch" in command for command in commands)


def test_builder_rejects_unsafe_source_archive_entry(tmp_path: Path) -> None:
    archive = tmp_path / "source.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        root = tarfile.TarInfo("veadk-python")
        root.type = tarfile.DIRTYPE
        output.addfile(root)
        package = tarfile.TarInfo("veadk-python/frontend/package.json")
        package.size = 2
        output.addfile(package, io.BytesIO(b"{}"))
        link = tarfile.TarInfo("veadk-python/frontend/escape")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        output.addfile(link)

    builder = StudioReleaseBuilder(_settings())

    with pytest.raises(ValueError, match="unsupported entry"):
        builder._extract_source(archive, tmp_path)


def test_tos_dependency_store_populates_and_reuses_cached_wheel(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"dependency-wheel"
    digest = hashlib.sha256(content).hexdigest()
    manifest = tmp_path / "dependencies.json"
    manifest.write_text(
        json.dumps(
            {
                "wheels": [
                    {
                        "filename": "dependency.whl",
                        "url": "https://example.com/dependency.whl",
                        "sha256": digest,
                    }
                ],
                "artifacts": [
                    {
                        "filename": "agentkit-linux-x64.tar.gz",
                        "url": (
                            "https://agentkit-cli.tos-cn-beijing.volces.com/"
                            "0.52.14/agentkit-linux-x64.tar.gz"
                        ),
                        "sha256": digest,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    downloads = 0

    def _urlopen(_url: str, *, timeout: int) -> io.BytesIO:
        nonlocal downloads
        assert timeout == 120
        downloads += 1
        return io.BytesIO(content)

    monkeypatch.setattr(
        "frontend.service.studio_release_server.tos_store.urllib.request.urlopen",
        _urlopen,
    )
    client = _DependencyCacheClient()
    store = TosDependencyStore(_settings(), client_factory=lambda: client)

    first = store.materialize(manifest, tmp_path / "first")
    second = store.materialize(manifest, tmp_path / "second")

    assert [path.read_bytes() for path in first] == [content, content]
    assert [path.read_bytes() for path in second] == [content, content]
    assert downloads == 2


def test_builder_restores_manifest_dependencies_from_cache(tmp_path: Path) -> None:
    prepared_root = tmp_path / ".studio-release"
    prepared_root.mkdir()
    manifest = prepared_root / "dependencies.json"
    manifest.write_text(
        '{"wheels": [], "artifacts": []}\n',
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dependency_store = _MemoryDependencyStore()
    progress: list[tuple[str, str]] = []
    builder = StudioReleaseBuilder(
        _settings(),
        dependency_store=dependency_store,
    )

    wheels = builder._prepare_dependency_wheels(
        tmp_path,
        prepared_root,
        workspace,
        lambda stage, message: progress.append((stage, message)),
    )

    assert wheels == workspace / "dependency-wheels"
    assert dependency_store.manifest == manifest
    assert (wheels / "dependency.whl").read_bytes() == b"wheel"
    assert progress == [("preparing", "正在从 TOS 缓存恢复 Studio 依赖包")]


def test_builder_generates_dependency_manifest_from_release_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source_root = Path(__file__).parents[1]
    prepared_root = tmp_path / ".studio-release"
    prepared_root.mkdir()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    dependency_store = _MemoryDependencyStore()
    builder = StudioReleaseBuilder(
        _settings(),
        dependency_store=dependency_store,
    )
    commands: list[list[str]] = []

    def capture_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        commands.append(command)
        assert kwargs["cwd"] == source_root
        destination = Path(command[command.index("--manifest") + 1])
        destination.write_text(
            json.dumps(
                {
                    "wheels": [
                        {
                            "filename": "dependency.whl",
                            "url": "https://example.com/dependency.whl",
                            "sha256": "a" * 64,
                        }
                    ],
                    "artifacts": [
                        {
                            "filename": "agentkit-linux-x64.tar.gz",
                            "url": (
                                "https://agentkit-cli.tos-cn-beijing.volces.com/"
                                "0.52.14/agentkit-linux-x64.tar.gz"
                            ),
                            "sha256": "b" * 64,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 0, stdout=b"")

    monkeypatch.setattr(release_builder.subprocess, "run", capture_run)

    wheels = builder._prepare_dependency_wheels(
        source_root,
        prepared_root,
        workspace,
        lambda _stage, _message: None,
    )

    assert wheels == workspace / "dependency-wheels"
    assert commands[0][:3] == [
        sys.executable,
        "-m",
        "veadk.cli.studio_dependencies",
    ]
    assert dependency_store.manifest == workspace / "dependencies.json"
    assert json.loads(dependency_store.manifest.read_text(encoding="utf-8"))["wheels"]


def test_tos_dependency_store_rejects_download_with_wrong_checksum(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = tmp_path / "dependencies.json"
    manifest.write_text(
        json.dumps(
            {
                "wheels": [
                    {
                        "filename": "dependency.whl",
                        "url": "https://example.com/dependency.whl",
                        "sha256": "a" * 64,
                    }
                ],
                "artifacts": [
                    {
                        "filename": "agentkit-linux-x64.tar.gz",
                        "url": (
                            "https://agentkit-cli.tos-cn-beijing.volces.com/"
                            "0.52.14/agentkit-linux-x64.tar.gz"
                        ),
                        "sha256": "b" * 64,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "frontend.service.studio_release_server.tos_store.urllib.request.urlopen",
        lambda _url, *, timeout: io.BytesIO(b"tampered"),
    )
    store = TosDependencyStore(
        _settings(),
        client_factory=lambda: _DependencyCacheClient(),
    )

    with pytest.raises(ValueError, match="checksum"):
        store.materialize(manifest, tmp_path / "destination")


def test_tos_dependency_store_uses_domestic_mirror_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = b"dependency-wheel"
    urls: list[str] = []

    def _urlopen(url: str, *, timeout: int) -> io.BytesIO:
        urls.append(url)
        assert timeout == 120
        if url.startswith("https://pypi.tuna.tsinghua.edu.cn/"):
            raise OSError("mirror unavailable")
        return io.BytesIO(content)

    monkeypatch.setattr(
        "frontend.service.studio_release_server.tos_store.urllib.request.urlopen",
        _urlopen,
    )
    store = TosDependencyStore(
        _settings(),
        client_factory=lambda: _DependencyCacheClient(),
    )

    downloaded = store._download(
        "https://files.pythonhosted.org/packages/example/dependency.whl",
        hashlib.sha256(content).hexdigest(),
    )

    assert downloaded == content
    assert urls == [
        "https://pypi.tuna.tsinghua.edu.cn/packages/example/dependency.whl",
        "https://mirrors.aliyun.com/pypi/packages/example/dependency.whl",
    ]


def test_stage_deployment_uses_frontend_service_package(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = Path(__file__).parents[1]
    destination = tmp_path / "deployment"
    destination.mkdir()
    dependency_specs: dict[str, importlib.machinery.ModuleSpec] = {}
    for dependency_name in ("tos", "crcmod"):
        dependency_root = tmp_path / "dependencies" / dependency_name
        dependency_root.mkdir(parents=True)
        (dependency_root / "__init__.py").write_text("", encoding="utf-8")
        spec = importlib.machinery.ModuleSpec(
            dependency_name, loader=None, is_package=True
        )
        spec.submodule_search_locations = [str(dependency_root)]
        dependency_specs[dependency_name] = spec

    def _install_runtime_wheels(*_args: Any, **_kwargs: Any) -> None:
        (destination / "site-packages").mkdir()

    monkeypatch.setattr(release_deploy.shutil, "which", lambda _name: "uv")
    monkeypatch.setattr(release_deploy.subprocess, "run", _install_runtime_wheels)
    monkeypatch.setattr(
        release_deploy,
        "_stage_node_archive",
        lambda _destination: None,
    )
    monkeypatch.setattr(
        release_deploy.importlib.util,
        "find_spec",
        dependency_specs.get,
    )

    release_deploy._stage_deployment(source_root, destination)

    package_root = destination / "frontend" / "service" / "studio_release_server"
    assert (destination / "frontend" / "__init__.py").is_file()
    assert (destination / "frontend" / "service" / "__init__.py").is_file()
    assert (package_root / "app.py").is_file()
    assert (package_root / "publisher.py").is_file()
    assert not (package_root / "deploy.py").exists()
    assert not (package_root / "deploy.sh").exists()
    assert not (destination / "veadk").exists()
    assert "frontend.service.studio_release_server.app:app" in (
        destination / "run.sh"
    ).read_text(encoding="utf-8")


def test_function_lookup_paginates() -> None:
    requested_pages: list[int] = []

    class _Client:
        def list_functions(self, request: Any) -> Any:
            requested_pages.append(request.page_number)
            if request.page_number == 1:
                return SimpleNamespace(
                    total=101,
                    items=[SimpleNamespace(name="another-function", id="other-id")],
                )
            return SimpleNamespace(
                total=101,
                items=[
                    SimpleNamespace(
                        name="veadk-studio-release-server-fn",
                        id="release-function-id",
                    )
                ],
            )

    service = SimpleNamespace(client=_Client())

    assert release_deploy._find_function_id(service) == "release-function-id"
    assert requested_pages == [1, 2]


def test_set_github_secret_reads_value_from_stdin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        invocation["command"] = command
        invocation.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(release_deploy.subprocess, "run", _run)

    release_deploy._set_github_secret("STUDIO_RELEASE_SERVER_URL", "https://x")

    assert invocation["command"] == [
        "gh",
        "secret",
        "set",
        "STUDIO_RELEASE_SERVER_URL",
        "--repo",
        "volcengine/veadk-python",
    ]
    assert invocation["input"] == "https://x"


def test_github_secret_preflight_checks_access_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invocation: dict[str, Any] = {}

    def _run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        invocation["command"] = command
        invocation.update(kwargs)
        return subprocess.CompletedProcess(command, 0, stdout="", stderr="")

    monkeypatch.setattr(release_deploy.subprocess, "run", _run)

    release_deploy._validate_github_secret_access()

    assert invocation["command"] == [
        "gh",
        "api",
        "repos/volcengine/veadk-python/actions/secrets/public-key",
        "--silent",
    ]


def test_release_server_readiness_uses_rotated_api_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[Any] = []

    def _urlopen(request: Any, *, timeout: int) -> Any:
        requests.append(request)
        assert timeout == 10
        return nullcontext(SimpleNamespace(status=200))

    monkeypatch.setattr(release_deploy.urllib.request, "urlopen", _urlopen)

    release_deploy._wait_for_health("https://release.example.com", "rotated-key")

    assert requests[0].full_url == "https://release.example.com/readyz"
    assert dict(requests[0].header_items())["X-api-key"] == "rotated-key"


def test_release_server_runtime_environment_records_provider() -> None:
    environment = release_deploy._runtime_environment(
        "x" * 32,
        bucket="veadk-studio-byteplus",
        provider="byteplus",
        region="ap-southeast-1",
    )

    assert environment["STUDIO_RELEASE_PROVIDER"] == "byteplus"
    assert environment["STUDIO_RELEASE_REGION"] == "ap-southeast-1"
    assert environment["STUDIO_RELEASE_BUCKET"] == "veadk-studio-byteplus"
    assert environment["STUDIO_RELEASE_THIN_BUNDLES"] == "false"

    enabled = release_deploy._runtime_environment(
        "x" * 32,
        bucket="veadk-studio-byteplus",
        provider="byteplus",
        region="ap-southeast-1",
        thin_bundles=True,
    )
    assert enabled["STUDIO_RELEASE_THIN_BUNDLES"] == "true"


def test_release_server_deploy_parser_requires_explicit_thin_bundle_opt_in() -> None:
    parser = release_deploy._parser()

    assert parser.parse_args([]).enable_thin_bundles is False
    assert parser.parse_args(["--enable-thin-bundles"]).enable_thin_bundles is True


def test_release_server_function_matches_production_resources(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        def create_function(self, request: Any) -> Any:
            captured["request"] = request
            return SimpleNamespace(id="release-function-id")

    class _Service:
        client = _Client()

        def _upload_and_mount_code(self, function_id: str, path: str) -> None:
            captured["upload"] = (function_id, path)

    function_id = release_deploy._create_release_function(
        _Service(),
        tmp_path,
        {"STUDIO_RELEASE_PROVIDER": "byteplus"},
        "trn:role",
    )

    request = captured["request"]
    assert function_id == "release-function-id"
    assert request.cpu_milli == 16_000
    assert request.memory_mb == 32_768
    assert request.request_timeout == 1800
    assert "勿删" in request.description
    assert captured["upload"] == ("release-function-id", str(tmp_path))


def test_release_server_retries_transient_code_upload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attempts = 0

    def _upload() -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise ValueError("Function code upload request failed.")

    monkeypatch.setattr(release_deploy.time, "sleep", lambda _seconds: None)

    release_deploy._retry_code_upload(_upload)

    assert attempts == 3


def test_release_server_reuses_running_serverless_gateway() -> None:
    gateways = [
        SimpleNamespace(
            id="provisioning-serverless",
            type="serverless",
            status="Creating",
        ),
        SimpleNamespace(id="running-dedicated", type="dedicated", status="Running"),
        SimpleNamespace(
            id="running-serverless",
            type="serverless",
            status="Running",
        ),
    ]

    gateway = release_deploy._find_reusable_serverless_gateway(gateways)

    assert gateway.id == "running-serverless"


def test_release_bucket_is_private_and_tagged_do_not_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[])

        def create_bucket(self, **kwargs: Any) -> None:
            captured["create"] = kwargs

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            raise KeyError("no tags")

        def put_bucket_tagging(self, **kwargs: Any) -> None:
            captured["tags"] = kwargs

    release_deploy._ensure_release_bucket(_Client(), "veadk-studio-byteplus")

    assert captured["create"] == {"bucket": "veadk-studio-byteplus"}
    assert captured["tags"]["tag_set"][0].to_dict() == {
        "Key": "note",
        "Value": "勿删",
    }


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_public_artifact_bucket_exposes_only_immutable_prefix(
    provider: str,
) -> None:
    captured: dict[str, Any] = {}

    class _Client:
        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[])

        def create_bucket(self, **kwargs: Any) -> None:
            captured["create"] = kwargs

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            raise KeyError("no tags")

        def put_bucket_tagging(self, **kwargs: Any) -> None:
            captured["tags"] = kwargs

        def put_bucket_policy(self, **kwargs: Any) -> None:
            captured["policy"] = kwargs

        def get_bucket_policy(self, **kwargs: Any) -> Any:
            assert kwargs["bucket"] == captured["create"]["bucket"]
            return SimpleNamespace(policy=captured["policy"]["policy"])

    bucket = release_deploy._ensure_public_artifact_bucket(
        _Client(),
        provider,  # type: ignore[arg-type]
    )
    policy = json.loads(captured["policy"]["policy"])
    statement = policy["Statement"][0]

    assert captured["create"] == {"bucket": bucket}
    assert statement["Principal"] == "*"
    assert statement["Action"] == ["tos:GetObject"]
    assert statement["Resource"] == [f"trn:tos:::{bucket}/veadk/studio/artifacts/v1/*"]
    assert "release-server/jobs" not in captured["policy"]["policy"]


def test_public_artifact_bucket_preserves_existing_policy_and_tags() -> None:
    bucket = "veadk-studio-public"

    class _Client:
        def __init__(self) -> None:
            self.policy: dict[str, object] = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Sid": "ExistingPrivateAutomation",
                        "Effect": "Allow",
                        "Principal": {"Service": "internal"},
                        "Action": ["tos:PutObject"],
                        "Resource": [f"trn:tos:::{bucket}/internal/*"],
                    }
                ],
            }
            self.tags = [SimpleNamespace(key="owner", value="studio")]
            self.policy_puts = 0
            self.tag_puts = 0

        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[SimpleNamespace(name=bucket)])

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(tag_set=self.tags)

        def put_bucket_tagging(self, **kwargs: Any) -> None:
            self.tags = list(kwargs["tag_set"])
            self.tag_puts += 1

        def get_bucket_policy(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(policy=json.dumps(self.policy))

        def put_bucket_policy(self, **kwargs: Any) -> None:
            self.policy = json.loads(kwargs["policy"])
            self.policy_puts += 1

    client = _Client()

    assert release_deploy._ensure_public_artifact_bucket(client, "volcengine") == bucket
    assert release_deploy._ensure_public_artifact_bucket(client, "volcengine") == bucket

    assert client.policy_puts == 1
    assert client.tag_puts == 1
    assert {item.key: item.value for item in client.tags} == {
        "owner": "studio",
        "note": "勿删",
    }
    statements = client.policy["Statement"]
    assert isinstance(statements, list)
    assert [item["Sid"] for item in statements] == [
        "ExistingPrivateAutomation",
        "PublicReadStudioRuntimeArtifacts",
    ]


def test_public_artifact_bucket_accepts_tos_normalized_policy() -> None:
    bucket = "veadk-studio-public"

    class _NotFoundError(Exception):
        status_code = 404

    class _Client:
        def __init__(self) -> None:
            self.policy: dict[str, object] | None = None
            self.policy_puts = 0

        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[SimpleNamespace(name=bucket)])

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(tag_set=[SimpleNamespace(key="note", value="勿删")])

        def get_bucket_policy(self, **_kwargs: Any) -> Any:
            if self.policy is None:
                raise _NotFoundError
            statements = self.policy.get("Statement")
            assert isinstance(statements, list) and len(statements) == 1
            statement = statements[0]
            assert isinstance(statement, dict)
            actions = statement.get("Action")
            resources = statement.get("Resource")
            assert isinstance(actions, list) and len(actions) == 1
            assert isinstance(resources, list) and len(resources) == 1
            normalized = {
                "Version": "1.0",
                "Statement": {
                    **statement,
                    "Principal": [statement["Principal"]],
                    "Action": actions[0],
                    "Resource": resources[0],
                },
            }
            return SimpleNamespace(policy=json.dumps(normalized))

        def put_bucket_policy(self, **kwargs: Any) -> None:
            self.policy = json.loads(kwargs["policy"])
            self.policy_puts += 1

    client = _Client()

    assert release_deploy._ensure_public_artifact_bucket(client, "volcengine") == bucket
    assert release_deploy._ensure_public_artifact_bucket(client, "volcengine") == bucket
    assert client.policy_puts == 1


def test_public_artifact_bucket_accepts_normalized_existing_owned_statement() -> None:
    bucket = "veadk-studio-public"

    class _Client:
        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[SimpleNamespace(name=bucket)])

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(tag_set=[SimpleNamespace(key="note", value="勿删")])

        def get_bucket_policy(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(
                policy=json.dumps(
                    {
                        "Version": "1.0",
                        "Statement": {
                            "Sid": "PublicReadStudioRuntimeArtifacts",
                            "Effect": "Allow",
                            "Principal": ["*"],
                            "Action": "tos:GetObject",
                            "Resource": (
                                f"trn:tos:::{bucket}/veadk/studio/artifacts/v1/*"
                            ),
                        },
                    }
                )
            )

        def put_bucket_policy(self, **_kwargs: Any) -> None:
            raise AssertionError("normalized matching policy must not be rewritten")

    assert (
        release_deploy._ensure_public_artifact_bucket(_Client(), "volcengine") == bucket
    )


def test_public_artifact_bucket_rejects_dropped_unrelated_policy() -> None:
    bucket = "veadk-studio-public"
    unrelated = {
        "Sid": "ExistingPrivateAutomation",
        "Effect": "Allow",
        "Principal": {"Service": "internal"},
        "Action": ["tos:PutObject"],
        "Resource": [f"trn:tos:::{bucket}/internal/*"],
    }

    class _Client:
        def __init__(self) -> None:
            self.policy_puts = 0

        def list_buckets(self) -> Any:
            return SimpleNamespace(buckets=[SimpleNamespace(name=bucket)])

        def get_bucket_tagging(self, **_kwargs: Any) -> Any:
            return SimpleNamespace(tag_set=[SimpleNamespace(key="note", value="勿删")])

        def get_bucket_policy(self, **_kwargs: Any) -> Any:
            statements = [unrelated]
            if self.policy_puts:
                statements = [
                    {
                        "Sid": "PublicReadStudioRuntimeArtifacts",
                        "Effect": "Allow",
                        "Principal": ["*"],
                        "Action": "tos:GetObject",
                        "Resource": (f"trn:tos:::{bucket}/veadk/studio/artifacts/v1/*"),
                    }
                ]
            return SimpleNamespace(
                policy=json.dumps({"Version": "2012-10-17", "Statement": statements})
            )

        def put_bucket_policy(self, **_kwargs: Any) -> None:
            self.policy_puts += 1

    with pytest.raises(RuntimeError, match="policy verification failed"):
        release_deploy._ensure_public_artifact_bucket(_Client(), "volcengine")


def test_public_artifact_bucket_rejects_owned_policy_conflict() -> None:
    with pytest.raises(RuntimeError, match="policy has a conflict"):
        release_deploy._merge_public_artifact_policy(
            {
                "Statement": [
                    {
                        "Sid": "PublicReadStudioRuntimeArtifacts",
                        "Effect": "Allow",
                        "Principal": "*",
                        "Action": ["tos:GetObject"],
                        "Resource": ["trn:tos:::wrong-bucket/*"],
                    }
                ]
            },
            "veadk-studio-public",
        )


def test_release_workflow_publishes_one_version_to_both_providers() -> None:
    workflow = (
        Path(__file__).parents[1]
        / ".github"
        / "workflows"
        / "publish-studio-release.yaml"
    ).read_text(encoding="utf-8")

    assert "provider: volcengine" in workflow
    assert "provider: byteplus" in workflow
    assert "BYTEPLUS_STUDIO_RELEASE_SERVER_URL" in workflow
    assert '"version": os.environ["RELEASE_VERSION"]' in workflow
    assert "thin_bundles:" in workflow
    assert '"thinBundle": os.environ["RELEASE_THIN_BUNDLES"]' in workflow
