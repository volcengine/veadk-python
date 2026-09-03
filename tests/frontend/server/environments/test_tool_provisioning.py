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

from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.environments import (
    _create_environment_tools_client,
    _environment_tool_model_env,
)
from frontend.server.environments.tool_provisioning import (
    AgentkitEnvironmentToolProvisioner,
)


@pytest.mark.parametrize(
    "provider,input_region,expected_region,expected_host",
    [
        ("volcengine", "cn-beijing", "cn-beijing", "open.volcengineapi.com"),
        ("byteplus", "cn-beijing", "ap-southeast-1", ""),
    ],
)
def test_environment_tools_client_is_provider_scoped(
    monkeypatch: pytest.MonkeyPatch,
    provider: Any,
    input_region: str,
    expected_region: str,
    expected_host: str,
) -> None:
    created: dict[str, Any] = {}

    class FakeClient:
        def set_host(self, host: str) -> None:
            created["host"] = host

    def fake_create(client_type: Any, *, provider: str, **kwargs: Any) -> Any:
        created.update(client_type=client_type, provider=provider, kwargs=kwargs)
        return FakeClient()

    monkeypatch.setattr(
        "frontend.server.environments.create_agentkit_client",
        fake_create,
    )

    _create_environment_tools_client(
        provider,
        input_region,
        lambda: ("ak", "sk", "token"),
    )

    assert created["provider"] == provider
    assert created["kwargs"] == {
        "access_key": "ak",
        "secret_key": "sk",
        "region": expected_region,
        "session_token": "token",
    }
    assert created.get("host", "") == expected_host


@pytest.mark.parametrize(
    "provider,region,expected_model,expected_base_url",
    [
        (
            "volcengine",
            "cn-beijing",
            "doubao-seed-2-1-pro-260628",
            "https://ark.cn-beijing.volces.com/api/v3",
        ),
        (
            "byteplus",
            "ap-southeast-1",
            "dola-seed-2-1-turbo-260628",
            "https://ark.ap-southeast.bytepluses.com/api/v3",
        ),
    ],
)
def test_environment_tool_model_env_uses_provider_defaults(
    monkeypatch: pytest.MonkeyPatch,
    provider: Any,
    region: str,
    expected_model: str,
    expected_base_url: str,
) -> None:
    token_calls: list[dict[str, Any]] = []

    def fake_get_ark_token(**kwargs: Any) -> str:
        token_calls.append(kwargs)
        return "resolved-model-key"

    monkeypatch.setattr(
        "frontend.server.environments.get_ark_token",
        fake_get_ark_token,
    )

    envs = _environment_tool_model_env(
        provider=provider,
        region=region,
        source={},
        resolve_credentials=lambda: ("ak", "sk", "token"),
    )

    assert envs == {
        "MODEL_AGENT_API_KEY": "resolved-model-key",
        "MODEL_AGENT_NAME": expected_model,
        "MODEL_AGENT_API_BASE": expected_base_url,
        "MODEL_AGENT_BASE_URL": expected_base_url,
        "MODEL_AGENT_PROVIDER": "openai",
        "CODEX_API_KEY": "resolved-model-key",
        "CODEX_BASE_URL": expected_base_url,
        "CODEX_MODEL": expected_model,
    }
    assert token_calls == [
        {
            "region": region,
            "api_key_name": None,
            "cloud_provider": provider,
            "access_key": "ak",
            "secret_key": "sk",
            "session_token": "token",
        }
    ]


def test_environment_tool_model_env_prefers_explicit_studio_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_token_lookup(**_kwargs: Any) -> str:
        raise AssertionError("explicit model key must avoid a cloud lookup")

    monkeypatch.setattr(
        "frontend.server.environments.get_ark_token",
        unexpected_token_lookup,
    )

    envs = _environment_tool_model_env(
        provider="volcengine",
        region="cn-beijing",
        source={
            "MODEL_AGENT_API_KEY": "explicit-key",
            "MODEL_AGENT_NAME": "explicit-model",
            "MODEL_AGENT_API_BASE": "https://models.example/api/v3/",
            "MODEL_AGENT_PROVIDER": "openai",
            "CODEX_API_KEY": "fallback-key",
            "CODEX_BASE_URL": "https://fallback.example/api/v3",
            "CODEX_MODEL": "fallback-model",
        },
        resolve_credentials=lambda: ("ak", "sk", "token"),
    )

    assert envs["MODEL_AGENT_API_KEY"] == "explicit-key"
    assert envs["MODEL_AGENT_NAME"] == "explicit-model"
    assert envs["MODEL_AGENT_API_BASE"] == "https://models.example/api/v3"
    assert envs["MODEL_AGENT_BASE_URL"] == "https://models.example/api/v3"
    assert envs["CODEX_API_KEY"] == "explicit-key"
    assert envs["CODEX_BASE_URL"] == "https://models.example/api/v3"
    assert envs["CODEX_MODEL"] == "explicit-model"


@pytest.mark.asyncio
async def test_provisioner_creates_private_tool_and_waits_until_ready() -> None:
    client = _FakeToolsClient(statuses=["Creating", "Ready"])
    sleeps: list[float] = []
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda provider, region: _assert_client_location(
            client, provider, region, "volcengine", "cn-beijing"
        ),
        sleep=lambda seconds: sleeps.append(seconds),
        poll_interval_seconds=0.25,
    )

    state = await provisioner.ensure_ready(
        image="registry.example/aio:v1",
        provider="volcengine",
        region="cn-beijing",
    )

    assert state.tool_id == "tool-1"
    assert state.status == "ready"
    assert len(client.created) == 1
    request = client.created[0]
    assert request.tool_type == "Private"
    assert request.image_url == "registry.example/aio:v1"
    assert request.command == "/opt/gem/run.sh"
    assert request.port == 8080
    envs = {item.key: item.value for item in request.envs}
    assert len(envs) == 57
    assert envs["SANDBOX_SRV_PORT"] == "8091"
    assert envs["VNC_SERVER_PORT"] == "5900"
    assert envs["WAIT_PORTS"] == "8091"
    assert envs["PUBLIC_PORT"] == "8080"
    assert envs["FAAS_SANDBOX_RUNTIME_INJECTION_ENABLE_SANDBOXD"] == "false"
    assert sleeps == [0.25]


@pytest.mark.asyncio
async def test_provisioner_injects_model_environment_on_create() -> None:
    client = _FakeToolsClient(statuses=["Ready"])
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda _provider, _region: client,
        model_environment_resolver=lambda provider, region: {
            "MODEL_AGENT_API_KEY": f"key-for-{provider}",
            "MODEL_AGENT_NAME": "test-model",
            "MODEL_AGENT_API_BASE": f"https://models.example/{region}",
            "MODEL_AGENT_BASE_URL": f"https://models.example/{region}",
            "MODEL_AGENT_PROVIDER": "openai",
            "CODEX_API_KEY": f"key-for-{provider}",
            "CODEX_BASE_URL": f"https://models.example/{region}",
            "CODEX_MODEL": "test-model",
            "IGNORED_SECRET": "must-not-be-injected",
        },
        poll_interval_seconds=0,
    )

    await provisioner.ensure_ready(
        image="registry.example/aio:model-env",
        provider="byteplus",
        region="ap-southeast-1",
    )

    envs = {item.key: item.value for item in client.created[0].envs}
    assert envs["MODEL_AGENT_API_KEY"] == "key-for-byteplus"
    assert envs["MODEL_AGENT_NAME"] == "test-model"
    assert envs["MODEL_AGENT_API_BASE"] == ("https://models.example/ap-southeast-1")
    assert envs["MODEL_AGENT_BASE_URL"] == ("https://models.example/ap-southeast-1")
    assert envs["MODEL_AGENT_PROVIDER"] == "openai"
    assert envs["CODEX_API_KEY"] == "key-for-byteplus"
    assert envs["CODEX_BASE_URL"] == "https://models.example/ap-southeast-1"
    assert envs["CODEX_MODEL"] == "test-model"
    assert "IGNORED_SECRET" not in envs
    assert client.created[0].model_agent_name == "test-model"


@pytest.mark.asyncio
async def test_provisioner_resolves_credentials_off_the_event_loop() -> None:
    import threading

    event_loop_thread = threading.get_ident()
    resolver_threads: list[int] = []
    client = _FakeToolsClient(statuses=["Ready"])
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda _provider, _region: client,
        model_environment_resolver=lambda _provider, _region: (
            resolver_threads.append(threading.get_ident()) or {}
        ),
        poll_interval_seconds=0,
    )

    await provisioner.ensure_ready(
        image="registry.example/aio:threaded-credentials",
        provider="volcengine",
        region="cn-beijing",
    )

    assert resolver_threads
    assert resolver_threads[0] != event_loop_thread


@pytest.mark.asyncio
async def test_provisioner_updates_changed_model_env_and_preserves_other_envs() -> None:
    client = _FakeToolsClient(statuses=["Ready", "Ready"])
    client.tools.append(
        SimpleNamespace(
            name="studio-env-6ad974efe5bc7eda",
            project_name="default",
            tool_type="Private",
            tool_id="tool-existing",
            image_url="registry.example/aio:model-update",
            command="/opt/gem/run.sh",
            port=8080,
            envs=[
                SimpleNamespace(key="MODEL_AGENT_API_KEY", value="old-key"),
                SimpleNamespace(key="UNRELATED_ENV", value="preserved"),
            ],
            status="Ready",
        )
    )
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda _provider, _region: client,
        model_environment_resolver=lambda _provider, _region: {
            "MODEL_AGENT_API_KEY": "new-key",
            "MODEL_AGENT_NAME": "new-model",
        },
        poll_interval_seconds=0,
    )

    await provisioner.ensure_ready(
        image="registry.example/aio:model-update",
        provider="volcengine",
        region="cn-beijing",
    )

    assert len(client.updated) == 1
    envs = {item.key: item.value for item in client.updated[0].envs}
    assert envs["MODEL_AGENT_API_KEY"] == "new-key"
    assert envs["MODEL_AGENT_NAME"] == "new-model"
    assert envs["UNRELATED_ENV"] == "preserved"
    assert client.updated[0].model_agent_name == "new-model"


@pytest.mark.asyncio
async def test_provisioner_resumes_creating_tool_without_restarting_update() -> None:
    client = _FakeToolsClient(statuses=["Creating", "Ready"])
    client.tools.append(
        SimpleNamespace(
            name="studio-env-6ad974efe5bc7eda",
            project_name="default",
            tool_type="Private",
            tool_id="tool-existing",
            image_url="registry.example/aio:model-update",
            command="/opt/gem/run.sh",
            port=8080,
            envs=[SimpleNamespace(key="MODEL_AGENT_API_KEY", value="old-key")],
            status="Creating",
        )
    )
    client.list_tools = lambda _request: pytest.fail(
        "a persisted Tool ID must bypass name lookup"
    )
    observed: list[tuple[str, str]] = []
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda _provider, _region: client,
        model_environment_resolver=lambda _provider, _region: {
            "MODEL_AGENT_API_KEY": "new-key",
        },
        poll_interval_seconds=0,
    )

    state = await provisioner.ensure_ready(
        image="registry.example/aio:model-update",
        provider="volcengine",
        region="cn-beijing",
        existing_tool_id="tool-existing",
        on_created=lambda tool: _record_tool_state(observed, tool),
    )

    assert state.tool_id == "tool-existing"
    assert observed == [("tool-existing", "creating")]
    assert client.updated == []


async def _record_tool_state(observed: list[tuple[str, str]], tool: Any) -> None:
    observed.append((tool.tool_id, tool.status))


def test_provisioner_default_ready_timeout_allows_slow_first_creation() -> None:
    provisioner = AgentkitEnvironmentToolProvisioner(lambda _provider, _region: None)

    assert provisioner._timeout_seconds >= 300


@pytest.mark.asyncio
async def test_provisioner_reuses_matching_tool_for_byteplus() -> None:
    client = _FakeToolsClient(statuses=["Ready", "Ready"])
    client.tools.append(
        SimpleNamespace(
            name="studio-env-906899d4750340f4",
            project_name="default",
            tool_type="Private",
            tool_id="tool-existing",
            image_url="registry.example/aio:v2",
            command="/opt/gem/run.sh",
            port=8080,
            envs=[],
            status="Ready",
        )
    )
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda provider, region: _assert_client_location(
            client, provider, region, "byteplus", "ap-southeast-1"
        ),
        poll_interval_seconds=0,
    )

    state = await provisioner.ensure_ready(
        image="registry.example/aio:v2",
        provider="byteplus",
        region="ap-southeast-1",
    )

    assert state.tool_id == "tool-existing"
    assert state.status == "ready"
    assert client.created == []
    assert len(client.updated) == 1
    updated_envs = {item.key: item.value for item in client.updated[0].envs}
    assert len(updated_envs) == 57
    assert updated_envs["SANDBOX_SRV_PORT"] == "8091"
    assert updated_envs["VNC_SERVER_PORT"] == "5900"
    assert updated_envs["WAIT_PORTS"] == "8091"
    assert updated_envs["PUBLIC_PORT"] == "8080"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "provider,region",
    [("volcengine", "cn-beijing"), ("byteplus", "ap-southeast-1")],
)
async def test_provisioner_recreates_a_deleted_persisted_tool(
    provider: str,
    region: str,
) -> None:
    client = _FakeToolsClient(statuses=["Ready"])
    provisioner = AgentkitEnvironmentToolProvisioner(
        lambda actual_provider, actual_region: _assert_client_location(
            client, actual_provider, actual_region, provider, region
        ),
        poll_interval_seconds=0,
    )

    state = await provisioner.ensure_ready(
        image="registry.example/aio:repaired",
        provider=provider,
        region=region,
        existing_tool_id="tool-deleted",
    )

    assert state.tool_id == "tool-1"
    assert state.status == "ready"
    assert len(client.created) == 1
    assert client.created[0].image_url == "registry.example/aio:repaired"


def _assert_client_location(
    client: Any,
    provider: str,
    region: str,
    expected_provider: str,
    expected_region: str,
) -> Any:
    assert provider == expected_provider
    assert region == expected_region
    return client


class _FakeToolsClient:
    def __init__(self, *, statuses: list[str]) -> None:
        self.statuses = statuses
        self.tools: list[Any] = []
        self.created: list[Any] = []
        self.updated: list[Any] = []

    def list_tools(self, request: Any) -> Any:
        name = request.filters[0].values[0]
        return SimpleNamespace(
            tools=[item for item in self.tools if item.name == name],
            next_token="",
        )

    def create_tool(self, request: Any) -> Any:
        self.created.append(request)
        tool = SimpleNamespace(
            name=request.name,
            project_name=request.project_name,
            tool_type=request.tool_type,
            tool_id="tool-1",
            image_url=request.image_url,
            command=request.command,
            port=request.port,
            envs=request.envs,
            status="Creating",
        )
        self.tools.append(tool)
        return tool

    def update_tool(self, request: Any) -> Any:
        self.updated.append(request)
        tool = next(item for item in self.tools if item.tool_id == request.tool_id)
        tool.image_url = request.image_url
        tool.command = request.command
        tool.port = request.port
        tool.envs = request.envs
        tool.status = "Creating"
        return tool

    def get_tool(self, request: Any) -> Any:
        tool = next(item for item in self.tools if item.tool_id == request.tool_id)
        tool.status = self.statuses.pop(0)
        return tool
