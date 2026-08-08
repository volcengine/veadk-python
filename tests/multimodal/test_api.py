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
"""HTTP contract tests for multimodal upload and delivery."""

from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from veadk.multimodal.api import mount_media_routes
from veadk.multimodal.service import MediaService
from veadk.multimodal.storage import LocalMediaStorage


def test_upload_download_and_session_cleanup(tmp_path: Path) -> None:
    app = FastAPI()
    mount_media_routes(app, MediaService(LocalMediaStorage(tmp_path)))
    client = TestClient(app)

    response = client.post(
        "/web/media",
        data={"app_name": "demo", "user_id": "user", "session_id": "session"},
        files={"file": ("guide.md", b"# Hello", "text/markdown")},
    )

    assert response.status_code == 200
    media = response.json()
    assert media["mimeType"] == "text/markdown"
    content_path = f"/web/media/demo/user/session/{media['id']}/content"
    content = client.get(content_path)
    assert content.status_code == 200
    assert content.content == b"# Hello"
    assert content.headers["content-type"].startswith("text/markdown")

    media_path = f"/web/media/demo/user/session/{media['id']}"
    assert client.delete(media_path).status_code == 200
    assert client.get(content_path).status_code == 404

    second_response = client.post(
        "/web/media",
        data={"app_name": "demo", "user_id": "user", "session_id": "session"},
        files={"file": ("notes.txt", b"hello", "text/plain")},
    )
    assert second_response.status_code == 200

    assert client.post("/web/media/demo/user/session/delete").status_code == 200
    second_id = second_response.json()["id"]
    assert (
        client.get(f"/web/media/demo/user/session/{second_id}/content").status_code
        == 404
    )


def test_upload_rejects_unsupported_file(tmp_path: Path) -> None:
    app = FastAPI()
    mount_media_routes(app, MediaService(LocalMediaStorage(tmp_path)))
    client = TestClient(app)

    response = client.post(
        "/web/media",
        data={"app_name": "demo", "user_id": "user", "session_id": "session"},
        files={"file": ("archive.zip", b"PK\x03\x04payload", "application/zip")},
    )

    assert response.status_code == 400
    assert "Unsupported media type" in response.json()["detail"]


def test_media_routes_authorize_every_user_scoped_operation(tmp_path: Path) -> None:
    app = FastAPI()
    authorized: list[str] = []

    def authorize(_request: Request, user_id: str) -> None:
        authorized.append(user_id)
        if user_id != "owner":
            raise HTTPException(status_code=403, detail="forbidden")

    mount_media_routes(
        app,
        MediaService(LocalMediaStorage(tmp_path)),
        authorize=authorize,
    )
    client = TestClient(app)

    denied_upload = client.post(
        "/web/media",
        data={"app_name": "demo", "user_id": "other", "session_id": "session"},
        files={"file": ("notes.txt", b"secret", "text/plain")},
    )
    owner_upload = client.post(
        "/web/media",
        data={"app_name": "demo", "user_id": "owner", "session_id": "session"},
        files={"file": ("notes.txt", b"secret", "text/plain")},
    )
    media_id = owner_upload.json()["id"]

    assert denied_upload.status_code == 403
    assert owner_upload.status_code == 200
    assert (
        client.get(f"/web/media/demo/other/session/{media_id}/content").status_code
        == 403
    )
    assert client.get(f"/web/media/demo/other/session/{media_id}").status_code == 403
    assert client.delete(f"/web/media/demo/other/session/{media_id}").status_code == 403
    assert client.delete("/web/media/demo/other/session").status_code == 403
    assert authorized == ["other", "owner", "other", "other", "other", "other"]
