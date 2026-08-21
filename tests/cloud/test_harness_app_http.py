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

import importlib

from fastapi.testclient import TestClient


def test_harness_app_exposes_agent_info(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        response = client.get(f"/web/agent-info/{app_name}")

        assert response.status_code == 200
        info = response.json()
        assert info["name"] == "test_harness"
        assert info["model"] == "openai/test-model"
        assert info["tools"] == []
        assert info["skills"] == []
        assert info["subAgents"] == []
        assert info["graph"]["id"] == "test_harness"
        assert info["graph"]["path"] == ["test_harness"]
        assert info["graph"]["children"] == []
        assert client.get("/web/agent-info/unknown").status_code == 404


def test_harness_app_disables_bff_tool_host_by_default(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        created = client.post(
            f"/apps/{app_name}/users/test-user/sessions",
            json={},
        )
        assert created.status_code == 200
        session_id = created.json()["id"]
        capabilities_path = (
            f"/harness/apps/{app_name}/users/test-user/sessions/"
            f"{session_id}/capabilities"
        )

        assert client.get(capabilities_path).status_code == 404
        assert client.get("/harness/capabilities/tools").status_code == 404
        assert client.get("/harness/studio-channel/v1/capabilities").json() == {
            "enabled": False,
            "protocol": "studio-tool-channel/1",
            "transports": [],
        }
        assert not any(
            getattr(route, "path", None) == "/harness/studio-channel/v1/http-runs"
            for route in harness_module.app.router.routes
        )
        assert not any(
            getattr(route, "path", None) == "/harness/run_sse"
            for route in harness_module.app.router.routes
        )
