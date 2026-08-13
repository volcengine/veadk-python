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

from unittest.mock import AsyncMock, Mock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.testclient import TestClient

from veadk.auth.middleware.oauth2_auth import (
    OAuth2Handler,
    _resolve_redirect_after_auth,
    register_oauth2_routes,
)


@pytest.fixture
def login_request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("studio.example.com", 443),
            "path": "/oauth2/login",
            "raw_path": b"/oauth2/login",
            "query_string": b"",
            "headers": [(b"host", b"studio.example.com")],
        }
    )


@pytest.mark.parametrize(
    ("redirect", "expected"),
    [
        (None, "/"),
        ("", "/"),
        ("/", "/"),
        ("dashboard?tab=1", "/dashboard?tab=1"),
        ("?tab=1", "/?tab=1"),
        ("#activity", "/#activity"),
        ("/dashboard?tab=1#activity", "/dashboard?tab=1#activity"),
        ("/search?q=100%", "/search?q=100%"),
        ("/%ZZ", "/%ZZ"),
        ("/files/a%2Fb", "/files/a%2Fb"),
        (
            "/web/openclaw/sessions/session-1/surface/token-1/openclaw/",
            "/web/openclaw/sessions/session-1/surface/token-1/openclaw/",
        ),
        (
            "/web/hermes/sessions/session-1/surface/token-1/hermes/"
            "?theme=dark#workspace",
            "/web/hermes/sessions/session-1/surface/token-1/hermes/"
            "?theme=dark#workspace",
        ),
        (
            "/web/sandbox/proxy/cloud-session/terminal/terminal"
            "?session_id=native-shell-1",
            "/web/sandbox/proxy/cloud-session/terminal/terminal"
            "?session_id=native-shell-1",
        ),
        (
            "https://studio.example.com/dashboard?tab=1#activity",
            "/dashboard?tab=1#activity",
        ),
        (
            "https://studio.example.com/web/openclaw/sessions/session-1/"
            "surface/token-1/openclaw/",
            "/web/openclaw/sessions/session-1/surface/token-1/openclaw/",
        ),
        ("https://STUDIO.EXAMPLE.COM:443/dashboard", "/dashboard"),
    ],
)
def test_resolve_redirect_after_auth_accepts_safe_targets(
    login_request: Request, redirect: str | None, expected: str
) -> None:
    assert _resolve_redirect_after_auth(login_request, redirect) == expected


@pytest.mark.parametrize(
    "redirect",
    [
        " //attacker.example/path",
        "//attacker.example/path",
        "///attacker.example/path",
        r"/\attacker.example/path",
        r"\\attacker.example\path",
        "%2f%2fattacker.example/path",
        "/%2fattacker.example/path",
        "/%252fattacker.example/path",
        "/%5c%5cattacker.example/path",
        "/%255cattacker.example/path",
        "/\r\nLocation: https://attacker.example",
        "https://attacker.example/path",
        "https://studio.example.com.attacker.example/path",
        "https://studio.example.com@attacker.example/path",
        "https://user@studio.example.com/path",
        "https://studio.example.com:444/path",
        "http://studio.example.com/path",
        "https://studio.example.com//attacker.example/path",
        "javascript:alert(1)",
    ],
)
def test_resolve_redirect_after_auth_rejects_unsafe_targets(
    login_request: Request, redirect: str
) -> None:
    assert _resolve_redirect_after_auth(login_request, redirect) == "/"


@pytest.mark.parametrize(
    ("stored_redirect", "expected"),
    [
        ("//attacker.example/path", "/"),
        ("/dashboard?tab=1", "/dashboard?tab=1"),
        (
            "https://studio.example.com/web/openclaw/sessions/session-1/"
            "surface/token-1/openclaw/",
            "/web/openclaw/sessions/session-1/surface/token-1/openclaw/",
        ),
        (
            "https://studio.example.com/web/sandbox/proxy/cloud-session/"
            "terminal/terminal?session_id=native-shell-1",
            "/web/sandbox/proxy/cloud-session/terminal/terminal"
            "?session_id=native-shell-1",
        ),
    ],
)
def test_oauth2_callback_revalidates_stored_redirect(
    stored_redirect: str, expected: str
) -> None:
    handler = Mock(spec=OAuth2Handler)
    handler.state_store = Mock()
    handler.state_store.validate_and_consume_state.return_value = {
        "redirect_after_auth": stored_redirect,
        "code_verifier": None,
    }
    handler.exchange_code_for_token = AsyncMock(return_value=Mock())
    handler.create_session_cookie.return_value = {
        "key": "veadk_session",
        "value": "session",
    }
    handler.create_user_id_cookie.return_value = None

    app = Starlette()
    register_oauth2_routes(app, handler)

    with TestClient(app, base_url="https://studio.example.com") as client:
        response = client.get(
            "/oauth2/callback",
            params={"code": "code", "state": "state"},
            follow_redirects=False,
        )

    assert response.status_code == 302
    assert response.headers["location"] == expected
