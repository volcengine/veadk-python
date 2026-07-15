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

"""Deployable API server for the PiAgent MCP example."""

from __future__ import annotations

import inspect
import logging
import os
import subprocess
import sys
from pathlib import Path

import uvicorn
import veadk
from google.adk.cli.fast_api import get_fast_api_app

AGENTS_DIR = str(Path(__file__).resolve().parent / "agents")
os.environ.setdefault("PIAGENT_BINARY", "/opt/piagent/pi/pi")
os.environ.setdefault("PIAGENT_INSTALL_DIR", "/opt/piagent")

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))
logger = logging.getLogger("uvicorn.error")


def build_app():
    app = get_fast_api_app(agents_dir=AGENTS_DIR, allow_origins=["*"], web=False)

    @app.on_event("startup")
    async def log_piagent_mcp_agentkit_startup() -> None:
        _log_piagent_agentkit_state()

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    return app


def _log_piagent_agentkit_state() -> None:
    binary = os.getenv("PIAGENT_BINARY")
    binary_source = "PIAGENT_BINARY"
    if not binary:
        install_dir = Path(
            os.getenv("PIAGENT_INSTALL_DIR", "~/.cache/veadk/piagent")
        ).expanduser()
        binary = str(install_dir / "pi" / "pi")
        binary_source = "PIAGENT_INSTALL_DIR"

    logger.info(
        "piagent MCP AgentKit startup: "
        f"python={sys.version.split()[0]} cwd={Path.cwd()} agents_dir={AGENTS_DIR}"
    )
    _log_veadk_state()
    _log_binary_state(binary, binary_source)
    _log_agent_dir_state(os.getenv("PIAGENT_AGENT_DIR"))


def _log_veadk_state() -> None:
    logger.info(
        "piagent MCP AgentKit startup: "
        f"veadk_version={getattr(veadk, '__version__', '<unknown>')} "
        f"veadk_path={inspect.getfile(veadk)}"
    )


def _log_binary_state(binary: str | None, source: str) -> None:
    if not binary:
        logger.warning("piagent MCP AgentKit startup: Pi binary is not configured")
        return

    path = Path(binary).expanduser()
    exists = path.exists()
    executable = os.access(path, os.X_OK) if exists else False
    logger.info(
        "piagent MCP AgentKit startup: "
        f"binary_source={source} binary={path} exists={exists} executable={executable}"
    )
    if not exists or not executable:
        return

    try:
        result = subprocess.run(
            [str(path), "--version"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except Exception as e:  # noqa: BLE001 - startup diagnostics only
        logger.warning(f"piagent MCP AgentKit startup: Pi version check failed: {e}")
        return

    output = (result.stdout or result.stderr).strip().splitlines()
    logger.info(
        "piagent MCP AgentKit startup: "
        f"Pi version check returncode={result.returncode} "
        f"output={output[0][:300] if output else '<empty>'}"
    )


def _log_agent_dir_state(agent_dir: str | None) -> None:
    if not agent_dir:
        logger.warning(
            "piagent MCP AgentKit startup: PIAGENT_AGENT_DIR is not configured"
        )
        return

    path = Path(agent_dir).expanduser()
    logger.info(
        "piagent MCP AgentKit startup: "
        f"agent_dir={path} exists={path.exists()} writable={os.access(path, os.W_OK)}"
    )


app = build_app()


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT)
