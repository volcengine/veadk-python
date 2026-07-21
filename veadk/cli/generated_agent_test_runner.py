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

"""Isolated subprocess entry point for generated-agent test runs.

The parent ``veadk frontend`` process starts this module in a separate Python
process and points it at a temporary generated project. User-generated
``agent.py`` code is loaded only in this child process, never in the parent
frontend server.
"""

from __future__ import annotations

import argparse
from importlib import import_module
from types import ModuleType
from typing import Any


_ADK_SERVER_STATE_KEY = "_veadk_adk_server"


def _looks_like_adk_server(value: object) -> bool:
    return all(
        hasattr(value, attr)
        for attr in (
            "artifact_service",
            "session_service",
            "memory_service",
            "credential_service",
            "current_app_name_ref",
            "auto_create_session",
        )
    )


def _find_adk_server(app: Any) -> object | None:
    """Find the ADK ApiServer captured by the default route closures."""
    for route in getattr(app.router, "routes", []) or []:
        endpoint = getattr(route, "endpoint", None)
        for cell in getattr(endpoint, "__closure__", None) or ():
            try:
                value = cell.cell_contents
            except ValueError:
                continue
            if _looks_like_adk_server(value):
                return value
    return None


def _bind_adk_server_services(app: Any) -> None:
    """Expose ADK services in the shape generated dynamic_a2a.py expects."""
    server = _find_adk_server(app)
    if server is None:
        return
    setattr(app.state, _ADK_SERVER_STATE_KEY, server)
    setattr(
        app,
        "_tmpl_attrs",
        {
            **getattr(app, "_tmpl_attrs", {}),
            "app_name": getattr(server, "default_app_name", None),
            "current_app_name_ref": getattr(server, "current_app_name_ref", None),
            "artifact_service": getattr(server, "artifact_service", None),
            "session_service": getattr(server, "session_service", None),
            "memory_service": getattr(server, "memory_service", None),
            "credential_service": getattr(server, "credential_service", None),
            "auto_create_session": getattr(server, "auto_create_session", False),
        },
    )


def _import_dynamic_a2a_helper(app_name: str) -> ModuleType | None:
    """Import the optional generated helper from either supported package layout."""
    module_names = (f"{app_name}.dynamic_a2a", f"agents.{app_name}.dynamic_a2a")
    for module_name in module_names:
        try:
            return import_module(module_name)
        except ModuleNotFoundError as exc:
            if exc.name != module_name:
                raise
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a temporary generated agent")
    parser.add_argument("--agents-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", required=True, type=int)
    args = parser.parse_args()

    import uvicorn
    from google.adk.cli.fast_api import get_fast_api_app

    app = get_fast_api_app(agents_dir=args.agents_dir, web=False)
    _bind_adk_server_services(app)

    # Generated projects with A2A center include a helper that overrides /run and
    # /run_sse so each debug turn gets registry-discovered remote_a2a_* tools.
    from google.adk.apps.app import App
    from google.adk.cli.utils.agent_loader import AgentLoader

    loader = AgentLoader(args.agents_dir)
    apps = loader.list_agents()
    if len(apps) == 1:
        agent_or_app = loader.load_agent(apps[0])
        root_agent = (
            agent_or_app.root_agent if isinstance(agent_or_app, App) else agent_or_app
        )
        helper = _import_dynamic_a2a_helper(apps[0])
        if helper is not None:
            helper.enable_dynamic_a2a_tools(app, root_agent)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
