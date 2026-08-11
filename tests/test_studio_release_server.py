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
from frontend.service.studio_release_server.tos_store import TosDependencyStore


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


def _settings() -> ReleaseServerSettings:
    return ReleaseServerSettings(
        api_key="release-key-with-at-least-thirty-two-characters",
        bucket="veadk-studio",
        region="cn-beijing",
        release_prefix="veadk/studio/main",
        job_prefix="veadk/studio/release-server/jobs",
        repository="volcengine/veadk-python",
    )


def _request(request_id: str = "12345-1") -> ReleaseRequest:
    return ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId=request_id,
        changelog=("发布 Studio 更新",),
    )


def test_release_request_accepts_studio_apmplus_config() -> None:
    request = ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId="12345-1",
        changelog=("发布 Studio 更新",),
        studioApmplus={"aid": " 12345 ", "token": " client-token "},
    )

    assert request.studio_apmplus is not None
    assert request.studio_apmplus.aid == "12345"
    assert request.studio_apmplus.token == "client-token"


def test_release_request_rejects_invalid_studio_apmplus_config() -> None:
    with pytest.raises(ValueError, match="Studio APMPlus aid"):
        ReleaseRequest(
            repository="volcengine/veadk-python",
            gitSha="a" * 40,
            requestId="12345-1",
            changelog=("发布 Studio 更新",),
            studioApmplus={"aid": "not-an-aid", "token": "client-token"},
        )


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


def test_builder_passes_studio_apmplus_to_publisher_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = ReleaseRequest(
        repository="volcengine/veadk-python",
        gitSha="a" * 40,
        requestId="12345-1",
        changelog=("发布 Studio 更新",),
        studioApmplus={"aid": "12345", "token": "client-token"},
    )
    captured: dict[str, Any] = {}

    monkeypatch.setattr(
        release_builder,
        "resolve_credentials",
        lambda: SimpleNamespace(
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
    builder = StudioReleaseBuilder(_settings())

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

    assert captured["env"]["VEADK_STUDIO_APMPLUS_AID"] == "12345"
    assert captured["env"]["VEADK_STUDIO_APMPLUS_TOKEN"] == "client-token"
    assert captured["env"]["VOLCENGINE_ACCESS_KEY"] == "release-ak"
    assert captured["command"][1].endswith("studio_release_server/publisher.py")
    assert "veadk.cli.studio_release" not in captured["command"]
    assert str(tmp_path) not in captured["env"].get("PYTHONPATH", "").split(os.pathsep)


def test_standalone_publisher_starts_without_importing_veadk() -> None:
    publisher = Path(release_builder.__file__).with_name("publisher.py")

    completed = subprocess.run(
        [sys.executable, "-I", str(publisher), "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr


def test_standalone_publisher_builds_bundle_from_source_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frontend_assets = tmp_path / "frontend-assets"
    frontend_assets.mkdir()
    (frontend_assets / "index.html").write_text("studio", encoding="utf-8")
    dependency_wheels = tmp_path / "dependencies"
    dependency_wheels.mkdir()
    (dependency_wheels / "dependency-1.0-py3-none-any.whl").write_bytes(b"wheel")

    def _run(command: list[str], **_kwargs: Any) -> subprocess.CompletedProcess[Any]:
        output_dir = Path(command[command.index("-o") + 1])
        (output_dir / "veadk_python-1.0.0-py3-none-any.whl").write_bytes(b"veadk")
        return subprocess.CompletedProcess(command, 0)

    monkeypatch.setattr(release_publisher.subprocess, "run", _run)
    output_dir = tmp_path / "output"
    bundle, manifest = release_publisher.build_studio_release(
        source_root=Path(__file__).parents[1],
        output_dir=output_dir,
        version="20260805190000",
        git_sha="a" * 40,
        changelog=("发布 Studio 更新",),
        frontend_assets=frontend_assets,
        dependency_wheels=dependency_wheels,
        env={
            "PATH": os.environ["PATH"],
            "VEADK_STUDIO_APMPLUS_AID": "12345",
            "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
        },
    )

    with zipfile.ZipFile(bundle) as archive:
        assert archive.read("requirements.txt").decode() == (
            "./dependency-1.0-py3-none-any.whl\n./veadk_python-1.0.0-py3-none-any.whl\n"
        )
        assert json.loads(archive.read(".studio-release-environment.json")) == {
            "VEADK_STUDIO_APMPLUS_AID": "12345",
            "VEADK_STUDIO_APMPLUS_TOKEN": "client-token",
        }
        assert (
            b'--provider "${CLOUD_PROVIDER:-${AGENTKIT_CLOUD_PROVIDER:-volcengine}}"'
            in archive.read("run.sh")
        )
    assert manifest.git_sha == "a" * 40
    assert manifest.sha256 == hashlib.sha256(bundle.read_bytes()).hexdigest()


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
                ]
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

    assert [path.read_bytes() for path in first] == [content]
    assert [path.read_bytes() for path in second] == [content]
    assert downloads == 1


def test_builder_restores_manifest_dependencies_from_cache(tmp_path: Path) -> None:
    prepared_root = tmp_path / ".studio-release"
    prepared_root.mkdir()
    manifest = prepared_root / "dependencies.json"
    manifest.write_text('{"wheels": []}\n', encoding="utf-8")
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
    original_run = subprocess.run

    def capture_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        commands.append(command)
        return original_run(command, **kwargs)

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
                ]
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
