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

import pytest
from frontend.server.workspace_tool import workspace_tool_request


@pytest.mark.parametrize(
    "provider,language", [("volcengine", "zh-CN"), ("byteplus", "en")]
)
def test_cloud_tool_preserves_native_entrypoint_and_model_configuration(
    provider, language
):
    model = {
        "MODEL_AGENT_NAME": "test-model",
        "MODEL_AGENT_BASE_URL": "https://example.test/v3",
        "MODEL_AGENT_API_KEY": "test-key",
    }
    image = "registry.example.test/studio/sandbox@sha256:" + "a" * 64
    request = workspace_tool_request(image, provider, model)
    env = {x.key: x.value for x in request.envs}
    assert len(request.command) <= 255
    assert "STUDIO_EDITOR_BOOTSTRAP" not in env
    assert request.image_url == image
    assert request.command == "/opt/gem/run.sh"
    assert request.tool_type == "Private"
    assert request.enable_snapshot is True
    assert request.cpu_milli == 8000
    assert request.memory_mb == 16384
    assert env["VSCODE_LANG"] == language
    assert {k: env[k] for k in model} == model
    assert "CODEX_REAL_BIN" not in env
    assert request.authorizer_configuration.key_auth.api_key_location == "Header"


def test_missing_model_configuration_fails_before_creating_tool():
    with pytest.raises(ValueError):
        workspace_tool_request("registry.example/studio:v1", "volcengine", {})


@pytest.mark.parametrize(
    "provider,region,registry",
    [
        ("volcengine", "cn-beijing", "enterprise-public-cn-beijing"),
        ("volcengine", "cn-shanghai", "enterprise-cn-shanghai-cn-shanghai"),
        ("byteplus", "ap-southeast-1", "enterprise-public-ap-southeast-1"),
    ],
)
def test_workspace_image_matches_deployment_region(
    monkeypatch, provider, region, registry
):
    from frontend.server.workspace_tool import resolve_workspace_image

    monkeypatch.delenv("STUDIO_WORKSPACE_IMAGE", raising=False)
    assert resolve_workspace_image(provider, region) == (
        f"{registry}.cr.volces.com/vefaas-public/agentkit-sandbox:studio-sandbox-1.0.1"
    )


def test_workspace_image_override_and_unknown_region(monkeypatch):
    from frontend.server.workspace_tool import resolve_workspace_image

    monkeypatch.delenv("STUDIO_WORKSPACE_IMAGE", raising=False)
    with pytest.raises(ValueError, match="STUDIO_WORKSPACE_IMAGE"):
        resolve_workspace_image("byteplus", "unknown")
    monkeypatch.setenv("STUDIO_WORKSPACE_IMAGE", " registry.example/studio:v2 ")
    assert (
        resolve_workspace_image("byteplus", "unknown") == "registry.example/studio:v2"
    )


def test_update_preserves_existing_workspace(monkeypatch):
    from frontend.server import workspace_tool

    def unexpected(**kwargs):
        pytest.fail("Existing workspace must not be replaced")

    monkeypatch.setattr(workspace_tool, "provision_workspace_tool", unexpected)
    assert (
        workspace_tool.workspace_update_environment(
            {"STUDIO_WORKSPACE_TOOL_ID": "t-existing"},
            provider="volcengine",
            region="cn-beijing",
            access_key="test",
            secret_key="test",
        )
        == {}
    )


@pytest.mark.parametrize(
    "provider,region",
    [
        ("volcengine", "cn-beijing"),
        ("volcengine", "cn-shanghai"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_update_fills_missing_workspace(monkeypatch, provider, region):
    from frontend.server import workspace_tool

    calls = []

    def provision(**kwargs):
        calls.append(kwargs)
        return "t-workspace"

    monkeypatch.setattr(workspace_tool, "provision_workspace_tool", provision)
    result = workspace_tool.workspace_update_environment(
        {"STUDIO_WORKSPACE_IMAGE": "registry.example/custom:v1"},
        provider=provider,
        region=region,
        access_key="test",
        secret_key="test",
    )
    assert result == {"STUDIO_WORKSPACE_TOOL_ID": "t-workspace"}
    assert calls[0]["provider"] == provider
    assert calls[0]["region"] == region
    assert calls[0]["image"] == "registry.example/custom:v1"


def test_update_provision_failure_is_not_ignored(monkeypatch):
    from frontend.server import workspace_tool

    def fail(**kwargs):
        raise RuntimeError("Provisioning failed")

    monkeypatch.setattr(workspace_tool, "provision_workspace_tool", fail)
    with pytest.raises(RuntimeError, match="Provisioning failed"):
        workspace_tool.workspace_update_environment(
            {},
            provider="volcengine",
            region="cn-beijing",
            access_key="test",
            secret_key="test",
        )


def test_old_release_startup_persists_binding_without_replacing_function_env(
    monkeypatch,
):
    from types import SimpleNamespace
    from unittest.mock import Mock
    from frontend.server import workspace_tool

    monkeypatch.setenv("VEADK_STUDIO_FUNCTION_ID", "fn-studio")
    monkeypatch.setenv("VEADK_STUDIO_DEPLOY_REGION", "cn-shanghai")
    client = Mock()
    client.get_function.return_value = SimpleNamespace(
        envs=[
            SimpleNamespace(key="EXISTING", value="keep"),
        ]
    )
    monkeypatch.setattr(
        "veadk.integrations.ve_faas.ve_faas.VeFaaS",
        lambda **kwargs: SimpleNamespace(client=client),
    )
    monkeypatch.setattr(
        workspace_tool, "provision_workspace_tool", lambda **kwargs: "t-new"
    )
    assert (
        workspace_tool.repair_deployed_workspace_binding(
            provider="volcengine",
            resolve_credentials=lambda: ("ak", "sk", ""),
        )
        == "t-new"
    )
    env = {
        item.key: item.value for item in client.update_function.call_args.args[0].envs
    }
    assert env == {"EXISTING": "keep", "STUDIO_WORKSPACE_TOOL_ID": "t-new"}
    client.release.assert_called_once()
    client.get_function.return_value.envs.append(
        SimpleNamespace(key="STUDIO_WORKSPACE_TOOL_ID", value="t-new")
    )
    client.reset_mock()
    assert (
        workspace_tool.repair_deployed_workspace_binding(
            provider="volcengine",
            resolve_credentials=lambda: ("ak", "sk", ""),
        )
        == "t-new"
    )
    client.update_function.assert_not_called()
    client.release.assert_not_called()


@pytest.mark.parametrize(
    "provider,region",
    [
        ("volcengine", "cn-beijing"),
        ("volcengine", "cn-shanghai"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_missing_workspace_update_injects_model_credentials(
    monkeypatch, provider, region
):
    from types import SimpleNamespace

    from frontend.server import workspace_tool

    captured = {}
    credentials = {
        "access_key": "test-ak",
        "secret_key": "test-sk",
        "session_token": "test-session",
        "region": region,
    }

    class Client:
        def __init__(self, **kwargs):
            assert kwargs == credentials

        def list_tools(self, request):
            return SimpleNamespace(tools=[])

        def create_tool(self, request):
            captured["request"] = request
            return SimpleNamespace(tool_id="t-configured")

        def get_tool(self, request):
            return SimpleNamespace(status="Ready")

    def get_token(**kwargs):
        assert kwargs == {**credentials, "cloud_provider": provider}
        return "test-model-token"

    monkeypatch.setattr("agentkit.sdk.tools.client.AgentkitToolsClient", Client)
    monkeypatch.setattr("veadk.auth.veauth.ark_veauth.get_ark_token", get_token)
    result = workspace_tool.workspace_update_environment(
        {}, provider=provider, **credentials
    )
    assert result == {"STUDIO_WORKSPACE_TOOL_ID": "t-configured"}
    request = captured["request"]
    env = {item.key: item.value for item in request.envs}
    assert env["MODEL_AGENT_API_KEY"] == "test-model-token"
    assert env["MODEL_AGENT_NAME"]
    assert env["MODEL_AGENT_BASE_URL"].startswith("https://")
    assert request.enable_snapshot is True
