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
import json
import tarfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.deployment_resources import DeploymentResourceService
from frontend.server.environments.dockerfile import build_dockerfile
from frontend.server.environments.models import (
    SUPPORTED_OPTION_IDS,
    CodePipelineResource,
    ContainerRegistryResource,
    EnvironmentBuild,
    EnvironmentInput,
    EnvironmentResourceInfo,
)
from frontend.server.environments.repository import TosEnvironmentRepository
from frontend.server.environments.resources import (
    EnvironmentCloudGateway,
    EnvironmentResourceError,
    EnvironmentResourceSettings,
    StudioEnvironmentCloudGateway,
    _redact,
)
from frontend.server.environments.routes import mount_environment_routes
from frontend.server.environments.service import EnvironmentService

_CURRENT_RECORD_FIELDS = (
    "baseEnvironment",
    "gitSource",
    "imageSource",
    "containerRepository",
)


class _TosError(Exception):
    def __init__(self, status_code: int):
        self.status_code = status_code
        super().__init__(f"TOS {status_code}")


class FakeTos:
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

    def delete_object(self, *, key, **_kwargs):
        self.objects.pop(key, None)

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


class FakeCloud:
    def __init__(self, statuses=None, *, provider="volcengine"):
        self.statuses = list(statuses or ["available"])
        self.provider = provider
        self.started: list[tuple[str, str]] = []
        self.log_calls = 0

    def describe(self):
        return _resource_info(self.provider, "managed", "managed")

    def start_build(self, *, context_key, image_tag):
        self.started.append((context_key, image_tag))
        resources = _resource_info(self.provider, "managed", "managed")
        return resources, "run-1", f"registry.example/env/images:{image_tag}"

    def build_status(self, resources, run_id):
        del resources, run_id
        return self.statuses.pop(0)

    def build_steps(self, resources, run_id):
        del resources, run_id
        from frontend.server.environments.models import EnvironmentBuildStep

        return [
            EnvironmentBuildStep(
                key="download",
                label="下载构建上下文",
                status="succeeded",
            ),
            EnvironmentBuildStep(
                key="extract",
                label="解压构建上下文",
                status="succeeded",
            ),
            EnvironmentBuildStep(
                key="build",
                label="构建并推送镜像",
                status="running",
            ),
        ]

    def build_log(self, resources, run_id):
        del resources, run_id
        self.log_calls += 1
        return "build failed"


class FakeCP:
    def __init__(self, *, provided=False, incompatible=False, run_error=False):
        self.workspaces = (
            [{"Id": "ws-provided", "Name": "customer-workspace"}] if provided else []
        )
        self.pipelines: dict[str, list[dict]] = {}
        self.incompatible = incompatible
        self.run_error = run_error
        self.created_workspaces: list[str] = []
        self.created_pipelines: list[str] = []
        self.run_parameters: list[dict] = []
        self.stages: list[dict] = []

    def list_workspaces(
        self, page_number=1, page_size=10, name_filter="", workspace_ids=None
    ):
        del page_number, page_size
        if workspace_ids and any(
            not str(item).startswith("ws-") for item in workspace_ids
        ):
            raise ValueError("workspace_ids only accepts CP workspace IDs")
        items = self.workspaces
        if workspace_ids:
            items = [item for item in items if item["Id"] in workspace_ids]
        if name_filter:
            items = [item for item in items if name_filter in item["Name"]]
        return {"Items": items, "TotalCount": len(items)}

    def get_workspaces_by_name(self, name, page_number=1, page_size=10):
        return self.list_workspaces(page_number, page_size, name_filter=name)

    def create_workspace(self, *, name, visibility, description=""):
        del visibility, description
        self.created_workspaces.append(name)
        self.workspaces.append({"Id": "ws-managed", "Name": name})
        return "ws-managed"

    def list_pipelines(
        self,
        workspace_id,
        page_number=1,
        page_size=10,
        name_filter="",
        pipeline_ids=None,
    ):
        del page_number, page_size
        items = self.pipelines.get(workspace_id, [])
        if name_filter:
            items = [item for item in items if name_filter in item["Name"]]
        if pipeline_ids:
            items = [item for item in items if item["Id"] in pipeline_ids]
        return {"Items": items, "TotalCount": len(items)}

    def _create_pipeline(self, *, workspace_id, pipeline_name, spec, parameters):
        self.created_pipelines.append(pipeline_name)
        item = {
            "Id": "pipeline-1",
            "Name": pipeline_name,
            "Spec": spec,
            "Parameters": [] if self.incompatible else parameters,
        }
        self.pipelines.setdefault(workspace_id, []).append(item)
        return "pipeline-1"

    def is_agentkit_build_pipeline(self, pipeline):
        return not self.incompatible and "tos-download" in pipeline.get("Spec", "")

    def run_pipeline(self, **kwargs):
        if self.run_error:
            raise RuntimeError("secret-value denied")
        self.run_parameters = kwargs["parameters"]
        return "run-1"

    def get_pipeline_run_status(self, **_kwargs):
        return "Succeeded"

    def list_pipeline_run_stages_inner(self, **_kwargs):
        return {"Items": self.stages}

    def download_and_merge_pipeline_logs(self, *, output_file, **_kwargs):
        with open(output_file, "w", encoding="utf-8") as stream:
            stream.write("failure log")
        return output_file


class FakeCR:
    def __init__(self, *, provided=False):
        self.registries = (
            [{"Name": "customer", "Status": "Running"}] if provided else []
        )
        self.namespaces = {"customer": [{"Name": "team"}]} if provided else {}
        self.repositories = (
            {("customer", "team"): [{"Name": "runtime"}]} if provided else {}
        )
        self.created: list[tuple[str, ...]] = []
        self.region = "cn-beijing"

    def list_registries(self, page_number, page_size):
        del page_number, page_size
        return {"Items": self.registries, "TotalCount": len(self.registries)}

    def list_namespaces(self, registry, page_number, page_size):
        del page_number, page_size
        items = self.namespaces.get(registry, [])
        return {"Items": items, "TotalCount": len(items)}

    def list_repositories(self, registry, namespace, page_number, page_size):
        del page_number, page_size
        items = self.repositories.get((registry, namespace), [])
        return {"Items": items, "TotalCount": len(items)}

    def _create_instance(self, registry):
        self.created.append(("registry", registry))
        self.registries.append({"Name": registry, "Status": "Running"})

    def _create_namespace(self, registry, namespace):
        self.created.append(("namespace", registry, namespace))
        self.namespaces.setdefault(registry, []).append({"Name": namespace})

    def _create_repo(self, registry, namespace, repository):
        self.created.append(("repository", registry, namespace, repository))
        self.repositories.setdefault((registry, namespace), []).append(
            {"Name": repository}
        )

    def _get_default_domain(self, registry):
        return f"{registry}.example.com"


def _resource_info(provider, cp_source, cr_source):
    return EnvironmentResourceInfo(
        provider=provider,
        region="cn-beijing" if provider == "volcengine" else "ap-southeast-1",
        codePipeline=CodePipelineResource(
            source=cp_source,
            workspaceId="ws-1",
            workspaceName="workspace",
            pipelineId="pipeline-1",
            pipelineName="environment-build",
            consoleUrl="https://console.example/cp",
        ),
        containerRegistry=ContainerRegistryResource(
            source=cr_source,
            registry="registry",
            namespace="environment",
            repository="images",
            domain="registry.example",
            imageRepository="registry.example/environment/images",
            consoleUrl="https://console.example/cr",
        ),
    )


class FakeToolProvisioner:
    def __init__(self, *, error: Exception | None = None):
        self.error = error
        self.calls: list[tuple[str, str, str]] = []

    async def ensure_ready(self, *, image, provider, region):
        from frontend.server.environments.tool_provisioning import (
            EnvironmentToolState,
        )

        self.calls.append((image, provider, region))
        if self.error is not None:
            raise self.error
        return EnvironmentToolState(
            tool_id=f"tool-{provider}",
            name="studio-env-test",
            status="ready",
        )


class BlockingToolProvisioner(FakeToolProvisioner):
    def __init__(self) -> None:
        import asyncio

        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def ensure_ready(self, *, image, provider, region):
        self.started.set()
        await self.release.wait()
        return await super().ensure_ready(
            image=image,
            provider=provider,
            region=region,
        )


def _service(tos=None, cloud=None, tool_provisioner=None):
    tos = tos or FakeTos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    return (
        EnvironmentService(
            repository,
            cloud or FakeCloud(),
            tool_provisioner=tool_provisioner,
        ),
        tos,
    )


def _payload(**updates):
    payload = {
        "name": "Python 通用开发",
        "description": "common runtime",
        "operatingSystem": "ubuntu-22.04",
        "language": "python-3.12",
        "optionIds": ["lark-cli", "pandoc"],
    }
    payload.update(updates)
    return payload


def test_legacy_environment_payload_defaults_to_ubuntu():
    config = EnvironmentInput.model_validate(_payload())

    assert config.base_environment == "ubuntu"


def test_aio_environment_preserves_the_shell_runtime_contract():
    config = EnvironmentInput.model_validate(
        _payload(
            baseEnvironment="aio-sandbox",
            operatingSystem="ubuntu-24.04",
            language="python-3.10",
        )
    )
    dockerfile = build_dockerfile(config)

    assert config.operating_system == "ubuntu-22.04"
    assert config.language == "python-3.12"
    assert (
        "ARG AIO_BASE_IMAGE="
        "agentkit-cli-2107625663-cn-beijing.cr.volces.com/agentkit/"
        "agent-native-requirements-aio:0.2.1-20260831"
    ) in dockerfile
    assert "FROM --platform=${AIO_BASE_PLATFORM} ${AIO_BASE_IMAGE}" in dockerfile
    assert "BASH_VENV_PATH=/opt/veadk-environment/.venv" in dockerfile
    assert "EXPOSE 8080" in dockerfile
    assert "CMD " not in dockerfile
    assert "ENTRYPOINT " not in dockerfile


@pytest.mark.parametrize("operating_system", ["ubuntu-22.04", "ubuntu-24.04"])
@pytest.mark.parametrize("language", ["python-3.10", "python-3.12"])
def test_all_os_language_combinations_generate_buildable_commented_dockerfiles(
    operating_system, language
):
    config = EnvironmentInput.model_validate(
        _payload(
            operatingSystem=operating_system,
            language=language,
            optionIds=["lark-cli", "pandoc", "playwright"],
        )
    )
    dockerfile = build_dockerfile(config)

    assert f"FROM ubuntu:{operating_system.removeprefix('ubuntu-')}" in dockerfile
    assert f"# Python {language.removeprefix('python-')}" in dockerfile
    assert "ca-certificates" in dockerfile
    assert "PIP_DEFAULT_TIMEOUT=300" in dockerfile
    assert "PIP_RETRIES=10" in dockerfile
    assert "PIP_INDEX_URL=https://pypi.org/simple" in dockerfile
    assert "PYTHON_SOURCE_BASE_URL=https://www.python.org/ftp/python" in dockerfile
    assert "PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.playwright.dev" in dockerfile
    assert "ARG APT_MIRROR_URL=http://archive.ubuntu.com/ubuntu" in dockerfile
    assert 'Acquire::Retries "5"' in dockerfile
    assert 'Acquire::ForceIPv4 "true"' in dockerfile
    assert dockerfile.count("apt-get update") == 1
    assert dockerfile.count("apt-get install -y --no-install-recommends") == 1
    assert "# VeADK:" in dockerfile
    assert "# lxml-html-clean:" in dockerfile
    assert (
        '"veadk-python[a2ui,database,eval,extensions,harness,harness-sidecar,pdf,speech]'
        '>=1.1.1"' in dockerfile
    )
    assert '"agentkit-sdk-python==0.8.4"' in dockerfile
    assert '"starlette<1.0.0"' in dockerfile
    assert "lxml-html-clean" in dockerfile
    assert 'ENV VEADK_ENVIRONMENT_IMAGE="1"' in dockerfile
    assert "# lark-cli:" in dockerfile
    assert "# pandoc:" in dockerfile
    assert "# Playwright:" in dockerfile
    assert "python -m playwright install chromium" in dockerfile
    assert "playwright install --with-deps" not in dockerfile
    uses_ubuntu_python = (
        operating_system == "ubuntu-22.04" and language == "python-3.10"
    ) or (operating_system == "ubuntu-24.04" and language == "python-3.12")
    assert ("Python-3.10.18.tgz" in dockerfile) is (
        not uses_ubuntu_python and language == "python-3.10"
    )
    assert ("Python-3.12.11.tgz" in dockerfile) is (
        not uses_ubuntu_python and language == "python-3.12"
    )
    assert ("./configure --prefix=/opt/python" in dockerfile) is (
        not uses_ubuntu_python
    )
    assert "astral.sh" not in dockerfile
    assert "github.com/astral-sh" not in dockerfile
    assert ("add-apt-repository" in dockerfile) is False
    assert ("ppa.launchpadcontent.net" in dockerfile) is False


@pytest.mark.parametrize(
    "option_ids,expected",
    [
        (
            ["github-cli"],
            [
                "# GitHub CLI: 在终端中管理 GitHub 工作流",
                "    gh \\",
            ],
        ),
        (
            ["opencli"],
            [
                "node-v22.18.0-linux-${node_arch}.tar.xz",
                "npm install --global @jackwener/opencli@1.8.7",
            ],
        ),
        (
            ["chromium"],
            [
                "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
                "python -m pip install --upgrade playwright",
                "python -m playwright install chromium",
            ],
        ),
        (
            ["playwright"],
            [
                "ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright",
                "python -m pip install --upgrade playwright",
                "python -m playwright install chromium",
            ],
        ),
    ],
)
def test_special_tool_recipes_include_reliable_installers(option_ids, expected):
    dockerfile = build_dockerfile(
        EnvironmentInput.model_validate(_payload(optionIds=option_ids))
    )

    for fragment in expected:
        assert fragment in dockerfile


@pytest.mark.parametrize(
    "option_ids",
    (["playwright", "chromium"], ["chromium", "playwright"]),
)
def test_playwright_and_chromium_share_one_browser_install(option_ids):
    dockerfile = build_dockerfile(
        EnvironmentInput.model_validate(_payload(optionIds=option_ids))
    )

    assert dockerfile.count("python -m pip install --upgrade playwright") == 1
    assert dockerfile.count("python -m playwright install chromium") == 1
    assert dockerfile.index(
        "python -m pip install --upgrade playwright"
    ) < dockerfile.index("python -m playwright install chromium")
    assert dockerfile.count("apt-get update") == 1
    assert "# Playwright:" in dockerfile
    assert "# Chromium:" in dockerfile


@pytest.mark.parametrize(
    "operating_system,expected_browser_package",
    [
        ("ubuntu-22.04", "libasound2"),
        ("ubuntu-24.04", "libasound2t64"),
    ],
)
def test_selected_apt_packages_are_installed_in_one_batch(
    operating_system, expected_browser_package
):
    dockerfile = build_dockerfile(
        EnvironmentInput.model_validate(
            _payload(
                operatingSystem=operating_system,
                optionIds=sorted(SUPPORTED_OPTION_IDS),
            )
        )
    )

    assert dockerfile.count("apt-get update") == 1
    assert dockerfile.count("apt-get install -y --no-install-recommends") == 1
    for package in (
        "ca-certificates",
        "xz-utils",
        "pandoc",
        "ripgrep",
        "gh",
        "git",
        "ffmpeg",
        expected_browser_package,
    ):
        assert f"    {package} \\" in dockerfile


def test_environment_crud_build_and_tos_version_layout():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "tenant/a")
    client = TestClient(app)

    created = client.post("/web/environments", json=_payload())
    assert created.status_code == 201
    environment = created.json()
    environment_id = environment["id"]
    assert environment["dockerfile"].startswith("# Operating system")
    assert "ownerId" not in environment

    listed = client.get("/web/environments").json()["items"]
    assert [item["id"] for item in listed] == [environment_id]

    updated = client.patch(
        f"/web/environments/{environment_id}",
        json={"language": "python-3.10", "optionIds": ["git"]},
    ).json()
    assert "# Python 3.10" in updated["dockerfile"]
    assert "# Git:" in updated["dockerfile"]

    started = client.post(f"/web/environments/{environment_id}/build")
    assert started.status_code == 202
    build = started.json()
    assert build["status"] == "building"
    version_id = build["versionId"]

    status = client.get(
        f"/web/environments/{environment_id}/builds/{version_id}"
    ).json()
    assert status["status"] == "available"
    latest = client.get(f"/web/environments/{environment_id}").json()["latestVersion"]
    assert latest["versionId"] == version_id
    assert latest["status"] == "available"
    prefix = f"veadk-studio/v2/environments/tenant%2Fa/{environment_id}"
    assert f"{prefix}/summary.json" in tos.objects
    assert (
        f"veadk-studio/v1/environments/tenant%2Fa/{environment_id}/summary.json"
        not in tos.objects
    )
    assert f"{prefix}/latest.json" in tos.objects
    assert f"{prefix}/versions/{version_id}/config.json" in tos.objects
    assert f"{prefix}/versions/{version_id}/Dockerfile" in tos.objects
    assert f"{prefix}/versions/{version_id}/context.tar.gz" in tos.objects
    assert f"{prefix}/versions/{version_id}/build.json" in tos.objects
    assert f"{prefix}/versions/{version_id}/image.json" in tos.objects

    assert client.delete(f"/web/environments/{environment_id}").status_code == 204
    assert client.get(f"/web/environments/{environment_id}").status_code == 404


def test_environment_list_reads_legacy_v1_records():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post("/web/environments", json=_payload()).json()
    current_key = f"veadk-studio/v2/environments/owner/{created['id']}/summary.json"
    legacy_key = f"veadk-studio/v1/environments/owner/{created['id']}/summary.json"
    legacy = json.loads(tos.objects.pop(current_key))
    for field in _CURRENT_RECORD_FIELDS:
        legacy.pop(field)
    tos.objects[legacy_key] = json.dumps(legacy).encode()

    response = client.get("/web/environments")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [created["id"]]
    assert response.json()["items"][0]["baseEnvironment"] == "ubuntu"
    assert current_key not in tos.objects


def test_environment_api_reads_a_complete_legacy_v1_environment_tree():
    initial_service, tos = _service()
    initial_app = FastAPI()
    mount_environment_routes(initial_app, initial_service, lambda _request: "owner")
    initial_client = TestClient(initial_app)
    created = initial_client.post("/web/environments", json=_payload()).json()
    started = initial_client.post(f"/web/environments/{created['id']}/build").json()
    initial_client.get(
        f"/web/environments/{created['id']}/builds/{started['versionId']}"
    )
    current_prefix = f"veadk-studio/v2/environments/owner/{created['id']}"
    legacy_prefix = f"veadk-studio/v1/environments/owner/{created['id']}"
    for current_key in [key for key in tos.objects if key.startswith(current_prefix)]:
        content = tos.objects.pop(current_key)
        if current_key.endswith(("/summary.json", "/config.json")):
            payload = json.loads(content)
            for field in _CURRENT_RECORD_FIELDS:
                payload.pop(field)
            content = json.dumps(payload).encode()
        elif current_key.endswith(("/build.json", "/latest.json")):
            payload = json.loads(content)
            for field in ("toolId", "toolStatus", "sourceCommitSha"):
                payload.pop(field)
            content = json.dumps(payload).encode()
        tos.objects[current_key.replace(current_prefix, legacy_prefix, 1)] = content

    restored_service, _ = _service(tos=tos)
    restored_app = FastAPI()
    mount_environment_routes(restored_app, restored_service, lambda _request: "owner")
    restored_client = TestClient(restored_app)

    listed = restored_client.get("/web/environments")
    build = restored_client.get(
        f"/web/environments/{created['id']}/builds/{started['versionId']}"
    )
    manifest = restored_client.get(
        f"/web/environments/{created['id']}/builds/{started['versionId']}/manifest"
    )

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()["items"]] == [created["id"]]
    assert build.status_code == 200
    assert build.json()["versionId"] == started["versionId"]
    assert manifest.status_code == 200
    assert manifest.json()["spec"]["baseEnvironment"] == "ubuntu"


def test_environment_list_prefers_v2_record_over_legacy_v1_record():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post("/web/environments", json=_payload()).json()
    current_key = f"veadk-studio/v2/environments/owner/{created['id']}/summary.json"
    legacy_key = f"veadk-studio/v1/environments/owner/{created['id']}/summary.json"
    legacy = json.loads(tos.objects[current_key])
    legacy["name"] = "旧版本名称"
    for field in _CURRENT_RECORD_FIELDS:
        legacy.pop(field)
    tos.objects[legacy_key] = json.dumps(legacy).encode()

    response = client.get("/web/environments")

    assert response.status_code == 200
    assert len(response.json()["items"]) == 1
    assert response.json()["items"][0]["name"] == created["name"]


def test_environment_update_copies_legacy_v1_record_to_v2():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post("/web/environments", json=_payload()).json()
    current_key = f"veadk-studio/v2/environments/owner/{created['id']}/summary.json"
    legacy_key = f"veadk-studio/v1/environments/owner/{created['id']}/summary.json"
    legacy = json.loads(tos.objects.pop(current_key))
    for field in _CURRENT_RECORD_FIELDS:
        legacy.pop(field)
    tos.objects[legacy_key] = json.dumps(legacy).encode()

    response = client.patch(
        f"/web/environments/{created['id']}", json={"name": "迁移后的环境"}
    )

    assert response.status_code == 200
    assert response.json()["name"] == "迁移后的环境"
    assert json.loads(tos.objects[current_key])["name"] == "迁移后的环境"
    assert json.loads(tos.objects[legacy_key])["name"] == created["name"]


def test_environment_list_repairs_records_written_to_legacy_prefix_by_new_schema():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post(
        "/web/environments",
        json=_payload(
            baseEnvironment="aio-sandbox",
            gitSource={
                "repositoryUrl": "https://github.com/example/repo.git",
                "ref": "main",
                "dockerfilePath": "Dockerfile",
            },
        ),
    ).json()
    current_key = f"veadk-studio/v2/environments/owner/{created['id']}/summary.json"
    legacy_key = f"veadk-studio/v1/environments/owner/{created['id']}/summary.json"
    polluted = tos.objects.pop(current_key)
    tos.objects[legacy_key] = polluted

    response = client.get("/web/environments")

    assert response.status_code == 200
    assert response.json()["items"][0]["gitSource"]["ref"] == "main"
    assert json.loads(tos.objects[current_key])["gitSource"]["ref"] == "main"
    repaired = json.loads(tos.objects[legacy_key])
    assert set(repaired) == {
        "name",
        "description",
        "operatingSystem",
        "language",
        "executionRuntime",
        "optionIds",
        "selectedSkills",
        "dockerfile",
        "id",
        "ownerId",
        "createdAt",
        "updatedAt",
        "latestVersionId",
    }


def test_environment_manifest_describes_the_immutable_image_version():
    service, _tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)

    environment = client.post(
        "/web/environments",
        json=_payload(
            name="Browser tools",
            description="Browser automation",
            operatingSystem="ubuntu-24.04",
            optionIds=["playwright", "chromium"],
        ),
    ).json()
    build = client.post(f"/web/environments/{environment['id']}/build").json()
    version_id = build["versionId"]

    client.patch(
        f"/web/environments/{environment['id']}",
        json={"name": "Edited after build", "optionIds": ["git"]},
    )
    response = client.get(
        f"/web/environments/{environment['id']}/builds/{version_id}/manifest"
    )

    assert response.status_code == 200
    manifest = response.json()
    assert manifest["apiVersion"] == "agentkit.studio/v1alpha1"
    assert manifest["kind"] == "Environment"
    assert manifest["metadata"] == {
        "id": environment["id"],
        "name": "Browser tools",
        "version": version_id,
        "description": "Browser automation",
    }
    assert manifest["spec"]["image"] == build["image"]
    assert manifest["spec"]["baseEnvironment"] == "ubuntu"
    assert manifest["spec"]["baseImage"] == "ubuntu:24.04"
    assert manifest["spec"]["operatingSystem"] == "ubuntu-24.04"
    assert manifest["spec"]["language"] == "python-3.12"
    assert manifest["spec"]["executionRuntime"] == "veadk"
    assert manifest["spec"]["packages"] == ["playwright", "chromium"]
    assert manifest["spec"]["capabilities"] == []
    assert manifest["spec"]["skills"] == []
    assert manifest["status"]["phase"] == "available"
    assert manifest["status"]["toolId"] == ""
    assert manifest["status"]["toolStatus"] == ""


@pytest.mark.parametrize(
    "provider,region",
    [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")],
)
def test_aio_build_provisions_and_persists_a_ready_private_tool(provider, region):
    provisioner = FakeToolProvisioner()
    service, tos = _service(
        cloud=FakeCloud(provider=provider),
        tool_provisioner=provisioner,
    )
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    with TestClient(app) as client:
        environment = client.post(
            "/web/environments",
            json=_payload(baseEnvironment="aio-sandbox"),
        ).json()
        started = client.post(f"/web/environments/{environment['id']}/build").json()

        provisioning = client.get(
            f"/web/environments/{environment['id']}/builds/{started['versionId']}"
        ).json()
        assert provisioning["status"] == "building"
        assert provisioning["toolStatus"] == "creating"
        assert provisioning["steps"][-1]["key"] == "sandbox-tool"
        assert provisioning["steps"][-1]["status"] == "running"

        completed = _wait_for_build(
            client,
            f"/web/environments/{environment['id']}/builds/{started['versionId']}",
        )
        manifest = client.get(
            f"/web/environments/{environment['id']}/builds/"
            f"{started['versionId']}/manifest"
        ).json()

    assert completed["status"] == "available"
    assert completed["toolId"] == f"tool-{provider}"
    assert completed["toolStatus"] == "ready"
    assert completed["steps"][-1]["key"] == "sandbox-tool"
    assert completed["steps"][-1]["status"] == "succeeded"
    assert provisioner.calls == [(started["image"], provider, region)]
    prefix = (
        f"veadk-studio/v2/environments/owner/{environment['id']}"
        f"/versions/{started['versionId']}"
    )
    persisted = json.loads(tos.objects[f"{prefix}/build.json"])
    assert persisted["toolId"] == f"tool-{provider}"
    assert persisted["toolStatus"] == "ready"
    assert manifest["status"]["toolId"] == f"tool-{provider}"
    assert manifest["status"]["toolStatus"] == "ready"


def test_ubuntu_build_does_not_provision_a_private_tool():
    provisioner = FakeToolProvisioner()
    service, _tos = _service(tool_provisioner=provisioner)
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    environment = client.post("/web/environments", json=_payload()).json()
    started = client.post(f"/web/environments/{environment['id']}/build").json()

    completed = client.get(
        f"/web/environments/{environment['id']}/builds/{started['versionId']}"
    ).json()

    assert completed["status"] == "available"
    assert completed["toolId"] == ""
    assert completed["toolStatus"] == ""
    assert provisioner.calls == []


def test_legacy_build_without_tool_fields_remains_valid():
    build = EnvironmentBuild.model_validate(
        {
            "environmentId": "a" * 32,
            "versionId": "20260831T010203Z-abcdef12",
            "status": "available",
            "image": "registry.example/environment:v1",
            "createdAt": "2026-08-31T01:02:03Z",
            "updatedAt": "2026-08-31T01:02:03Z",
        }
    )

    assert build.tool_id == ""
    assert build.tool_status == ""


@pytest.mark.asyncio
@pytest.mark.parametrize("query", ["list", "get", "get_build"])
async def test_environment_queries_backfill_legacy_aio_tool_binding(query: str):
    initial_service, tos = _service(tool_provisioner=FakeToolProvisioner())
    app = FastAPI()
    mount_environment_routes(app, initial_service, lambda _request: "owner")
    with TestClient(app) as client:
        environment = client.post(
            "/web/environments",
            json=_payload(baseEnvironment="aio-sandbox"),
        ).json()
        started = client.post(f"/web/environments/{environment['id']}/build").json()
        build_url = (
            f"/web/environments/{environment['id']}/builds/{started['versionId']}"
        )
        client.get(build_url)
        _wait_for_build(client, build_url)
    prefix = (
        f"veadk-studio/v2/environments/owner/{environment['id']}"
        f"/versions/{started['versionId']}"
    )
    legacy = json.loads(tos.objects[f"{prefix}/build.json"])
    legacy.pop("toolId")
    legacy.pop("toolStatus")
    tos.objects[f"{prefix}/build.json"] = json.dumps(legacy).encode()

    blocking = BlockingToolProvisioner()
    restored_service, _ = _service(tos=tos, tool_provisioner=blocking)
    if query == "list":
        result = (await restored_service.list("owner"))[0].latest_version
    elif query == "get":
        result = (await restored_service.get("owner", environment["id"])).latest_version
    else:
        result = await restored_service.get_build(
            "owner",
            environment["id"],
            started["versionId"],
        )

    assert result is not None
    assert result.status == "building"
    assert result.tool_status == "creating"
    await blocking.started.wait()
    tasks = list(restored_service._tool_tasks.values())
    blocking.release.set()
    await __import__("asyncio").gather(*tasks)

    completed = await restored_service.get_build(
        "owner",
        environment["id"],
        started["versionId"],
    )
    assert completed.status == "available"
    assert completed.tool_id == "tool-volcengine"
    assert completed.tool_status == "ready"
    assert len(blocking.calls) == 1


@pytest.mark.asyncio
async def test_resolving_legacy_aio_version_backfills_persisted_tool_binding():
    initial_provisioner = FakeToolProvisioner()
    service, tos = _service(tool_provisioner=initial_provisioner)
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    with TestClient(app) as client:
        environment = client.post(
            "/web/environments",
            json=_payload(baseEnvironment="aio-sandbox"),
        ).json()
        started = client.post(f"/web/environments/{environment['id']}/build").json()
        build_url = (
            f"/web/environments/{environment['id']}/builds/{started['versionId']}"
        )
        client.get(build_url)
        _wait_for_build(client, build_url)
    prefix = (
        f"veadk-studio/v2/environments/owner/{environment['id']}"
        f"/versions/{started['versionId']}"
    )
    legacy = json.loads(tos.objects[f"{prefix}/build.json"])
    legacy.pop("toolId")
    legacy.pop("toolStatus")
    tos.objects[f"{prefix}/build.json"] = json.dumps(legacy).encode()

    backfill = FakeToolProvisioner()
    restored_service, _ = _service(
        tos=tos,
        tool_provisioner=backfill,
    )
    with pytest.raises(ValueError, match="正在准备"):
        await restored_service.resolve_for_agent(
            "owner",
            environment["id"],
            started["versionId"],
        )

    await __import__("asyncio").gather(*restored_service._tool_tasks.values())
    resolved = await restored_service.resolve_for_agent(
        "owner",
        environment["id"],
        started["versionId"],
    )

    assert resolved.tool_id == "tool-volcengine"
    assert resolved.tool_status == "ready"
    assert len(backfill.calls) == 1
    persisted = json.loads(tos.objects[f"{prefix}/build.json"])
    assert persisted["toolId"] == "tool-volcengine"
    assert persisted["toolStatus"] == "ready"


@pytest.mark.asyncio
async def test_persisted_creating_state_resumes_after_service_restart():
    tos = FakeTos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    blocking = BlockingToolProvisioner()
    service = EnvironmentService(
        repository,
        cast(EnvironmentCloudGateway, FakeCloud()),
        tool_provisioner=blocking,
    )
    environment = await service.create(
        "owner",
        EnvironmentInput.model_validate(_payload(baseEnvironment="aio-sandbox")),
    )
    started = await service.start_build("owner", environment.id)

    creating = await service.get_build("owner", environment.id, started.version_id)
    await blocking.started.wait()
    assert creating.status == "building"
    assert creating.tool_status == "creating"
    for task in service._tool_tasks.values():
        task.cancel()
    await __import__("asyncio").gather(
        *service._tool_tasks.values(), return_exceptions=True
    )

    resumed_provisioner = FakeToolProvisioner()
    resumed_service = EnvironmentService(
        repository,
        cast(EnvironmentCloudGateway, FakeCloud()),
        tool_provisioner=resumed_provisioner,
    )
    resumed = await resumed_service.get_build(
        "owner", environment.id, started.version_id
    )
    assert resumed.status == "building"
    assert resumed.tool_status == "creating"
    await __import__("asyncio").gather(*resumed_service._tool_tasks.values())

    completed = await repository.get_build("owner", environment.id, started.version_id)
    assert completed.status == "available"
    assert completed.tool_id == "tool-volcengine"
    assert completed.tool_status == "ready"
    assert len(resumed_provisioner.calls) == 1


def _wait_for_build(client: TestClient, url: str) -> dict:
    for _ in range(20):
        result = client.get(url).json()
        if result["status"] in {"available", "failed"}:
            return result
        time.sleep(0.01)
    raise AssertionError("environment build did not reach a terminal state")


def test_build_detail_returns_steps_and_only_downloads_logs_when_requested():
    cloud = FakeCloud(statuses=["building", "available"])
    service, tos = _service(cloud=cloud)
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    environment_id = client.post("/web/environments", json=_payload()).json()["id"]
    build = client.post(f"/web/environments/{environment_id}/build").json()
    version_id = build["versionId"]

    active = client.get(
        f"/web/environments/{environment_id}/builds/{version_id}"
    ).json()

    assert active["status"] == "building"
    assert active["currentStep"] == "构建并推送镜像"
    assert [item["status"] for item in active["steps"]] == [
        "succeeded",
        "succeeded",
        "running",
    ]
    assert active["logTail"] == ""
    assert cloud.log_calls == 0

    complete = client.get(
        f"/web/environments/{environment_id}/builds/{version_id}?includeLogs=true"
    ).json()

    assert complete["status"] == "available"
    assert complete["logTail"] == "build failed"
    assert complete["logUpdatedAt"]
    assert cloud.log_calls == 1
    prefix = (
        f"veadk-studio/v2/environments/owner/{environment_id}/versions/{version_id}"
    )
    assert tos.objects[f"{prefix}/build.log"] == b"build failed"


def test_gateway_maps_cp_step_names_and_statuses():
    cp = FakeCP()
    cp.stages = [
        {
            "Tasks": [
                {
                    "Steps": [
                        {"Name": "download", "Status": "Succeeded"},
                        {"Name": "extract", "Status": "Running"},
                        {"Name": "build", "Status": "Pending"},
                    ]
                }
            ]
        }
    ]
    resources = DeploymentResourceService("volcengine", "cn-beijing")
    resources._cp = cp
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine", region="cn-beijing", bucket="studio"
        ),
        resource_service=resources,
    )

    steps = gateway.build_steps(
        _resource_info("volcengine", "managed", "managed"), "run-1"
    )

    assert [(step.label, step.status) for step in steps] == [
        ("下载构建上下文", "succeeded"),
        ("解压构建上下文", "running"),
        ("构建并推送镜像", "pending"),
    ]


def test_custom_dockerfile_is_preserved_verbatim():
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    custom = "FROM ubuntu:24.04\n# custom package\nRUN echo custom"

    response = TestClient(app).post(
        "/web/environments", json=_payload(dockerfile=custom)
    )

    assert response.status_code == 201
    assert response.json()["dockerfile"] == custom
    environment_id = response.json()["id"]
    summary = tos.objects[
        f"veadk-studio/v2/environments/owner/{environment_id}/summary.json"
    ]
    assert json.loads(summary)["dockerfile"] == custom


def test_environment_build_snapshots_local_skills_into_fixed_image_directory(tmp_path):
    service, tos = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    created = client.post(
        "/web/environments",
        json=_payload(
            selectedSkills=[
                {
                    "source": "local",
                    "folder": "release-notes",
                    "name": "release-notes",
                    "localFiles": [
                        {
                            "path": "skills/release-notes/SKILL.md",
                            "content": (
                                "---\nname: release-notes\n"
                                "description: Draft release notes.\n---\n"
                            ),
                        }
                    ],
                }
            ]
        ),
    )
    assert created.status_code == 201
    environment = created.json()
    assert environment["selectedSkills"][0]["localFiles"] == []
    assert environment["selectedSkills"][0]["artifactId"]

    build = client.post(f"/web/environments/{environment['id']}/build")
    assert build.status_code == 202
    version_id = build.json()["versionId"]
    prefix = (
        f"veadk-studio/v2/environments/owner/{environment['id']}/versions/{version_id}"
    )
    manifest = json.loads(tos.objects[f"{prefix}/skills-manifest.json"])
    assert manifest["skills"][0]["name"] == "release-notes"
    assert manifest["skills"][0]["folder"] == "release-notes"
    assert manifest["skills"][0]["digest"]
    with tarfile.open(
        fileobj=io.BytesIO(tos.objects[f"{prefix}/context.tar.gz"])
    ) as archive:
        names = set(archive.getnames())
        dockerfile_file = archive.extractfile("Dockerfile")
        assert dockerfile_file is not None
        dockerfile = dockerfile_file.read().decode()
    assert ".studio/environment-skills/release-notes/SKILL.md" in names
    assert ".studio/environment-skills-manifest.json" in names
    assert "/opt/veadk/environment/skills/" in dockerfile

    completed = client.get(f"/web/environments/{environment['id']}/builds/{version_id}")
    assert completed.json()["status"] == "available"
    snapshot = __import__("asyncio").run(
        service.get_skill_files_for_agent("owner", environment["id"], version_id)
    )
    assert [(file.path, file.content) for file in snapshot] == [
        (
            "release-notes/SKILL.md",
            "---\nname: release-notes\ndescription: Draft release notes.\n---\n",
        )
    ]
    staged = __import__("asyncio").run(
        service.stage_skill_files_for_agent(
            "owner", environment["id"], version_id, tmp_path / "environment-skills"
        )
    )
    assert (staged / "release-notes" / "SKILL.md").read_text() == snapshot[0].content

    preserved = client.patch(
        f"/web/environments/{environment['id']}",
        json={
            "selectedSkills": [
                {
                    "source": "local",
                    "folder": "release-notes",
                    "name": "release-notes",
                }
            ]
        },
    )
    assert preserved.status_code == 200
    assert (
        preserved.json()["selectedSkills"][0]["artifactId"]
        == (environment["selectedSkills"][0]["artifactId"])
    )


def test_environment_resolution_rejects_non_available_version():
    service, _tos = _service(cloud=FakeCloud(statuses=["building"]))
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    environment_id = client.post("/web/environments", json=_payload()).json()["id"]
    version_id = client.post(f"/web/environments/{environment_id}/build").json()[
        "versionId"
    ]

    import asyncio

    with pytest.raises(ValueError, match="尚未构建完成"):
        asyncio.run(service.resolve_for_agent("owner", environment_id, version_id))


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
@pytest.mark.parametrize("provided_cp", [False, True])
@pytest.mark.parametrize("provided_cr", [False, True])
def test_resource_matrix_supports_managed_and_provided_combinations(
    provider, provided_cp, provided_cr
):
    region = "cn-beijing" if provider == "volcengine" else "ap-southeast-1"
    cp = FakeCP(provided=provided_cp)
    cr = FakeCR(provided=provided_cr)
    resources = DeploymentResourceService(provider, region)
    resources._cp = cp
    resources._cr = cr
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider=provider,
            region=region,
            bucket="studio",
            cp_workspace="customer-workspace" if provided_cp else "",
            cr_repository="customer/team/runtime" if provided_cr else "",
        ),
        resource_service=resources,
    )

    resolved, run_id, image = gateway.start_build(
        context_key="environments/id/versions/v/context.tar.gz",
        image_tag="v1",
    )

    assert run_id == "run-1"
    assert resolved.code_pipeline.source == ("provided" if provided_cp else "managed")
    assert resolved.container_registry.source == (
        "provided" if provided_cr else "managed"
    )
    assert (
        image.endswith("/runtime:v1")
        if provided_cr
        else image.endswith("/base-images:v1")
    )
    parameter_keys = {item["Key"] for item in cp.run_parameters}
    assert {"TOS_PROJECT_FILE_PATH", "DOCKERFILE_PATH", "CR_TAG"} <= parameter_keys
    created_pipeline = next(iter(cp.pipelines[resolved.code_pipeline.workspace_id]))
    assert created_pipeline["Name"] == "veadk-studio-environment-build-v8"
    assert (
        'buildParams: "--build-arg APT_MIRROR_URL=$APT_MIRROR_URL --build-arg PIP_INDEX_URL=$PIP_INDEX_URL --build-arg PYTHON_SOURCE_BASE_URL=$PYTHON_SOURCE_BASE_URL --build-arg PLAYWRIGHT_DOWNLOAD_HOST=$PLAYWRIGHT_DOWNLOAD_HOST"'
        in created_pipeline["Spec"]
    )
    assert "compression: gzip" in created_pipeline["Spec"]
    assert "disableSSLVerify: false" in created_pipeline["Spec"]
    assert "loginCredential: []" in created_pipeline["Spec"]
    assert "useCache: true" in created_pipeline["Spec"]
    assert "cacheType: default" in created_pipeline["Spec"]
    assert 'cacheUrl: ""' in created_pipeline["Spec"]
    run_parameters = {item["Key"]: item["Value"] for item in cp.run_parameters}
    assert run_parameters["APT_MIRROR_URL"] == (
        "http://mirrors.volces.com/ubuntu"
        if provider == "volcengine"
        else "http://mirror.sg.gs/ubuntu"
    )
    assert run_parameters["PIP_INDEX_URL"] == (
        "https://mirrors.aliyun.com/pypi/simple/"
        if provider == "volcengine"
        else "https://pypi.org/simple"
    )
    assert run_parameters["PYTHON_SOURCE_BASE_URL"] == (
        "https://mirrors.huaweicloud.com/python"
        if provider == "volcengine"
        else "https://www.python.org/ftp/python"
    )
    assert run_parameters["PLAYWRIGHT_DOWNLOAD_HOST"] == (
        "https://npmmirror.com/mirrors/playwright"
        if provider == "volcengine"
        else "https://cdn.playwright.dev"
    )
    assert bool(cp.created_workspaces) is (not provided_cp)
    assert bool(cr.created) is (not provided_cr)
    expected_host = (
        "console.byteplus.com" if provider == "byteplus" else "console.volcengine.com"
    )
    assert expected_host in resolved.code_pipeline.console_url
    assert expected_host in resolved.container_registry.console_url


@pytest.mark.parametrize(
    "provider,region,expected_registry",
    [
        ("volcengine", "cn-beijing", "agentkit-cli-2100123456"),
        ("byteplus", "ap-southeast-1", "agentkit-platform-2100123456"),
    ],
)
def test_managed_cr_reuses_the_account_stable_agentkit_registry(
    provider, region, expected_registry
):
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider=provider,
            region=region,
            bucket="veadk-studio-2100123456",
        ),
        resource_service=DeploymentResourceService(provider, region, ("ak", "sk", "")),
    )

    assert gateway.describe().container_registry.registry == expected_registry


def test_managed_cr_creation_is_idempotent():
    cp = FakeCP()
    cr = FakeCR()
    resources = DeploymentResourceService("volcengine", "cn-beijing")
    resources._cp = cp
    resources._cr = cr
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine",
            region="cn-beijing",
            bucket="studio",
        ),
        resource_service=resources,
    )

    gateway.start_build(context_key="one/context.tar.gz", image_tag="v1")
    gateway.start_build(context_key="two/context.tar.gz", image_tag="v2")

    assert cr.created == [
        ("registry", "veadk-studio-environments"),
        ("namespace", "veadk-studio-environments", "runtime-environments"),
        (
            "repository",
            "veadk-studio-environments",
            "runtime-environments",
            "base-images",
        ),
    ]


def test_environment_resources_are_resolved_once_and_reused(monkeypatch):
    cp = FakeCP()
    cr = FakeCR()
    resources = DeploymentResourceService("byteplus", "ap-southeast-1")
    resources._cp = cp
    resources._cr = cr
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="byteplus",
            region="ap-southeast-1",
            bucket="studio",
        ),
        resource_service=resources,
    )
    resolve_counts = {"cp": 0, "cr": 0}
    resolve_cp = gateway._resolve_code_pipeline
    resolve_cr = gateway._resolve_container_registry

    def counted_cp():
        resolve_counts["cp"] += 1
        return resolve_cp()

    def counted_cr():
        resolve_counts["cr"] += 1
        return resolve_cr()

    monkeypatch.setattr(gateway, "_resolve_code_pipeline", counted_cp)
    monkeypatch.setattr(gateway, "_resolve_container_registry", counted_cr)

    gateway.start_build(context_key="one/context.tar.gz", image_tag="v1")
    gateway.start_build(context_key="two/context.tar.gz", image_tag="v2")

    assert resolve_counts == {"cp": 1, "cr": 1}


def test_concurrent_builds_do_not_duplicate_resource_resolution(monkeypatch):
    cp = FakeCP()
    cr = FakeCR()
    resources = DeploymentResourceService("volcengine", "cn-beijing")
    resources._cp = cp
    resources._cr = cr
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine",
            region="cn-beijing",
            bucket="studio",
        ),
        resource_service=resources,
    )
    resolve_counts = {"cp": 0, "cr": 0}
    count_lock = threading.Lock()
    resolve_cp = gateway._resolve_code_pipeline
    resolve_cr = gateway._resolve_container_registry

    def counted_cp():
        with count_lock:
            resolve_counts["cp"] += 1
        time.sleep(0.02)
        return resolve_cp()

    def counted_cr():
        with count_lock:
            resolve_counts["cr"] += 1
        time.sleep(0.02)
        return resolve_cr()

    monkeypatch.setattr(gateway, "_resolve_code_pipeline", counted_cp)
    monkeypatch.setattr(gateway, "_resolve_container_registry", counted_cr)

    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [
            executor.submit(
                gateway.start_build,
                context_key=f"{index}/context.tar.gz",
                image_tag=f"v{index}",
            )
            for index in range(4)
        ]
        for future in futures:
            future.result()

    assert resolve_counts == {"cp": 1, "cr": 1}
    assert cr.created == [
        ("registry", "veadk-studio-environments"),
        ("namespace", "veadk-studio-environments", "runtime-environments"),
        (
            "repository",
            "veadk-studio-environments",
            "runtime-environments",
            "base-images",
        ),
    ]


def test_transient_cr_timeout_is_retried_without_resolving_cp_again(monkeypatch):
    class ReadTimeout(Exception):
        pass

    cp = FakeCP()
    cr = FakeCR()
    resources = DeploymentResourceService("byteplus", "ap-southeast-1")
    resources._cp = cp
    resources._cr = cr
    list_resources = resources.list_resources
    repository_calls = 0

    def flaky_list_resources(kind, **kwargs):
        nonlocal repository_calls
        if kind == "cr-repository":
            repository_calls += 1
            if repository_calls == 1:
                raise ReadTimeout("CR API read timed out")
        return list_resources(kind, **kwargs)

    monkeypatch.setattr(resources, "list_resources", flaky_list_resources)
    monkeypatch.setattr(
        "frontend.server.environments.resources.time.sleep", lambda _delay: None
    )
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="byteplus",
            region="ap-southeast-1",
            bucket="studio",
        ),
        resource_service=resources,
    )
    resolve_cp = gateway._resolve_code_pipeline
    cp_calls = 0

    def counted_cp():
        nonlocal cp_calls
        cp_calls += 1
        return resolve_cp()

    monkeypatch.setattr(gateway, "_resolve_code_pipeline", counted_cp)

    gateway.start_build(context_key="context.tar.gz", image_tag="v1")

    assert repository_calls == 2
    assert cp_calls == 1


def test_non_network_resource_error_is_not_retried(monkeypatch):
    cp = FakeCP()
    cr = FakeCR()
    resources = DeploymentResourceService("byteplus", "ap-southeast-1")
    resources._cp = cp
    resources._cr = cr
    repository_calls = 0

    def denied_list_resources(kind, **_kwargs):
        nonlocal repository_calls
        if kind == "cr-repository":
            repository_calls += 1
            raise PermissionError("ListRepositories denied")
        return {"items": []}

    monkeypatch.setattr(resources, "list_resources", denied_list_resources)
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="byteplus",
            region="ap-southeast-1",
            bucket="studio",
        ),
        resource_service=resources,
    )

    with pytest.raises(EnvironmentResourceError, match="ListRepositories denied"):
        gateway.start_build(context_key="context.tar.gz", image_tag="v1")

    assert repository_calls == 1


def test_resource_settings_use_deploy_flags_only():
    settings = EnvironmentResourceSettings.from_env(
        provider="volcengine",
        region="cn-beijing",
        bucket="studio",
        source={
            "VEADK_STUDIO_ENVIRONMENT_CP_WORKSPACE": "workspace-from-flag",
            "VEADK_STUDIO_ENVIRONMENT_CR_REPOSITORY": "registry/team/repo",
            "CP_WORKSPACE": "ignored",
            "CR_REPOSITORY": "ignored/ignored/ignored",
        },
    )
    assert settings.cp_workspace == "workspace-from-flag"
    assert settings.cr_repository == "registry/team/repo"


@pytest.mark.parametrize(
    "cp_workspace,cr_repository,error",
    [
        ("missing", "", "Workspace 不存在"),
        ("", "registry/namespace", "registry/namespace/repository"),
    ],
)
def test_resource_configuration_failures_are_actionable(
    cp_workspace, cr_repository, error
):
    resources = DeploymentResourceService("volcengine", "cn-beijing")
    resources._cp = FakeCP()
    resources._cr = FakeCR()
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine",
            region="cn-beijing",
            bucket="studio",
            cp_workspace=cp_workspace,
            cr_repository=cr_repository,
        ),
        resource_service=resources,
    )
    with pytest.raises(EnvironmentResourceError, match=error):
        gateway.start_build(context_key="context.tar.gz", image_tag="v1")


def test_build_start_error_is_redacted_and_persisted():
    cp = FakeCP(run_error=True)
    cr = FakeCR()
    resources = DeploymentResourceService(
        "volcengine", "cn-beijing", ("ak", "secret-value", None)
    )
    resources._cp = cp
    resources._cr = cr
    gateway = StudioEnvironmentCloudGateway(
        EnvironmentResourceSettings(
            provider="volcengine", region="cn-beijing", bucket="studio"
        ),
        ("ak", "secret-value", None),
        resource_service=resources,
    )
    service, _ = _service(cloud=gateway)
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")
    client = TestClient(app)
    environment_id = client.post("/web/environments", json=_payload()).json()["id"]

    response = client.post(f"/web/environments/{environment_id}/build")

    assert response.status_code == 202
    assert response.json()["status"] == "failed"
    assert "secret-value" not in response.json()["error"]
    assert "***" in response.json()["error"]

    detail = client.get(
        "/web/environments/"
        f"{environment_id}/builds/{response.json()['versionId']}?includeLogs=true"
    )

    assert detail.status_code == 200
    assert detail.json()["error"] == response.json()["error"]
    assert "缺少 CodePipeline 运行信息" not in detail.json()["error"]


def test_build_log_redaction_removes_pipeline_temporary_credentials():
    log = (
        'Resp {"sessionToken":"session-value","accessKeyId":"temp-ak",'
        '"secretAccessKey":"temp-sk","registryToken":"cr-token",'
        '"dockerPassword":"cr-password"}\nAuthorization: Bearer signed-token\n'
        "Authorization: Basic registry-login"
    )

    redacted = _redact(log, ("configured-ak", "configured-sk", None))

    assert "session-value" not in redacted
    assert "temp-ak" not in redacted
    assert "temp-sk" not in redacted
    assert "signed-token" not in redacted
    assert "cr-token" not in redacted
    assert "cr-password" not in redacted
    assert "registry-login" not in redacted
    assert redacted.count("***") == 7


def test_environment_resources_route_returns_names_and_console_links():
    service, _ = _service()
    app = FastAPI()
    mount_environment_routes(app, service, lambda _request: "owner")

    response = TestClient(app).get("/web/environment-resources")

    assert response.status_code == 200
    body = response.json()
    assert body["codePipeline"]["workspaceName"]
    assert body["codePipeline"]["consoleUrl"].startswith("https://")
    assert body["containerRegistry"]["repository"]
    assert body["containerRegistry"]["consoleUrl"].startswith("https://")
