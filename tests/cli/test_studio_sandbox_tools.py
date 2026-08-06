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
    ensure_studio_tool_snapshot,
)


def test_ensure_studio_code_env_tool_reuses_ready_exact_name() -> None:
    snapshot_enabled = False

    def _update(request: object) -> SimpleNamespace:
        nonlocal snapshot_enabled
        assert request.model_dump(by_alias=True, exclude_none=True) == {
            "EnableSnapshot": True,
            "ToolId": "tool-existing",
        }
        snapshot_enabled = True
        return SimpleNamespace(tool_id="tool-existing")

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
        get_tool=lambda _: SimpleNamespace(
            status="Ready", enable_snapshot=snapshot_enabled
        ),
        update_tool=_update,
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("ready Tool must be reused")
        ),
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-12345678",
            client=client,
            timeout_seconds=1,
            poll_interval=0,
            sleep=lambda _: None,
        )
        == "tool-existing"
    )


def test_ensure_studio_code_env_tool_creates_ready_code_env() -> None:
    requests: list[object] = []
    mutation_slots: list[None] = []

    def _create(request: object) -> SimpleNamespace:
        requests.append(request)
        return SimpleNamespace(tool_id="tool-created")

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=True),
        create_tool=_create,
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-skill-12345678",
            client=client,
            timeout_seconds=0,
            before_mutation=lambda: mutation_slots.append(None),
        )
        == "tool-created"
    )
    request = requests[0]
    assert mutation_slots == [None]
    assert request.name == "veadk-studio-demo-skill-12345678"
    assert request.tool_type == "CodeEnv"
    assert request.project_name == "default"
    assert request.cpu_milli == 4000
    assert request.memory_mb == 8192
    assert request.enable_snapshot is True
    assert request.envs is None


def test_ensure_studio_code_env_tool_explicitly_disables_snapshots() -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=False),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id="tool-temporary")
        ),
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-temporary-12345678",
            client=client,
            timeout_seconds=0,
            enable_snapshot=False,
        )
        == "tool-temporary"
    )
    assert requests[0].enable_snapshot is False


@pytest.mark.parametrize(
    ("kind", "tool_type"),
    [("openclaw", "ArkClawEnv"), ("hermes", "HermesEnv")],
)
def test_ensure_studio_agent_tool_creates_managed_tool(
    kind: str,
    tool_type: str,
) -> None:
    requests: list[object] = []
    mutation_slots: list[None] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=True),
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
            before_mutation=lambda: mutation_slots.append(None),
        )
        == f"tool-{kind}"
    )
    request = requests[0]
    assert mutation_slots == [None]
    assert request.tool_type == tool_type
    assert request.model_agent_name == "doubao-seed-evolving"
    assert request.enable_snapshot is True
    assert request.envs is None


def test_ensure_studio_agent_tool_explicitly_disables_snapshots() -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=False),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id="tool-temporary")
        ),
    )

    assert (
        ensure_studio_agent_tool(
            name="veadk-studio-demo-openclaw-temporary-12345678",
            kind="openclaw",
            model_name="doubao-seed-evolving",
            client=client,
            timeout_seconds=0,
            enable_snapshot=False,
        )
        == "tool-temporary"
    )
    assert requests[0].enable_snapshot is False


def test_ensure_configured_studio_tool_enables_snapshots() -> None:
    updates: list[dict[str, object]] = []
    mutation_slots: list[None] = []

    class Client:
        enabled = False

        def get_tool(self, _request: object) -> SimpleNamespace:
            return SimpleNamespace(status="Ready", enable_snapshot=self.enabled)

        def update_tool(self, request: object) -> SimpleNamespace:
            updates.append(request.model_dump(by_alias=True, exclude_none=True))
            self.enabled = True
            return SimpleNamespace(tool_id="tool-configured")

    assert (
        ensure_studio_tool_snapshot(
            tool_id="tool-configured",
            name="Codex",
            client=Client(),
            timeout_seconds=1,
            poll_interval=0,
            sleep=lambda _: None,
            before_mutation=lambda: mutation_slots.append(None),
        )
        == "tool-configured"
    )
    assert updates == [{"EnableSnapshot": True, "ToolId": "tool-configured"}]
    assert mutation_slots == [None]


def test_agent_model_credential_is_bound_to_tool_as_complete_env_set() -> None:
    access_key = os.urandom(16).hex()
    model_api_key = os.urandom(24).hex()
    secret_key = os.urandom(24).hex()
    calls: list[tuple[str, dict[str, object]]] = []
    update_slots: list[None] = []

    class FakeApi:
        def call(
            self,
            _service: str,
            action: str,
            _version: str,
            body: dict[str, object],
        ) -> dict[str, object]:
            calls.append((action, body))
            if action == "GetTool":
                return {"Tool": {"Envs": [{"Key": "EXISTING_ENV", "Value": "kept"}]}}
            return {}

    with (
        patch("agentkit.auth._openapi.OpenApiClient", return_value=FakeApi()),
        patch(
            "veadk.auth.veauth.ark_veauth.get_ark_token",
            return_value=model_api_key,
        ),
    ):
        ensure_studio_agent_model_credential(
            tool_id="tool-openclaw",
            kind="openclaw",
            model_name="doubao-seed-evolving",
            access_key=access_key,
            secret_key=secret_key,
            before_update=lambda: update_slots.append(None),
        )

    assert [action for action, _ in calls] == ["GetTool", "UpdateTool"]
    assert update_slots == [None]
    updated_envs = cast(list[dict[str, str]], calls[1][1]["Envs"])
    envs = {item["Key"]: item["Value"] for item in updated_envs}
    assert envs == {
        "EXISTING_ENV": "kept",
        "MODEL_AGENT_API_KEY": model_api_key,
        "MODEL_AGENT_NAME": "doubao-seed-evolving",
        "MODEL_AGENT_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        "ARK_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
    }
