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
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from frontend.server.artifacts.models import (
    ArtifactIngestCandidate,
    ArtifactMetadataPatch,
)
from frontend.server.artifacts.repository import ArtifactNotFound, TosArtifactRepository
from frontend.server.artifacts.routes import mount_routes
from frontend.server.artifacts.service import ArtifactService


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS {status_code}")
        self.status_code = status_code


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: Any,
        forbid_overwrite: bool = False,
        **_: Any,
    ) -> None:
        object_key = (bucket, key)
        if forbid_overwrite and object_key in self.objects:
            raise _TosError(409)
        data = content.read() if hasattr(content, "read") else bytes(content)
        self.objects[object_key] = data

    def get_object(self, *, bucket: str, key: str) -> io.BytesIO:
        try:
            return io.BytesIO(self.objects[(bucket, key)])
        except KeyError as error:
            raise _TosError(404) from error

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        keys = sorted(
            key
            for object_bucket, key in self.objects
            if object_bucket == bucket and key.startswith(prefix)
        )
        start = int(continuation_token or 0)
        selected = keys[start : start + max_keys]
        next_index = start + len(selected)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in selected],
            is_truncated=next_index < len(keys),
            next_continuation_token=(
                str(next_index) if next_index < len(keys) else None
            ),
        )

    def delete_object(self, *, bucket: str, key: str) -> None:
        self.objects.pop((bucket, key), None)

    def pre_signed_url(
        self, *_: Any, bucket: str, key: str, **__: Any
    ) -> SimpleNamespace:
        assert (bucket, key) in self.objects
        return SimpleNamespace(signed_url=f"https://signed.example/{key}")


def _candidate(
    *,
    session_id: str = "session-1",
    event_id: str = "event-1",
) -> ArtifactIngestCandidate:
    now = datetime(2026, 8, 16, 8, 0, tzinfo=timezone.utc)
    return ArtifactIngestCandidate.model_validate(
        {
            "sourceUrl": "https://example.com/generated.png",
            "name": "generated.png",
            "mimeType": "image/png",
            "appName": "visual-agent",
            "agentId": "runtime-1",
            "agentName": "Visual Agent",
            "sessionId": session_id,
            "sessionTitle": "Generate a cover",
            "sessionUpdatedAt": now.isoformat(),
            "createdAt": now.isoformat(),
            "origin": {
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "eventId": event_id,
                "invocationId": "invocation-1",
                "toolName": "image_generate",
                "taskId": "task-1",
            },
        }
    )


def _service(client: _FakeTosClient) -> ArtifactService:
    repository = TosArtifactRepository(
        bucket="studio",
        client_factory=lambda: client,
    )
    service = ArtifactService(
        repository,
        source_host_suffixes=(".example.com",),
    )

    async def download(_url: str, _mime: str, target: Any) -> tuple[str, int]:
        target.write_bytes(b"\x89PNG\r\nartifact")
        return "image/png", target.stat().st_size

    service._download = download  # type: ignore[method-assign]
    return service


@pytest.mark.asyncio
async def test_sync_uses_user_artifact_namespace_and_is_idempotent() -> None:
    client = _FakeTosClient()
    service = _service(client)

    first = await service.sync("owner@example.com", [_candidate()])
    second = await service.sync("owner@example.com", [_candidate()])

    assert len(first) == len(second) == 1
    assert first[0].id == second[0].id
    keys = [key for bucket, key in client.objects if bucket == "studio"]
    assert len(keys) == 2
    assert all(
        key.startswith("veadk-studio/v1/users/owner%40example.com/artifacts/")
        for key in keys
    )
    assert any(key.endswith("/metadata.json") for key in keys)
    assert any("/content/generated.png" in key for key in keys)


@pytest.mark.asyncio
async def test_metadata_edit_does_not_replace_immutable_content() -> None:
    client = _FakeTosClient()
    service = _service(client)
    item = (await service.sync("owner", [_candidate()]))[0]
    content_key = next(key for _, key in client.objects if "/content/" in key)
    content_before = client.objects[("studio", content_key)]

    updated = await service.update(
        "owner",
        item.id,
        ArtifactMetadataPatch(name="cover.png", description="Hero", tags=["hero"]),
    )

    assert updated.name == "cover.png"
    assert updated.description == "Hero"
    assert updated.tags == ["hero"]
    assert client.objects[("studio", content_key)] == content_before


@pytest.mark.asyncio
async def test_owner_isolation_and_explicit_delete() -> None:
    client = _FakeTosClient()
    service = _service(client)
    item = (await service.sync("owner-a", [_candidate()]))[0]

    with pytest.raises(ArtifactNotFound):
        await service.get("owner-b", item.id)

    await service.delete("owner-a", item.id)
    assert await service.list("owner-a") == []


def test_routes_use_authenticated_owner_for_list_content_edit_and_delete() -> None:
    client = _FakeTosClient()
    service = _service(client)
    app = FastAPI()
    mount_routes(app, service, lambda request: request.headers["X-Owner"])
    http = TestClient(app)

    sync = http.post(
        "/web/artifacts/sync",
        headers={"X-Owner": "owner"},
        json={"candidates": [_candidate().model_dump(mode="json", by_alias=True)]},
    )
    assert sync.status_code == 200
    artifact = sync.json()["items"][0]

    listing = http.get("/web/artifacts", headers={"X-Owner": "owner"})
    assert listing.status_code == 200
    assert listing.json()["items"][0]["origin"]["toolName"] == "image_generate"

    content = http.get(
        f"/web/artifacts/{artifact['id']}/content?download=true",
        headers={"X-Owner": "owner"},
    )
    assert content.status_code == 200
    assert content.content == b"\x89PNG\r\nartifact"
    assert content.headers["content-disposition"].startswith("attachment;")

    patched = http.patch(
        f"/web/artifacts/{artifact['id']}",
        headers={"X-Owner": "owner"},
        json={"description": "Edited"},
    )
    assert patched.status_code == 200
    assert patched.json()["description"] == "Edited"

    deleted = http.delete(
        f"/web/artifacts/{artifact['id']}",
        headers={"X-Owner": "owner"},
    )
    assert deleted.status_code == 204
    assert http.get("/web/artifacts", headers={"X-Owner": "owner"}).json() == {
        "items": []
    }
