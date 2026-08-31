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

import io
import subprocess
import tarfile
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.environments.git_repository import (
    GitRepositoryError,
    PublicGitRepositoryInspector,
    RepositoryFile,
    RepositorySnapshot,
)
from frontend.server.environments.models import (
    CodePipelineResource,
    ContainerRegistryResource,
    ContainerRepository,
    EnvironmentBuildStatus,
    EnvironmentBuildStep,
    EnvironmentResourceInfo,
    EnvironmentResources,
    ImageSource,
    RepositoryInspection,
)
from frontend.server.environments.repository import TosEnvironmentRepository
from frontend.server.environments.resources import (
    EnvironmentResourceSettings,
    StudioEnvironmentCloudGateway,
)
from frontend.server.environments.routes import mount_environment_routes
from frontend.server.environments.service import EnvironmentService


class _TosError(Exception):
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _Tos:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_object(self, *, key, content, forbid_overwrite=False, **_kwargs):
        if forbid_overwrite and key in self.objects:
            raise _TosError(409)
        self.objects[key] = bytes(content)

    def get_object(self, *, key, **_kwargs):
        if key not in self.objects:
            raise _TosError(404)
        return io.BytesIO(self.objects[key])

    def list_objects_type2(self, *, prefix, **_kwargs):
        return SimpleNamespace(
            contents=[
                SimpleNamespace(key=key)
                for key in sorted(self.objects)
                if key.startswith(prefix)
            ],
            is_truncated=False,
            next_continuation_token="",
        )


def _resources() -> EnvironmentResourceInfo:
    return EnvironmentResourceInfo(
        provider="volcengine",
        region="cn-beijing",
        codePipeline=CodePipelineResource(
            source="managed", workspaceId="ws", pipelineId="pipeline"
        ),
        containerRegistry=ContainerRegistryResource(
            source="provided",
            registry="registry",
            namespace="agents",
            repository="environments",
            domain="registry.example.com",
            imageRepository="registry.example.com/agents/environments",
        ),
    )


class _Inspector:
    def inspect(self, repository_url, ref=""):
        return RepositoryInspection(
            repositoryUrl=repository_url,
            ref=ref or "main",
            commitSha="a" * 40,
            dockerfiles=["services/api.Dockerfile"],
        )

    def snapshot(self, source):
        return RepositorySnapshot(
            inspection=self.inspect(source.repository_url, source.ref),
            files=(
                RepositoryFile("app.txt", b"application"),
                RepositoryFile(
                    "services/api.Dockerfile", b"FROM scratch\nCOPY app.txt /app.txt\n"
                ),
            ),
        )


class _Cloud:
    def __init__(self) -> None:
        self.builds: list[dict[str, Any]] = []
        self.image_bindings = 0

    def describe(self):
        return _resources()

    def start_build(self, **kwargs):
        self.builds.append(kwargs)
        return _resources(), "run-1", "registry.example.com/agents/environments:v1"

    def resolve_image_source(self, source):
        self.image_bindings += 1
        return _resources(), (
            f"registry.example.com/{source.namespace}/{source.repository}:"
            f"{source.reference}"
        )

    def build_status(
        self, resources: EnvironmentResources, run_id: str
    ) -> EnvironmentBuildStatus:
        del resources, run_id
        return "available"

    def build_steps(
        self, resources: EnvironmentResources, run_id: str
    ) -> list[EnvironmentBuildStep]:
        del resources, run_id
        return []

    def build_log(self, resources: EnvironmentResources, run_id: str) -> str:
        del resources, run_id
        return ""


def _payload(**updates):
    value = {
        "name": "Git environment",
        "operatingSystem": "ubuntu-24.04",
        "language": "python-3.12",
    }
    value.update(updates)
    return value


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/example/repo.git",
        "file:///tmp/repo",
        "https://token@github.com/example/repo.git",
        "https://github.com/example/repo.git?token=secret",
    ],
)
def test_public_git_inspector_rejects_unsafe_urls(url):
    inspector = PublicGitRepositoryInspector(
        resolver=lambda *_args, **_kwargs: [(2, 1, 6, "", ("140.82.112.4", 443))]
    )

    with pytest.raises(GitRepositoryError):
        inspector.inspect(url)


def test_public_git_inspector_rejects_private_dns_answers():
    inspector = PublicGitRepositoryInspector(
        resolver=lambda *_args, **_kwargs: [(2, 1, 6, "", ("127.0.0.1", 443))]
    )

    with pytest.raises(GitRepositoryError, match="私有网络"):
        inspector.inspect("https://git.example.com/team/repo.git")


def test_public_git_inspector_pins_all_git_operations_to_validated_dns_answers(
    monkeypatch,
):
    resolutions = 0

    def resolver(*_args, **_kwargs):
        nonlocal resolutions
        resolutions += 1
        return [
            (2, 1, 6, "", ("140.82.112.4", 443)),
            (10, 1, 6, "", ("2606:50c0:8000::154", 443, 0, 0)),
        ]

    inspector = PublicGitRepositoryInspector(resolver=resolver)
    calls: list[tuple[tuple[str, ...], str]] = []

    def run_git(*args: str, cwd: Path, curlopt_resolve: str = "") -> str:
        del cwd
        calls.append((args, curlopt_resolve))
        if "clone" in args:
            root = Path(args[-1])
            root.mkdir()
            (root / "Dockerfile").write_text("FROM python:3.12", encoding="utf-8")
        if "ls-tree" in args:
            return "100644 blob deadbeef 16\tDockerfile\n"
        if "branch" in args:
            return "main\n"
        if "rev-parse" in args:
            return "a" * 40
        return ""

    monkeypatch.setattr(inspector, "_run_git", run_git)

    inspected = inspector.inspect("https://GitHub.com/example/repo.git")

    assert resolutions == 1
    assert inspected.dockerfiles == ["Dockerfile"]
    assert {pin for _args, pin in calls} == {
        "github.com:443:140.82.112.4,[2606:50c0:8000::154]"
    }


def test_git_process_receives_the_pinned_curl_resolution(monkeypatch, tmp_path):
    captured: list[str] = []

    def run(command, **_kwargs):
        captured.extend(command)
        return SimpleNamespace(stdout="")

    monkeypatch.setattr(subprocess, "run", run)

    PublicGitRepositoryInspector()._run_git(
        "ls-remote",
        "https://github.com/example/repo.git",
        cwd=tmp_path,
        curlopt_resolve="github.com:443:140.82.112.4",
    )

    assert "http.curloptResolve=github.com:443:140.82.112.4" in captured


def test_git_repository_limits_files_and_total_size(tmp_path):
    (tmp_path / "one").write_bytes(b"12")
    (tmp_path / "two").write_bytes(b"34")

    with pytest.raises(GitRepositoryError, match="文件数"):
        PublicGitRepositoryInspector(max_files=1)._read_files(
            tmp_path, include_content=False
        )
    with pytest.raises(GitRepositoryError, match="大小"):
        PublicGitRepositoryInspector(max_bytes=3)._read_files(
            tmp_path, include_content=False
        )


def test_git_repository_timeout_has_an_actionable_error(monkeypatch, tmp_path):
    def timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired(["git"], timeout=1)

    monkeypatch.setattr(subprocess, "run", timeout)

    with pytest.raises(GitRepositoryError, match="超时"):
        PublicGitRepositoryInspector(timeout_seconds=1)._run_git("status", cwd=tmp_path)


def test_git_build_snapshots_repository_root_and_selected_dockerfile():
    tos = _Tos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    cloud = _Cloud()
    service = EnvironmentService(repository, cloud, git_inspector=_Inspector())
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post(
        "/web/environments",
        json=_payload(
            gitSource={
                "repositoryUrl": "https://github.com/example/repo.git",
                "ref": "main",
                "dockerfilePath": "services/api.Dockerfile",
            },
            containerRepository={
                "region": "cn-beijing",
                "registry": "registry",
                "namespace": "agents",
                "repository": "environments",
            },
        ),
    ).json()

    build = client.post(f"/web/environments/{created['id']}/build")

    assert build.status_code == 202
    assert build.json()["sourceCommitSha"] == "a" * 40
    assert cloud.builds[0]["dockerfile_path"] == "services/api.Dockerfile"
    assert cloud.builds[0]["container_repository"].registry == "registry"
    context_key = next(key for key in tos.objects if key.endswith("context.tar.gz"))
    with tarfile.open(fileobj=io.BytesIO(tos.objects[context_key])) as archive:
        assert set(archive.getnames()) == {"app.txt", "services/api.Dockerfile"}


def test_git_build_reports_when_selected_dockerfile_disappeared():
    class _MissingDockerfileInspector(_Inspector):
        def snapshot(self, source):
            return RepositorySnapshot(
                inspection=self.inspect(source.repository_url, source.ref),
                files=(RepositoryFile("app.txt", b"application"),),
            )

    tos = _Tos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    service = EnvironmentService(
        repository,
        _Cloud(),
        git_inspector=_MissingDockerfileInspector(),
    )
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post(
        "/web/environments",
        json=_payload(
            gitSource={
                "repositoryUrl": "https://github.com/example/repo.git",
                "ref": "main",
                "dockerfilePath": "services/api.Dockerfile",
            }
        ),
    ).json()

    response = client.post(f"/web/environments/{created['id']}/build")

    assert response.status_code == 400
    assert "重新探查并选择" in response.json()["detail"]


def test_existing_image_creates_available_version_without_cp_build():
    tos = _Tos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    cloud = _Cloud()
    service = EnvironmentService(repository, cloud, git_inspector=_Inspector())
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")

    response = TestClient(app).post(
        "/web/environments",
        json=_payload(
            imageSource={
                "region": "cn-beijing",
                "registry": "registry",
                "namespace": "agents",
                "repository": "runtime",
                "reference": "stable",
            }
        ),
    )

    assert response.status_code == 201
    assert response.json()["latestVersion"]["status"] == "available"
    assert response.json()["latestVersion"]["image"].endswith("/agents/runtime:stable")
    assert cloud.image_bindings == 1
    assert cloud.builds == []


def test_existing_image_update_creates_a_new_available_version():
    tos = _Tos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    cloud = _Cloud()
    service = EnvironmentService(repository, cloud, git_inspector=_Inspector())
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post(
        "/web/environments",
        json=_payload(
            imageSource={
                "region": "cn-beijing",
                "registry": "registry",
                "namespace": "agents",
                "repository": "runtime",
                "reference": "v1",
            }
        ),
    ).json()

    updated = client.patch(
        f"/web/environments/{created['id']}",
        json={
            "imageSource": {
                "region": "cn-beijing",
                "registry": "registry",
                "namespace": "agents",
                "repository": "runtime",
                "reference": "v2",
            }
        },
    )

    assert updated.status_code == 200
    body = updated.json()
    assert body["latestVersion"]["status"] == "available"
    assert body["latestVersion"]["image"].endswith("/agents/runtime:v2")
    assert body["latestVersion"]["versionId"] != created["latestVersion"]["versionId"]
    assert cloud.image_bindings == 2
    assert cloud.builds == []


class _SelectedResourceService:
    def __init__(self) -> None:
        self.required: list[tuple[str, str, str, str]] = []
        self.parameters: list[dict[str, str]] = []
        self.cr = SimpleNamespace(
            _get_default_domain=lambda registry: f"{registry}.example.com"
        )
        self.cp = SimpleNamespace(run_pipeline=self._run_pipeline)

    def _require_existing_resource(
        self, kind, *, resource_id, registry="", namespace="", **_kwargs
    ):
        self.required.append((kind, resource_id, registry, namespace))
        return {"id": resource_id, "name": resource_id}

    def _cr_client(self):
        return self.cr

    def _cp_client(self):
        return self.cp

    def _run_pipeline(self, **kwargs):
        self.parameters = kwargs["parameters"]
        return "run-selected"


def test_cp_build_validates_and_uses_selected_container_repository(monkeypatch):
    resources = _SelectedResourceService()
    target_resources = _SelectedResourceService()
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine", region="cn-beijing", bucket="studio"
        ),
        resource_service=resources,  # type: ignore[arg-type]
        resource_service_factory=lambda region: (
            target_resources
            if region == "ap-southeast-1"
            else pytest.fail(f"unexpected region: {region}")
        ),  # type: ignore[arg-type]
    )
    monkeypatch.setattr(
        gateway, "_cached_code_pipeline", lambda: _resources().code_pipeline
    )
    selection = {
        "region": "ap-southeast-1",
        "registry": "production",
        "namespace": "agents",
        "repository": "runtime",
    }

    resolved, run_id, image = gateway.start_build(
        context_key="context.tar.gz",
        image_tag="v1",
        dockerfile_path="deploy/Runtime.Dockerfile",
        container_repository=ContainerRepository.model_validate(selection),
    )

    assert run_id == "run-selected"
    assert image == "production.example.com/agents/runtime:v1"
    assert resolved.container_registry.repository == "runtime"
    assert target_resources.required == [
        ("cr-registry", "production", "", ""),
        ("cr-namespace", "agents", "production", ""),
        ("cr-repository", "runtime", "production", "agents"),
    ]
    parameters = {item["Key"]: item["Value"] for item in resources.parameters}
    assert parameters["DOCKERFILE_PATH"] == (
        "/workspace/environment/deploy/Runtime.Dockerfile"
    )
    assert parameters["CR_INSTANCE"] == "production"
    assert parameters["CR_REGION"] == "ap-southeast-1"


def test_existing_image_can_resolve_container_repository_in_selected_region():
    regional_resources = _SelectedResourceService()
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="byteplus", region="ap-southeast-1", bucket="studio"
        ),
        resource_service=_SelectedResourceService(),  # type: ignore[arg-type]
        resource_service_factory=lambda region: (
            regional_resources
            if region == "cn-beijing"
            else pytest.fail(f"unexpected region: {region}")
        ),  # type: ignore[arg-type]
    )

    resolved, image = gateway.resolve_image_source(
        ImageSource(
            region="cn-beijing",
            registry="production",
            namespace="agents",
            repository="runtime",
            reference="v1",
        )
    )

    assert resolved.region == "cn-beijing"
    assert resolved.container_registry.region == "cn-beijing"
    assert image == "production.example.com/agents/runtime:v1"
    assert regional_resources.required[-1] == (
        "cr-repository",
        "runtime",
        "production",
        "agents",
    )
