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
from typing import Any, cast
from unittest.mock import patch

import pytest
from agentkit.auth.errors import NetworkError
from agentkit.toolkit.errors import ApiError

import veadk.cli.studio_sandbox_tools as studio_sandbox_tools
from veadk.cli.studio_sandbox_tools import (
    ensure_studio_codex_model_environment,
    ensure_studio_agent_model_credential,
    ensure_studio_agent_tool,
    ensure_studio_code_env_tool,
    ensure_studio_dev_env_tool,
    inspect_studio_codex_model_environment,
    studio_sandbox_agent_model_name,
    studio_sandbox_model_base_url,
    studio_sandbox_tool_name,
    studio_sandbox_tool_name_candidates,
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


def test_ensure_studio_code_env_tool_reuses_legacy_name() -> None:
    requested_names: list[str] = []

    def _list_tools(request: object) -> SimpleNamespace:
        filters = cast(Any, request).filters
        requested_name = str(filters[0].values[0])
        requested_names.append(requested_name)
        tools = []
        if requested_name == "studio-demo-chat-123456":
            tools.append(
                SimpleNamespace(
                    name=requested_name,
                    project_name="default",
                    tool_type="CodeEnv",
                    tool_id="legacy-tool",
                )
            )
        return SimpleNamespace(tools=tools, next_token=None)

    client = SimpleNamespace(
        list_tools=_list_tools,
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=lambda _: pytest.fail("the legacy Tool must be reused"),
    )

    assert (
        ensure_studio_code_env_tool(
            name="studio-demo-codex-123456",
            legacy_names=("studio-demo-chat-123456",),
            client=client,
            timeout_seconds=0,
        )
        == "legacy-tool"
    )
    assert requested_names == [
        "studio-demo-codex-123456",
        "studio-demo-chat-123456",
    ]


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
    assert len(getattr(request, "client_token")) == 32
    assert getattr(request, "cpu_milli") == 4000
    assert getattr(request, "memory_mb") == 8192
    assert getattr(request, "envs") is None
    assert getattr(request, "enable_snapshot") is False


@pytest.mark.parametrize(
    "transient_error",
    [
        RuntimeError("QPS limit exceeded"),
        ConnectionError("temporary connection failure"),
        NetworkError("Failed to CreateTool: network error"),
        ApiError(
            "Failed to CreateTool: request limit exceeded",
            error_code="RequestLimitExceeded",
        ),
    ],
    ids=[
        "qps-limit",
        "connection-error",
        "agentkit-network-error",
        "agentkit-request-limit",
    ],
)
def test_ensure_studio_code_env_tool_retries_transient_create_errors(
    transient_error: Exception,
) -> None:
    create_calls = 0
    client_tokens: list[str] = []
    sleeps: list[float] = []

    def _create(request: object) -> SimpleNamespace:
        nonlocal create_calls
        create_calls += 1
        client_tokens.append(str(getattr(request, "client_token")))
        if create_calls == 1:
            raise transient_error
        return SimpleNamespace(tool_id="tool-after-retry")

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=_create,
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-retry-12345678",
            client=client,
            timeout_seconds=0,
            create_max_attempts=3,
            create_retry_delay=0.25,
            sleep=sleeps.append,
        )
        == "tool-after-retry"
    )
    assert create_calls == 2
    assert len(set(client_tokens)) == 1
    assert len(client_tokens[0]) == 32
    assert sleeps == [0.25]


def test_ensure_studio_code_env_tool_spaces_create_api_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = 100.0
    create_started_at: list[float] = []
    sleeps: list[float] = []

    def _sleep(delay: float) -> None:
        nonlocal now
        sleeps.append(delay)
        now += delay

    def _create(_: object) -> SimpleNamespace:
        create_started_at.append(now)
        return SimpleNamespace(tool_id=f"tool-{len(create_started_at)}")

    monkeypatch.setattr(studio_sandbox_tools.time, "monotonic", lambda: now)
    monkeypatch.setattr(studio_sandbox_tools, "_NEXT_CREATE_TOOL_AT", 0.0)
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=_create,
    )

    for suffix in ("first", "second"):
        ensure_studio_code_env_tool(
            name=f"veadk-studio-demo-{suffix}-12345678",
            client=client,
            timeout_seconds=0,
            create_min_interval=0.5,
            sleep=_sleep,
        )

    assert create_started_at == [100.0, 100.5]
    assert create_started_at[1] - create_started_at[0] >= 0.5
    assert sleeps == [0.5]


def test_ensure_studio_code_env_tool_preserves_exhausted_create_error() -> None:
    create_calls = 0
    sleeps: list[float] = []
    last_error = TimeoutError("temporary create timeout")

    def _create(_: object) -> SimpleNamespace:
        nonlocal create_calls
        create_calls += 1
        raise last_error

    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        create_tool=_create,
    )

    with pytest.raises(RuntimeError, match="veadk-studio-demo-retry-12345678") as exc:
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-retry-12345678",
            client=client,
            timeout_seconds=0,
            create_max_attempts=3,
            create_retry_delay=0.25,
            sleep=sleeps.append,
        )

    assert create_calls == 3
    assert sleeps == [0.25, 0.5]
    assert exc.value.__cause__ is last_error


@pytest.mark.parametrize(
    ("get_tool", "timeout_seconds"),
    [
        (lambda _: SimpleNamespace(status="Failed"), 60),
        (lambda _: SimpleNamespace(status="Creating"), 0),
        (
            lambda _: (_ for _ in ()).throw(
                ConnectionError("temporary status lookup failure")
            ),
            60,
        ),
    ],
    ids=["failed", "timeout", "get-tool-error"],
)
def test_ensure_studio_code_env_tool_ready_errors_include_tool_id(
    get_tool: object,
    timeout_seconds: float,
) -> None:
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        create_tool=lambda _: SimpleNamespace(tool_id="tool-with-ready-error"),
        get_tool=get_tool,
    )

    with pytest.raises(RuntimeError, match="tool-with-ready-error"):
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-ready-error-12345678",
            client=client,
            timeout_seconds=timeout_seconds,
        )


def test_ensure_studio_code_env_tool_creates_snapshot_enabled_code_env() -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=True),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id="snapshot-tool")
        ),
    )

    assert (
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-12345678_snapshot",
            enable_snapshot=True,
            client=client,
            timeout_seconds=0,
        )
        == "snapshot-tool"
    )
    assert getattr(requests[0], "tool_type") == "CodeEnv"
    assert getattr(requests[0], "enable_snapshot") is True


def test_ensure_studio_code_env_tool_rejects_reused_tool_with_wrong_snapshot_mode() -> (
    None
):
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(
            tools=[
                SimpleNamespace(
                    name="veadk-studio-demo-chat-12345678_snapshot",
                    project_name="default",
                    tool_type="CodeEnv",
                    tool_id="tool-existing",
                )
            ],
            next_token=None,
        ),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=False),
        create_tool=lambda _: (_ for _ in ()).throw(
            AssertionError("an exact-name Tool must not be recreated")
        ),
    )

    with pytest.raises(RuntimeError, match="expected snapshot enabled"):
        ensure_studio_code_env_tool(
            name="veadk-studio-demo-chat-12345678_snapshot",
            enable_snapshot=True,
            client=client,
            timeout_seconds=0,
        )


def test_ensure_studio_dev_env_tool_creates_ready_dev_env() -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready"),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id="dev-tool")
        ),
    )

    assert (
        ensure_studio_dev_env_tool(
            name="veadk-studio-demo-dev-12345678",
            client=client,
            timeout_seconds=0,
        )
        == "dev-tool"
    )
    assert getattr(requests[0], "tool_type") == "DevEnv"


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
    assert request.enable_snapshot is False


@pytest.mark.parametrize("kind", ["openclaw", "hermes"])
def test_ensure_studio_agent_tool_creates_snapshot_enabled_managed_tool(
    kind: str,
) -> None:
    requests: list[object] = []
    client = SimpleNamespace(
        list_tools=lambda _: SimpleNamespace(tools=[], next_token=None),
        get_tool=lambda _: SimpleNamespace(status="Ready", enable_snapshot=True),
        create_tool=lambda request: (
            requests.append(request) or SimpleNamespace(tool_id=f"snapshot-{kind}")
        ),
    )

    ensure_studio_agent_tool(
        name=f"veadk-studio-demo-{kind}-12345678_snapshot",
        kind=kind,
        model_name="doubao-seed-evolving",
        enable_snapshot=True,
        client=client,
        timeout_seconds=0,
    )

    assert requests[0].enable_snapshot is True


def test_studio_sandbox_tool_name_uses_short_studio_format() -> None:
    assert studio_sandbox_tool_name("Studio App", "chat") == (
        "studio-studio-app-chat-1d66ce"
    )


def test_codex_tool_name_candidates_prefer_codex_and_fall_back_to_chat() -> None:
    assert studio_sandbox_tool_name_candidates("Studio App", "codex") == (
        "studio-studio-app-codex-1d66ce",
        "studio-studio-app-chat-1d66ce",
    )
    assert studio_sandbox_tool_name_candidates(
        "Studio App",
        "codex",
        snapshot=True,
    ) == (
        "studio-studio-app-codex-1d66ce_snapshot",
        "studio-studio-app-chat-1d66ce_snapshot",
    )


def test_studio_sandbox_tool_name_normalizes_invalid_characters() -> None:
    assert studio_sandbox_tool_name("  My_App@2026!  ", "skill") == (
        "studio-my-app-2026-skill-6c7faf"
    )


def test_studio_sandbox_tool_name_truncates_normalized_app_name_to_20_chars() -> None:
    assert (
        studio_sandbox_tool_name(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789",
            "chat",
        )
        == "studio-abcdefghijklmnopqrst-chat-1655ef"
    )


def test_studio_sandbox_tool_name_hash_distinguishes_normalization_collisions() -> None:
    underscore_name = studio_sandbox_tool_name("My_App", "chat")
    space_name = studio_sandbox_tool_name("My App", "chat")

    assert underscore_name == "studio-my-app-chat-6bcaca"
    assert space_name == "studio-my-app-chat-58967a"
    assert underscore_name != space_name


@pytest.mark.parametrize("purpose", ["chat", "openclaw", "hermes"])
def test_snapshot_tool_name_appends_snapshot_suffix(purpose: str) -> None:
    standard = studio_sandbox_tool_name("Studio App", purpose)
    snapshot = studio_sandbox_tool_name("Studio App", purpose, snapshot=True)

    assert snapshot == f"{standard}_snapshot"


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


def test_codex_model_environment_noops_when_model_envs_are_present() -> None:
    updates: list[object] = []
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="MODEL_AGENT_API_KEY", value="model-key"),
                SimpleNamespace(
                    key="MODEL_AGENT_BASE_URL",
                    value="https://model.example.com/api/v3",
                ),
            ]
        ),
        update_tool=updates.append,
    )

    updated = ensure_studio_codex_model_environment(
        tool_id="tool-codex",
        client=client,
    )

    assert updated is False
    assert updates == []


def test_codex_model_environment_inspection_reports_update_state() -> None:
    updates: list[object] = []
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="CODEX_API_KEY", value="codex-key"),
                SimpleNamespace(
                    key="CODEX_BASE_URL",
                    value="https://ark.cn-beijing.volces.com/api/v3",
                ),
                SimpleNamespace(key="MODEL_AGENT_API_KEY", value="model-key"),
            ]
        ),
        update_tool=updates.append,
    )

    status = inspect_studio_codex_model_environment(
        tool_id="tool-codex",
        client=client,
    )

    assert status.needs_model_env_update is True
    assert status.can_update_model_env is True
    assert status.model_env_error == ""
    assert status.has_model_agent_api_key is True
    assert status.has_model_agent_base_url is False
    assert status.has_codex_api_key is True
    assert status.has_codex_base_url is True
    assert updates == []


def test_codex_model_environment_inspection_reports_codex_env_errors() -> None:
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="MODEL_AGENT_API_KEY", value="model-key"),
            ]
        )
    )

    status = inspect_studio_codex_model_environment(
        tool_id="tool-codex",
        client=client,
    )

    assert status.needs_model_env_update is True
    assert status.can_update_model_env is False
    assert "CODEX_API_KEY" in status.model_env_error
    assert "CODEX_BASE_URL" in status.model_env_error


def test_codex_model_environment_backfills_missing_model_envs_from_codex() -> None:
    updates: list[object] = []
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[
                SimpleNamespace(key="EXISTING_ENV", value="kept"),
                SimpleNamespace(key="CODEX_API_KEY", value="codex-key"),
                SimpleNamespace(
                    key="CODEX_BASE_URL",
                    value="https://ark.cn-beijing.volces.com/api/v3",
                ),
                SimpleNamespace(key="MODEL_AGENT_API_KEY", value="existing-model-key"),
            ]
        ),
        update_tool=updates.append,
    )

    updated = ensure_studio_codex_model_environment(
        tool_id=" tool-codex ",
        client=client,
    )

    assert updated is True
    assert len(updates) == 1
    assert getattr(updates[0], "tool_id") == "tool-codex"
    envs = {
        item.key: item.value for item in cast(list[Any], getattr(updates[0], "envs"))
    }
    assert envs == {
        "EXISTING_ENV": "kept",
        "CODEX_API_KEY": "codex-key",
        "CODEX_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
        "MODEL_AGENT_API_KEY": "existing-model-key",
        "MODEL_AGENT_BASE_URL": "https://ark.cn-beijing.volces.com/api/v3",
    }


def test_codex_model_environment_requires_codex_envs_before_backfill() -> None:
    client = SimpleNamespace(
        get_tool=lambda _: SimpleNamespace(
            envs=[SimpleNamespace(key="CODEX_API_KEY", value="codex-key")]
        ),
        update_tool=lambda _: pytest.fail("invalid Codex envs must not be persisted"),
    )

    with pytest.raises(ValueError, match="CODEX_BASE_URL"):
        ensure_studio_codex_model_environment(
            tool_id="tool-codex",
            client=client,
        )


def test_byteplus_agent_model_configuration() -> None:
    assert studio_sandbox_agent_model_name("byteplus") == "dola-seed-2-1-turbo-260628"
    assert studio_sandbox_model_base_url("byteplus") == (
        "https://ark.ap-southeast.bytepluses.com/api/v3"
    )


def test_volcengine_agent_model_configuration() -> None:
    assert studio_sandbox_agent_model_name("volcengine") == (
        "doubao-seed-2-1-pro-260628"
    )
