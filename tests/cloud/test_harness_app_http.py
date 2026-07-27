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


def test_harness_app_supports_session_capability_overrides(monkeypatch):
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

        initial = client.get(capabilities_path)
        assert initial.status_code == 200
        assert initial.json()["revision"] == 0

        added = client.post(
            capabilities_path,
            json={
                "kind": "tool",
                "name": "get_city_weather",
                "expected_revision": 0,
            },
        )
        assert added.status_code == 200
        assert added.json()["revision"] == 1
        assert any(
            item["id"] == "session:tool:get_city_weather" and item["custom"] is True
            for item in added.json()["tools"]
        )

        removed = client.delete(
            capabilities_path + "/session:tool:get_city_weather",
            params={"expected_revision": 1},
        )
        assert removed.status_code == 200
        assert removed.json()["revision"] == 2
        assert not any(item["custom"] for item in removed.json()["tools"])

        assert client.get("/harness/capabilities/tools").status_code == 200
        assert any(
            getattr(route, "path", None) == "/harness/run_sse"
            for route in harness_module.app.router.routes
        )
