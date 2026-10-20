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

"""Provider routing tests for Studio Sandbox sessions."""

from types import SimpleNamespace
from typing import Any

import pytest
from agentkit.platform.context import (
    reset_default_cloud_provider,
    set_default_cloud_provider,
)
from agentkit.sdk.tools.client import AgentkitToolsClient

from veadk.cli.agentkit_sandbox_region import (
    resolve_sandbox_client_region,
    sandbox_region_candidates,
)
from veadk.cli.frontend_sandbox import AgentkitSandboxGateway


def test_sandbox_regions_use_region_env_as_volcengine_preference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert sandbox_region_candidates(provider="volcengine") == (
        "cn-shanghai",
        "cn-beijing",
    )


def test_explicit_sandbox_region_preference_wins_over_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert sandbox_region_candidates("cn-beijing", provider="volcengine") == (
        "cn-beijing",
        "cn-shanghai",
    )


def test_sandbox_client_region_uses_region_env_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("AGENTKIT_SANDBOX_REGION", raising=False)
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert resolve_sandbox_client_region("", provider="volcengine") == "cn-shanghai"


def test_sandbox_client_region_prefers_explicit_and_sandbox_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AGENTKIT_SANDBOX_REGION", "cn-shanghai")
    monkeypatch.setenv("REGION", "cn-beijing")

    assert (
        resolve_sandbox_client_region("cn-beijing", provider="volcengine")
        == "cn-beijing"
    )
    assert resolve_sandbox_client_region("", provider="volcengine") == "cn-shanghai"


def test_byteplus_sandbox_client_region_ignores_volcengine_region_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert resolve_sandbox_client_region("", provider="byteplus") == "ap-southeast-1"


def test_byteplus_sandbox_regions_never_fall_back_to_volcengine(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("REGION", "cn-shanghai")

    assert sandbox_region_candidates(
        "cn-beijing",
        provider="byteplus",
    ) == ("ap-southeast-1",)


@pytest.mark.asyncio
async def test_byteplus_create_session_uses_byteplus_agentkit_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, str, Any]] = []

    def _call(client: Any, method_name: str, request: Any) -> SimpleNamespace:
        calls.append((client, method_name, request))
        return SimpleNamespace(
            session_id="session-id",
            endpoint="https://sandbox.byteplus.example.com",
            user_session_id=request.user_session_id,
        )

    monkeypatch.setattr("veadk.cli.frontend_sandbox.call_session_client", _call)
    token = set_default_cloud_provider("byteplus")
    try:
        gateway = AgentkitSandboxGateway(
            lambda region: AgentkitToolsClient(
                access_key="byteplus-ak",
                secret_key="byteplus-sk",
                region=region,
            ),
            region_candidates=sandbox_region_candidates(
                "ap-southeast-1",
                provider="byteplus",
            ),
        )
        session = await gateway.create_session("tool-id", display_name="Dev")
    finally:
        reset_default_cloud_provider(token)

    assert session.region == "ap-southeast-1"
    assert len(calls) == 1
    client, method_name, request = calls[0]
    assert method_name == "create_session"
    assert client.host == "agentkit.ap-southeast-1.byteplusapi.com"
    assert client.api_version == "2025-10-30"
    assert request.tool_id == "tool-id"
