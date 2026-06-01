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

"""`veadk frontend` -- serve the A2UI web UI together with the agent API server.

This is a self-contained launcher built on Google ADK's supported
`get_fast_api_app`. In the default mode it serves both the agent API
(`/list-apps`, `/run_sse`, sessions, ...) and the built React UI from a single
process, so there is no cross-origin setup. In `--dev` mode it serves only the
API (with CORS allowing the Vite dev server) for React hot reload.
"""

import os

from pathlib import Path

import click

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

DEV_SERVER_ORIGIN = "http://localhost:5173"

# Built UI shipped inside the package (output of `npm run build`).
PACKAGED_WEBUI = Path(__file__).resolve().parent.parent / "webui"


def _resolve_frontend_dir(arg: str | None) -> Path:
    """Resolve the built-UI directory.

    Priority: explicit ``--frontend-dir`` > packaged ``veadk/webui`` (works for
    pip-installed users) > ``./frontend/dist`` relative to cwd (dev fallback).
    """
    if arg:
        return Path(arg).resolve()
    if (PACKAGED_WEBUI / "index.html").is_file():
        return PACKAGED_WEBUI
    return (Path.cwd() / "frontend" / "dist").resolve()


@click.command()
@click.option(
    "--agents-dir",
    default="examples",
    show_default=True,
    help="Directory containing agent apps (each subdir exposes a `root_agent`).",
)
@click.option(
    "--frontend-dir",
    default=None,
    help="Override the built React UI directory. Defaults to the UI shipped "
    "with the package (veadk/webui), falling back to ./frontend/dist.",
)
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8000, show_default=True, type=int)
@click.option(
    "--dev",
    is_flag=True,
    default=False,
    help=(
        "Dev mode: serve API only and allow CORS from the Vite dev server "
        f"({DEV_SERVER_ORIGIN}). Run `npm run dev` in ./frontend alongside this."
    ),
)
@click.option(
    "--oauth2-user-pool",
    default=None,
    help="VeIdentity User Pool name. When set, enables SSO: unauthenticated "
    "browsers are redirected to login and the UI uses the signed-in user.",
)
@click.option(
    "--oauth2-user-pool-client",
    default=None,
    help="VeIdentity User Pool client name (required with --oauth2-user-pool).",
)
@click.option(
    "--oauth2-redirect-uri",
    default=None,
    help="OAuth2 redirect URI. Defaults to http://{host}:{port}/oauth2/callback.",
)
@click.option(
    "--oauth2-provider",
    default="veidentity",
    show_default=True,
    help="SSO provider id shown on the login page (e.g. veidentity, github, "
    "google). Drives the login button's label/icon.",
)
@click.option(
    "--oauth2-provider-label",
    default=None,
    help="Display label for the SSO login button (defaults to a name derived "
    "from --oauth2-provider).",
)
def frontend(
    agents_dir: str,
    frontend_dir: str | None,
    host: str,
    port: int,
    dev: bool,
    oauth2_user_pool: str | None,
    oauth2_user_pool_client: str | None,
    oauth2_redirect_uri: str | None,
    oauth2_provider: str,
    oauth2_provider_label: str | None,
) -> None:
    """Launch the A2UI web UI backed by the ADK agent API server."""
    from google.adk.cli.fast_api import get_fast_api_app

    agents_dir = os.path.abspath(agents_dir)
    allow_origins = [DEV_SERVER_ORIGIN] if dev else []

    app = get_fast_api_app(
        agents_dir=agents_dir,
        allow_origins=allow_origins,
        web=False,  # we serve our own UI, not the bundled ADK dev UI
    )

    if oauth2_user_pool and oauth2_user_pool_client:
        from veadk.auth.middleware.oauth2_auth import OAuth2Config, setup_oauth2

        redirect_uri = oauth2_redirect_uri or f"http://{host}:{port}/oauth2/callback"
        oauth2_config = OAuth2Config.from_veidentity(
            user_pool_name=oauth2_user_pool,
            client_name=oauth2_user_pool_client,
            redirect_uri=redirect_uri,
        )
        # Allow cookies over http for local/non-TLS serving.
        oauth2_config.cookie_secure = False

        # Expose the configured provider(s) to the login page (unauthenticated).
        label = oauth2_provider_label or oauth2_provider.replace("_", " ").title()
        providers = [
            {"id": oauth2_provider, "label": label, "loginUrl": "/oauth2/login"}
        ]

        @app.get("/web/auth-config")
        async def _web_auth_config():
            return {"providers": providers}

        # Protect the API but exempt the SPA shell + this config endpoint so the
        # app can load and render its own login page when not signed in.
        setup_oauth2(
            app,
            oauth2_config,
            exempt_paths={"/", "/index.html", "/favicon.ico", "/web/auth-config"},
            exempt_prefixes={"/assets"},
        )
        logger.info(
            f"OAuth2 SSO enabled (provider={oauth2_provider}, "
            f"user_pool={oauth2_user_pool}, client={oauth2_user_pool_client}, "
            f"redirect_uri={redirect_uri})"
        )

    if dev:
        logger.info(
            f"A2UI dev mode: API on http://{host}:{port}, "
            f"run `cd frontend && npm run dev` and open {DEV_SERVER_ORIGIN}"
        )
    else:
        from fastapi.staticfiles import StaticFiles

        webui = _resolve_frontend_dir(frontend_dir)
        if not (webui / "index.html").is_file():
            raise click.ClickException(
                f"Built UI not found at {webui}. Build it with: "
                "cd frontend && npm install && npm run build "
                "(or use --dev for the Vite dev server)."
            )
        # Mount last so it doesn't shadow the API routes registered above.
        app.mount("/", StaticFiles(directory=str(webui), html=True), name="frontend")
        logger.info(
            f"A2UI UI + API serving on http://{host}:{port} (UI: {webui}, agents: {agents_dir})"
        )

    import uvicorn

    uvicorn.run(app, host=host, port=port)
