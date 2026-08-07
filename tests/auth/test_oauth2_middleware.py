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

import time
from urllib.parse import parse_qs, urlparse

from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from veadk.auth.middleware.oauth2_auth import (
    OAuth2Config,
    OAuth2Session,
    setup_oauth2,
)


def test_browser_login_returns_to_relative_target_behind_http_proxy(
    monkeypatch,
) -> None:
    async def workspace(_request):
        return PlainTextResponse("workspace")

    app = Starlette(routes=[Route("/workspace", workspace)])
    handler = setup_oauth2(
        app,
        OAuth2Config(
            authorize_url="https://identity.example.com/authorize",
            token_url="https://identity.example.com/token",
            client_id="client-id",
            client_secret="client-secret",
            redirect_uri="https://studio.example.com/oauth2/callback",
            cookie_secure=True,
        ),
    )

    async def exchange_code_for_token(_code, code_verifier=None):
        return OAuth2Session(
            access_token="access-token",
            expires_at=time.time() + 3600,
            user_info={"sub": "user-1"},
        )

    monkeypatch.setattr(handler, "exchange_code_for_token", exchange_code_for_token)

    with TestClient(app, base_url="http://studio.internal") as client:
        login = client.get(
            "/workspace?mode=create&source=existing",
            follow_redirects=False,
        )
        assert login.status_code == 302
        state = parse_qs(urlparse(login.headers["location"]).query)["state"][0]

        callback = client.get(
            f"/oauth2/callback?code=authorization-code&state={state}",
            follow_redirects=False,
        )

    assert callback.status_code == 302
    assert callback.headers["location"] == "/workspace?mode=create&source=existing"
    set_cookie_headers = callback.headers.get_list("set-cookie")
    assert {header.split("=", 1)[0] for header in set_cookie_headers} == {
        "veadk_session",
        "veadk_user_id",
    }
    assert all("Secure" in header for header in set_cookie_headers)
