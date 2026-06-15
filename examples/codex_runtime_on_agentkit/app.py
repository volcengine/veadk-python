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

"""Deployable agent API server for the codex-runtime demo.

Serves the Google ADK FastAPI app (``/list-apps``, ``/run_sse``, sessions, ...)
for the agents under ``./agents``. AgentKit runs this container with
``python -m app`` on port 8000. Locally it is equivalent to
``veadk frontend --dev --agents-dir examples/codex_runtime_on_agentkit/agents``.
"""

import os
from pathlib import Path

import uvicorn
from google.adk.cli.fast_api import get_fast_api_app

# Agent apps live next to this file; each subdir exposes a `root_agent`.
AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))


def build_app():
    app = get_fast_api_app(agents_dir=AGENTS_DIR, web=False)

    # A simple health endpoint for the runtime's liveness checks.
    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
