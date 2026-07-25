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

import importlib.machinery
import shutil
import tarfile
from collections.abc import Callable
from concurrent.futures import Executor, Future
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
import pytest

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


class _InlineExecutor(Executor):
    def submit(self, function: Any, *args: Any, **kwargs: Any) -> Future[None]:
        future: Future[None] = Future()
        try:
            function(*args, **kwargs)
        except Exception as error:  # pragma: no cover - executor contract
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
