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

import asyncio
import time
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from veadk.auth.middleware.oauth2_auth import (
    OIDCDiscoveryConfig,
    OAuth2Config,
    OAuth2Handler,
    OAuth2Session,
    _resolve_redirect_after_auth,
    register_oauth2_routes,
    setup_oauth2,
)


def oauth2_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://identity.example.com/authorize",
        token_url="https://identity.example.com/token",
        client_id="studio-client",
        client_secret="studio-secret",
        redirect_uri="https://studio.example.com/oauth2/callback",
        session_timeout_seconds=30 * 24 * 60 * 60,
    )


def session_request(handler: OAuth2Handler, session: OAuth2Session) -> Request:
    cookie = handler.encode_session(session)
    return Request(
        {
            "type": "http",
            "method": "GET",
            "scheme": "https",
            "server": ("studio.example.com", 443),
            "path": "/api/test",
            "raw_path": b"/api/test",
            "query_string": b"",
            "headers": [
                (b"host", b"studio.example.com"),
                (b"cookie", f"veadk_session={cookie}".encode()),
            ],
        }
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


@pytest.mark.asyncio
async def test_fetch_user_info_keeps_only_cookie_safe_fields() -> None:
    config = oauth2_config()
    config.userinfo_url = "https://identity.example.com/userinfo"
    config.user_id_field = "employee_id"
    handler = OAuth2Handler(config)
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "sub": "user-1",
        "email": "user@example.com",
        "name": "Example User",
        "picture": "https://identity.example.com/avatar.png",
        "employee_id": "employee-1",
        "tenant_id": "tenant-1",
        "roles": ["admin"],
        "external.claims": {"opaque": "x" * 10_000},
    }
    handler._http_client.get = AsyncMock(return_value=response)

    user_info = await handler._fetch_user_info("access-token")
    cookie = handler.encode_session(
        OAuth2Session(
            access_token="access-token",
            expires_at=time.time() + 3600,
            user_info=user_info,
        )
    )

    assert user_info == {
        "sub": "user-1",
        "email": "user@example.com",
        "name": "Example User",
        "picture": "https://identity.example.com/avatar.png",
        "employee_id": "employee-1",
    }
    assert len(cookie) < 4096


def test_refresh_token_keeps_browser_cookie_beyond_access_token_lifetime() -> None:
    handler = OAuth2Handler(oauth2_config())
    now = time.time()
    session = OAuth2Session(
        access_token="access-token",
        expires_at=now + 3600,
        refresh_token="refresh-token",
        session_expires_at=now + 30 * 24 * 60 * 60,
    )

    max_age = handler.create_session_cookie(session)["max_age"]

    assert 29 * 24 * 60 * 60 < max_age <= 30 * 24 * 60 * 60


def test_expired_access_token_remains_available_for_refresh() -> None:
    handler = OAuth2Handler(oauth2_config())
    session = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token",
        session_expires_at=time.time() + 3600,
    )

    restored = handler.get_session_from_request(session_request(handler, session))

    assert restored is not None
    assert restored.refresh_token == "refresh-token"


def test_expired_browser_session_is_not_available_for_refresh() -> None:
    handler = OAuth2Handler(oauth2_config())
    session = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="expired-refresh-token",
        session_expires_at=time.time() - 1,
    )

    restored = handler.get_session_from_request(session_request(handler, session))

    assert restored is None


@pytest.mark.asyncio
async def test_legacy_refresh_session_is_upgraded_before_access_token_expiry() -> None:
    handler = OAuth2Handler(oauth2_config())
    legacy = OAuth2Session(
        access_token="access-token",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token",
    )

    upgraded, cookie_changed = await handler.get_or_refresh_session(
        session_request(handler, legacy)
    )

    assert upgraded is not None
    assert upgraded.session_expires_at is not None
    assert 29 * 24 * 60 * 60 < upgraded.session_expires_at - time.time()
    assert cookie_changed is True


@pytest.mark.asyncio
async def test_legacy_session_without_refresh_token_is_not_extended() -> None:
    handler = OAuth2Handler(oauth2_config())
    legacy = OAuth2Session(
        access_token="access-token",
        expires_at=time.time() + 3600,
    )

    restored, cookie_changed = await handler.get_or_refresh_session(
        session_request(handler, legacy)
    )

    assert restored == legacy
    assert restored.session_expires_at is None
    assert cookie_changed is False


def test_legacy_session_upgrade_is_portable_across_instances() -> None:
    async def protected(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    first_app = Starlette(routes=[Route("/api/test", protected)])
    first_handler = setup_oauth2(first_app, oauth2_config())
    legacy = OAuth2Session(
        access_token="access-token",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token",
        user_info={"sub": "user-1"},
    )
    first_handler.validate_access_token = AsyncMock(return_value={"sub": "user-1"})

    with TestClient(first_app, base_url="https://studio.example.com") as client:
        client.cookies.set(
            "veadk_session",
            first_handler.encode_session(legacy),
            domain="studio.example.com",
            path="/",
        )
        response = client.get("/api/test", headers={"Accept": "application/json"})
        upgraded_cookie = client.cookies["veadk_session"]

    second_handler = OAuth2Handler(oauth2_config())
    restored = second_handler.decode_session(upgraded_cookie)

    assert response.status_code == 200
    assert "veadk_session=" in response.headers["set-cookie"]
    assert restored is not None
    assert restored.refresh_token == "refresh-token"
    assert restored.session_expires_at is not None
    assert 29 * 24 * 60 * 60 < restored.session_expires_at - time.time()


@pytest.mark.asyncio
async def test_get_or_refresh_session_recovers_expired_access_token() -> None:
    handler = OAuth2Handler(oauth2_config())
    absolute_expiry = time.time() + 3600
    expired = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-1",
        session_expires_at=absolute_expiry,
        user_info={"sub": "user-1"},
    )
    refreshed = OAuth2Session(
        access_token="access-token-2",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token-2",
        session_expires_at=absolute_expiry,
        user_info=expired.user_info,
    )
    handler.refresh_access_token = AsyncMock(return_value=refreshed)

    result, cookie_changed = await handler.get_or_refresh_session(
        session_request(handler, expired)
    )

    assert result == refreshed
    assert cookie_changed is True
    handler.refresh_access_token.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_access_token_coalesces_rotating_token_requests() -> None:
    handler = OAuth2Handler(oauth2_config())
    session = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-1",
        session_expires_at=time.time() + 3600,
    )
    refreshed = OAuth2Session(
        access_token="access-token-2",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token-2",
        session_expires_at=session.session_expires_at,
    )

    async def refresh_once(_: OAuth2Session) -> OAuth2Session:
        await asyncio.sleep(0)
        return refreshed

    handler._refresh_access_token_once = AsyncMock(side_effect=refresh_once)

    first, second = await asyncio.gather(
        handler.refresh_access_token(session),
        handler.refresh_access_token(session),
    )

    assert first == refreshed
    assert second == refreshed
    handler._refresh_access_token_once.assert_awaited_once()


@pytest.mark.asyncio
async def test_refresh_access_token_preserves_absolute_session_expiry() -> None:
    handler = OAuth2Handler(oauth2_config())
    absolute_expiry = time.time() + 3600
    session = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-1",
        session_expires_at=absolute_expiry,
        user_info={"sub": "user-1"},
    )
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {
        "access_token": "access-token-2",
        "refresh_token": "refresh-token-2",
        "expires_in": 3600,
    }
    handler._http_client.post = AsyncMock(return_value=response)

    refreshed = await handler.refresh_access_token(session)

    assert refreshed is not None
    assert refreshed.access_token == "access-token-2"
    assert refreshed.refresh_token == "refresh-token-2"
    assert refreshed.session_expires_at == absolute_expiry
    assert refreshed.user_info == {"sub": "user-1"}
    handler._http_client.post.assert_awaited_once()


def test_userinfo_refreshes_expired_access_token_and_rotates_cookie() -> None:
    handler = OAuth2Handler(oauth2_config())
    absolute_expiry = time.time() + 3600
    expired = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-1",
        session_expires_at=absolute_expiry,
        user_info={"sub": "user-1"},
    )
    refreshed = OAuth2Session(
        access_token="access-token-2",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token-2",
        session_expires_at=absolute_expiry,
        user_info=expired.user_info,
    )
    handler.refresh_access_token = AsyncMock(return_value=refreshed)
    handler.validate_access_token = AsyncMock(return_value={"sub": "user-1"})

    app = Starlette()
    register_oauth2_routes(app, handler)

    with TestClient(app, base_url="https://studio.example.com") as client:
        client.cookies.set(
            "veadk_session",
            handler.encode_session(expired),
            domain="studio.example.com",
            path="/",
        )
        response = client.get("/oauth2/userinfo")
        rotated = handler.decode_session(client.cookies["veadk_session"])

    assert response.status_code == 200
    assert response.json() == {"sub": "user-1"}
    assert rotated is not None
    assert rotated.access_token == "access-token-2"
    assert rotated.refresh_token == "refresh-token-2"


def test_userinfo_marks_failed_rotating_refresh_as_retryable() -> None:
    handler = OAuth2Handler(oauth2_config())
    expired = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-used-by-another-instance",
        session_expires_at=time.time() + 3600,
        user_info={"sub": "user-1"},
    )
    handler.refresh_access_token = AsyncMock(return_value=None)

    app = Starlette()
    register_oauth2_routes(app, handler)

    with TestClient(app, base_url="https://studio.example.com") as client:
        client.cookies.set(
            "veadk_session",
            handler.encode_session(expired),
            domain="studio.example.com",
            path="/",
        )
        response = client.get("/oauth2/userinfo")

    assert response.status_code == 401
    assert response.headers["X-VeADK-OAuth-Refresh-Retry"] == "1"


def test_protected_request_refreshes_expired_access_token() -> None:
    async def protected(_: Request) -> JSONResponse:
        return JSONResponse({"ok": True})

    app = Starlette(routes=[Route("/api/test", protected)])
    handler = setup_oauth2(app, oauth2_config())
    absolute_expiry = time.time() + 3600
    expired = OAuth2Session(
        access_token="expired-access-token",
        expires_at=time.time() - 1,
        refresh_token="refresh-token-1",
        session_expires_at=absolute_expiry,
        user_info={"sub": "user-1"},
    )
    refreshed = OAuth2Session(
        access_token="access-token-2",
        expires_at=time.time() + 3600,
        refresh_token="refresh-token-2",
        session_expires_at=absolute_expiry,
        user_info=expired.user_info,
    )
    handler.refresh_access_token = AsyncMock(return_value=refreshed)
    handler.validate_access_token = AsyncMock(return_value={"sub": "user-1"})

    with TestClient(app, base_url="https://studio.example.com") as client:
        client.cookies.set("veadk_session", handler.encode_session(expired))
        response = client.get("/api/test", headers={"Accept": "application/json"})

    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert "veadk_session=" in response.headers["set-cookie"]


def test_from_veidentity_uses_refresh_token_absolute_lifetime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_client = Mock()
    identity_client.get_user_pool.return_value = (
        "pool-id",
        "identity.example.com",
    )
    identity_client.get_user_pool_client.return_value = (
        "client-id",
        "client-secret",
    )
    identity_client.get_user_pool_client_refresh_token_lifetime.return_value = (
        30 * 24 * 60 * 60
    )
    monkeypatch.setattr(
        "veadk.auth.middleware.oauth2_auth._fetch_oidc_discovery",
        lambda _: OIDCDiscoveryConfig(
            issuer="https://identity.example.com",
            authorization_endpoint="https://identity.example.com/authorize",
            token_endpoint="https://identity.example.com/token",
        ),
    )

    config = OAuth2Config.from_veidentity(
        user_pool_uid="pool-id",
        client_uid="client-id",
        redirect_uri="https://studio.example.com/oauth2/callback",
        auto_create=False,
        auto_register_callback=False,
        identity_client=identity_client,
    )

    assert config.session_timeout_seconds == 30 * 24 * 60 * 60


def test_from_veidentity_supports_vestack_oidc_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    identity_client = Mock()
    identity_client.get_user_pool.return_value = (
        "pool-id",
        "auth.example.com",
    )
    identity_client.get_user_pool_client.return_value = (
        "client-id",
        "client-secret",
    )
    identity_client.get_user_pool_client_refresh_token_lifetime.return_value = None
    observed: list[str] = []
    monkeypatch.setenv(
        "VEIDENTITY_OIDC_BASE_URL",
        "http://{user_pool_domain}/userpool/{user_pool_uid}",
    )
    monkeypatch.setattr(
        "veadk.auth.middleware.oauth2_auth._fetch_oidc_discovery",
        lambda base_url: (
            observed.append(base_url)
            or OIDCDiscoveryConfig(
                issuer=f"{base_url}/issuer",
                authorization_endpoint=f"{base_url}/authorize",
                token_endpoint=f"{base_url}/oauth/token",
            )
        ),
    )

    OAuth2Config.from_veidentity(
        user_pool_uid="pool-id",
        client_uid="client-id",
        redirect_uri="http://studio.example.com/oauth2/callback",
        auto_create=False,
        auto_register_callback=False,
        identity_client=identity_client,
    )

    assert observed == ["http://auth.example.com/userpool/pool-id"]
