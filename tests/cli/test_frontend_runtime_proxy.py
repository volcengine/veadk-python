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

import base64
import json
from pathlib import Path
from threading import Barrier
from types import SimpleNamespace
from typing import Any, ClassVar

import httpx
import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from frontend.server.environments.session_mounts import SessionEnvironmentMount
from veadk.cli import cli_frontend
from veadk.cli.cli_frontend import (
    _build_agentkit_proxy_headers,
    _frontend_allow_origins,
    _open_browser_when_ready,
    _run_frontend_server,
    _runtime_regions,
    _studio_resource_region,
)
from veadk.tools import list_builtin_tools
from veadk.utils.cloud_provider import CloudProvider


def test_runtime_proxy_uses_same_socket_studio_tool_channel_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    opened: dict[str, Any] = {}

    class _FakeStudioRun:
        runtime_context = SimpleNamespace(
            instance_name="instance-channel",
            request_id="request-channel",
        )

        async def stream(self):
            yield b'data: {"id":"event-1","author":"agent"}\n\n'

    async def fake_open_studio_tool_run(**kwargs: Any) -> _FakeStudioRun:
        opened.update(kwargs)
        return _FakeStudioRun()

    monkeypatch.setattr(
        "frontend.server.studio_tools.open_studio_tool_run",
        fake_open_studio_tool_run,
    )

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        assert kwargs["endpoint"] == "https://runtime.example"
        assert kwargs["authorization"] == "Bearer runtime-api-key"
        return True

    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    class _UnexpectedHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs
            raise AssertionError("run_sse must not open a separate HTTP connection")

    monkeypatch.setattr("httpx.AsyncClient", _UnexpectedHttpClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "6 * 7"}]},
                "custom_metadata": {
                    "veadkInvocation": {
                        "skills": [{"name": "review-code"}],
                        "environmentMounts": True,
                    }
                },
                "platform_tools": [
                    "get_city_weather",
                    "web_fetch",
                    "web_search",
                ],
            },
        )

    assert response.status_code == 200
    assert response.text == 'data: {"id":"event-1","author":"agent"}\n\n'
    assert response.headers["x-studio-faas-instance"] == "instance-channel"
    assert response.headers["x-studio-faas-request-id"] == "request-channel"
    assert opened["endpoint"] == "https://runtime.example"
    assert opened["authorization"] == "Bearer runtime-api-key"
    assert opened["runtime_id"] == "runtime-1"
    assert opened["payload"]["custom_metadata"] == {
        "veadkInvocation": {"skills": [{"name": "review-code"}]}
    }
    assert {item["name"] for item in opened["catalog"].manifests()} == {
        "get_city_weather",
        "web_fetch",
        "web_search",
    }


def test_runtime_proxy_builds_a_per_run_selected_tool_catalog(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    opened: dict[str, Any] = {}

    class _FakeStudioRun:
        async def stream(self):
            yield b'data: {"id":"selected-run"}\n\n'

    async def fake_open_studio_tool_run(**kwargs: Any) -> _FakeStudioRun:
        opened.update(kwargs)
        return _FakeStudioRun()

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(
        "frontend.server.studio_tools.open_studio_tool_run",
        fake_open_studio_tool_run,
    )
    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "6 * 7"}]},
                "platform_tools": ["get_city_weather"],
            },
        )

    assert response.status_code == 200
    assert [item["name"] for item in opened["catalog"].manifests()] == [
        "get_city_weather"
    ]
    assert "platform_tools" not in opened["payload"]


def test_runtime_proxy_resolves_environment_mount_without_forwarding_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    mount = SessionEnvironmentMount(
        environment_id="a" * 32,
        environment_version_id="version-1",
        image="registry.example/aio:test",
        provider="volcengine",
        region="cn-beijing",
    )
    resolved: dict[str, Any] = {}

    async def fake_resolve(owner_id: str, selection: Any) -> SessionEnvironmentMount:
        resolved.update(owner_id=owner_id, selection=selection)
        return mount

    monkeypatch.setattr(app.state.session_environment_mounts, "resolve", fake_resolve)
    opened: dict[str, Any] = {}

    class _FakeStudioRun:
        async def stream(self):
            yield b'data: {"id":"mounted-run"}\n\n'

    async def fake_open_studio_tool_run(**kwargs: Any) -> _FakeStudioRun:
        opened.update(kwargs)
        return _FakeStudioRun()

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(
        "frontend.server.studio_tools.open_studio_tool_run",
        fake_open_studio_tool_run,
    )
    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "pwd"}]},
                "platform_tools": ["get_city_weather"],
                "environment_mount": {
                    "environment_id": "a" * 32,
                    "environment_version_id": "version-1",
                },
            },
        )

    assert response.status_code == 200
    assert resolved["owner_id"] == "local"
    assert resolved["selection"].environment_id == "a" * 32
    assert opened["environment_mount"] is mount
    assert opened["owner_id"] == "local"
    assert "environment_mount" not in opened["payload"]


@pytest.mark.parametrize("provider", ["volcengine", "byteplus"])
def test_runtime_proxy_resolves_multiple_environment_mounts_and_adds_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: CloudProvider,
) -> None:
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "byte-ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "byte-sk")
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    mounts = (
        SessionEnvironmentMount(
            environment_id="a" * 32,
            environment_version_id="version-1",
            image="registry.example/aio:first",
            provider=provider,
            region=("ap-southeast-1" if provider == "byteplus" else "cn-beijing"),
            name="First",
            description="Authoring environment for product and specification design.",
            manifest={"spec": {"capabilities": ["authoring", "design"]}},
        ),
        SessionEnvironmentMount(
            environment_id="b" * 32,
            environment_version_id="version-2",
            image="registry.example/aio:second",
            provider=provider,
            region=("ap-southeast-1" if provider == "byteplus" else "cn-beijing"),
            name="Second",
            description="Engineering environment for implementation and tests.",
            manifest={"spec": {"capabilities": ["engineering", "shell-exec"]}},
        ),
    )
    resolved: dict[str, Any] = {}

    async def fake_resolve_many(owner_id: str, selections: Any) -> Any:
        resolved.update(owner_id=owner_id, selections=selections)
        return mounts

    monkeypatch.setattr(
        app.state.session_environment_mounts, "resolve_many", fake_resolve_many
    )
    opened: dict[str, Any] = {}

    class _FakeStudioRun:
        async def stream(self):
            yield b'data: {"id":"mounted-run"}\n\n'

    async def fake_open_studio_tool_run(**kwargs: Any) -> _FakeStudioRun:
        opened.update(kwargs)
        return _FakeStudioRun()

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        del kwargs
        return True

    monkeypatch.setattr(
        "frontend.server.studio_tools.open_studio_tool_run",
        fake_open_studio_tool_run,
    )
    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region="
            + ("ap-southeast-1" if provider == "byteplus" else "cn-beijing"),
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "pwd"}]},
                "custom_metadata": {
                    "veadkInvocation": {"skills": [{"name": "review-code"}]}
                },
                "platform_tools": [],
                "environment_mounts": [
                    {
                        "environment_id": "a" * 32,
                        "environment_version_id": "version-1",
                    },
                    {
                        "environment_id": "b" * 32,
                        "environment_version_id": "version-2",
                    },
                ],
            },
        )

    assert response.status_code == 200
    assert resolved["owner_id"] == "local"
    assert [item.environment_id for item in resolved["selections"]] == [
        "a" * 32,
        "b" * 32,
    ]
    assert opened["environment_mounts"] == mounts
    assert opened["environment_mount"] is None
    assert [item["name"] for item in opened["catalog"].manifests()] == [
        "execute_in_sandbox",
        "get_env_manifest",
        "list_envs",
    ]
    assert "environment_mounts" not in opened["payload"]
    message = opened["payload"]["new_message"]
    assert message["role"] == "user"
    assert message["parts"][0] == {"text": "pwd"}
    hidden_routing_part = message["parts"][1]
    assert hidden_routing_part["partMetadata"] == {
        "veadkTransport": {"hidden": True, "hideText": True}
    }
    routing_instruction = hidden_routing_part["text"]
    assert "first tool call MUST be list_envs" in routing_instruction
    assert "authoring/design environment" in routing_instruction
    assert "choose review for review" in routing_instruction
    assert "choose engineering for implementation" in routing_instruction
    assert "execute_in_sandbox for every shell or CLI command" in routing_instruction
    assert "take priority over knowledge bases" in routing_instruction
    assert (
        "Do not call collect_resources or create_agents unless" in routing_instruction
    )
    assert "First" in routing_instruction
    assert "Authoring environment for product and specification design." in (
        routing_instruction
    )
    assert '"capabilities": ["authoring", "design"]' in routing_instruction
    assert '"environment_id": "' + ("a" * 32) + '"' in routing_instruction
    assert "Second" in routing_instruction
    assert "Engineering environment for implementation and tests." in (
        routing_instruction
    )
    assert '"capabilities": ["engineering", "shell-exec"]' in routing_instruction
    assert '"environment_id": "' + ("b" * 32) + '"' in routing_instruction
    assert opened["payload"]["custom_metadata"] == {
        "veadkInvocation": {
            "skills": [{"name": "review-code"}],
            "environmentMounts": True,
        }
    }


def test_runtime_tool_capabilities_expose_safe_local_metadata(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        assert kwargs == {
            "endpoint": "https://runtime.example",
            "authorization": "Bearer runtime-api-key",
        }
        return True

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-tool-channel/runtime-1/capabilities?region=cn-beijing"
        )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["supported"] is True
    assert {item["id"] for item in body["tools"]} == {
        *list_builtin_tools(),
        "branch_compare",
        "current_time",
        "execute_in_sandbox",
        "get_env_manifest",
        "list_envs",
    }
    assert all("input_schema" not in item for item in body["tools"])


def test_empty_platform_tool_selection_uses_plain_run_without_forwarding_control(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    async def unexpected_capability_query(**kwargs: Any) -> bool:
        del kwargs
        raise AssertionError("an empty selection must not open the Tool Channel")

    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        unexpected_capability_query,
    )
    forwarded: dict[str, Any] = {}

    class _FakeUpstreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_raw(self):
            yield b'data: {"id":"plain-empty-selection"}\n\n'

        async def aclose(self) -> None:
            pass

    class _FakeHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(self, *args: Any, **kwargs: Any) -> object:
            del args
            forwarded.update(json.loads(kwargs["content"]))
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            del request
            assert stream
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeHttpClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
                "platform_tools": [],
            },
        )

    assert response.status_code == 200
    assert "plain-empty-selection" in response.text
    assert "platform_tools" not in forwarded


def test_runtime_route_channel_connects_after_runtime_probe(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_ROUTE_CHANNEL", "demo")
    connected: dict[str, Any] = {}

    class _FakeRouteChannelManager:
        def __init__(self, registry: Any) -> None:
            self.registry = registry

        async def ensure_connected(self, **kwargs: Any) -> bool:
            connected.update(kwargs)
            return True

        def connected(self, runtime_id: str) -> bool:
            return runtime_id == "runtime-1"

        async def close(self) -> None:
            pass

    monkeypatch.setattr(
        "frontend.server.studio_routes.StudioRouteChannelManager",
        _FakeRouteChannelManager,
    )
    app = _create_frontend_app(monkeypatch, tmp_path)

    runtime = SimpleNamespace(
        runtime_id="runtime-1",
        project_name="default",
        network_configurations=[
            SimpleNamespace(
                endpoint="https://runtime.example",
                network_type="public",
            )
        ],
        authorizer_configuration=SimpleNamespace(
            key_auth=SimpleNamespace(api_key="runtime-api-key"),
            custom_jwt_authorizer=None,
        ),
        tags=[],
    )

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            raise RuntimeError("InvalidAgentKitRuntime.NotFound: hidden")

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                agent_kit_runtimes=[runtime],
                next_token=None,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-route-channel/runtime-1/connect?region=cn-beijing"
        )

    assert response.status_code == 200
    assert response.json()["connected"] is True
    assert response.json()["supported"] is True
    assert response.json()["catalogRevision"].startswith("sha256:")
    assert connected == {
        "runtime_id": "runtime-1",
        "endpoint": "https://runtime.example",
        "authorization": "Bearer runtime-api-key",
    }


def test_runtime_tool_capabilities_use_list_fallback_when_get_is_hidden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    runtime = SimpleNamespace(
        runtime_id="runtime-1",
        network_configurations=[
            SimpleNamespace(
                endpoint="https://runtime.example",
                network_type="public",
            )
        ],
        authorizer_configuration=SimpleNamespace(
            key_auth=SimpleNamespace(api_key="runtime-api-key"),
            custom_jwt_authorizer=None,
        ),
        tags=[],
    )

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            raise RuntimeError("InvalidAgentKitRuntime.NotFound: hidden")

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                agent_kit_runtimes=[runtime],
                next_token=None,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    async def fake_runtime_supports_bff_tools(**kwargs: Any) -> bool:
        assert kwargs == {
            "endpoint": "https://runtime.example",
            "authorization": "Bearer runtime-api-key",
        }
        return True

    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        fake_runtime_supports_bff_tools,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-tool-channel/runtime-1/capabilities?region=cn-beijing"
        )

    assert response.status_code == 200
    assert response.json()["supported"] is True


def test_runtime_proxy_uses_plain_run_sse_when_runtime_lacks_bff_tool_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                runtime_id="runtime-1",
                project_name="default",
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    async def runtime_lacks_bff_tool_host(**kwargs: Any) -> bool:
        del kwargs
        return False

    async def unexpected_channel(**kwargs: Any) -> None:
        del kwargs
        raise AssertionError("unsupported Runtime must not open the BFF tool channel")

    monkeypatch.setattr(
        "frontend.server.studio_tools.runtime_supports_bff_tools",
        runtime_lacks_bff_tool_host,
    )
    monkeypatch.setattr(
        "frontend.server.studio_tools.open_studio_tool_run",
        unexpected_channel,
    )

    class _FakeUpstreamResponse:
        status_code = 200
        headers = {"content-type": "text/event-stream"}

        async def aiter_raw(self):
            yield b'data: {"id":"plain-run"}\n\n'

        async def aclose(self) -> None:
            pass

    class _FakeHttpClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(self, *args: Any, **kwargs: Any) -> object:
            del args, kwargs
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            del request
            assert stream
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeHttpClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
                "platform_tools": ["get_city_weather"],
            },
        )

    assert response.status_code == 200
    assert response.text == 'data: {"id":"plain-run"}\n\n'


def _create_frontend_app(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    site_logo: str | None = None,
    site_title: str | None = None,
    studio: bool = False,
    provider: str = "volcengine",
    admins: str | None = None,
    developers: str | None = None,
) -> FastAPI:
    captured: dict[str, Any] = {}
    monkeypatch.setattr("dotenv.find_dotenv", lambda *args, **kwargs: "")
    monkeypatch.setattr(
        "uvicorn.run",
        lambda app, **kwargs: captured.setdefault("app", app),
    )
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "sk")

    _run_frontend_server(
        agents_dir=str(tmp_path),
        frontend_dir=None,
        site_logo=site_logo,
        site_title=site_title,
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
        studio_admins=admins,
        studio_developers=developers,
        open_browser=False,
        provider=provider,  # type: ignore[arg-type]
        studio=studio,
    )
    return captured["app"]


def test_proxy_headers_do_not_forward_unvalidated_authorization() -> None:
    headers = _build_agentkit_proxy_headers(
        {
            "Authorization": "Bearer unvalidated.jwt.token",
            "Cookie": "session=secret",
            "Accept": "application/json",
        },
        api_key=None,
    )

    assert headers == {"Accept": "application/json"}


def test_vite_allows_both_loopback_browser_origins() -> None:
    assert _frontend_allow_origins(vite=True) == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    assert _frontend_allow_origins(vite=False) == []


class _FakeHttpResponse:
    def __init__(self, status: int = 200) -> None:
        self.status = status

    def __enter__(self) -> "_FakeHttpResponse":
        return self

    def __exit__(self, *args: object) -> None:
        return None


def test_open_browser_waits_for_http_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[tuple[str, float]] = []
    opened: list[str] = []

    def _urlopen(request: Any, timeout: float) -> _FakeHttpResponse:
        requests.append((request.full_url, timeout))
        return _FakeHttpResponse(200)

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    _open_browser_when_ready(
        "http://127.0.0.1:8877",
        "127.0.0.1",
        8877,
        timeout=1.0,
    )

    assert requests == [("http://127.0.0.1:8877/web/ui-config", 1.0)]
    assert opened == ["http://127.0.0.1:8877"]


def test_open_browser_falls_back_to_root_http_probe(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    requests: list[str] = []
    opened: list[str] = []

    def _urlopen(request: Any, timeout: float) -> _FakeHttpResponse:
        del timeout
        requests.append(request.full_url)
        if request.full_url.endswith("/web/ui-config"):
            return _FakeHttpResponse(503)
        return _FakeHttpResponse(200)

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    _open_browser_when_ready(
        "http://127.0.0.1:8877",
        "127.0.0.1",
        8877,
        timeout=1.0,
    )

    assert requests == [
        "http://127.0.0.1:8877/web/ui-config",
        "http://127.0.0.1:8877",
    ]
    assert opened == ["http://127.0.0.1:8877"]


def test_open_browser_treats_http_client_error_as_ready(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import urllib.error

    opened: list[str] = []

    def _urlopen(request: Any, timeout: float) -> _FakeHttpResponse:
        del timeout
        raise urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr("urllib.request.urlopen", _urlopen)
    monkeypatch.setattr("webbrowser.open", lambda url: opened.append(url) or True)

    _open_browser_when_ready(
        "http://127.0.0.1:8877",
        "127.0.0.1",
        8877,
        timeout=1.0,
    )

    assert opened == ["http://127.0.0.1:8877"]


def test_open_browser_timeout_logs_manual_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import itertools
    import urllib.error

    warnings: list[str] = []
    times = itertools.chain([100.0, 100.0, 100.6], itertools.repeat(100.6))

    monkeypatch.setattr("time.time", lambda: next(times))
    monkeypatch.setattr("time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            urllib.error.URLError("connection refused")
        ),
    )
    monkeypatch.setattr("webbrowser.open", lambda _url: False)
    monkeypatch.setattr(
        cli_frontend.logger,
        "warning",
        lambda message: warnings.append(message),
    )
    monkeypatch.setattr(cli_frontend.logger, "info", lambda _message: None)

    _open_browser_when_ready(
        "http://127.0.0.1:8877",
        "127.0.0.1",
        8877,
        timeout=0.5,
    )

    assert len(warnings) == 1
    assert "Open http://127.0.0.1:8877 manually" in warnings[0]
    assert "connection refused" in warnings[0]


def test_open_browser_warns_when_browser_returns_false(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    warnings: list[str] = []

    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: _FakeHttpResponse(200),
    )
    monkeypatch.setattr("webbrowser.open", lambda _url: False)
    monkeypatch.setattr(
        cli_frontend.logger,
        "warning",
        lambda message: warnings.append(message),
    )

    _open_browser_when_ready(
        "http://127.0.0.1:8877",
        "127.0.0.1",
        8877,
        timeout=1.0,
    )

    assert warnings == [
        "Could not open the browser automatically. Open http://127.0.0.1:8877 manually."
    ]


def test_runtime_regions_use_both_volcengine_regions() -> None:
    assert _runtime_regions("volcengine", "all") == [
        "cn-beijing",
        "cn-shanghai",
    ]


def test_runtime_regions_use_byteplus_default_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("BYTEPLUS_REGION", raising=False)
    assert _runtime_regions("byteplus", "all") == ["ap-southeast-1"]
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-2")
    assert _runtime_regions("byteplus", "all") == ["ap-southeast-2"]


def test_studio_resource_region_uses_beijing_for_local_studio() -> None:
    assert (
        _studio_resource_region(
            "volcengine",
            {
                "REGION": "cn-shanghai",
                "VEADK_STUDIO_DEPLOY_REGION": "cn-shanghai",
            },
        )
        == "cn-beijing"
    )


@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-shanghai"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_studio_resource_region_uses_cloud_studio_deployment_region(
    provider: CloudProvider,
    region: str,
) -> None:
    assert (
        _studio_resource_region(
            provider,
            {
                "VEADK_STUDIO_FUNCTION_ID": "function-1",
                "VEADK_STUDIO_DEPLOY_REGION": region,
            },
        )
        == region
    )


def test_studio_resource_region_uses_vefaas_region_fallback() -> None:
    assert (
        _studio_resource_region(
            "volcengine",
            {
                "_FAAS_FUNC_ID": "function-1",
                "APP_REGION": "cn-shanghai",
            },
        )
        == "cn-shanghai"
    )


@pytest.mark.parametrize(
    ("provider", "conflicting_provider", "region"),
    [
        ("volcengine", "byteplus", "cn-shanghai"),
        ("byteplus", "volcengine", "ap-southeast-1"),
    ],
)
def test_skill_and_knowledge_clients_use_cloud_studio_provider_and_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: CloudProvider,
    conflicting_provider: CloudProvider,
    region: str,
) -> None:
    from agentkit.platform.context import (
        default_cloud_provider,
        get_default_cloud_provider,
    )

    requested_clients: list[tuple[str, object, str]] = []

    class FakeSkillsClient:
        def __init__(self, **kwargs: Any) -> None:
            requested_clients.append(
                ("skills", get_default_cloud_provider(), kwargs["region"])
            )

        def list_skill_spaces(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(items=[], total_count=0)

    class FakeKnowledgeClient:
        def __init__(self, **kwargs: Any) -> None:
            requested_clients.append(
                ("knowledge", get_default_cloud_provider(), kwargs["region"])
            )

        def list_knowledge_bases(self, request: object) -> SimpleNamespace:
            del request
            return SimpleNamespace(knowledge_bases=[], next_token="")

    monkeypatch.setattr(
        "agentkit.sdk.skills.client.AgentkitSkillsClient",
        FakeSkillsClient,
    )
    monkeypatch.setattr(
        "agentkit.sdk.knowledge.client.AgentkitKnowledgeClient",
        FakeKnowledgeClient,
    )
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "sk")
    monkeypatch.setenv("VEADK_STUDIO_FUNCTION_ID", "function-1")
    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_REGION", region)
    app = _create_frontend_app(
        monkeypatch,
        tmp_path,
        studio=True,
        provider=provider,
    )

    with default_cloud_provider(conflicting_provider):
        with TestClient(app) as client:
            skills = client.get("/web/skill-spaces")
            knowledge = client.get("/web/knowledge-bases")
        assert get_default_cloud_provider().value == conflicting_provider

    assert skills.status_code == 200
    assert knowledge.status_code == 200
    assert [
        (kind, context.value, client_region)
        for kind, context, client_region in requested_clients
    ] == [
        ("skills", provider, region),
        ("knowledge", provider, region),
    ]


@pytest.mark.parametrize(
    (
        "provider",
        "conflicting_provider",
        "requested_region",
        "expected_region",
        "expected_host",
    ),
    [
        (
            "volcengine",
            "byteplus",
            "cn-shanghai",
            "cn-shanghai",
            "open.volcengineapi.com",
        ),
        (
            "byteplus",
            "volcengine",
            "cn-beijing",
            "ap-southeast-1",
            "agentkit.ap-southeast-1.byteplusapi.com",
        ),
    ],
)
def test_environment_sandbox_client_uses_studio_provider_endpoint_and_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    provider: CloudProvider,
    conflicting_provider: CloudProvider,
    requested_region: str,
    expected_region: str,
    expected_host: str,
) -> None:
    from agentkit.platform.context import (
        default_cloud_provider,
        get_default_cloud_provider,
    )

    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "byte-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "byte-sk")
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)

    with default_cloud_provider(conflicting_provider):
        client = app.state.environment_sandbox_resolver._client_factory(
            provider,
            requested_region,
        )
        active_provider = get_default_cloud_provider()
        assert active_provider is not None
        assert active_provider.value == conflicting_provider

    assert client.region == expected_region
    assert client.host == expected_host


def test_environment_sandbox_client_preserves_vestack_agentkit_host(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", "volc-ak")
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", "volc-sk")
    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_TARGET", "vestack")
    monkeypatch.setenv("VOLCENGINE_AGENTKIT_HOST", "agentkit.internal.example")
    app = _create_frontend_app(monkeypatch, tmp_path, provider="volcengine")

    client = app.state.environment_sandbox_resolver._client_factory(
        "volcengine",
        "e70",
    )

    assert client.region == "e70"
    assert client.host == "agentkit.internal.example"


def test_environment_sandbox_client_rejects_cross_provider_mount(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from veadk.cli.frontend_sandbox import SandboxConfigurationError

    app = _create_frontend_app(monkeypatch, tmp_path, provider="volcengine")

    with pytest.raises(SandboxConfigurationError, match="云服务商不一致"):
        app.state.environment_sandbox_resolver._client_factory(
            "byteplus",
            "ap-southeast-1",
        )


def test_byteplus_runtime_list_uses_vefaas_iam_credentials(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, provider="byteplus")
    monkeypatch.delenv("BYTEPLUS_ACCESS_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SECRET_KEY", raising=False)
    monkeypatch.delenv("BYTEPLUS_SESSION_TOKEN", raising=False)
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-1")
    calls: list[tuple[str, str, str, str]] = []

    import builtins

    real_open = builtins.open

    def _fake_open(path: object, *args: object, **kwargs: object):
        if path == "/var/run/secrets/iam/credential":
            return real_open(
                tmp_path / "iam-credential.json",
                *args,
                **kwargs,
            )
        return real_open(path, *args, **kwargs)

    (tmp_path / "iam-credential.json").write_text(
        json.dumps(
            {
                "access_key_id": "iam-ak",
                "secret_access_key": "iam-sk",
                "session_token": "iam-token",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(builtins, "open", _fake_open)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(
                (
                    kwargs["access_key"],
                    kwargs["secret_key"],
                    kwargs["session_token"],
                    kwargs["region"],
                )
            )

        def list_runtimes(self, _request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                agent_kit_runtimes=[
                    SimpleNamespace(
                        name="runtime-bp",
                        runtime_id="runtime-bp-id",
                        status="Ready",
                        created_at="2026-08-06T10:00:00Z",
                        tags=[],
                    )
                ],
                next_token="",
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtimes",
            params={"region": "all", "page_size": 1},
        )

    assert response.status_code == 200
    assert response.json()["runtimes"][0]["name"] == "runtime-bp"
    assert calls == [("iam-ak", "iam-sk", "iam-token", "ap-southeast-1")]


def test_byteplus_runtime_detail_coerces_volcengine_region(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, provider="byteplus")
    monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
    monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
    monkeypatch.setenv("BYTEPLUS_REGION", "ap-southeast-1")
    calls: list[str] = []

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append(kwargs["region"])

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                runtime_id=getattr(request, "runtime_id", ""),
                name="runtime-bp",
                status="Ready",
                network_configurations=[],
                envs=[],
                tags=[],
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-detail",
            params={"runtimeId": "runtime-bp-id", "region": "cn-shanghai"},
        )

    assert response.status_code == 200
    assert response.json()["region"] == "ap-southeast-1"
    assert calls == ["ap-southeast-1"]


def test_ui_config_serves_custom_branding(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_RELEASE_VERSION", "20260726093000")
    logo = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8A"
        "AQUBAScY42YAAAAASUVORK5CYII="
    )
    logo_path = tmp_path / "logo.png"
    logo_path.write_bytes(logo)
    app = _create_frontend_app(
        monkeypatch,
        tmp_path,
        site_logo=str(logo_path),
        site_title="火山助手",
    )

    with TestClient(app) as client:
        config_response = client.get("/web/ui-config")
        logo_response = client.get("/web/site-logo")

    assert config_response.status_code == 200
    assert config_response.json()["branding"] == {
        "title": "火山助手",
        "logoUrl": "/web/site-logo",
    }
    assert config_response.json()["version"] == "20260726093000"
    assert logo_response.status_code == 200
    assert logo_response.headers["content-type"].startswith("image/png")
    assert logo_response.content == logo


def test_ui_config_serves_studio_telemetry_config(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_ID", "stddep_test")
    monkeypatch.setenv("VEADK_STUDIO_USER_POOL_ID", "pool-id")
    monkeypatch.setenv("VEADK_STUDIO_APPLICATION_ID", "app-id")
    monkeypatch.setenv("VEADK_STUDIO_FUNCTION_ID", "func-id")
    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_REGION", "cn-beijing")
    monkeypatch.setenv("VEADK_STUDIO_PROJECT", "studio-project")
    monkeypatch.setenv("VEADK_STUDIO_ACCOUNT_ID", "2100123456")
    monkeypatch.setenv("VEADK_STUDIO_ACCOUNT_ID_RESOLUTION_ERROR", "sts unavailable")
    app = _create_frontend_app(monkeypatch, tmp_path, studio=True)

    with TestClient(app) as client:
        response = client.get("/web/ui-config")

    assert response.status_code == 200
    telemetry = response.json()["telemetry"]
    assert telemetry == {
        "enabled": True,
        "studio": {
            "deployId": "stddep_test",
            "userPoolId": "pool-id",
            "applicationId": "app-id",
            "functionId": "func-id",
            "region": "cn-beijing",
            "project": "studio-project",
            "version": response.json()["version"],
            "accountId": "2100123456",
            "accountIdResolutionError": "sts unavailable",
        },
    }


def test_ui_config_disables_telemetry_outside_studio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, studio=False)

    with TestClient(app) as client:
        response = client.get("/web/ui-config")

    assert response.status_code == 200
    assert response.json()["telemetry"]["enabled"] is False
    assert response.json()["features"]["agentUsage"] is False


def test_ui_config_enables_agent_usage_only_in_studio(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, studio=True)

    with TestClient(app) as client:
        response = client.get("/web/ui-config")

    assert response.status_code == 200
    assert response.json()["features"]["agentUsage"] is True


def test_runtime_list_paginates_across_regions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[tuple[str, str, int]] = []
    runtimes = {
        "cn-beijing": [
            ("beijing-new", "2026-07-21T05:00:00Z"),
            ("beijing-mid", "2026-07-21T03:00:00Z"),
            ("beijing-old", "2026-07-21T01:00:00Z"),
        ],
        "cn-shanghai": [
            ("shanghai-new", "2026-07-21T06:00:00Z"),
            ("shanghai-old", "2026-07-21T02:00:00Z"),
        ],
    }

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            offset = int(getattr(request, "next_token", "") or 0)
            page_size = request.max_results
            calls.append((self.region, str(offset), page_size))
            source = runtimes[self.region]
            page = source[offset : offset + page_size]
            page_end = offset + len(page)
            return SimpleNamespace(
                agent_kit_runtimes=[
                    SimpleNamespace(
                        name=name,
                        runtime_id=f"runtime-{name}",
                        status="Ready",
                        created_at=created_at,
                        description=f"Description for {name}",
                        cpu_milli=1000,
                        memory_mb=2048,
                        tags=[],
                    )
                    for name, created_at in page
                ],
                next_token=str(page_end) if page_end < len(source) else "",
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )

    with TestClient(app) as client:
        first = client.get("/web/runtimes", params={"region": "all", "page_size": 2})
        first_calls = list(calls)
        cached_first = client.get(
            "/web/runtimes", params={"region": "all", "page_size": 2}
        )
        cached_first_calls = list(calls)
        second = client.get(
            "/web/runtimes",
            params={
                "region": "all",
                "page_size": 2,
                "next_token": first.json()["nextToken"],
            },
        )
        third = client.get(
            "/web/runtimes",
            params={
                "region": "all",
                "page_size": 2,
                "next_token": second.json()["nextToken"],
            },
        )

    assert [item["name"] for item in first.json()["runtimes"]] == [
        "shanghai-new",
        "beijing-new",
    ]
    assert first.json()["runtimes"][0]["description"] == (
        "Description for shanghai-new"
    )
    assert first.json()["runtimes"][0]["cpuMilli"] == 1000
    assert first.json()["runtimes"][0]["memoryMb"] == 2048
    assert sorted(first_calls) == [
        ("cn-beijing", "0", 2),
        ("cn-shanghai", "0", 2),
    ]
    assert cached_first.json() == first.json()
    assert cached_first_calls == first_calls
    assert first.json()["nextToken"] == "all:2"
    assert [item["name"] for item in second.json()["runtimes"]] == [
        "beijing-mid",
        "shanghai-old",
    ]
    assert second.json()["nextToken"] == "all:4"
    assert [item["name"] for item in third.json()["runtimes"]] == ["beijing-old"]
    assert third.json()["nextToken"] == ""


@pytest.mark.parametrize("scope", ["all", "mine"])
def test_runtime_list_fetches_regions_concurrently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, scope: str
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    regional_requests = Barrier(2)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_runtimes(self, _request: Any) -> SimpleNamespace:
            regional_requests.wait(timeout=2)
            return SimpleNamespace(
                agent_kit_runtimes=[
                    SimpleNamespace(
                        name=self.region,
                        runtime_id=f"runtime-{self.region}",
                        status="Ready",
                        created_at="2026-07-21T05:00:00Z",
                        tags=[SimpleNamespace(key="veadk:owner", value="developer")],
                    )
                ],
                next_token="",
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtimes",
            params={"region": "all", "page_size": 2, "scope": scope},
            headers={"X-VeADK-Local-User": "developer"},
        )

    assert response.status_code == 200
    assert {item["name"] for item in response.json()["runtimes"]} == {
        "cn-beijing",
        "cn-shanghai",
    }


def test_runtime_list_surfaces_redacted_error_chain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    access_key = "runtime-access-key-123456"
    secret_key = "runtime-secret-key-123456"
    monkeypatch.setenv("VOLCENGINE_ACCESS_KEY", access_key)
    monkeypatch.setenv("VOLCENGINE_SECRET_KEY", secret_key)

    class _FailingRuntimeClient:
        def __init__(self, **_: Any) -> None:
            pass

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            try:
                raise OSError(
                    "DNS lookup failed for agentkit.cn-beijing.example; "
                    f"secret_key={secret_key}"
                )
            except OSError as cause:
                raise RuntimeError(
                    f"Failed to ListRuntimes: network error; access_key={access_key}"
                ) from cause

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FailingRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.get("/web/runtimes", params={"region": "cn-beijing"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "Failed to ListRuntimes: network error" in detail
    assert "DNS lookup failed for agentkit.cn-beijing.example" in detail
    assert "Caused by:" in detail
    assert access_key not in detail
    assert secret_key not in detail
    assert "access_key=***" in detail
    assert "secret_key=***" in detail


def test_runtime_list_surfaces_all_regional_failures(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FailingRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_runtimes(self, _request: Any) -> SimpleNamespace:
            try:
                raise OSError(f"{self.region} DNS lookup failed")
            except OSError as cause:
                raise RuntimeError(
                    f"{self.region} control plane unavailable"
                ) from cause

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FailingRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.get("/web/runtimes", params={"region": "all"})

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "cn-beijing control plane unavailable" in detail
    assert "cn-shanghai control plane unavailable" in detail
    assert "cn-beijing DNS lookup failed" in detail
    assert "cn-shanghai DNS lookup failed" in detail


def test_viking_knowledgebases_include_agentkit_imported_bases(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path, admins="admin")
    requests: list[tuple[str, int]] = []

    class _FakeKnowledgeClient:
        def __init__(self, **kwargs: Any) -> None:
            self.region = kwargs["region"]

        def list_knowledge_bases(self, request: Any) -> SimpleNamespace:
            requests.append((request.next_token or "", request.max_results))
            if not request.next_token:
                return SimpleNamespace(
                    knowledge_bases=[
                        SimpleNamespace(
                            name="vikingkl_we4191n",
                            knowledge_id="kb-agentkit-we",
                            provider_knowledge_id="kb-yef-example-we",
                            provider_type="VIKINGDB_KNOWLEDGE",
                            description="Imported from VikingDB",
                            project_name="default",
                            region=self.region,
                            status="Ready",
                            last_update_time="2026-02-10T12:45:32Z",
                        )
                    ],
                    next_token="next-page",
                )
            return SimpleNamespace(
                knowledge_bases=[
                    SimpleNamespace(
                        name="vikingkl_35idqf7",
                        knowledge_id="kb-agentkit-35",
                        provider_knowledge_id="kb-yef-example-35",
                        provider_type="VIKINGDB_KNOWLEDGE",
                        description="Second page",
                        project_name="default",
                        region=self.region,
                        status="Ready",
                        last_update_time="2026-02-10T14:33:09Z",
                    )
                ],
                next_token="",
            )

    class _FakeKnowledgeService:
        def __init__(self, **_: Any) -> None:
            pass

        def list_collections(self, **_: Any) -> list[Any]:
            return []

    class _FakeVikingDbApi:
        def __init__(self, *_: Any, **__: Any) -> None:
            pass

        def list_vikingdb_collection(self, _request: Any) -> SimpleNamespace:
            return SimpleNamespace(collections=[], total_count=0)

    monkeypatch.setattr(
        "agentkit.sdk.knowledge.client.AgentkitKnowledgeClient",
        _FakeKnowledgeClient,
    )
    monkeypatch.setattr(
        "volcengine.viking_knowledgebase.VikingKnowledgeBaseService",
        _FakeKnowledgeService,
    )
    monkeypatch.setattr("volcenginesdkvikingdb.VIKINGDBApi", _FakeVikingDbApi)

    with TestClient(app) as client:
        response = client.get(
            "/web/viking-knowledgebases",
            headers={"X-VeADK-Local-User": "admin"},
        )

    assert response.status_code == 200
    data = response.json()
    assert requests == [("", 100), ("next-page", 100)]
    assert data["totalCount"] == 2
    items = data["items"]
    assert [item["name"] for item in items] == [
        "vikingkl_35idqf7",
        "vikingkl_we4191n",
    ]
    assert items[1]["id"] == "vikingkl_we4191n"
    assert items[1]["resourceId"] == "kb-yef-example-we"
    assert items[1]["agentkitKnowledgeId"] == "kb-agentkit-we"
    assert items[1]["sourceKind"] == "agentkit"
    assert items[1]["sourceLabel"] == "AgentKit Knowledge Base"


def test_viking_memories_list_route_uses_server_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    calls: list[dict[str, Any]] = []

    class _FakeMemoryClient:
        def __init__(self, **kwargs: Any) -> None:
            calls.append({"init": kwargs})

        def list_collections(
            self,
            *,
            project: str,
            page_number: int,
            page_size: int,
        ) -> dict[str, Any]:
            calls.append(
                {
                    "project": project,
                    "page_number": page_number,
                    "page_size": page_size,
                }
            )
            return {
                "Result": {
                    "TotalCount": 1,
                    "Collections": [
                        {
                            "CollectionName": "agent_memory",
                            "Description": "Agent memory",
                            "ProjectName": project,
                            "ResourceId": "mem-123",
                            "BuiltinEventTypes": [
                                "sys_event_v1",
                                "sys_profile_v1",
                            ],
                        }
                    ],
                }
            }

    monkeypatch.setattr(
        "veadk.integrations.ve_viking_db_memory.ve_viking_db_memory.VikingDBMemoryClient",
        _FakeMemoryClient,
    )

    with TestClient(app) as client:
        response = client.get("/web/viking-memories")

    assert response.status_code == 200
    data = response.json()
    assert calls[0]["init"]["ak"] == "ak"
    assert calls[0]["init"]["sk"] == "sk"
    assert calls[1] == {"project": "default", "page_number": 1, "page_size": 100}
    assert data["totalCount"] == 1
    assert data["items"][0] == {
        "id": "agent_memory",
        "name": "agent_memory",
        "description": "Agent memory",
        "projectName": "default",
        "region": "cn-beijing",
        "resourceId": "mem-123",
        "updatedAt": "",
        "memoryTypes": ["sys_event_v1", "sys_profile_v1"],
    }


@pytest.mark.parametrize(
    ("authorizer", "expected_authorization"),
    [
        (
            SimpleNamespace(
                key_auth=None,
                custom_jwt_authorizer=SimpleNamespace(
                    discovery_url="https://issuer.example/.well-known/openid-configuration",
                    allowed_clients=["frontend-client"],
                ),
            ),
            "Bearer validated.jwt.token",
        ),
        (
            SimpleNamespace(
                key_auth=SimpleNamespace(api_key="runtime-api-key"),
                custom_jwt_authorizer=None,
            ),
            "Bearer runtime-api-key",
        ),
    ],
)
def test_runtime_proxy_uses_authorizer_credential(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    authorizer: SimpleNamespace,
    expected_authorization: str,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    @app.middleware("http")
    async def _mark_validated_oauth_token(request: Request, call_next):
        request.state.oauth2_access_token_validated = True
        request.state.oauth2_access_token = "validated.jwt.token"
        return await call_next(request)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=authorizer,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    upstream_headers: dict[str, str] = {}
    upstream_url = ""

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {
            "content-type": "application/json",
            "x-faas-instance-name": "instance-plain",
            "x-faas-request-id": "request-plain",
        }

        async def aiter_raw(self):
            yield b'["demo_agent"]'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            nonlocal upstream_url
            upstream_url = url
            upstream_headers.update(headers)
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    async def _unexpected_get_body(_request: Request) -> bytes:
        raise AssertionError("GET proxy requests must not read the client body")

    monkeypatch.setattr(Request, "body", _unexpected_get_body)

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-proxy/runtime-1/dev/apps/demo_agent/debug/trace/"
            "session/session-1"
            "?region=cn-beijing"
        )

    assert response.status_code == 200
    assert response.json() == ["demo_agent"]
    assert upstream_url == (
        "https://runtime.example/dev/apps/demo_agent/debug/trace/session/session-1"
    )
    assert upstream_headers["Authorization"] == expected_authorization


def test_runtime_proxy_exposes_safe_instance_context(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type="public",
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {
            "content-type": "text/event-stream",
            "x-faas-instance-name": "instance-plain",
            "x-faas-request-id": "request-plain",
            "x-session-id": "must-not-leave-the-bff",
        }

        async def aiter_raw(self):
            yield b'data: {"id":"event-1","author":"agent"}\n\n'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(self, *args: Any, **kwargs: Any) -> object:
            del args, kwargs
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            del request, stream
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "agent",
                "user_id": "user-1",
                "session_id": "session-1",
                "new_message": {"role": "user", "parts": [{"text": "hello"}]},
            },
        )

    assert response.status_code == 200
    assert response.headers["x-studio-faas-instance"] == "instance-plain"
    assert response.headers["x-studio-faas-request-id"] == "request-plain"
    assert "x-session-id" not in response.headers


def test_runtime_proxy_preserves_api_region_with_distinct_runtime_region(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["region"] == "cn-beijing"

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )
    forwarded_params: dict[str, str] = {}

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b'{"items": []}'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            del method, url, headers, content
            forwarded_params.update(params)
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            del request, stream
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-proxy/runtime-1/harness/skills/spaces"
            "?region=all&_runtime_region=cn-beijing"
        )

    assert response.status_code == 200
    assert forwarded_params == {"region": "all"}


def test_runtime_proxy_accepts_post_delete_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )
    upstream_method = ""
    upstream_params: dict[str, str] = {}

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b"{}"

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            nonlocal upstream_method, upstream_params
            upstream_method = method
            upstream_params = params
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            "/web/runtime-proxy/runtime-1/apps/demo/users/user/sessions/session"
            "?region=cn-beijing&_method=DELETE"
        )

    assert response.status_code == 200
    assert upstream_method == "DELETE"
    assert upstream_params == {}


@pytest.mark.parametrize(
    (
        "network_type",
        "request_method",
        "proxy_path",
        "query",
        "provider",
        "expected_region",
        "expected_attempts",
        "succeeds_on_attempt",
        "expected_status",
    ),
    [
        (
            "private",
            "GET",
            "list-apps",
            "?region=cn-beijing",
            "volcengine",
            "cn-beijing",
            1,
            None,
            502,
        ),
        (
            "public",
            "GET",
            "list-apps",
            "?region=cn-beijing",
            "volcengine",
            "cn-beijing",
            1,
            None,
            502,
        ),
        (
            "public",
            "GET",
            "list-apps",
            "?_runtime_region=ap-southeast-1&probe_retry=connect",
            "byteplus",
            "ap-southeast-1",
            2,
            2,
            200,
        ),
        (
            "public",
            "GET",
            "apps/demo/users/user/sessions",
            "?region=cn-beijing",
            "volcengine",
            "cn-beijing",
            3,
            3,
            200,
        ),
        (
            "public",
            "HEAD",
            "apps/demo/users/user/sessions",
            "?region=cn-beijing",
            "volcengine",
            "cn-beijing",
            3,
            None,
            502,
        ),
        (
            "public",
            "POST",
            "apps/demo/users/user/sessions",
            "?region=cn-beijing",
            "volcengine",
            "cn-beijing",
            1,
            None,
            502,
        ),
    ],
)
def test_runtime_proxy_retry_policy(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    network_type: str,
    request_method: str,
    proxy_path: str,
    query: str,
    provider: str,
    expected_region: str,
    expected_attempts: int,
    succeeds_on_attempt: int | None,
    expected_status: int,
) -> None:
    if provider == "byteplus":
        monkeypatch.setenv("BYTEPLUS_ACCESS_KEY", "bp-ak")
        monkeypatch.setenv("BYTEPLUS_SECRET_KEY", "bp-sk")
        monkeypatch.setenv("BYTEPLUS_REGION", expected_region)
    app = _create_frontend_app(monkeypatch, tmp_path, provider=provider)
    runtime_client_regions: list[str] = []

    async def _noop_sleep(delay: float) -> None:
        pass

    monkeypatch.setattr("veadk.cli.cli_frontend.asyncio.sleep", _noop_sleep)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            runtime_client_regions.append(kwargs["region"])

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example",
                        network_type=network_type,
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    attempts = 0
    forwarded_params: list[dict[str, str]] = []

    class _FakeUpstreamResponse:
        def __init__(self) -> None:
            self.status_code = 200
            self.headers = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b"[]"

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            forwarded_params.append(params)
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            nonlocal attempts
            attempts += 1
            if succeeds_on_attempt == attempts:
                return _FakeUpstreamResponse()
            raise httpx.ConnectError("connect failed")

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.request(
            request_method,
            f"/web/runtime-proxy/runtime-1/{proxy_path}{query}",
        )

    assert response.status_code == expected_status
    assert runtime_client_regions == [expected_region]
    assert attempts == expected_attempts
    assert forwarded_params == [{}] * expected_attempts
    if expected_status == 200:
        assert response.json() == []
    elif request_method != "HEAD":
        assert response.json()["detail"] == (
            "runtime_private_endpoint_unreachable"
            if network_type == "private"
            else "runtime_proxy_connect_error"
        )


@pytest.mark.parametrize(
    "error_code",
    ["InvalidResource.NotFound", "InvalidAgentKitRuntime.NotFound"],
)
def test_runtime_proxy_classifies_runtime_lookup_not_found_without_raw_error(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    error_code: str,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            raise RuntimeError(f"{error_code}: protected-upstream-detail")

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                agent_kit_runtimes=[],
                next_token=None,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-proxy/runtime-1/list-apps?_runtime_region=cn-shanghai"
        )

    assert response.status_code == 404
    assert response.json() == {"detail": "runtime_not_found"}
    assert "protected-upstream-detail" not in response.text


def test_runtime_proxy_uses_exact_list_item_when_role_get_runtime_is_hidden(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    app = _create_frontend_app(monkeypatch, tmp_path)
    list_requests: list[Any] = []

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            assert kwargs["region"] == "cn-shanghai"

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            raise RuntimeError(
                "InvalidAgentKitRuntime.NotFound: protected-upstream-detail"
            )

        def list_runtimes(self, request: Any) -> SimpleNamespace:
            list_requests.append(request)
            return SimpleNamespace(
                agent_kit_runtimes=[
                    SimpleNamespace(
                        runtime_id="runtime-1",
                        name="runtime-name",
                        status="Ready",
                        current_version_number=2,
                        network_configurations=[
                            SimpleNamespace(
                                endpoint="https://runtime.example",
                                network_type="public",
                            )
                        ],
                        authorizer_configuration=SimpleNamespace(
                            key_auth=SimpleNamespace(api_key="runtime-api-key"),
                            custom_jwt_authorizer=None,
                        ),
                        tags=[],
                    )
                ],
                next_token=None,
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient",
        _FakeRuntimeClient,
    )

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b'["demo_agent"]'

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            assert method == "GET"
            assert url == "https://runtime.example/list-apps"
            assert params == {}
            assert headers["Authorization"] == "Bearer runtime-api-key"
            assert content == b""
            return object()

        async def send(
            self,
            request: object,
            *,
            stream: bool,
        ) -> _FakeUpstreamResponse:
            del request
            assert stream is True
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.get(
            "/web/runtime-proxy/runtime-1/list-apps"
            "?_runtime_region=cn-shanghai&probe_retry=connect"
        )

    assert response.status_code == 200
    assert response.json() == ["demo_agent"]
    assert len(list_requests) == 1


def test_runtime_proxy_resolves_studio_media_before_forwarding(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv("VEADK_MEDIA_LOCAL_DIR", str(tmp_path / "media"))
    app = _create_frontend_app(monkeypatch, tmp_path)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def get_runtime(self, request: Any) -> SimpleNamespace:
            return SimpleNamespace(
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )
    upstream_body = b""

    class _FakeUpstreamResponse:
        status_code = 200
        headers: ClassVar[dict[str, str]] = {"content-type": "application/json"}

        async def aiter_raw(self):
            yield b"{}"

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            pass

        def build_request(
            self,
            method: str,
            url: str,
            *,
            params: dict[str, str],
            headers: dict[str, str],
            content: bytes,
        ) -> object:
            nonlocal upstream_body
            upstream_body = content
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)
    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUB"
        "AScY42YAAAAASUVORK5CYII="
    )

    with TestClient(app) as client:
        upload = client.post(
            "/web/media",
            data={
                "app_name": "demo",
                "user_id": "user",
                "session_id": "session",
            },
            files={"file": ("cat.png", png, "image/png")},
        )
        assert upload.status_code == 200
        media = upload.json()
        response = client.post(
            "/web/runtime-proxy/runtime-1/run_sse?region=cn-beijing",
            json={
                "app_name": "demo",
                "user_id": "user",
                "session_id": "session",
                "new_message": {
                    "role": "user",
                    "parts": [
                        {
                            "fileData": {
                                "fileUri": media["uri"],
                                "mimeType": "image/png",
                            },
                            "partMetadata": {"veadkMedia": media},
                        }
                    ],
                },
            },
        )

    assert response.status_code == 200
    forwarded_part = json.loads(upstream_body)["new_message"]["parts"][0]
    assert "fileData" not in forwarded_part
    assert base64.b64decode(forwarded_part["inlineData"]["data"]) == png
    assert forwarded_part["partMetadata"]["veadkMedia"]["uri"] == media["uri"]


@pytest.mark.parametrize(
    ("upstream_path", "status_code", "chunks", "expected_completions"),
    [
        (
            "run_sse",
            200,
            [b'data: {"id":"event-1","author":"agent"}\n\n'],
            1,
        ),
        ("run_sse", 200, [b'data: {"error":"model failed"}\n\n'], 0),
        ("run_sse", 200, [b": keep-alive\n\ndata: [DONE]\n\n"], 0),
        ("run_sse", 500, [b'{"detail":"upstream failed"}'], 0),
    ],
)
def test_studio_runtime_proxy_only_schedules_successful_completed_sse(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    upstream_path: str,
    status_code: int,
    chunks: list[bytes],
    expected_completions: int,
) -> None:
    class _Automation:
        def __init__(self) -> None:
            self.started: list[Any] = []
            self.completed: list[Any] = []
            self.closed = False

        def session_started(self, activity: Any) -> None:
            self.started.append(activity)

        def session_completed(self, activity: Any) -> None:
            self.completed.append(activity)

        async def get_optimizations(self, runtime_id: str, app_name: str) -> None:
            del runtime_id, app_name

        async def close(self) -> None:
            self.closed = True

    automation = _Automation()

    class _UsageService:
        def __init__(self) -> None:
            self.recorded: list[dict[str, Any]] = []
            self.closed = False

        def record_success(self, **kwargs: Any) -> None:
            self.recorded.append(kwargs)

        async def close(self) -> None:
            self.closed = True

    usage = _UsageService()
    monkeypatch.setattr(
        "frontend.server.evaluation_automation.create_service",
        lambda **kwargs: automation,
    )
    monkeypatch.setattr(
        "frontend.server.agent_usage.create_service",
        lambda **kwargs: usage,
    )
    app = _create_frontend_app(monkeypatch, tmp_path, studio=True)

    class _FakeRuntimeClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def get_runtime(self, request: Any) -> SimpleNamespace:
            del request
            return SimpleNamespace(
                project_name="support",
                tags=[],
                network_configurations=[
                    SimpleNamespace(
                        endpoint="https://runtime.example", network_type="public"
                    )
                ],
                authorizer_configuration=SimpleNamespace(
                    key_auth=SimpleNamespace(api_key="runtime-api-key"),
                    custom_jwt_authorizer=None,
                ),
            )

    class _FakeUpstreamResponse:
        def __init__(self) -> None:
            self.status_code = status_code
            self.headers = {"content-type": "text/event-stream"}

        async def aiter_raw(self):
            for chunk in chunks:
                yield chunk

        async def aclose(self) -> None:
            pass

    class _FakeAsyncClient:
        def __init__(self, **kwargs: Any) -> None:
            del kwargs

        def build_request(self, *args: Any, **kwargs: Any) -> object:
            del args, kwargs
            return object()

        async def send(self, request: object, *, stream: bool) -> _FakeUpstreamResponse:
            del request, stream
            return _FakeUpstreamResponse()

        async def aclose(self) -> None:
            pass

    monkeypatch.setattr(
        "agentkit.sdk.runtime.client.AgentkitRuntimeClient", _FakeRuntimeClient
    )
    monkeypatch.setattr("httpx.AsyncClient", _FakeAsyncClient)

    with TestClient(app) as client:
        response = client.post(
            f"/web/runtime-proxy/runtime-1/{upstream_path}?region=cn-beijing",
            headers={"X-VeADK-Local-User": "user-1"},
            json={
                "app_name": "agent",
                "user_id": "untrusted-body-user",
                "session_id": "session-1",
                "new_message": {
                    "role": "user",
                    "parts": [{"text": "hello"}],
                },
            },
        )
        optimizations = client.get(
            "/web/evaluation/optimizations",
            headers={"X-VeADK-Local-User": "user-1"},
            params={
                "runtimeId": "runtime-1",
                "region": "cn-beijing",
                "appName": "agent",
            },
        )

    assert response.status_code == status_code
    assert optimizations.status_code == 200
    assert optimizations.json()["groups"] == []
    assert len(automation.started) == 1
    assert len(automation.completed) == expected_completions
    assert automation.closed
    assert usage.closed
    assert len(usage.recorded) == expected_completions
    if usage.recorded:
        assert usage.recorded[0]["runtime_id"] == "runtime-1"
        assert usage.recorded[0]["app_name"] == "agent"
        assert usage.recorded[0]["user_id"] == "user-1"
        assert usage.recorded[0]["display_name"] == "user-1"
        assert usage.recorded[0]["invocation_id"]
    assert automation.started[0].project_name == "support"
    assert automation.started[0].runtime_authorization.get_secret_value() == (
        "Bearer runtime-api-key"
    )
