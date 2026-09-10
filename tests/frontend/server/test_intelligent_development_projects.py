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

import asyncio
from datetime import datetime, timezone
import hashlib
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
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
from frontend.server.intelligent_development_projects import routes as routes_module
from frontend.server.intelligent_development_projects import (
    repository as repository_module,
)
from frontend.server.intelligent_development_projects.routes import (
    mount_intelligent_development_project_routes,
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


@pytest.fixture
def name_store():
    tos = FakeTos()
    repository = _repository(tos)
    service = IntelligentDevelopmentProjectService(repository)
    artifact = b"source archive"
    report = b'{"status":"passed"}'
    version = _version(
        version_id="b" * 32,
        artifact=artifact,
        report=report,
        created_at=datetime(2026, 9, 10, 8, tzinfo=timezone.utc),
    )
    project = asyncio.run(
        repository.commit_version(
            "owner",
            "Original project",
            version,
            artifact,
            report,
            project_origin="migration",
        )
    )
    app = FastAPI()
    mount_intelligent_development_project_routes(
        app,
        prefix="/projects-api",
        owner_resolver=lambda request: request.headers.get("x-test-owner", "owner"),
        project_service=service,
    )
    with TestClient(app) as client:
        yield SimpleNamespace(
            tos=tos,
            repository=repository,
            service=service,
            client=client,
            project=project,
            version=version,
            artifact=artifact,
            report=report,
            url=f"/projects-api/projects/{project.project_id}",
        )


def test_names_are_durable_display_metadata_without_changing_source(name_store):
    store = name_store
    original = dict(store.tos.objects)
    response = store.client.patch(store.url, json={"name": "  新项目 Cafe\u0301  "})
    assert response.status_code == 200
    assert response.json()["project"]["name"] == "新项目 Café"
    assert "ownerId" not in response.json()["project"]
    version_url = f"{store.url}/versions/{store.version.version_id}"
    response = store.client.patch(version_url, json={"name": "生产版 & '稳定'"})
    assert response.status_code == 200
    assert response.json()["version"]["name"] == "生产版 & '稳定'"
    projects = store.client.get("/projects-api/projects?origin=migration").json()
    assert projects["projects"][0]["name"] == "新项目 Café"
    versions = store.client.get(f"{store.url}/versions").json()["versions"]
    assert versions[0]["name"] == "生产版 & '稳定'"
    assert versions[0]["agentName"] == store.version.agent_name
    assert all(store.tos.objects[key] == value for key, value in original.items())
    assert len(store.tos.objects) == len(original) + 2
    assert (
        "name"
        not in asyncio.run(
            store.service.get_version(
                "owner",
                store.project.project_id,
                store.version.version_id,
            )
        ).model_dump()
    )
    binding = asyncio.run(
        store.service.create_binding(
            owner_id="owner",
            session_id="new-optimization",
            display_name="ignored",
            project_id=store.project.project_id,
        )
    )
    assert binding.project_name == "新项目 Café"


@pytest.mark.parametrize(
    "name",
    [
        "",
        "   ",
        "名" * 129,
        "😀" * 129,
        "line\n",
        "\tname",
        "name\x00",
        "name\x7f",
        "name\u0085",
        "name\u202e",
        "name\u2066",
        "name\u200b",
        "name\u2028",
        "name\u2029",
        "<script>alert(1)</script>",
        "name>",
        "\ud800",
        None,
        42,
        ["name"],
    ],
)
@pytest.mark.parametrize("version", [False, True])
def test_name_api_rejects_unsafe_or_invalid_text_without_writing(
    name_store, name, version
):
    store = name_store
    original = dict(store.tos.objects)
    url = f"{store.url}/versions/{store.version.version_id}" if version else store.url
    response = store.client.patch(
        url,
        content=json.dumps({"name": name}),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert store.tos.objects == original


@pytest.mark.parametrize(
    "name", ["名" * 128, "😀" * 128, "e\u0301" * 128, "../a; $value & 'b'"]
)
def test_name_limits_count_normalized_unicode_characters(name_store, name):
    response = name_store.client.patch(name_store.url, json={"name": name})
    assert response.status_code == 200
    assert len(response.json()["project"]["name"]) <= 128


@pytest.mark.parametrize(
    "body,status", [("{", 422), ("[]", 422), ("null", 422), ("x" * 4097, 413)]
)
@pytest.mark.parametrize("version", [False, True])
def test_name_request_parsing_is_bounded_and_does_not_reflect_input(
    name_store, body, status, version
):
    store = name_store
    original = dict(store.tos.objects)
    url = f"{store.url}/versions/{store.version.version_id}" if version else store.url
    response = store.client.patch(
        url, content=body, headers={"Content-Type": "application/json"}
    )
    assert response.status_code == status
    assert "x" * 256 not in response.text
    assert store.tos.objects == original


@pytest.mark.parametrize("version", [False, True])
def test_name_api_rejects_deeply_nested_json(name_store, version):
    original = dict(name_store.tos.objects)
    url = (
        f"{name_store.url}/versions/{name_store.version.version_id}"
        if version
        else name_store.url
    )
    response = name_store.client.patch(
        url,
        content="[" * 1500 + "]" * 1500,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SOURCE_PROJECT_NAME_INVALID"
    assert name_store.tos.objects == original


@pytest.mark.parametrize("version", [False, True])
def test_name_api_handles_parser_recursion_errors_without_reflecting_input(
    name_store, monkeypatch: pytest.MonkeyPatch, version
):
    original = dict(name_store.tos.objects)
    # CPython versions have different JSON recursion limits. Exercise the
    # parser failure contract even when this interpreter accepts the nesting.
    parser = Mock(side_effect=RecursionError("untrusted input must not be echoed"))
    monkeypatch.setattr(routes_module, "json", SimpleNamespace(loads=parser))
    url = (
        f"{name_store.url}/versions/{name_store.version.version_id}"
        if version
        else name_store.url
    )
    response = name_store.client.patch(url, json={"name": "New name"})
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "SOURCE_PROJECT_NAME_INVALID"
    assert "untrusted input" not in response.text
    parser.assert_called_once()
    assert name_store.tos.objects == original


def test_name_api_enforces_owner_resource_and_field_boundaries(name_store):
    store = name_store
    original = dict(store.tos.objects)
    for suffix in ("", f"/versions/{store.version.version_id}"):
        response = store.client.patch(
            store.url + suffix,
            json={"name": "Other"},
            headers={"x-test-owner": "someone-else"},
        )
        assert response.status_code == 404
        response = store.client.patch(
            store.url + suffix, json={"name": "Other", "agentName": "changed"}
        )
        assert response.status_code == 422
    response = store.client.patch(
        f"{store.url}/versions/{'c' * 32}", json={"name": "Other"}
    )
    assert response.status_code == 404
    assert store.tos.objects == original
    summary_key = next(
        key for key in store.tos.objects if key.endswith("/summary.json")
    )
    store.tos.objects[summary_key] = (
        store.project.model_copy(
            update={"origin": "intelligent-development"},
        )
        .model_dump_json(by_alias=True)
        .encode()
    )
    assert store.client.patch(store.url, json={"name": "Other"}).status_code == 409
    assert (
        store.client.patch(
            f"{store.url}/versions/{store.version.version_id}", json={"name": "Other"}
        ).status_code
        == 409
    )


@pytest.mark.parametrize("version", [False, True])
def test_name_errors_preserve_existing_data_and_do_not_hide_corruption(
    name_store, version
):
    store = name_store
    url = f"{store.url}/versions/{store.version.version_id}" if version else store.url
    assert store.client.patch(url, json={"name": "Saved"}).status_code == 200
    store.tos.fail_put_suffix = "/display.json"
    response = store.client.patch(url, json={"name": "Failed"})
    assert response.status_code == 503
    assert response.json()["detail"]["retryable"] is True
    store.tos.fail_put_suffix = ""
    list_url = (
        f"{store.url}/versions"
        if version
        else "/projects-api/projects?origin=migration"
    )
    listing = store.client.get(list_url).json()
    assert listing["versions" if version else "projects"][0]["name"] == "Saved"
    display_key = next(
        key for key in store.tos.objects if key.endswith("/display.json")
    )
    store.tos.objects[display_key] = b'{"name":"<script>"}'
    assert store.client.get(list_url).status_code == 502


def test_names_survive_commit_retries_and_new_versions_then_are_cleaned_on_delete(
    name_store,
):
    store = name_store
    version_url = f"{store.url}/versions/{store.version.version_id}"
    assert (
        store.client.patch(store.url, json={"name": "Renamed project"}).status_code
        == 200
    )
    assert store.client.patch(version_url, json={"name": "Baseline"}).status_code == 200
    repeated = asyncio.run(
        store.repository.commit_version(
            "owner",
            "Original project",
            store.version,
            store.artifact,
            store.report,
            project_origin="migration",
        )
    )
    assert repeated.name == "Renamed project"
    second = store.version.model_copy(
        update={
            "version_id": "c" * 32,
            "parent_version_id": store.version.version_id,
            "created_at": datetime(2026, 9, 10, 9, tzinfo=timezone.utc),
        }
    )
    asyncio.run(
        store.repository.commit_version(
            "owner",
            "Old binding name",
            second,
            store.artifact,
            store.report,
        )
    )
    versions = store.client.get(f"{store.url}/versions").json()["versions"]
    assert [item["versionId"] for item in versions] == [
        second.version_id,
        store.version.version_id,
    ]
    assert versions[0]["name"] is None
    assert versions[1]["name"] == "Baseline"
    assert store.client.delete(version_url).status_code == 200
    assert not any(
        f"/versions/{store.version.version_id}/" in key for key in store.tos.objects
    )
    assert (
        store.client.delete(f"{store.url}/versions/{second.version_id}").status_code
        == 200
    )
    assert not store.tos.objects
    assert store.client.patch(store.url, json={"name": "Resurrect"}).status_code == 404


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
