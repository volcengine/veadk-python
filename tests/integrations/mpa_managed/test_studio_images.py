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

"""Isolated OCI discovery and Studio retry regression tests."""

import asyncio
import hashlib
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from frontend.server import mpa_creation_images as images
from veadk.integrations.mpa.managed.config import ConfigurationError


class Registry:
    def __init__(self):
        self.documents = {}
        self.tags = []
        self.requests = []
        self.challenge = True
        self.next_page: str | None = None

    def document(self, value):
        data = json.dumps(value).encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        self.documents[digest] = data
        return digest

    def image(self, tag, created, architecture="amd64", *, index=False):
        config = self.document(
            {"created": created, "architecture": architecture, "os": "linux"}
        )
        manifest = self.document({"config": {"digest": config}})
        if index:
            manifest = self.document(
                {
                    "manifests": [
                        {
                            "platform": {"os": "unknown", "architecture": "unknown"},
                            "digest": "sha256:" + "0" * 64,
                        },
                        {
                            "platform": {"os": "linux", "architecture": architecture},
                            "digest": manifest,
                        },
                    ]
                }
            )
        self.documents[tag] = self.documents[manifest]
        self.tags.append(tag)
        return "sha256:" + hashlib.sha256(self.documents[tag]).hexdigest()

    def handle(self, request):
        self.requests.append(request)
        path = request.url.path
        repository = images.STUDIO_IMAGE_REPOSITORIES["runtimeImage"].split("/", 1)[1]
        if path == "/token":
            return httpx.Response(200, json={"token": "ephemeral-test-token"})
        if self.challenge and "authorization" not in request.headers:
            return httpx.Response(
                401,
                headers={
                    "www-authenticate": f'Bearer realm="https://{request.url.host}/token",service="harbor-registry",scope="repository:{repository}:pull"'
                },
            )
        if path.endswith("/tags/list"):
            headers = {"link": self.next_page} if self.next_page else {}
            return httpx.Response(200, json={"tags": self.tags}, headers=headers)
        key = path.rsplit("/", 1)[1]
        if key in self.documents:
            data = self.documents[key]
            return httpx.Response(200, content=data)
        return httpx.Response(404, json={"error": "private-error-must-not-escape"})


def resolve(registry):
    return asyncio.run(
        images.resolve_studio_images(
            ("runtimeImage",), transport=httpx.MockTransport(registry.handle)
        )
    )


def test_newest_build_wins_over_tag_sort_and_index_attestation_is_ignored():
    registry = Registry()
    registry.image("zzz-old", "2026-09-01T00:00:00Z")
    digest = registry.image("aaa-new", "2026-10-01T00:00:00.123456789Z", index=True)
    registry.image(
        "arm-newest", "2026-10-08T00:00:00Z", architecture="arm64", index=True
    )
    assert resolve(registry) == {
        "runtimeImage": images.STUDIO_IMAGE_REPOSITORIES["runtimeImage"] + "@" + digest
    }
    assert any(r.url.path == "/token" for r in registry.requests)
    assert not any(r.url.path.endswith("0" * 64) for r in registry.requests)


def test_single_manifest_and_timestamp_tie_are_deterministic():
    registry = Registry()
    registry.image("a", "2026-10-01T00:00:00Z")
    digest = registry.image("b", "2026-10-01T00:00:00Z")
    assert resolve(registry)["runtimeImage"].endswith("@" + digest)


@pytest.mark.parametrize("created", [None, "", "not-a-date", "2026-10-01T00:00:00"])
def test_invalid_or_unzoned_build_time_fails_explicitly(created):
    registry = Registry()
    registry.image("bad", created)
    with pytest.raises(ConfigurationError, match="metadata"):
        resolve(registry)


@pytest.mark.parametrize("architecture", [None, "arm64"])
def test_no_compatible_image_is_not_empty_success(architecture):
    registry = Registry()
    if architecture:
        registry.image("arm", "2026-10-01T00:00:00Z", architecture=architecture)
    with pytest.raises(ConfigurationError, match="Linux/amd64"):
        resolve(registry)


def test_failure_is_redacted_and_does_not_fall_back():
    registry = Registry()
    registry.tags = ["missing"]
    with pytest.raises(ConfigurationError) as exc:
        resolve(registry)
    assert "private-error" not in str(exc.value)
    assert "ephemeral-test-token" not in str(exc.value)


def test_challenge_cannot_send_credentials_to_other_origin():
    called = []

    def handle(request):
        called.append(request.url.host)
        return httpx.Response(
            401,
            headers={
                "www-authenticate": 'Bearer realm="https://evil.example/token",service="registry",scope="repository:bad:pull"'
            },
        )

    with pytest.raises(ConfigurationError, match="authentication"):
        asyncio.run(
            images.resolve_studio_images(
                ("runtimeImage",), transport=httpx.MockTransport(handle)
            )
        )
    assert len(called) == 1


def test_tag_limit_does_not_select_from_incomplete_list():
    registry = Registry()
    registry.tags = [f"v{x}" for x in range(101)]
    with pytest.raises(ConfigurationError, match="limit"):
        resolve(registry)


def test_cross_origin_pagination_is_rejected():
    registry = Registry()
    registry.next_page = '<https://evil.example/tags>; rel="next"'
    with pytest.raises(ConfigurationError, match="pagination"):
        resolve(registry)


def test_content_digest_is_verified():
    registry = Registry()
    registry.image("bad", "2026-10-01T00:00:00Z")
    manifest = json.loads(registry.documents["bad"])
    registry.documents[manifest["config"]["digest"]] = b'{"created":"tampered"}'
    with pytest.raises(ConfigurationError, match="digest"):
        resolve(registry)


def test_timeout_is_redacted():
    def handle(request):
        raise httpx.ReadTimeout("signed-url-secret", request=request)

    with pytest.raises(ConfigurationError, match="unavailable") as exc:
        asyncio.run(
            images.resolve_studio_images(
                ("runtimeImage",), transport=httpx.MockTransport(handle)
            )
        )
    assert "signed-url-secret" not in str(exc.value)


def test_cancellation_propagates():
    async def handle(request):
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            images.resolve_studio_images(
                ("runtimeImage",), transport=httpx.MockTransport(handle)
            )
        )


def test_manual_inputs_and_stored_snapshot_skip_discovery(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from frontend.server import mpa_creation
    from veadk.integrations.mpa.managed.tasks import CreationTasks
    import sys

    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(
        mpa_creation, "load_volcengine_credentials", lambda *args: object()
    )
    discover = AsyncMock(side_effect=ConfigurationError("registry unavailable"))
    monkeypatch.setattr(mpa_creation, "resolve_studio_images", discover)
    service = CreationTasks(tmp_path / "tasks.db")
    service.command = lambda: [sys.executable, "-c", "raise SystemExit(1)"]
    app = FastAPI()
    mpa_creation.mount_mpa_creation_routes(
        app, owner=lambda request: "owner", service=service
    )
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "region": "cn-beijing",
        "runtimeImage": "repo/mpa:v1",
        "workerImage": "repo/worker:v1",
    }
    with TestClient(app) as client:
        first = client.post("/web/mpa-creation/tasks", json=payload)
        assert first.status_code == 202
        retry = client.post("/web/mpa-creation/tasks", json=payload)
        assert retry.status_code == 202
        assert retry.json()["images"] == first.json()["images"]
        assert discover.await_count == 0
        changed = client.post(
            "/web/mpa-creation/tasks", json={**payload, "runtimeImage": ""}
        )
        assert changed.status_code == 409
        assert discover.await_count == 0
        unavailable = client.post(
            "/web/mpa-creation/tasks",
            json={
                **payload,
                "requestId": "22222222-2222-4222-8222-222222222222",
                "runtimeImage": "",
            },
        )
        assert unavailable.status_code == 400


def test_blank_retry_config_and_submission_use_owner_snapshot_when_registry_is_down(
    tmp_path, monkeypatch
):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from frontend.server import mpa_creation
    from veadk.integrations.mpa.managed.tasks import CreationTasks, owner_key
    import sys

    monkeypatch.setenv("VEADK_MPA_CONFIG_MODEL_AGENT_API_KEY", "test-model-key")
    monkeypatch.setattr(
        mpa_creation, "load_volcengine_credentials", lambda *args: object()
    )
    service = CreationTasks(tmp_path / "tasks.db")
    service.command = lambda: [sys.executable, "-c", "raise SystemExit(1)"]
    payload = {
        "requestId": "11111111-1111-4111-8111-111111111111",
        "agentId": "mi-test",
        "region": "cn-beijing",
        "description": "",
    }
    snapshot = {
        "runtimeImage": "repo/mpa@sha256:" + "a" * 64,
        "workerImage": "repo/worker@sha256:" + "b" * 64,
    }

    async def seed():
        task = await service.start(
            owner_key("owner"), payload, config_path=None, timeout=30, images=snapshot
        )
        await asyncio.gather(*service.running.values())
        await service.close()
        return task

    first = asyncio.run(seed())
    discover = AsyncMock(side_effect=ConfigurationError("registry unavailable"))
    monkeypatch.setattr(mpa_creation, "resolve_studio_images", discover)
    app = FastAPI()
    mpa_creation.mount_mpa_creation_routes(
        app, owner=lambda request: "owner", service=service
    )
    with TestClient(app) as client:
        config = client.get(
            "/web/mpa-creation/config",
            params={"region": "cn-beijing", "requestId": payload["requestId"]},
        )
        assert config.json()["configured"] is True
        assert config.json()["runtimeImage"] == snapshot["runtimeImage"]
        retry = client.post("/web/mpa-creation/tasks", json=payload)
        assert retry.status_code == 202
        assert retry.json()["taskId"] == first["taskId"]
        assert retry.json()["images"] == snapshot
        assert discover.await_count == 0
    assert (
        service.request_images(owner_key("another-owner"), payload["requestId"]) is None
    )


def test_blob_storage_redirect_strips_bearer_and_checks_digest():
    registry = Registry()
    registry.image("latest", "2026-10-01T00:00:00Z")
    blob_digest = json.loads(registry.documents["latest"])["config"]["digest"]
    storage_requests = []

    def handle(request):
        if request.url.host == "objects.tos-cn-beijing.volces.com":
            storage_requests.append(request)
            return httpx.Response(200, content=registry.documents[blob_digest])
        if request.url.path.endswith("/blobs/" + blob_digest):
            return httpx.Response(
                307,
                headers={
                    "location": "https://objects.tos-cn-beijing.volces.com/config?signature=local-test"
                },
            )
        return registry.handle(request)

    asyncio.run(
        images.resolve_studio_images(
            ("runtimeImage",), transport=httpx.MockTransport(handle)
        )
    )
    assert len(storage_requests) == 1
    assert "authorization" not in storage_requests[0].headers


def test_body_limit_rejects_large_metadata():
    def handle(request):
        return httpx.Response(200, content=b"x" * (1024 * 1024 + 1))

    with pytest.raises(ConfigurationError, match="size limit"):
        asyncio.run(
            images.resolve_studio_images(
                ("runtimeImage",), transport=httpx.MockTransport(handle)
            )
        )


def test_pagination_scans_later_tags():
    registry = Registry()
    registry.challenge = False
    registry.image("old", "2026-09-01T00:00:00Z")
    digest = registry.image("new", "2026-10-01T00:00:00Z")

    def handle(request):
        if request.url.path.endswith("/tags/list"):
            if request.url.params.get("last"):
                return httpx.Response(200, json={"tags": ["new"]})
            return httpx.Response(
                200,
                json={"tags": ["old"]},
                headers={"link": f'<{request.url.path}?n=100&last=old>; rel="next"'},
            )
        return registry.handle(request)

    result = asyncio.run(
        images.resolve_studio_images(
            ("runtimeImage",), transport=httpx.MockTransport(handle)
        )
    )
    assert result["runtimeImage"].endswith(digest)


def test_nanosecond_build_order_is_preserved():
    registry = Registry()
    registry.image("zzz-older", "2026-10-01T00:00:00.123456001Z")
    digest = registry.image("aaa-newer", "2026-10-01T00:00:00.123456999Z")
    assert resolve(registry)["runtimeImage"].endswith(digest)
