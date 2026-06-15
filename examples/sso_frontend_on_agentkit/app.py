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

"""Deployable entry point: VeADK web UI (A2UI) behind VeIdentity SSO, on AgentKit.

Serves the bundled web UI plus the ADK agent API for the agents under ``./agents``
and protects them with VeIdentity OAuth2 single sign-on. SSO is configured purely
through runtime environment variables (see README). AgentKit runs this container
with ``python -m app`` on port 8000.

Two adaptations make it work behind the AgentKit gateway (which authenticates every
request with the runtime key in the ``Authorization`` header and forwards that header
to the container):

1. ``_StripGatewayAuth`` removes the gateway key from ``Authorization`` before the SSO
   middleware runs, so SSO falls back to its session cookie instead of trying to decode
   the opaque key as a user JWT ("Invalid JWT format"). A genuine user JWT is preserved.
2. The served ``index.html`` forwards the page querystring onto its ``/assets/*`` URLs,
   so that if the gateway is configured to take the key from the query string, the
   browser's subresource requests carry it too.

Everything else comes from the pip-installed ``veadk-python`` (>= 0.5.39).
"""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit

import uvicorn
import veadk
from fastapi import Request
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

AGENTS_DIR = os.path.abspath(str(Path(__file__).resolve().parent / "agents"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
WEBUI = Path(veadk.__file__).resolve().parent / "webui"

app = get_fast_api_app(agents_dir=AGENTS_DIR, allow_origins=[], web=False)


@app.get("/ping")
def ping() -> dict[str, str]:
    return {"status": "ok"}


# ---- SSO: VeIdentity user pool (config from runtime env) ----
redirect_uri = (
    os.getenv("OAUTH2_REDIRECT_URI") or f"http://{HOST}:{PORT}/oauth2/callback"
)
oauth2_config = OAuth2Config.from_veidentity(
    user_pool_uid=os.environ["OAUTH2_USER_POOL_ID"],
    client_uid=os.environ["OAUTH2_USER_POOL_CLIENT_ID"],
    redirect_uri=redirect_uri,
)
# Secure cookies over HTTPS (runtime), plain over local HTTP.
oauth2_config.cookie_secure = redirect_uri.lower().startswith("https://")
origin = urlsplit(redirect_uri)
oauth2_config.logout_redirect_url = f"{origin.scheme}://{origin.netloc}/"
oauth2_config.end_session_url = None

providers = [
    {"id": "veidentity", "label": "火山引擎 Identity", "loginUrl": "/oauth2/login"}
]


@app.get("/web/auth-config")
async def _web_auth_config() -> dict:
    return {"providers": providers}


# Protect the API; exempt the SPA shell, assets, and the login-config endpoint so
# the app can load and render its own login page when unauthenticated.
setup_oauth2(
    app,
    oauth2_config,
    exempt_paths={"/", "/index.html", "/favicon.ico", "/web/auth-config", "/ping"},
    exempt_prefixes={"/assets", "/skillhub"},
)

# ---- Serving with querystring injection ----
_index_html = (WEBUI / "index.html").read_text(encoding="utf-8")
_ASSET_REF = re.compile(r'((?:src|href)=")(/[^"?]+)(")')


def _render_index(request: Request) -> HTMLResponse:
    qs = request.url.query
    if not qs:
        return HTMLResponse(_index_html)
    html = _ASSET_REF.sub(
        lambda m: f"{m.group(1)}{m.group(2)}?{qs}{m.group(3)}", _index_html
    )
    return HTMLResponse(html)


app.mount("/assets", StaticFiles(directory=str(WEBUI / "assets")), name="assets")


@app.get("/")
async def _spa_root(request: Request):
    return _render_index(request)


# SPA fallback: real static files as-is, otherwise the injected HTML shell.
# Registered last so it never shadows the API routes above.
@app.get("/{path:path}")
async def _spa_fallback(path: str, request: Request):
    candidate = WEBUI / path
    if path and candidate.is_file():
        return FileResponse(str(candidate))
    return _render_index(request)


class _StripGatewayAuth:
    """Drop a non-JWT ``Authorization`` header before the SSO middleware sees it.

    Behind the AgentKit gateway the runtime key rides in ``Authorization: Bearer
    <key>`` and the gateway forwards that header to this container. The SSO
    middleware treats any ``Authorization`` header as the user's access token and
    tries to decode it as a JWT — the opaque gateway key fails with "Invalid JWT
    format", and the session cookie is never consulted.

    The gateway has already authenticated the request upstream, so the key is of
    no use here. Remove it when it is not a well-formed JWT (3 dot-separated
    parts), letting the SSO middleware fall back to the session cookie. A genuine
    user JWT (e.g. from a programmatic client) is left untouched.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = scope.get("headers", [])
            auth = next((v for k, v in headers if k == b"authorization"), None)
            if auth is not None:
                value = auth.split(b" ", 1)[1] if b" " in auth else auth
                if len(value.split(b".")) != 3:  # not a JWT -> gateway key
                    scope = {
                        **scope,
                        "headers": [
                            (k, v) for k, v in headers if k != b"authorization"
                        ],
                    }
        await self.app(scope, receive, send)


asgi_app = _StripGatewayAuth(app)


if __name__ == "__main__":
    uvicorn.run(asgi_app, host=HOST, port=PORT)
