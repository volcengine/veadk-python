# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace as NS
from typing import cast

import pytest

from veadk.cli.studio_sandbox_updates import SandboxToolUpdates


class Client:
    def __init__(self, tool_type="CodeEnv", envs=None):
        self.tool = NS(
            tool_id="tool",
            tool_type=tool_type,
            image_url="registry/old:1",
            status="Ready",
            envs=envs or [],
        )
        self.updates = []
        self.catalog_calls = 0

    def get_tool(self, request):
        return self.tool

    def update_tool(self, request):
        self.updates.append(request.model_dump(by_alias=True, exclude_none=True))
        if request.image_url:
            self.tool.image_url = request.image_url
        if request.envs is not None:
            self.tool.envs = request.envs

    def _invoke_api(self, *, api_action, request, response_type):
        assert api_action == "ListToolTypes"
        self.catalog_calls += 1
        return response_type(
            ToolTypes=[{"ToolType": self.tool.tool_type, "ImageUrl": "registry/new:2"}],
            NextToken="",
        )


@pytest.mark.parametrize(
    "provider,region", [("volcengine", "cn-shanghai"), ("byteplus", "ap-southeast-1")]
)
def test_image_update_and_idempotency(provider, region):
    client = Client("HermesEnv")
    service = SandboxToolUpdates(provider, lambda r: client, regions=(region,))
    state = service.inspect("tool")
    assert state["needsImageUpdate"] is True
    result = service.update("tool")
    assert result["updated"] is True
    assert result["state"]["needsImageUpdate"] is False
    assert client.updates == [{"ToolId": "tool", "ImageUrl": "registry/new:2"}]
    assert service.update("tool")["updated"] is False


def test_codex_combines_repair_with_image_and_preserves_envs():
    client = Client(
        envs=[
            NS(key="CODEX_API_KEY", value="old-secret"),
            NS(key="CODEX_BASE_URL", value="https://models"),
            NS(key="CUSTOM", value="kept"),
        ]
    )
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    service.update("tool")
    assert len(client.updates) == 1
    envs = {e["Key"]: e["Value"] for e in client.updates[0]["Envs"]}
    assert envs["CUSTOM"] == "kept"
    assert envs["MODEL_AGENT_API_KEY"] == "old-secret"
    assert envs["MODEL_AGENT_BASE_URL"] == "https://models"


def test_shared_tool_concurrent_updates_only_send_once():
    client = Client("DevEnv")
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(service.update, ["tool", "tool"]))
    assert sum(r["updated"] for r in results) == 1
    assert len(client.updates) == 1


def test_updating_tool_is_not_submitted_again():
    client = Client("DevEnv")
    client.tool.status = "Updating"
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    with pytest.raises(ValueError, match="Updating"):
        service.update("tool")
    assert not client.updates


def test_ready_without_matching_image_is_not_success():
    client = Client("DevEnv")
    client.update_tool = lambda request: None
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",), timeout_seconds=0
    )
    with pytest.raises(TimeoutError):
        service.update("tool")


def test_catalog_pagination_and_cache():
    client = Client("DevEnv")
    tokens = []

    def invoke(*, api_action, request, response_type):
        tokens.append(request.next_token)
        if request.next_token is None:
            return response_type(ToolTypes=[], NextToken="page2")
        return response_type(
            ToolTypes=[{"ToolType": "DevEnv", "ImageUrl": "registry/new:2"}]
        )

    client._invoke_api = invoke
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    assert service.inspect("tool")["needsImageUpdate"]
    service.inspect("tool")
    assert tokens == [None, "page2"]


def test_provider_factory_uses_byteplus_host_even_with_volcengine_default(monkeypatch):
    from agentkit.sdk.tools.client import AgentkitToolsClient
    from frontend.server.agentkit_clients import create_agentkit_client

    monkeypatch.setenv("CLOUD_PROVIDER", "volcengine")
    client = create_agentkit_client(
        AgentkitToolsClient,
        provider="byteplus",
        access_key="test-ak",
        secret_key="test-sk",
        region="ap-southeast-1",
    )
    assert "byteplus" in client.service_info.host


def test_private_tool_is_not_upgraded_from_catalog():
    client = Client("Private")
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    assert not service.inspect("tool")["canUpdate"]
    with pytest.raises(ValueError):
        service.update("tool")
    assert not client.updates


def test_nonempty_model_variables_are_preserved():
    client = Client(
        envs=[
            NS(key="MODEL_AGENT_API_KEY", value="existing"),
            NS(key="MODEL_AGENT_BASE_URL", value="https://custom"),
        ]
    )
    service = SandboxToolUpdates(
        "volcengine", lambda r: client, regions=("cn-shanghai",)
    )
    service.update("tool")
    assert "Envs" not in client.updates[0]


def test_routes_authorize_deduplicate_and_hide_sdk_secrets():
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from frontend.server.sandbox_updates import register_sandbox_update_routes

    calls = []

    def inspect(tool_id):
        calls.append(tool_id)
        return {"toolId": tool_id, "error": ""}

    def update(tool_id):
        raise ValueError("SDK request body contains secret-value")

    def admin(request):
        if request.headers.get("x-test-role") != "admin":
            raise HTTPException(403)

    app = FastAPI()
    register_sandbox_update_routes(
        app,
        service=cast(SandboxToolUpdates, NS(inspect=inspect, update=update)),
        require_admin=admin,
        configured_tools=lambda: {
            "codex": "shared",
            "deepseek_harness": "shared",
            "dev": "",
        },
    )
    with TestClient(app) as client:
        assert client.get("/web/system-info/sandbox-tools/updates").status_code == 403
        assert (
            client.post("/web/system-info/sandbox-tools/codex/update").status_code
            == 403
        )
        headers = {"x-test-role": "admin"}
        assert (
            client.get(
                "/web/system-info/sandbox-tools/updates", headers=headers
            ).status_code
            == 200
        )
        assert calls == ["shared"]
        assert (
            client.post(
                "/web/system-info/sandbox-tools/unknown/update", headers=headers
            ).status_code
            == 400
        )
        result = client.post(
            "/web/system-info/sandbox-tools/deepseek_harness/update", headers=headers
        )
        assert result.status_code == 502
        assert "secret-value" not in result.text
