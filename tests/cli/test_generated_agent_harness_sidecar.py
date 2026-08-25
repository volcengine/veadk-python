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

import pytest
from pydantic import ValidationError

from veadk.cli.generated_agent_codegen import (
    AgentDraft,
    debug_runtime_env_from_draft,
    generate_project_from_draft,
)
from veadk.extensions.harness import sidecar


def _files(draft: AgentDraft) -> dict[str, str]:
    project = generate_project_from_draft(draft)
    return {item.path: item.content for item in project.files}


def test_disabled_draft_keeps_the_standard_generated_project(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_sidecar_runtime_api",
        lambda: pytest.fail(
            "project generation must not load the Sidecar runtime integration"
        ),
    )
    files = _files(AgentDraft(name="plain-agent"))

    assert "harness-sidecar" not in files["requirements.txt"]
    assert "agentkit-sdk-python==0.8.4" in files["requirements.txt"]
    assert "agentkit-sdk-python==0.8.1" not in files["requirements.txt"]
    assert "google-adk==2.1.0" in files["requirements.txt"]
    assert "mcp==1.26.0" not in files["requirements.txt"]
    assert "main.py" not in files
    assert "HarnessExtension" not in files["app.py"]
    assert "HarnessExtension" not in files["agents/plain_agent/agent.py"]


def test_selected_component_generates_extra_app_plugins_and_close_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        sidecar,
        "_sidecar_runtime_api",
        lambda: pytest.fail(
            "project generation must not load the Sidecar runtime integration"
        ),
    )
    files = _files(
        AgentDraft.model_validate(
            {
                "name": "sidecar-agent",
                "harnessSidecar": {
                    "componentOverrides": {"context_engine": True},
                },
            }
        )
    )

    requirements = files["requirements.txt"]
    app_py = files["app.py"]
    main_py = files["main.py"]
    agent_py = files["agents/sidecar_agent/agent.py"]
    assert "veadk-python[harness-sidecar]" in requirements
    assert "agentkit-sdk-python==0.8.1" in requirements
    assert "agentkit-sdk-python==0.8.4" not in requirements
    assert "google-adk==2.1.0" in requirements
    assert requirements.splitlines().count("mcp==1.26.0") == 1
    assert "bytedance-agentkit-harness-sidecar" not in requirements
    assert "HarnessExtension.from_env()" in agent_py
    assert "plugins=harness_extension.plugins()" in agent_py
    assert "app=agent_app" in app_py
    assert "harness_extension=harness_extension" in app_py
    assert "from app import app" in main_py
    assert "from veadk.integrations.agentkit import run_agentkit_app" in main_py
    assert "run_agentkit_app(app)" in main_py
    compile(main_py, "main.py", "exec")
    assert "HARNESS_SIDECAR_ENABLED=true" in files[".env.example"]


def test_mcp_resilience_constructs_toolsets_after_sidecar_gateway_binding() -> None:
    files = _files(
        AgentDraft.model_validate(
            {
                "name": "sidecar-mcp-agent",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.test/orders/mcp",
                        "authTokenEnv": "MCP_ORDERS_TOKEN",
                    },
                    {
                        "name": "inventory",
                        "transport": "http",
                        "url": "https://mcp.example.test/inventory/mcp",
                        "authTokenEnv": "MCP_INVENTORY_TOKEN",
                    },
                ],
                "harnessSidecar": {
                    "componentOverrides": {"mcp_resilience": True},
                },
            }
        )
    )

    agent_py = files["agents/sidecar_mcp_agent/agent.py"]
    assert agent_py.index("HarnessExtension.from_env()") < agent_py.index("MCPToolset(")
    assert "def _managed_mcp_connection(index: int)" in agent_py
    assert 'os.environ.get("MCP_URLS", "")' in agent_py
    assert 'os.environ.get("MCP_API_KEY", "")' in agent_py
    assert "httpx_client_factory=managed_mcp_http_client_factory" in agent_py
    assert "timeout=30.0" in agent_py
    assert "sse_read_timeout=300.0" in agent_py
    assert "connection_params=_managed_mcp_connection(0)" in agent_py
    assert "connection_params=_managed_mcp_connection(1)" in agent_py
    assert "MCP gateway endpoint count does not match" in agent_py
    compile(agent_py, "agent.py", "exec")


def test_plain_http_mcp_tool_keeps_direct_connection_without_sidecar_gateway() -> None:
    files = _files(
        AgentDraft.model_validate(
            {
                "name": "plain-mcp-agent",
                "mcpTools": [
                    {
                        "name": "orders",
                        "transport": "http",
                        "url": "https://mcp.example.test/orders/mcp",
                        "authTokenEnv": "MCP_ORDERS_TOKEN",
                    }
                ],
            }
        )
    )

    agent_py = files["agents/plain_mcp_agent/agent.py"]
    assert "_managed_mcp_connection" not in agent_py
    assert "managed_mcp_http_client_factory" not in agent_py
    assert "timeout=30.0" not in agent_py
    assert "sse_read_timeout=300.0" not in agent_py
    assert 'url="https://mcp.example.test/orders/mcp"' in agent_py
    assert 'os.environ["MCP_ORDERS_TOKEN"]' in agent_py


def test_ops_profile_is_preserved_in_generated_public_configuration() -> None:
    draft = AgentDraft.model_validate(
        {
            "name": "ops-agent",
            "harnessSidecar": {
                "profile": "ops",
                "componentOverrides": {
                    component_id: True
                    for component_id in sidecar.STUDIO_HARNESS_COMPONENT_IDS
                },
            },
        }
    )

    assert draft.harnessSidecar is not None
    assert draft.harnessSidecar.profile == "ops"
    assert "HARNESS_PROFILE=ops" in _files(draft)[".env.example"]


def test_ark_runtime_env_includes_current_and_legacy_model_names() -> None:
    env = debug_runtime_env_from_draft(
        AgentDraft(name="sidecar-agent", modelName="test-model")
    )

    assert env["MODEL_AGENT_NAME"] == "test-model"
    assert env["MODEL_NAME"] == "test-model"


def test_generated_intent_rejects_sql_readonly_as_a_user_option() -> None:
    with pytest.raises(ValidationError, match="sql_readonly"):
        AgentDraft.model_validate(
            {
                "name": "invalid",
                "harnessSidecar": {
                    "componentOverrides": {"sql_readonly": True},
                },
            }
        )
