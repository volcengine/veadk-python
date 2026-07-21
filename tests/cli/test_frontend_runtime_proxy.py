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
    _frontend_allow_origins,
    _run_frontend_server,
)


def _create_frontend_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    site_logo: str | None = None,
    site_title: str | None = None,
) -> FastAPI:
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
        site_logo=site_logo,
        site_title=site_title,
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


def test_vite_allows_both_loopback_browser_origins() -> None:
    assert _frontend_allow_origins(vite=True) == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    assert _frontend_allow_origins(vite=False) == []


def test_ui_config_serves_custom_branding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    logo = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
        "AQUBAScY42YAAAAASUVORK5CYII="
    )
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(logo)
    app = _create_frontend_app(
        monkeypatch,
        tmp_path,
        site_logo=str(logo_path),
        site_title="火山助手",
    )

    with TestClient(app) as client:
        config_response = client.get("/web/ui-config")
        logo_response = client.get("/web/site-logo")

    assert config_response.status_code == 200
    assert config_response.json()["branding"] == {
        "title": "火山助手",
        "logoUrl": "/web/site-logo",
    }
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"].startswith("image/png")
    assert logo_response.content == logo


def test_runtime_list_paginates_across_regions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, str, int]] = []
    runtimes = {
        "cn-beijing": [
            ("beijing-new", "2026-07-21T05:00:00Z"),
            ("beijing-mid", "2026-07-21T03:00:00Z"),
            ("beijing-old", "2026-07-21T01:00:00Z"),
        ],
        "cn-shanghai": [
            ("shanghai-new", "2026-07-21T06:00:00Z"),
            ("shanghai-old", "2026-07-21T02:00:00Z"),
        ],
    }

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            offset = int(getattr(request, "next_token", "") or 0)
            page_size = request.max_results
            calls.append((self.region, str(offset), page_size))
            source = runtimes[self.region]
            page = source[offset : offset + page_size]
            page_end = offset + len(page)
            return SimpleNamespace(
                agent_kit_runtimes=[
                    SimpleNamespace(
                        name=name,
                        runtime_id=f"runtime-{name}",
                        status="Ready",
                        created_at=created_at,
                        tags=[],
                    )
                    for name, created_at in page
                ],
                next_token=str(page_end) if page_end < len(source) else "",
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )

    with TestClient(app) as client:
        first = client.get("/web/runtimes", params={"region": "all", "page_size": 2})
        first_calls = list(calls)
        second = client.get(
            "/web/runtimes",
            params={
                "region": "all",
                "page_size": 2,
                "next_token": first.json()["nextToken"],
            },
        )
        third = client.get(
            "/web/runtimes",
            params={
                "region": "all",
                "page_size": 2,
                "next_token": second.json()["nextToken"],
            },
        )

    assert [item["name"] for item in first.json()["runtimes"]] == [
        "shanghai-new",
        "beijing-new",
    ]
    assert sorted(first_calls) == [
        ("cn-beijing", "0", 2),
        ("cn-shanghai", "0", 2),
    ]
    assert first.json()["nextToken"] == "all:2"
    assert [item["name"] for item in second.json()["runtimes"]] == [
        "beijing-mid",
        "shanghai-old",
    ]
    assert second.json()["nextToken"] == "all:4"
    assert [item["name"] for item in third.json()["runtimes"]] == ["beijing-old"]
    assert third.json()["nextToken"] == ""


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
