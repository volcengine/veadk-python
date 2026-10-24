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
import zipfile
from io import BytesIO

import httpx
import pytest

from veadk.skills.ma_infra import (
    MaInfraSkillConfig,
    MaInfraSkillError,
    MaInfraSkillsClient,
)


def _zip(content: bytes = b"SKILL") -> bytes:
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as target:
        target.writestr("SKILL.md", content)
    return buffer.getvalue()


def _config(**kwargs: str) -> MaInfraSkillConfig:
    values = {
        "base_url": "https://ma-infra.example",
        "api_key": "key-1",
        "account_id": "account-1",
        **kwargs,
    }
    return MaInfraSkillConfig(**values)


def _client(handler) -> MaInfraSkillsClient:
    transport = httpx.MockTransport(handler)
    return MaInfraSkillsClient(_config(), transport=transport)


def _json_response(payload: object, status: int = 200) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        headers={"Content-Type": "application/json"},
    )


def test_config_from_env_requires_base_url(monkeypatch) -> None:
    monkeypatch.delenv("MA_SKILLS_BASE_URL", raising=False)
    assert MaInfraSkillConfig.from_env() is None

    monkeypatch.setenv("MA_SKILLS_BASE_URL", " https://ma-infra.example/ ")
    monkeypatch.setenv("MA_SKILLS_API_KEY", "key-1")
    monkeypatch.setenv("MA_SKILLS_ACCOUNT_ID", "account-1")

    config = MaInfraSkillConfig.from_env()
    assert config is not None
    assert config.base_url == "https://ma-infra.example"
    assert config.api_key == "key-1"
    assert config.account_id == "account-1"


def test_list_skills_sends_account_headers_and_parses_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["x-api-key"] == "key-1"
        assert request.headers["X-Top-Account-Id"] == "account-1"
        assert request.url.params["source"] == "custom"
        return _json_response(
            {
                "data": [
                    {
                        "id": "s-1",
                        "type": "skill",
                        "display_name": "document-summary",
                        "description": "d",
                        "latest_version_id": "v1",
                        "source": {"type": "custom"},
                    }
                ],
                "next_page": None,
            }
        )

    client = _client(handler)
    skills = client.list_skills()
    assert skills[0]["id"] == "s-1"
    assert skills[0]["display_name"] == "document-summary"
    assert skills[0]["latest_version_id"] == "v1"


def test_get_version_resolves_latest_to_concrete_id() -> None:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return _json_response(
            {
                "id": "v2",
                "type": "skill_version",
                "name": "document-summary",
                "description": "d",
            }
        )

    client = _client(handler)
    meta = client.get_version("s-1", "latest")

    assert meta["id"] == "v2"
    assert meta["name"] == "document-summary"
    assert seen == ["/v1/skills/s-1/versions/latest"]


def test_download_content_resolves_latest_before_download() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        if request.url.path.endswith("/content"):
            return httpx.Response(200, content=_zip())
        return _json_response(
            {
                "id": "v2",
                "type": "skill_version",
                "name": "document-summary",
                "description": "d",
            }
        )

    client = _client(handler)
    content = client.download_content("s-1", "latest")

    assert content.startswith(b"PK")
    assert paths == [
        "/v1/skills/s-1/versions/latest",
        "/v1/skills/s-1/versions/v2/content",
    ]


def test_download_content_uses_pinned_version_directly() -> None:
    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, content=_zip())

    client = _client(handler)
    content = client.download_content("s-1", "v1")

    assert content.startswith(b"PK")
    assert paths == ["/v1/skills/s-1/versions/v1/content"]


def test_create_skill_sends_multipart_archive() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "multipart/form-data" in request.headers["Content-Type"]
        assert (
            b"document-summary" in request.content or b"display_name" in request.content
        )
        return _json_response(
            {
                "id": "s-9",
                "type": "skill",
                "display_name": "document-summary",
                "description": "d",
                "latest_version_id": "v1",
            }
        )

    client = _client(handler)
    created = client.create_skill("document-summary", _zip())

    assert created["id"] == "s-9"


def test_delete_skill_round_trips() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "DELETE"
        return _json_response({"id": "s-1", "type": "skill_deleted"})

    client = _client(handler)
    assert client.delete_skill("s-1")["type"] == "skill_deleted"


def test_error_body_is_surfaced() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(
            {
                "type": "error",
                "error": {"type": "invalid_request_error", "message": "bad id"},
            },
            status=400,
        )

    client = _client(handler)
    with pytest.raises(MaInfraSkillError) as excinfo:
        client.get_skill("s-1")
    assert excinfo.value.status_code == 400
    assert excinfo.value.code == "invalid_request_error"
    assert not excinfo.value.retryable


def test_transport_failure_is_retryable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom")

    client = _client(handler)
    with pytest.raises(MaInfraSkillError) as excinfo:
        client.list_skills()
    assert excinfo.value.retryable is True


@pytest.mark.asyncio
async def test_async_helpers_delegate_to_sync() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response({"data": [], "next_page": None})

    client = _client(handler)
    skills = await client.alist_skills()
    assert skills == []
    await asyncio.to_thread(client.close)
