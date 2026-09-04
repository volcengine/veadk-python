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
import types
import uuid

import pytest
from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient


def _first_run_sse_endpoint(harness_module):
    for route in harness_module.app.router.routes:
        if getattr(route, "path", None) == "/run_sse" and "POST" in getattr(
            route, "methods", set()
        ):
            return route.endpoint
    raise AssertionError("run_sse route not found")


def _closure_cell(function, name):
    freevars = function.__code__.co_freevars
    closure = function.__closure__ or ()
    if name not in freevars:
        raise AssertionError(f"{function.__name__} has no closure cell {name}")
    return closure[freevars.index(name)]


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


def test_harness_session_create_accepts_id_and_get_agent_config(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        user_id = f"user-{uuid.uuid4()}"
        session_id = f"session-{uuid.uuid4()}"
        created = client.post(
            f"/apps/{app_name}/users/{user_id}/sessions",
            json={"id": session_id},
        )

        assert created.status_code == 200
        assert created.json()["id"] == session_id

        config = client.get(
            "/get_agent_config",
            params={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
            },
        )

        assert config.status_code == 200
        body = config.json()
        assert body["app_name"] == app_name
        assert body["user_id"] == user_id
        assert body["session_id"] == session_id
        assert body["harness"]["model_name"] == "test-model"
        assert body["harness"]["runtime"] == "adk"
        assert body["harness"]["max_llm_calls"] == 10

        camel_config = client.get(
            "/get_agent_config",
            params={
                "appName": app_name,
                "userId": user_id,
                "sessionId": session_id,
            },
        )

        assert camel_config.status_code == 200
        assert camel_config.json()["harness"]["model_name"] == "test-model"

        default_config = client.get("/get_agent_config")

        assert default_config.status_code == 200
        assert default_config.json()["user_id"] == "default"
        assert default_config.json()["session_id"] == "default"
        assert default_config.json()["harness"]["model_name"] == "test-model"


def test_run_sse_harness_does_not_persist_across_same_session(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    seen = []

    async def fake_run_sse_events(
        self, req, tip_token="", auth_header="", plugins=None
    ):
        seen.append(
            req.harness.model_dump(mode="json", exclude_unset=True)
            if req.harness is not None
            else None
        )
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(harness_module, "has_a2a_registry_config", lambda agent: True)
    monkeypatch.setattr(
        harness_module.harness_app,
        "_run_sse_events",
        types.MethodType(fake_run_sse_events, harness_module.harness_app),
    )

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        user_id = f"user-{uuid.uuid4()}"
        session_id = f"session-{uuid.uuid4()}"
        client.post(
            f"/apps/{app_name}/users/{user_id}/sessions",
            json={"id": session_id},
        )

        first = client.post(
            "/run_sse",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "hello"}],
                },
                "harness": {
                    "knowledgebase": {
                        "type": "local",
                        "id": "kb-1",
                    },
                },
            },
        )
        second = client.post(
            "/run_sse",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "hello again"}],
                },
                "harness": {
                    "longterm_memory": {
                        "type": "local",
                        "id": "memory-1",
                    },
                },
            },
        )
        third = client.post(
            "/run_sse",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "hello from default config"}],
                },
            },
        )
        config = client.post(
            "/get_agent_config",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
            },
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert third.status_code == 200
        assert seen == [
            {
                "knowledgebase": {
                    "type": "local",
                    "id": "kb-1",
                },
            },
            {
                "longterm_memory": {
                    "type": "local",
                    "id": "memory-1",
                },
            },
            None,
        ]
        assert config.status_code == 200
        returned_harness = config.json()["harness"]
        assert returned_harness["runtime"] == "adk"
        assert returned_harness["max_llm_calls"] == 10
        assert "knowledgebase" not in returned_harness
        assert "longterm_memory" not in returned_harness


def test_run_sse_harness_merge_uses_default_config_not_session_config(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    monkeypatch.setattr(
        harness_module.harness_app,
        "default_harness_config",
        {
            "model_name": "default-model",
            "knowledgebase": {
                "type": "local",
                "id": "default-kb",
            },
            "temperature": 0.2,
        },
    )
    seen = []

    async def fake_run_sse_events(
        self, req, tip_token="", auth_header="", plugins=None
    ):
        seen.append(req.harness.model_dump(mode="json", exclude_unset=True))
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(
        harness_module.harness_app,
        "_run_sse_events",
        types.MethodType(fake_run_sse_events, harness_module.harness_app),
    )

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        user_id = f"user-{uuid.uuid4()}"
        session_id = f"session-{uuid.uuid4()}"
        client.post(
            f"/apps/{app_name}/users/{user_id}/sessions",
            json={"id": session_id},
        )

        first = client.post(
            "/run_sse",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "streaming": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "session kb should not be reused"}],
                },
                "harness": {
                    "knowledgebase": {
                        "type": "local",
                        "id": "session-kb",
                    },
                },
            },
        )
        second = client.post(
            "/run_sse",
            json={
                "app_name": app_name,
                "user_id": user_id,
                "session_id": session_id,
                "streaming": True,
                "harness_merge": True,
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "merge with default only"}],
                },
                "harness": {
                    "longterm_memory": {
                        "type": "local",
                        "id": "memory-1",
                    },
                },
            },
        )

        assert first.status_code == 200
        assert second.status_code == 200
        assert seen == [
            {
                "knowledgebase": {
                    "type": "local",
                    "id": "session-kb",
                },
            },
            {
                "model_name": "default-model",
                "knowledgebase": {
                    "type": "local",
                    "id": "default-kb",
                },
                "temperature": 0.2,
                "longterm_memory": {
                    "type": "local",
                    "id": "memory-1",
                },
            },
        ]


@pytest.mark.parametrize(
    (
        "payload_extra",
        "headers",
        "body_plugin_names",
        "header_plugin_names",
        "default_plugin_names",
        "expected_plugin_names",
    ),
    [
        (
            {"harness_enhance": {"enabled": True, "components": "compactor"}},
            {"x-test-harness": "1"},
            ["body-plugin"],
            ["header-plugin"],
            ["default-plugin"],
            ["body-plugin"],
        ),
        (
            {},
            {"x-test-harness": "1"},
            [],
            ["header-plugin"],
            ["default-plugin"],
            ["header-plugin"],
        ),
        (
            {},
            {},
            [],
            [],
            ["default-plugin"],
            ["default-plugin"],
        ),
    ],
)
def test_run_sse_uses_harness_plugins_from_body_headers_or_default(
    monkeypatch,
    payload_extra,
    headers,
    body_plugin_names,
    header_plugin_names,
    default_plugin_names,
    expected_plugin_names,
):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    body_plugins = [types.SimpleNamespace(name=name) for name in body_plugin_names]
    header_plugins = [types.SimpleNamespace(name=name) for name in header_plugin_names]
    default_plugins = [
        types.SimpleNamespace(name=name) for name in default_plugin_names
    ]
    seen = []

    def fake_plugins_from_enhance(enhance):
        return body_plugins if enhance is not None and enhance.enabled else []

    def fake_plugins_from_headers(request_headers):
        return header_plugins if request_headers.get("x-test-harness") else []

    async def fake_run_sse_events(
        self, req, tip_token="", auth_header="", plugins=None
    ):
        seen.append([getattr(plugin, "name", "") for plugin in plugins or []])
        yield "data: [DONE]\n\n"

    monkeypatch.setattr(harness_module, "has_a2a_registry_config", lambda agent: False)
    monkeypatch.setattr(
        harness_module,
        "build_harness_plugins_from_enhance",
        fake_plugins_from_enhance,
    )
    monkeypatch.setattr(
        harness_module,
        "build_harness_plugins_from_headers",
        fake_plugins_from_headers,
    )
    monkeypatch.setattr(harness_module.harness_app, "plugins", default_plugins)
    monkeypatch.setattr(
        harness_module.harness_app,
        "_run_sse_events",
        types.MethodType(fake_run_sse_events, harness_module.harness_app),
    )

    with TestClient(harness_module.app) as client:
        app_name = client.get("/list-apps").json()[0]
        payload = {
            "app_name": app_name,
            "user_id": f"user-{uuid.uuid4()}",
            "session_id": f"session-{uuid.uuid4()}",
            "streaming": True,
            "new_message": {
                "role": "user",
                "parts": [{"text": "hello with plugins"}],
            },
            **payload_extra,
        }
        response = client.post("/run_sse", json=payload, headers=headers)

    assert response.status_code == 200
    assert seen == [expected_plugin_names]


def test_get_agent_config_redacts_resource_configs(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    monkeypatch.setattr(
        harness_module.harness_app,
        "default_harness_config",
        {
            "model_name": "test-model",
            "knowledgebase": {
                "type": "viking",
                "id": "kb-1",
                "config": {"index": "secret-kb-index", "api_key": "secret"},
            },
            "longterm_memory": {
                "type": "mem0",
                "id": "memory-1",
                "config": {"index": "secret-memory-index", "api_key": "secret"},
            },
        },
    )

    with TestClient(harness_module.app) as client:
        response = client.get("/get_agent_config")

    assert response.status_code == 200
    assert response.json()["harness"]["knowledgebase"] == {"id": "kb-1"}
    assert response.json()["harness"]["longterm_memory"] == {"id": "memory-1"}


def test_run_sse_without_harness_or_session_config_delegates_to_adk(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    endpoint = _first_run_sse_endpoint(harness_module)
    adk_run_sse_cell = _closure_cell(endpoint, "adk_run_sse")
    original_adk_run_sse = adk_run_sse_cell.cell_contents
    delegated = []

    async def fake_adk_run_sse(req):
        delegated.append(
            {
                "app_name": req.app_name,
                "user_id": req.user_id,
                "session_id": req.session_id,
                "harness": req.harness,
            }
        )
        return PlainTextResponse("delegated")

    async def fail_run_sse_events(
        self, req, tip_token="", auth_header="", plugins=None
    ):
        raise AssertionError("run_sse should delegate to the ADK handler")
        yield "data: unreachable\n\n"

    monkeypatch.setattr(harness_module, "has_a2a_registry_config", lambda agent: False)
    monkeypatch.setattr(
        harness_module.harness_app,
        "_run_sse_events",
        types.MethodType(fail_run_sse_events, harness_module.harness_app),
    )
    adk_run_sse_cell.cell_contents = fake_adk_run_sse
    try:
        with TestClient(harness_module.app) as client:
            app_name = client.get("/list-apps").json()[0]
            response = client.post(
                "/run_sse",
                json={
                    "app_name": app_name,
                    "user_id": f"user-{uuid.uuid4()}",
                    "session_id": f"session-{uuid.uuid4()}",
                    "streaming": True,
                    "new_message": {
                        "role": "user",
                        "parts": [{"text": "hello without overrides"}],
                    },
                },
            )
    finally:
        adk_run_sse_cell.cell_contents = original_adk_run_sse

    assert response.status_code == 200
    assert response.text == "delegated"
    assert len(delegated) == 1
    assert delegated[0]["app_name"] == app_name
    assert delegated[0]["harness"] is None


def test_harness_invoke_uses_harness_max_llm_calls(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    seen = []

    class FakeRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, **kwargs):
            run_config = kwargs["run_config"]
            seen.append(getattr(run_config, "max_llm_calls", None))
            return "ok"

    monkeypatch.setattr(harness_module, "Runner", FakeRunner)
    monkeypatch.setattr(
        harness_module,
        "spawn_harness_run_agent",
        lambda agent, *_args, **_kwargs: agent,
    )

    with TestClient(harness_module.app) as client:
        response = client.post(
            "/harness/invoke",
            json={
                "prompt": "hello",
                "harness_name": "test-harness",
                "harness": {"model_name": "model-b", "max_llm_calls": 7},
                "run_agent_request": {
                    "user_id": f"user-{uuid.uuid4()}",
                    "session_id": f"session-{uuid.uuid4()}",
                },
            },
        )

    assert response.status_code == 200
    assert response.json()["output"] == "ok"
    assert seen == [7]


def test_harness_invoke_harness_merge_uses_default_config(monkeypatch):
    monkeypatch.setenv("MODEL_AGENT_API_KEY", "test-api-key")
    monkeypatch.setenv("MODEL_NAME", "test-model")
    monkeypatch.setenv("HARNESS_NAME", "test-harness")

    harness_module = importlib.import_module("veadk.cloud.harness_app.app")
    monkeypatch.setattr(
        harness_module.harness_app,
        "default_harness_config",
        {
            "model_name": "default-model",
            "knowledgebase": {
                "type": "local",
                "id": "default-kb",
            },
        },
    )
    seen = []

    class FakeRunner:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def run(self, **kwargs):
            return "ok"

    def fake_spawn(agent, prompt, overrides, *_args, **_kwargs):
        seen.append(overrides.model_dump(mode="json", exclude_unset=True))
        return agent

    monkeypatch.setattr(harness_module, "Runner", FakeRunner)
    monkeypatch.setattr(harness_module, "spawn_harness_run_agent", fake_spawn)

    with TestClient(harness_module.app) as client:
        first = client.post(
            "/harness/invoke",
            json={
                "prompt": "hello",
                "harness_name": "test-harness",
                "harness": {
                    "longterm_memory": {
                        "type": "local",
                        "id": "memory-1",
                    },
                },
                "run_agent_request": {
                    "user_id": f"user-{uuid.uuid4()}",
                    "session_id": f"session-{uuid.uuid4()}",
                },
            },
        )
        second = client.post(
            "/harness/invoke",
            json={
                "prompt": "hello",
                "harness_name": "test-harness",
                "harness_merge": True,
                "harness": {
                    "longterm_memory": {
                        "type": "local",
                        "id": "memory-1",
                    },
                },
                "run_agent_request": {
                    "user_id": f"user-{uuid.uuid4()}",
                    "session_id": f"session-{uuid.uuid4()}",
                },
            },
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert seen == [
        {
            "longterm_memory": {
                "type": "local",
                "id": "memory-1",
            },
        },
        {
            "model_name": "default-model",
            "knowledgebase": {
                "type": "local",
                "id": "default-kb",
            },
            "longterm_memory": {
                "type": "local",
                "id": "memory-1",
            },
        },
    ]
