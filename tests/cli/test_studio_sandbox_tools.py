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

"""Tests for deploy-time Studio Sandbox Tool provisioning."""

import os
from types import SimpleNamespace
from typing import cast
from unittest.mock import patch

import pytest

from veadk.cli.studio_sandbox_tools import (
    ensure_studio_agent_model_credential,
    ensure_studio_agent_tool,
    ensure_studio_code_env_tool,
    ensure_studio_dev_env_tool,
    studio_sandbox_agent_model_name,
    studio_sandbox_model_base_url,
)


def test_ensure_studio_code_env_tool_reuses_ready_exact_name() -> None:
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="veadk-studio-demo-chat-12345678",
                    project_name="default",
                    tool_type="CodeEnv",
                    tool_id="tool-existing",
                )
            ],
            next_token=None,
        ),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("ready Tool must be reused")
        ),
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-12345678",
            client=client,
            timeout_seconds=0,
        )
        == "tool-existing"
    )


def test_ensure_studio_code_env_tool_creates_ready_code_env() -> None:
    requests: list[object] = []

    def _create(request: object) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(tool_id="tool-created")

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=_create,
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-skill-12345678",
            client=client,
            timeout_seconds=0,
        )
        == "tool-created"
    )
    request = requests[0]
    assert getattr(request, "name") == "veadk-studio-demo-skill-12345678"
    assert getattr(request, "tool_type") == "CodeEnv"
    assert getattr(request, "project_name") == "default"
    assert getattr(request, "cpu_milli") == 4000
    assert getattr(request, "memory_mb") == 8192
    assert getattr(request, "envs") is None


@pytest.mark.parametrize(
    ("provider", "region", "expected_image"),
    [
        (
            "volcengine",
            "cn-beijing",
            "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/devenv:0.0.1",
        ),
        (
            "byteplus",
            "ap-southeast-1",
            "enterprise-public-ap-southeast-1.cr.volces.com/vefaas-public/devenv:0.0.1",
        ),
    ],
)
def test_ensure_studio_dev_env_tool_creates_complete_shared_environment(
    provider: str,
    region: str,
    expected_image: str,
) -> None:
    requests: list[object] = []

    def _get_tool(_: object) -> SimpleNamespace:
        return SimpleNamespace(
            status="Ready",
            image_url=expected_image,
            command="/opt/gem/run.sh",
            port=8080,
            cpu_milli=4000,
            memory_mb=8192,
        )

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=_get_tool,
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id="tool-devenv")
        ),
    )

    assert (
        ensure_studio_dev_env_tool(
            name="veadk-studio-demo-dev-12345678",
            provider=provider,
            region=region,
            client=client,
            timeout_seconds=0,
        )
        == "tool-devenv"
    )
    request = requests[0]
    assert request.tool_type == "DevEnv"
    assert request.image_url == expected_image
    assert request.command == "/opt/gem/run.sh"
    assert request.port == 8080
    assert request.cpu_milli == 4000
    assert request.memory_mb == 8192


def test_ensure_studio_dev_env_tool_updates_an_incomplete_existing_tool() -> None:
    updates: list[object] = []

    def _get_tool(_: object) -> SimpleNamespace:
        if updates:
            return SimpleNamespace(
                status="Ready",
                image_url=(
                    "enterprise-public-ap-southeast-1.cr.volces.com/"
                    "vefaas-public/devenv:0.0.1"
                ),
                command="/opt/gem/run.sh",
                port=8080,
                cpu_milli=4000,
                memory_mb=8192,
            )
        return SimpleNamespace(
            status="Ready",
            image_url="",
            command="",
            port=0,
            cpu_milli=1000,
            memory_mb=2048,
        )

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="veadk-studio-demo-dev-12345678",
                    project_name="default",
                    tool_type="DevEnv",
                    tool_id="dev-tool",
                )
            ],
            next_token=None,
        ),
        get_tool=_get_tool,
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("existing DevEnv Tool must be reused")
        ),
        update_tool=updates.append,
    )

    assert (
        ensure_studio_dev_env_tool(
            name="veadk-studio-demo-dev-12345678",
            provider="byteplus",
            region="ap-southeast-1",
            client=client,
            timeout_seconds=0,
        )
        == "dev-tool"
    )
    assert len(updates) == 1
    request = updates[0]
    assert getattr(request, "tool_id") == "dev-tool"
    assert getattr(request, "tool_type") == "DevEnv"
    assert getattr(request, "image_url") == (
        "enterprise-public-ap-southeast-1.cr.volces.com/vefaas-public/devenv:0.0.1"
    )
    assert getattr(request, "command") == "/opt/gem/run.sh"
    assert getattr(request, "port") == 8080
    assert getattr(request, "cpu_milli") == 4000
    assert getattr(request, "memory_mb") == 8192


def test_ensure_studio_dev_env_tool_reuses_a_complete_existing_tool() -> None:
    update_tool = pytest.fail
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="veadk-studio-demo-dev-12345678",
                    project_name="default",
                    tool_type="DevEnv",
                    tool_id="dev-tool",
                )
            ],
            next_token=None,
        ),
        get_tool=lambda _: SimpleNamespace(
            status="Ready",
            image_url=(
                "enterprise-public-cn-beijing.cr.volces.com/vefaas-public/devenv:0.0.1"
            ),
            command="/opt/gem/run.sh",
            port=8080,
            cpu_milli=4000,
            memory_mb=8192,
        ),
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("existing DevEnv Tool must be reused")
        ),
        update_tool=update_tool,
    )

    assert (
        ensure_studio_dev_env_tool(
            name="veadk-studio-demo-dev-12345678",
            provider="volcengine",
            region="cn-beijing",
            client=client,
            timeout_seconds=0,
        )
        == "dev-tool"
    )


@pytest.mark.parametrize(
    ("kind", "tool_type"),
    [("openclaw", "ArkClawEnv"), ("hermes", "HermesEnv")],
)
def test_ensure_studio_agent_tool_creates_managed_tool(
    kind: str,
    tool_type: str,
) -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id=f"tool-{kind}")
        ),
    )

    assert (
        ensure_studio_agent_tool(
            name=f"veadk-studio-demo-{kind}-12345678",
            kind=kind,
            model_name="doubao-seed-evolving",
            client=client,
            timeout_seconds=0,
        )
        == f"tool-{kind}"
    )
    request = requests[0]
    assert request.tool_type == tool_type
    assert request.model_agent_name == "doubao-seed-evolving"
    assert request.envs is None


def test_agent_model_credential_is_bound_to_tool_as_complete_env_set() -> None:
    access_key = os.urandom(16).hex()
    model_api_key = os.urandom(24).hex()
    secret_key = os.urandom(24).hex()
    updates: list[object] = []
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[SimpleNamespace(key="EXISTING_ENV", value="kept")]
        ),
        update_tool=updates.append,
    )

    with patch(
        "veadk.auth.veauth.ark_veauth.get_ark_token",
        return_value=model_api_key,
    ):
        ensure_studio_agent_model_credential(
            tool_id="tool-openclaw",
            kind="openclaw",
            model_name="doubao-seed-evolving",
            access_key=access_key,
            secret_key=secret_key,
            client=client,
        )

    assert len(updates) == 1
    assert getattr(updates[0], "model_agent_name") == "doubao-seed-evolving"
    updated_envs = cast(list[object], getattr(updates[0], "envs"))
    envs = {getattr(item, "key"): getattr(item, "value") for item in updated_envs}
    assert envs == {
        "EXISTING_ENV": "kept",
        "MODEL_AGENT_API_KEY": model_api_key,
        "MODEL_AGENT_NAME": "doubao-seed-evolving",
        "MODEL_AGENT_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
    }


def test_byteplus_agent_model_configuration() -> None:
    assert studio_sandbox_agent_model_name("byteplus") == ("dola-seed-2-1-turbo-260628")
    assert studio_sandbox_model_base_url("byteplus") == (
        "https://ark.ap-southeast.bytepluses.com/api/v3"
    )


def test_volcengine_agent_model_configuration() -> None:
    assert studio_sandbox_agent_model_name("volcengine") == (
        "doubao-seed-2-1-pro-260628"
    )
