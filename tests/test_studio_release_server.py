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
import shutil
import subprocess
import tarfile
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
from frontend.service.studio_release_server import deploy as release_deploy
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
    assert current.status_code == 200
    assert current.json()["state"] == "succeeded"
    assert current.json()["result"]["gitSha"] == "a" * 40


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
        prepared_root,
        workspace,
        lambda stage, message: progress.append((stage, message)),
    )

    assert wheels == workspace / "dependency-wheels"
    assert dependency_store.manifest == manifest
    assert (wheels / "dependency.whl").read_bytes() == b"wheel"
    assert progress == [("preparing", "正在从 TOS 缓存恢复 Studio 依赖包")]


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
        release_deploy.importlib.util,
        "find_spec",
        dependency_specs.get,
    )

    release_deploy._stage_deployment(source_root, destination)

    package_root = destination / "frontend" / "service" / "studio_release_server"
    assert (destination / "frontend" / "__init__.py").is_file()
    assert (destination / "frontend" / "service" / "__init__.py").is_file()
    assert (package_root / "app.py").is_file()
    assert not (package_root / "deploy.py").exists()
    assert not (package_root / "deploy.sh").exists()
    assert not (destination / "veadk").exists()
    assert "frontend.service.studio_release_server.app:app" in (
        destination / "run.sh"
    ).read_text(encoding="utf-8")


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
