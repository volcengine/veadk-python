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

import base64
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from veadk.cli.cli_frontend import (
    _build_agentkit_proxy_headers,
    _run_frontend_server,
)


def _create_frontend_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")

    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        host="127.0.0.1",
        port=8765,
        dev=True,
        vite=True,
        oauth2_user_pool=None,
        oauth2_user_pool_client=None,
        oauth2_user_pool_uid=None,
        oauth2_user_pool_client_uid=None,
        oauth2_redirect_uri=None,
        oauth2_provider=None,
        oauth2_provider_label=None,
        auth_mode="frontend",
        generated_agent_test_run_ttl=60,
        open_browser=False,
    )
    return captured["app"]


def test_proxy_headers_do_not_forward_unvalidated_authorization() -> None:
    headers = _build_agentkit_proxy_headers(
        {
            "Authorization": "Bearer unvalidated.jwt.token",
            "Cookie": "session=secret",
            "Accept": "application/json",
        },
        api_key=None,
    )

    assert headers == {"Accept": "application/json"}


@pytest.mark.parametrize(
    ("authorizer", "expected_authorization"),
    [
        (
            SimpleNamespace(
                key_auth=None,
                custom_jwt_authorizer=SimpleNamespace(
                    discovery_url="https://issuer.example/.well-known/openid-configuration",
                    allowed_clients=["frontend-client"],
                ),
            ),
            "Bearer validated.jwt.token",
        ),
        (
            SimpleNamespace(
                key_auth=SimpleNamespace(api_key="runtime-api-key"),
                custom_jwt_authorizer=None,
            ),
            "Bearer runtime-api-key",
        ),
    ],
)
def test_runtime_proxy_uses_authorizer_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    authorizer: SimpleNamespace,
    expected_authorization: str,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    @app.middleware("http")
    async def _mark_validated_oauth_token(request: Request, call_next):
        request.state.oauth2_access_token_validated = True
        request.state.oauth2_access_token = "validated.jwt.token"
        return await call_next(request)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=authorizer,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    upstream_headers: dict[str, str] = {}
    upstream_url = ""

    class _FakeUpstreamResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b'["demo_agent"]'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            nonlocal upstream_url
            upstream_url = url
            upstream_headers.update(headers)
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-proxy/runtime-1/dev/apps/demo_agent/debug/trace/"
            "session/session-1"
            "?region=cn-beijing"
        )

    assert response.status_code == 200
    assert response.json() == ["demo_agent"]
    assert upstream_url == (
        "https://runtime.example/dev/apps/demo_agent/debug/trace/session/session-1"
    )
    assert upstream_headers["Authorization"] == expected_authorization


def test_runtime_proxy_resolves_studio_media_before_forwarding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VEADK_MEDIA_LOCAL_DIR", str(tmp_path / "media"))
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )
    upstream_body = b""

    class _FakeUpstreamResponse:
        status_code = 200
        headers = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b"{}"

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            nonlocal upstream_body
            upstream_body = content
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
        "AScY42YAAAAASUVORK5CYII="
    )

    with TestClient(app) as client:
        upload = client.post(
            "/web/media",
            data={
                "app_name": "demo",
                "user_id": "user",
                "session_id": "session",
            },
            files={"file": ("cat.png", png, "image/png")},
        )
        assert upload.status_code == 200
        media = upload.json()
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "demo",
                "user_id": "user",
                "session_id": "session",
                "new_message": {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": media["uri"],
                                "mimeType": "image/png",
                            },
                            "partMetadata": {"veadkMedia": media},
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200
    forwarded_part = json.loads(upstream_body)["new_message"]["parts"][0]
    assert "fileData" not in forwarded_part
    assert base64.b64decode(forwarded_part["inlineData"]["data"]) == png
    assert forwarded_part["partMetadata"]["veadkMedia"]["uri"] == media["uri"]
