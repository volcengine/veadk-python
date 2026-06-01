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
def frontend(
    agents_dir: str,
    frontend_dir: str | None,
    host: str,
    port: int,
    dev: bool,
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
