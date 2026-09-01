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
import base64
import io
import json
import zlib
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Literal

from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.environments.models import (
    CodePipelineResource,
    ContainerRegistryResource,
    EnvironmentBuild,
    EnvironmentResourceInfo,
    EnvironmentSkillManifest,
    EnvironmentSkillManifestEntry,
)
from frontend.server.environments.repository import TosEnvironmentRepository
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


def _resources(
    region: str = "cn-beijing",
    provider: Literal["volcengine", "byteplus"] = "volcengine",
) -> EnvironmentResourceInfo:
    return EnvironmentResourceInfo(
        provider=provider,
        region=region,
        codePipeline=CodePipelineResource(source="managed"),
        containerRegistry=ContainerRegistryResource(
            source="provided",
            region=region,
            registry="registry",
            namespace="agents",
            repository="runtime",
            domain="registry.example.com",
            imageRepository="registry.example.com/agents/runtime",
        ),
    )


class _Cloud:
    def __init__(
        self,
        provider: Literal["volcengine", "byteplus"] = "volcengine",
    ) -> None:
        self.provider = provider
        self.image_resolutions = 0
        self.build_starts = 0

    def describe(self):
        return _resources(provider=self.provider)

    def resolve_image_source(self, source):
        self.image_resolutions += 1
        separator = "@" if source.reference.startswith("sha256:") else ":"
        return _resources(source.region, self.provider), (
            f"registry.example.com/{source.namespace}/{source.repository}"
            f"{separator}{source.reference}"
        )

    def start_build(self, **_kwargs):
        self.build_starts += 1
        raise AssertionError("share-code import must not start CodePipeline")


def _payload(**updates):
    value = {
        "name": "Shared environment",
        "description": "portable config",
        "operatingSystem": "ubuntu-24.04",
        "language": "python-3.12",
        "executionRuntime": "veadk",
        "optionIds": ["git", "jq"],
        "selectedSkills": [],
        "dockerfile": "FROM ubuntu:24.04\nRUN echo shared",
    }
    value.update(updates)
    return value


def _harness(provider: Literal["volcengine", "byteplus"] = "volcengine"):
    tos = _Tos()
    repository = TosEnvironmentRepository(bucket="studio", client_factory=lambda: tos)
    cloud = _Cloud(provider)
    service = EnvironmentService(repository, cloud)
    app = FastAPI()
    mount_environment_routes(
        app,
        service,
        lambda request: request.headers.get("X-Owner", "owner-a"),
    )
    return TestClient(app), tos, cloud, repository, service


def _client():
    client, tos, cloud, _repository, _service = _harness()
    return client, tos, cloud


def _decode_payload(share_code: str):
    encoded = share_code.removeprefix("akenv://v1/")
    return json.loads(
        zlib.decompress(
            base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
        ).decode()
    )


def _share_code_from_bytes(value: bytes) -> str:
    encoded = base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")
    return f"akenv://v1/{encoded}"


def test_share_code_uses_compact_explicit_fields_and_round_trips_environment_input():
    client, tos, cloud = _client()
    created = client.post(
        "/web/environments",
        json=_payload(
            selectedSkills=[
                {
                    "source": "skillhub",
                    "folder": "release-notes",
                    "name": "release-notes",
                    "description": "Draft release notes",
                    "slug": "public/release-notes",
                    "namespace": "public",
                    "version": "1.2.3",
                }
            ]
        ),
    ).json()
    stored_keys = set(tos.objects)

    exported = client.post(f"/web/environments/{created['id']}/share-code")

    assert exported.status_code == 200
    assert set(tos.objects) == stored_keys
    share_code = exported.json()["shareCode"]
    assert share_code.startswith("akenv://v1/")
    assert exported.json()["name"] == "Shared environment"
    payload = _decode_payload(share_code)
    compact = json.dumps(
        payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    uncompressed_code = _share_code_from_bytes(compact)
    assert len(share_code) < len(uncompressed_code) * 0.8
    assert set(payload) == {"n", "d", "o", "l", "r", "p", "s", "f", "g", "i", "c"}
    assert payload["f"] == "FROM ubuntu:24.04\nRUN echo shared"
    assert set(payload["s"][0]) == {
        "x",
        "f",
        "n",
        "d",
        "u",
        "ns",
        "lf",
        "si",
        "sn",
        "sr",
        "id",
        "v",
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    for excluded in ("ownerId", "latestVersion", "runId", "logTail"):
        assert excluded not in serialized

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    )

    assert imported.status_code == 200
    item = imported.json()["items"][0]
    assert item["status"] == "created"
    assert item["environment"]["name"] == created["name"]
    assert item["environment"]["description"] == created["description"]
    assert item["environment"]["operatingSystem"] == created["operatingSystem"]
    assert item["environment"]["language"] == created["language"]
    assert item["environment"]["executionRuntime"] == created["executionRuntime"]
    assert item["environment"]["optionIds"] == created["optionIds"]
    assert item["environment"]["selectedSkills"] == created["selectedSkills"]
    assert item["environment"]["dockerfile"] == created["dockerfile"]
    assert item["environment"]["gitSource"] is None
    assert item["environment"]["containerRepository"] is None
    assert item["environment"]["imageSource"] is None
    assert item["environment"]["latestVersion"] is None
    assert cloud.build_starts == 0


def test_git_and_target_repository_fields_round_trip_without_a_build_record():
    client, _tos, cloud = _client()
    source = {
        "repositoryUrl": "https://github.com/example/public-agent.git",
        "ref": "release/v1",
        "dockerfilePath": "deploy/Agent.Dockerfile",
    }
    target = {
        "region": "cn-shanghai",
        "registry": "production",
        "namespace": "agents",
        "repository": "runtime-environments",
    }
    created = client.post(
        "/web/environments",
        json=_payload(dockerfile="", gitSource=source, containerRepository=target),
    ).json()
    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    ).json()["items"][0]["environment"]

    assert imported["gitSource"] == source
    assert imported["containerRepository"] == target
    assert imported["imageSource"] is None
    assert imported["latestVersion"] is None
    assert cloud.build_starts == 0


def test_latest_available_build_round_trips_as_an_external_version(tmp_path):
    client, tos, cloud, repository, service = _harness()
    created = client.post(
        "/web/environments",
        json=_payload(
            baseEnvironment="aio-sandbox",
            operatingSystem="ubuntu-22.04",
            selectedSkills=[
                {
                    "source": "local",
                    "folder": "release-notes",
                    "name": "release-notes",
                    "version": "1.2.3",
                    "localFiles": [
                        {
                            "path": "skills/release-notes/SKILL.md",
                            "content": (
                                "---\nname: release-notes\n---\n\n"
                                "Draft a release note.\n"
                            ),
                        }
                    ],
                }
            ],
        ),
    ).json()
    record = asyncio.run(repository.get("owner-a", created["id"]))
    now = datetime.now(timezone.utc)
    source_build = EnvironmentBuild(
        environmentId=created["id"],
        versionId="20260831T000000Z-deadbeef",
        status="available",
        image="registry.example.com/agents/runtime@sha256:" + "a" * 64,
        toolId="tool-shared-runtime",
        toolStatus="ready",
        resources=_resources("cn-shanghai"),
        currentStep="环境镜像已就绪",
        sourceCommitSha="b" * 40,
        createdAt=now,
        updatedAt=now,
    )
    skill_manifest = EnvironmentSkillManifest(
        skills=[
            EnvironmentSkillManifestEntry(
                name="release-notes",
                folder="release-notes",
                source="local",
                version="1.2.3",
                digest="c" * 64,
            )
        ]
    )
    skill_files = [
        (
            "release-notes/SKILL.md",
            b"---\nname: release-notes\n---\n\nDraft a release note.\n",
        )
    ]
    asyncio.run(
        repository.create_external_version(
            record,
            source_build,
            skill_manifest,
            skill_files,
        )
    )
    stored_keys = set(tos.objects)

    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]

    assert set(tos.objects) == stored_keys
    payload = _decode_payload(share_code)
    assert payload["a"]["i"] == source_build.image
    assert payload["a"]["t"] == "tool-shared-runtime"
    assert payload["a"]["u"] == "ready"
    assert payload["a"]["e"] == _resources("cn-shanghai").model_dump(
        mode="json", by_alias=True
    )
    assert payload["a"]["s"] == "b" * 40
    assert payload["a"]["m"][0]["n"] == "release-notes"
    assert payload["a"]["f"][0] == {
        "p": "release-notes/SKILL.md",
        "c": skill_files[0][1].decode(),
    }
    serialized = json.dumps(payload, ensure_ascii=False)
    for excluded in ("runId", "logTail", "createdAt", "updatedAt", "ownerId"):
        assert excluded not in serialized

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    ).json()["items"][0]["environment"]

    latest = imported["latestVersion"]
    assert latest["status"] == "available"
    assert latest["image"] == source_build.image
    assert latest["toolId"] == "tool-shared-runtime"
    assert latest["toolStatus"] == "ready"
    assert latest["sourceCommitSha"] == "b" * 40
    assert latest["versionId"] != source_build.version_id
    assert latest["resources"]["provider"] == "volcengine"
    assert latest["resources"]["region"] == "cn-shanghai"
    assert latest["resources"]["containerRegistry"]["repository"] == "runtime"
    assert cloud.build_starts == 0
    assert cloud.image_resolutions == 0
    imported_manifest = asyncio.run(
        repository.get_skill_manifest(
            "owner-b",
            imported["id"],
            latest["versionId"],
        )
    )
    assert imported_manifest == skill_manifest
    imported_files = asyncio.run(
        repository.get_version_skill_files(
            "owner-b",
            imported["id"],
            latest["versionId"],
        )
    )
    assert imported_files == skill_files
    staged = asyncio.run(
        service.stage_skill_files_for_agent(
            "owner-b",
            imported["id"],
            latest["versionId"],
            tmp_path / "staged",
        )
    )
    assert (staged / "release-notes" / "SKILL.md").read_bytes() == skill_files[0][1]
    assert any(
        "/environments/owner-b/" in key and key.endswith("/image.json")
        for key in tos.objects
    )


def test_old_code_and_environment_without_available_build_import_unbuilt():
    client, _tos, cloud, repository, _service = _harness()
    created = client.post("/web/environments", json=_payload()).json()
    record = asyncio.run(repository.get("owner-a", created["id"]))
    now = datetime.now(timezone.utc)
    failed = EnvironmentBuild(
        environmentId=created["id"],
        versionId="20260831T000001Z-deadbeef",
        status="failed",
        image="registry.example.com/agents/runtime:failed",
        resources=_resources(),
        error="build failed",
        createdAt=now,
        updatedAt=now,
    )
    asyncio.run(repository.create_external_version(record, failed))

    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]
    payload = _decode_payload(share_code)
    assert "a" not in payload
    old_v1_code = _share_code_from_bytes(
        zlib.compress(
            json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8"),
            level=9,
        )
    )

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [old_v1_code]},
    ).json()["items"][0]["environment"]

    assert imported["latestVersion"] is None
    assert cloud.build_starts == 0


def test_available_build_from_another_provider_is_not_imported_as_usable():
    source_client, _tos, _cloud, repository, _service = _harness("volcengine")
    created = source_client.post("/web/environments", json=_payload()).json()
    record = asyncio.run(repository.get("owner-a", created["id"]))
    now = datetime.now(timezone.utc)
    source_build = EnvironmentBuild(
        environmentId=created["id"],
        versionId="20260831T000002Z-deadbeef",
        status="available",
        image="registry.example.com/agents/runtime@sha256:" + "a" * 64,
        toolId="tool-volcengine-only",
        toolStatus="ready",
        resources=_resources(provider="volcengine"),
        createdAt=now,
        updatedAt=now,
    )
    asyncio.run(repository.create_external_version(record, source_build))
    share_code = source_client.post(
        f"/web/environments/{created['id']}/share-code"
    ).json()["shareCode"]

    target_client, _tos, target_cloud, _repository, _service = _harness("byteplus")
    response = target_client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    )

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["status"] == "failed"
    assert "云厂商与当前 Studio 不一致" in item["error"]
    assert (
        target_client.get(
            "/web/environments",
            headers={"X-Owner": "owner-b"},
        ).json()["items"]
        == []
    )
    assert target_cloud.build_starts == 0


def test_local_skill_files_are_embedded_without_owner_scoped_artifact_id():
    client, tos, _cloud = _client()
    created = client.post(
        "/web/environments",
        json=_payload(
            selectedSkills=[
                {
                    "source": "local",
                    "folder": "private-helper",
                    "name": "private-helper",
                    "localFiles": [
                        {
                            "path": "skills/private-helper/SKILL.md",
                            "content": "---\nname: private-helper\n---\n",
                        }
                    ],
                }
            ]
        ),
    ).json()
    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]
    payload = _decode_payload(share_code)

    assert payload["s"][0]["lf"] == [
        {
            "p": "skills/private-helper/SKILL.md",
            "c": "---\nname: private-helper\n---\n",
        }
    ]
    assert "artifactId" not in json.dumps(payload)

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    ).json()["items"][0]["environment"]

    assert imported["selectedSkills"][0]["localFiles"] == []
    assert imported["selectedSkills"][0]["artifactId"]
    owner_b_skill_keys = [
        key
        for key in tos.objects
        if "/environments/owner-b/" in key and "/skills/" in key
    ]
    assert len(owner_b_skill_keys) == 1


def test_inspect_and_import_keep_order_and_report_in_batch_duplicates():
    client, _tos, cloud = _client()
    created = client.post("/web/environments", json=_payload()).json()
    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]
    invalid = "akenv://v1/not-valid-json"

    inspected = client.post(
        "/web/environment-share-codes/inspect",
        json={"shareCodes": [share_code, invalid, share_code]},
    )

    assert inspected.status_code == 200
    assert [(item["index"], item["valid"]) for item in inspected.json()["items"]] == [
        (0, True),
        (1, False),
        (2, True),
    ]

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code, share_code, invalid]},
    )

    assert imported.status_code == 200
    body = imported.json()
    assert [item["status"] for item in body["items"]] == [
        "created",
        "duplicate",
        "failed",
    ]
    assert (
        body["items"][0]["environment"]["id"] == body["items"][1]["environment"]["id"]
    )
    assert (body["createdCount"], body["duplicateCount"], body["failedCount"]) == (
        1,
        1,
        1,
    )
    assert cloud.build_starts == 0


def test_image_source_is_revalidated_on_import_without_starting_cp():
    client, _tos, cloud, repository, _service = _harness()
    created = client.post(
        "/web/environments",
        json=_payload(
            dockerfile="",
            imageSource={
                "region": "cn-shanghai",
                "registry": "production",
                "namespace": "agents",
                "repository": "runtime",
                "reference": "stable",
            },
        ),
    ).json()
    source_build = asyncio.run(
        repository.get_build(
            "owner-a",
            created["id"],
            created["latestVersion"]["versionId"],
        )
    )
    asyncio.run(
        repository.update_build(
            "owner-a",
            source_build.model_copy(
                update={"tool_id": "tool-existing-image", "tool_status": "ready"}
            ),
        )
    )
    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]
    cloud.image_resolutions = 0

    imported = client.post(
        "/web/environment-share-codes/import",
        headers={"X-Owner": "owner-b"},
        json={"shareCodes": [share_code]},
    ).json()["items"][0]

    assert imported["status"] == "created"
    assert imported["environment"]["imageSource"] == created["imageSource"]
    assert imported["environment"]["latestVersion"]["status"] == "available"
    assert imported["environment"]["latestVersion"]["toolId"] == "tool-existing-image"
    assert imported["environment"]["latestVersion"]["toolStatus"] == "ready"
    assert cloud.image_resolutions == 1
    assert cloud.build_starts == 0


def test_export_is_owner_scoped_and_batch_size_is_limited():
    client, _tos, _cloud = _client()
    created = client.post("/web/environments", json=_payload()).json()

    denied = client.post(
        f"/web/environments/{created['id']}/share-code",
        headers={"X-Owner": "owner-b"},
    )
    too_many = client.post(
        "/web/environment-share-codes/inspect",
        json={"shareCodes": ["akenv://v1/e30"] * 21},
    )

    assert denied.status_code == 404
    assert too_many.status_code == 422


def test_export_rejects_git_urls_that_could_embed_credentials():
    client, _tos, _cloud = _client()
    created = client.post(
        "/web/environments",
        json=_payload(
            dockerfile="",
            gitSource={
                "repositoryUrl": "https://token@example.com/team/repo.git",
                "ref": "main",
                "dockerfilePath": "Dockerfile",
            },
        ),
    ).json()

    response = client.post(f"/web/environments/{created['id']}/share-code")

    assert response.status_code == 400
    assert "不含用户名、密码、Token" in response.json()["detail"]


def test_oversized_and_unknown_version_codes_fail_clearly():
    client, _tos, _cloud = _client()
    oversized = "akenv://v1/" + "a" * (4 * 1024 * 1024)

    response = client.post(
        "/web/environment-share-codes/inspect",
        json={"shareCodes": [oversized, "akenv://v2/e30"]},
    )

    assert response.status_code == 200
    assert [item["valid"] for item in response.json()["items"]] == [False, False]
    assert "大小限制" in response.json()["items"][0]["error"]
    assert "格式无效" in response.json()["items"][1]["error"]


def test_compressed_share_code_rejects_bombs_truncation_and_trailing_data():
    client, _tos, _cloud = _client()
    created = client.post("/web/environments", json=_payload()).json()
    share_code = client.post(f"/web/environments/{created['id']}/share-code").json()[
        "shareCode"
    ]
    encoded = share_code.removeprefix("akenv://v1/")
    compressed = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4))
    bomb = zlib.compress(b"x" * (4 * 1024 * 1024 + 1), level=9)

    response = client.post(
        "/web/environment-share-codes/inspect",
        json={
            "shareCodes": [
                _share_code_from_bytes(bomb),
                _share_code_from_bytes(compressed[:-1]),
                _share_code_from_bytes(compressed + b"trailing"),
            ]
        },
    )

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["valid"] for item in items] == [False, False, False]
    assert "大小限制" in items[0]["error"]
    assert "损坏或不完整" in items[1]["error"]
    assert "损坏或不完整" in items[2]["error"]
