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

"""Offline regressions for registry-backed A2A deployment with Sidecar off."""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.cli.test_studio_rbac import (
    _create_studio_app,
    _runtime,
    _runtime_with_public_endpoint,
    _RuntimeJsonResponse,
)
from veadk.cli.generated_agent_codegen import AgentDraft, generate_project_from_draft
from veadk.cli.legacy_runtime_recovery import (
    LegacyRecoveryError,
    apply_source_preserving_edits,
    build_sidecar_mcp_servers_json,
    mcp_editor_draft_without_credentials,
    mcp_reuse_supplied_credentials,
)


def _registry_entry() -> dict[str, Any]:
    # Studio's A2A selector configures discovery on its parent, not a named Agent.
    return {
        "name": "",
        "agentType": "a2a",
        "a2aRegistry": {"enabled": True, "registrySpaceId": "offline-space"},
        "mcpTools": [],
    }


def test_a2a_registry_entries_are_not_mcp_agent_identities() -> None:
    draft = {"name": "root_agent", "subAgents": [_registry_entry()]}
    assert (
        mcp_reuse_supplied_credentials(
            published_draft=draft,
            edited_draft=draft,
            published_reference_values={},
            reuse_requests=(),
        )
        == ()
    )
    assert (
        json.loads(build_sidecar_mcp_servers_json(draft=draft, secret_values={})) == []
    )


def test_a2a_registry_inactive_mcp_fields_are_still_sanitized() -> None:
    entry = _registry_entry()
    entry["mcpTools"] = [{"authToken": "offline-inactive-secret"}]
    draft = {"name": "root_agent", "subAgents": [entry]}
    sanitized = mcp_editor_draft_without_credentials(draft)
    assert "offline-inactive-secret" not in json.dumps(sanitized)
    assert entry["mcpTools"][0]["authToken"] == "offline-inactive-secret"


def test_a2a_registry_does_not_relax_local_agent_identity_or_source_preservation() -> (
    None
):
    for child in ({"name": "", "agentType": "llm"}, {"name": "root_agent"}):
        with pytest.raises(LegacyRecoveryError, match="agent_identity_invalid"):
            mcp_reuse_supplied_credentials(
                published_draft={"name": "root_agent"},
                edited_draft={"name": "root_agent", "subAgents": [child]},
                published_reference_values={},
                reuse_requests=(),
            )
    with pytest.raises(LegacyRecoveryError):
        apply_source_preserving_edits(
            {"name": "root_agent"},
            {"name": "root_agent", "subAgents": [_registry_entry()]},
        )


@pytest.mark.parametrize("provider", ["byteplus", "volcengine"])
@pytest.mark.parametrize("operation", ["create", "add-registry", "retain-registry"])
def test_a2a_registry_deployment_without_sidecar(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: str,
    operation: str,
) -> None:
    from agentkit.sdk.runtime.client import AgentkitRuntimeClient

    region = "ap-southeast-1" if provider == "byteplus" else "cn-shanghai"
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "test-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "test-sk")
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "offline-model-key")
    monkeypatch.setattr(
        "agentkit.utils.template_utils.render_template", lambda _: "offline"
    )
    monkeypatch.setattr(
        "veadk.auth.veauth.ark_veauth.get_ark_token", lambda **_: "offline-model-key"
    )
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._sync_volcengine_runtime_tags", lambda **_: None
    )
    # Always exercise asynchronous preparation, independent of CI scheduling.
    monkeypatch.setattr(
        "veadk.cli.cli_frontend._RUNTIME_UPDATE_CAPABILITY_INITIAL_WAIT_SECONDS",
        0.0,
    )
    runtime = _runtime_with_public_endpoint(_runtime("offline-runtime", "developer"))
    runtime.current_version_number = 3
    runtime.status = "Ready"
    runtime.role_name = "runtime-role"
    runtime.artifact_url = ""
    runtime.envs = []
    published: dict[str, Any] = {
        "name": "root_agent",
        "description": "Offline A2A regression",
        "instruction": "Use agent discovery.",
        "cloudProvider": provider,
        "subAgents": [
            {"name": "worker", "instruction": "Help the root.", "subAgents": []}
        ],
    }
    if operation == "retain-registry":
        published["subAgents"][0]["subAgents"] = [_registry_entry()]
    requested = copy.deepcopy(published)
    requested["subAgents"][0]["subAgents"] = [_registry_entry()]
    captured: list[dict[str, Any]] = []

    def get_runtime(_self: Any, request: Any) -> Any:
        assert request.runtime_id == runtime.runtime_id
        return runtime

    monkeypatch.setattr(AgentkitRuntimeClient, "get_runtime", get_runtime)

    class RuntimeClient:
        def __init__(self, **_kwargs: Any) -> None:
            pass

        async def __aenter__(self) -> "RuntimeClient":
            return self

        async def __aexit__(self, *_args: Any) -> None:
            pass

        async def request(self, _method: str, url: str, **_kwargs: Any) -> Any:
            if url.endswith("/list-apps"):
                return _RuntimeJsonResponse(["root_agent"])
            assert url.endswith("/web/agent-info/root_agent")
            return _RuntimeJsonResponse({"name": "root_agent", "draft": published})

    monkeypatch.setattr("httpx.AsyncClient", RuntimeClient)

    def launch(*, config_file: str, **_kwargs: Any) -> Any:
        captured.append(yaml.safe_load(Path(config_file).read_text()))
        runtime.current_version_number = 4
        return SimpleNamespace(
            success=True,
            error=None,
            deploy_result=SimpleNamespace(
                endpoint_url="https://runtime.example.test",
                metadata={
                    "runtime_id": runtime.runtime_id,
                    "runtime_name": runtime.name,
                },
            ),
        )

    monkeypatch.setattr("agentkit.toolkit.sdk.launch", launch)
    project = generate_project_from_draft(AgentDraft.model_validate(requested))
    python_files = [item.content for item in project.files if item.path.endswith(".py")]
    assert any("build_a2a_registry_tools(" in content for content in python_files)
    for content in python_files:
        compile(content, "generated.py", "exec")
    app = _create_studio_app(
        monkeypatch, tmp_path, developers="developer", provider=provider
    )
    headers = {"X-VeADK-Local-User": "developer"}
    payload: dict[str, Any] = {
        "name": "root_agent",
        "draft": requested,
        "files": [item.model_dump() for item in project.files],
        "createEvaluationSets": False,
        "config": {"region": region},
        "harnessSidecar": {"enabled": False, "componentOverrides": {}},
    }
    with TestClient(app) as client:
        if operation != "create":
            params = {
                "runtimeId": runtime.runtime_id,
                "region": region,
                "appName": "root_agent",
            }
            capability = client.get(
                "/web/runtime-update-capability",
                headers=headers,
                params=params,
            )
            assert capability.status_code == 202
            deadline = time.monotonic() + 10
            while capability.status_code == 202 and time.monotonic() < deadline:
                assert capability.json()["recoveryStatus"] == "preparing"
                assert capability.json()["canUpdate"] is False
                time.sleep(0.02)
                capability = client.get(
                    "/web/runtime-update-capability",
                    headers=headers,
                    params=params,
                )
            assert capability.status_code == 200
            assert capability.json()["canUpdate"] is True
            payload.update(
                runtimeId=runtime.runtime_id,
                appName="root_agent",
                editMode="regenerate",
                updateEtag=capability.json()["etag"],
                baseRuntimeVersion=3,
            )
        response = client.post("/web/deploy-agentkit", headers=headers, json=payload)
    assert response.status_code == 200, response.text
    frames = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert frames[-1]["success"] is True, frames[-1]
    assert len(captured) == 1
    runtime_envs = captured[0]["launch_types"]["cloud"]["runtime_envs"]
    assert runtime_envs.get("HARNESS_SIDECAR_ENABLED", "false") == "false"
    assert "MCP_SERVERS_JSON" not in runtime_envs
