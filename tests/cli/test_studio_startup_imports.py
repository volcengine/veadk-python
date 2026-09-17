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


def test_studio_tools_defer_builtin_model_clients_until_first_call() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.studio_tools.registry import build_studio_tool_registry

registry = build_studio_tool_registry()
names = {item["name"] for item in registry.manifests()}
assert {"image_edit", "link_reader"} <= names

unexpected = sorted(
    name
    for name in sys.modules
    if name == "pydantic.v1.tools"
    or name == "volcenginesdkarkruntime"
    or name.startswith("volcenginesdkarkruntime.")
)
if unexpected:
    raise SystemExit("built-in model clients loaded during Studio cold start")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_tool_catalog_defers_builtin_execution_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import veadk.cli.studio_start
from frontend.server.studio_tools.registry import build_studio_tool_registry

registry = build_studio_tool_registry()
registered = {manifest["name"] for manifest in registry.manifests()}
required = {
    "coding",
    "image_generate",
    "run_code",
    "video_generate",
    "web_search",
}
if not required <= registered:
    raise SystemExit("Studio built-in catalog is incomplete")

unexpected = sorted(
    name
    for name in sys.modules
    if name == "google.adk.auth"
    or name.startswith("google.adk.auth.")
    or name == "google.adk.agents"
    or name.startswith("google.adk.agents.")
    or name == "google.adk.tools"
    or name.startswith("google.adk.tools.")
    or name == "veadk.tools.builtin_tools._agentkit"
    or name == "veadk.tools.builtin_tools.create_agent"
    or name.startswith("veadk.tools.builtin_tools.create_agent.")
)
if unexpected:
    raise SystemExit("built-in execution runtime loaded while building Studio catalog")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


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


def test_video_routes_defer_provider_runtime_until_first_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.video.routes import build_video_service

service = build_video_service(
    provider="volcengine",
    resolve_credentials=lambda: ("unused", "unused", None),
)
unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "frontend.server.video.client",
        "frontend.server.video.service",
        "frontend.server.video.storage",
        "veadk.auth.veauth.ark_veauth",
    }
)
if unexpected:
    raise SystemExit("video request runtime loaded during Studio startup")

assert service.capabilities().provider == "volcengine"
if "frontend.server.video.service" not in sys.modules:
    raise SystemExit("video request runtime did not load on first use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_complete_studio_app_defers_model_catalog_network_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import os
import sys
import tempfile
from unittest.mock import patch

os.environ["VOLCENGINE_ACCESS_KEY"] = "unused"
os.environ["VOLCENGINE_SECRET_KEY"] = "unused"
os.environ["_VEADK_STUDIO_LAZY_ADK_PACKAGES"] = "1"

from veadk.cli.cli_frontend import _run_frontend_server

captured = {}
with tempfile.TemporaryDirectory() as agents_dir:
    with patch("dotenv.find_dotenv", return_value=""), patch(
        "uvicorn.run",
        side_effect=lambda app, **kwargs: captured.setdefault("app", app),
    ):
        _run_frontend_server(
            agents_dir=agents_dir,
            frontend_dir=None,
            site_logo=None,
            site_title=None,
            host="127.0.0.1",
            port=8765,
            dev=True,
            vite=True,
            oauth2_user_pool=None,
            oauth2_user_pool_client=None,
            oauth2_user_pool_uid=None,
            oauth2_user_pool_client_uid=None,
            oauth2_redirect_uri=None,
            oauth2_provider=None,
            oauth2_provider_label=None,
            auth_mode="frontend",
            generated_agent_test_run_ttl=60,
            open_browser=False,
            provider="volcengine",
            studio=True,
        )

assert captured["app"] is not None
unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "frontend.server.video.client",
        "veadk.auth.veauth.ark_veauth",
        "veadk.utils.misc",
        "veadk.utils.volcengine_sign",
        "requests",
    }
)
if unexpected:
    raise SystemExit("model catalog network runtime loaded during Studio startup")

import asyncio

from frontend.server.model_catalog.routes import build_model_catalog_service

service = build_model_catalog_service(
    provider="volcengine",
    resolve_credentials=lambda: ("unused", "unused", None),
    signed_request=lambda **_kwargs: {
        "Result": {"TotalCount": 0, "Items": []},
    },
)
response = asyncio.run(service.list_api_keys())
assert response.keys == []
for expected in (
    "frontend.server.video.client",
    "veadk.utils.volcengine_sign",
    "requests",
):
    if expected not in sys.modules:
        raise SystemExit("model catalog network runtime did not load on first use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_feishu_setup_defers_qr_provider_until_first_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.feishu_bot_setup import create_feishu_bot_setup_service

service = create_feishu_bot_setup_service()
unexpected = sorted(
    name
    for name in sys.modules
    if name == "qrcode"
    or name.startswith("qrcode.")
    or name == "frontend.server.feishu_bot_setup.feishu_app_registration"
)
if unexpected:
    raise SystemExit("Feishu QR provider loaded during Studio startup")

provider = service._provider._resolve()
if type(provider).__name__ != "FeishuAppRegistrationProvider":
    raise SystemExit("Feishu QR provider did not load on first use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_update_routes_defer_updater_runtime_until_first_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import asyncio
import sys

from fastapi import FastAPI
import httpx

from veadk.cli.studio_self_update_bootstrap import (
    LazyStudioSelfUpdater,
    mount_lazy_studio_update_routes,
)

app = FastAPI()
updater = LazyStudioSelfUpdater(
    provider="volcengine",
    credential_resolver=lambda: ("unused", "unused", None),
    branding_logo=None,
)
mount_lazy_studio_update_routes(app, updater, lambda _request: None)
if "veadk.cli.studio_self_update" in sys.modules:
    raise SystemExit("Studio updater runtime loaded during route setup")

async def verify_first_request():
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get("/web/studio-update")
    assert response.status_code == 200
    assert response.json()["enabled"] is False

asyncio.run(verify_first_request())
if "veadk.cli.studio_self_update" not in sys.modules:
    raise SystemExit("Studio updater runtime did not load on first request")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_disabled_studio_route_channel_defers_request_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import os
import sys

os.environ.pop("VEADK_STUDIO_ROUTE_CHANNEL", None)

from frontend.server.studio_routes.registry import build_studio_route_registry

registry = build_studio_route_registry(provider="volcengine")
assert registry.enabled is False
unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "frontend.server.studio_routes.connector",
        "frontend.server.studio_routes.skill_catalog",
        "frontend.server.skills.repository",
        "frontend.server.skills.storage",
        "frontend.server.skills.system_spaces",
        "veadk.integrations.agentkit.studio_routes.host",
    }
)
if unexpected:
    raise SystemExit("disabled Studio route channel loaded request runtime")

os.environ["VEADK_STUDIO_ROUTE_CHANNEL"] = "skill-catalog"
enabled = build_studio_route_registry(provider="volcengine")
assert enabled.enabled is True
assert len(enabled.manifests()) == 3
if "frontend.server.studio_routes.skill_catalog" not in sys.modules:
    raise SystemExit("Studio route request runtime did not load when enabled")
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

import frontend.server.skills.devenv as devenv

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
        "agentkit.auth.errors",
        "requests",
        "veadk.skills.skill",
    }
)
if unexpected:
    raise SystemExit("Skill workbench AgentKit runtime loaded at startup")

assert devenv._is_transient_dependency_error(RuntimeError("test")) is False
if "requests" not in sys.modules or "agentkit.auth.errors" not in sys.modules:
    raise SystemExit("Skill workbench network runtime did not load on first use")
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

import frontend.server.migration.gateway as gateway

unexpected = sorted(
    name
    for name in sys.modules
    if name in {
        "agentkit.sdk.tools.types",
        "agentkit.toolkit.cli.sandbox.env_config",
        "agentkit.toolkit.cli.sandbox.sandbox_client",
        "veadk.cli.agentkit_session_metadata",
        "veadk.cli.frontend_skill_creator",
        "requests",
    }
)
if unexpected:
    raise SystemExit("Migration Gateway AgentKit runtime loaded at startup")

assert gateway._requests().__name__ == "requests"
if "requests" not in sys.modules:
    raise SystemExit("Migration Gateway network runtime did not load on first use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_migration_routes_defer_source_project_runtime_until_persistence() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.migration.routes

unexpected = sorted(
    name
    for name in sys.modules
    if name == "frontend.server.source_projects"
    or name.startswith("frontend.server.intelligent_development_projects")
    or name == "frontend.server.intelligent_development_task"
    or name == "frontend.server.sandbox_remote"
    or name == "agentkit.toolkit.cli.sandbox.sandbox_client"
)
if unexpected:
    raise SystemExit("migration source-project runtime loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_source_project_service_defers_sandbox_runtime_until_first_use() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.intelligent_development_projects.service

unexpected = sorted(
    name
    for name in sys.modules
    if name == "frontend.server.intelligent_development_task"
    or name == "frontend.server.sandbox_remote"
    or name == "veadk.cli.frontend_sandbox"
    or name == "agentkit.toolkit.cli.sandbox.sandbox_client"
)
if unexpected:
    raise SystemExit("source-project Sandbox runtime loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_environment_service_defers_generated_project_runtime_until_build() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.environments as environments

unexpected = sorted(
    name
    for name in sys.modules
    if name == "veadk.cli.generated_agent_codegen"
    or name == "veadk.cli.generated_agent_skills"
    or name == "veadk.auth.veauth.ark_veauth"
    or name == "requests"
)
if unexpected:
    raise SystemExit("generated project runtime loaded by environment composition")

assert environments._get_ark_token().__name__ == "get_ark_token"
if "veadk.auth.veauth.ark_veauth" not in sys.modules:
    raise SystemExit("environment model auth runtime did not load on first use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_intelligent_development_routes_defer_sandbox_helpers_until_first_use() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.intelligent_development_routes

unexpected = sorted(
    name
    for name in sys.modules
    if name == "frontend.server.sandbox_remote"
    or name == "veadk.cli.frontend_skill_creator"
    or name == "agentkit.toolkit.cli.sandbox.env_config"
    or name == "agentkit.toolkit.cli.sandbox.sandbox_client"
)
if unexpected:
    raise SystemExit("intelligent development Sandbox helpers loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_intelligent_development_runner_defers_sandbox_transport_until_first_use() -> (
    None
):
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from frontend.server.intelligent_development_runs import runner, shell

assert shell.RunShell is not None
for module in (
    "frontend.server.sandbox_remote",
    "agentkit.toolkit.cli.sandbox.sandbox_client",
    "requests",
):
    assert module not in sys.modules, module

transport = runner.SandboxRemoteTransport("http://127.0.0.1:1")
from frontend.server.sandbox_remote import SandboxRemoteTransport

assert isinstance(transport, SandboxRemoteTransport)
assert "agentkit.toolkit.cli.sandbox.sandbox_client" in sys.modules
assert "requests" in sys.modules
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_workspace_projects_defers_sandbox_transport_until_first_use() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.workspace_projects

unexpected = sorted(
    name
    for name in sys.modules
    if name == "frontend.server.sandbox_remote"
    or name == "agentkit.toolkit.cli.sandbox.sandbox_client"
)
if unexpected:
    raise SystemExit("workspace project Sandbox transport loaded at startup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_workspace_preview_route_setup_defers_project_sandbox_runtime() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from fastapi import FastAPI

from frontend.server.workspace_preview import mount_workspace_preview_routes

app = FastAPI()
mount_workspace_preview_routes(app, object(), lambda _request: "owner", lambda _request: "creator")

unexpected = sorted(
    name
    for name in sys.modules
    if name == "frontend.server.workspace_projects"
    or name == "frontend.server.sandbox_remote"
    or name == "agentkit.toolkit.cli.sandbox.sandbox_client"
)
if unexpected:
    raise SystemExit("workspace preview Sandbox runtime loaded during route setup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_workspace_tool_defers_agentkit_types_until_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.workspace_tool

if "agentkit.sdk.tools.types" in sys.modules:
    raise SystemExit("workspace Tool SDK types loaded during route setup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_agent_review_repository_defers_runtime_sdk_until_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import frontend.server.agent_reviews.repository

unexpected = sorted(
    name
    for name in sys.modules
    if name == "agentkit.sdk.runtime.types"
    or name == "agentkit.sdk.runtime.client"
)
if unexpected:
    raise SystemExit("Agent review Runtime SDK loaded during route setup")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_entrypoint_defers_unused_google_adk_package_exports() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

import veadk.cli.studio_start
from google.adk.cli.fast_api import get_fast_api_app

assert callable(get_fast_api_app)
unexpected = sorted(
    name
    for name in sys.modules
    if name == "google.adk.cli.cli_tools_click"
    or name == "google.adk.workflow._workflow"
    or name == "google.adk.workflow._graph"
    or name == "google.adk.workflow._function_node"
    or name == "google.adk.evaluation"
    or name.startswith("google.adk.evaluation.")
)
if unexpected:
    raise SystemExit("unused Google ADK package exports loaded by Studio entrypoint")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_fast_api_defers_evaluation_storage_until_first_use() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys
import tempfile
from pathlib import Path

from veadk.cli.studio_start import studio_fast_api_factory

with tempfile.TemporaryDirectory() as agents_dir:
    app_dir = Path(agents_dir, "agent-test")
    app_dir.mkdir()
    app = studio_fast_api_factory()(agents_dir=agents_dir, web=False)
    assert any(route.path == "/list-apps" for route in app.routes)
    if "google.adk.evaluation" in sys.modules:
        raise SystemExit("evaluation storage loaded while constructing Studio app")

    fast_api = sys.modules["google.adk.cli.fast_api"]
    manager = fast_api.LocalEvalSetsManager(agents_dir=agents_dir)
    assert manager.list_eval_sets("agent-test") == []
    if "google.adk.evaluation.local_eval_sets_manager" not in sys.modules:
        raise SystemExit("evaluation storage not loaded for a real request")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_fast_api_defers_genai_models_until_first_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys
import tempfile
from pathlib import Path

from veadk.cli.studio_start import studio_fast_api_factory

with tempfile.TemporaryDirectory() as agents_dir:
    Path(agents_dir, "agent-test").mkdir()
    app = studio_fast_api_factory()(agents_dir=agents_dir, web=False)
    assert any(route.path == "/run_sse" for route in app.routes)

    genai_types = sys.modules["google.genai.types"]
    real_module_loaded = getattr(
        genai_types,
        "_veadk_real_module_loaded",
        None,
    )
    if real_module_loaded is None or real_module_loaded():
        raise SystemExit("Google GenAI models loaded while constructing Studio app")

    genai_models = sys.modules["google.genai.models"]
    real_models_module_loaded = getattr(
        genai_models,
        "_veadk_real_module_loaded",
        None,
    )
    if real_models_module_loaded is None or real_models_module_loaded():
        raise SystemExit("Google GenAI client loaded while constructing Studio app")

    from google.adk.cli.api_server import RunAgentRequest

    request = RunAgentRequest.model_validate(
        {
            "app_name": "agent-test",
            "user_id": "user-test",
            "session_id": "session-test",
            "new_message": {
                "role": "user",
                "parts": [{"text": "hello"}],
            },
        }
    )
    assert type(request.new_message).__name__ == "Content"
    assert request.new_message.parts[0].text == "hello"
    dumped = request.model_dump(mode="json")
    assert dumped["new_message"]["parts"][0]["text"] == "hello"
    if not real_module_loaded():
        raise SystemExit("Google GenAI models not loaded for a real request")

    from google.adk.tools.function_tool import FunctionTool

    def sample_tool(value: str) -> str:
        return value

    declaration = FunctionTool(sample_tool)._get_declaration()
    assert declaration.parameters_json_schema["properties"]["value"] == {
        "title": "Value",
        "type": "string",
    }

    from google.adk.telemetry import _experimental_semconv
    from google.adk.telemetry import tracing

    assert isinstance(
        tracing._instrumented_with_opentelemetry_instrumentation_google_genai(),
        bool,
    )
    transformed = _experimental_semconv.transformers.t_contents("hello")
    assert transformed[0].parts[0].text == "hello"
    if not real_models_module_loaded():
        raise SystemExit("Google GenAI client not loaded for real telemetry use")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_studio_deferred_genai_models_support_openapi_first_use() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys
import tempfile
from pathlib import Path

from veadk.cli.studio_start import studio_fast_api_factory

with tempfile.TemporaryDirectory() as agents_dir:
    Path(agents_dir, "agent-test").mkdir()
    app = studio_fast_api_factory()(agents_dir=agents_dir, web=False)
    genai_types = sys.modules["google.genai.types"]
    real_module_loaded = genai_types._veadk_real_module_loaded
    if real_module_loaded():
        raise SystemExit("Google GenAI models loaded before OpenAPI generation")

    schema = app.openapi()
    assert "/run_sse" in schema["paths"]
    assert schema["components"]["schemas"]["RunAgentRequest"]
    if not real_module_loaded():
        raise SystemExit("Google GenAI models not loaded for OpenAPI generation")
"""

    subprocess.run(
        [sys.executable, "-c", script],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )


def test_session_metadata_defers_agentkit_models_until_first_request() -> None:
    root = Path(__file__).resolve().parents[2]
    script = """
import sys

from veadk.cli import agentkit_session_metadata as metadata

assert metadata.session_display_name_metadata_value("Studio") == "Studio"
if "agentkit.sdk.tools.types" in sys.modules:
    raise SystemExit("AgentKit Session models loaded during Studio route setup")

request = metadata.build_list_sessions_request(
    tool_id="tool-test",
    max_results=10,
    username="owner-test",
)
assert request is not None
if "agentkit.sdk.tools.types" not in sys.modules:
    raise SystemExit("AgentKit Session models not loaded for a real request")
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
