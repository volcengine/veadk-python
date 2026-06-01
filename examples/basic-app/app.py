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

"""Deployable front+back server for the basic-app demo.

One process serves BOTH:
- the agent API (Google ADK FastAPI app: /list-apps, /run_sse, sessions, ...)
- the A2UI web frontend, which ships inside the installed veadk package at
  `veadk/webui` (so a plain `pip install veadk-python[a2ui]` is enough — there
  is nothing to bundle into this project).

AgentKit runs this container with `python -m app` on port 8000, which is exactly
what this module does. Locally it is equivalent to `veadk frontend
--agents-dir examples/basic-app/agents`.
"""

import os
from pathlib import Path

import uvicorn
import veadk
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app

# Agent apps live next to this file; each subdir exposes a `root_agent`.
AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")

# The built UI shipped with the veadk package (committed at veadk/webui).
WEBUI_DIR = Path(veadk.__file__).resolve().parent / "webui"

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


def build_app():
    app = get_fast_api_app(agents_dir=AGENTS_DIR, web=False)

    # A simple health endpoint for the runtime's liveness checks.
    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    if (WEBUI_DIR / "index.html").is_file():
        # Mount last so it doesn't shadow the API routes registered above.
        app.mount("/", StaticFiles(directory=str(WEBUI_DIR), html=True), name="webui")
    return app


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
