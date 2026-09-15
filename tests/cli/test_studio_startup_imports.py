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

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


def test_studio_startup_modules_do_not_eagerly_load_generated_cloud_models() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import importlib
import sys

for module in (
    "frontend.server.user_management.directory",
    "frontend.server.skills.reviewer_profiles",
    "veadk.cli.studio_vpc_network",
    "veadk.integrations.agentkit.studio_routes.protocol",
):
    importlib.import_module(module)

unexpected = sorted(
    name
    for name in sys.modules
    if name.startswith((
        "volcenginesdkid",
        "volcenginesdkvefaas",
        "volcenginesdkvpc",
    ))
)
if unexpected:
    raise SystemExit("generated cloud SDKs loaded during Studio startup")
if "veadk.integrations.agentkit.app" in sys.modules:
    raise SystemExit("AgentKit application loaded by a protocol-only import")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_tool_catalog_does_not_eagerly_load_branch_model_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.studio_tools.registry import build_studio_tool_registry

if "veadk.agent" in sys.modules:
    raise SystemExit("VeADK Agent loaded before Studio tool catalog construction")

registry = build_studio_tool_registry()
assert any(item["name"] == "branch_compare" for item in registry.manifests())

if "veadk.agent" in sys.modules:
    raise SystemExit("branch model runtime loaded during Studio cold start")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_tools_defer_sandbox_runtime_until_first_sandbox_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.studio_tools.registry import build_studio_tool_registry

registry = build_studio_tool_registry()
assert any(item["name"] == "branch_compare" for item in registry.manifests())

unexpected = sorted(
    name
    for name in (
        "veadk.cli.agentkit_session_metadata",
        "veadk.cli.codex_app_server",
    )
    if name in sys.modules
)
if unexpected:
    raise SystemExit("Sandbox session runtime loaded during Studio cold start")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_codex_sandbox_default_connection_factory_is_lazy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import frontend.server.studio_tools.codex_sandbox as codex_sandbox
    from frontend.server.environments.session_mounts import SessionEnvironmentMount
    from frontend.server.studio_tools.registry import StudioToolExecutionContext
    from frontend.server.studio_tools.sandbox_shell import SandboxExecutionTarget

    created_endpoints: list[str] = []
    connection = object()

    class Targets:
        async def resolve(
            self,
            mount: SessionEnvironmentMount,
            context: StudioToolExecutionContext,
        ) -> SandboxExecutionTarget:
            del mount, context
            raise AssertionError("target resolution is not a startup operation")

    def connection_factory(endpoint: str) -> object:
        created_endpoints.append(endpoint)
        return connection

    monkeypatch.setattr(
        codex_sandbox,
        "CodexAppServerSession",
        connection_factory,
    )
    delegate = codex_sandbox.CodexSandboxDelegate(Targets())

    assert created_endpoints == []
    assert delegate._connection_factory("https://sandbox.example") is connection
    assert created_endpoints == ["https://sandbox.example"]


def test_frontend_branding_defers_optional_logo_network_stack() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from veadk.cli.frontend_branding import normalize_site_title

assert normalize_site_title(None) == "AgentKit Studio"
for module in ("filetype", "httpx"):
    if module in sys.modules:
        raise SystemExit(f"optional branding dependency loaded at startup: {module}")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_logger_import_does_not_load_general_network_helpers() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from veadk.utils.logger import get_logger

assert get_logger("startup").name == "veadk.startup"
for module in ("requests", "yaml"):
    if module in sys.modules:
        raise SystemExit(f"general utility dependency loaded by logger: {module}")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_evaluation_automation_defers_model_runtime_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.evaluation_automation

if "veadk.agent" in sys.modules:
    raise SystemExit("evaluation model runtime loaded during Studio cold start")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_generated_agent_planner_defers_model_runtime_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import veadk.cli.generated_agent_planner

if "veadk.agent" in sys.modules:
    raise SystemExit("generated Agent planner loaded model runtime at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_generated_agent_mcp_defers_protocol_runtime_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import veadk.cli.generated_agent_mcp

unexpected = sorted(
    name
    for name in sys.modules
    if name == "mcp"
    or name.startswith("mcp.")
    or name == "google.adk.tools.mcp_tool"
    or name.startswith("google.adk.tools.mcp_tool.")
)
if unexpected:
    raise SystemExit("generated Agent MCP protocol runtime loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_skill_workbench_defers_agentkit_runtime_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.skills.devenv

unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "agentkit.sdk.skills.client",
        "agentkit.sdk.skills.types",
        "agentkit.sdk.tools.client",
        "agentkit.sdk.tools.types",
        "agentkit.toolkit.cli.sandbox.env_config",
        "agentkit.toolkit.cli.sandbox.sandbox_client",
        "veadk.skills.skill",
    }
)
if unexpected:
    raise SystemExit("Skill workbench AgentKit runtime loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_gateway_defers_agentkit_runtime_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.migration.gateway

unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "agentkit.sdk.tools.types",
        "agentkit.toolkit.cli.sandbox.env_config",
        "agentkit.toolkit.cli.sandbox.sandbox_client",
        "veadk.cli.agentkit_session_metadata",
        "veadk.cli.frontend_skill_creator",
    }
)
if unexpected:
    raise SystemExit("Migration Gateway AgentKit runtime loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_knowledge_routes_defer_document_extraction_stack() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.knowledge.routes

unexpected = sorted(
    name
    for name in sys.modules
    if name == "trafilatura"
    or name.startswith("trafilatura.")
    or name == "dateparser"
    or name.startswith("dateparser.")
)
if unexpected:
    raise SystemExit("web document extraction stack loaded during Studio cold start")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
