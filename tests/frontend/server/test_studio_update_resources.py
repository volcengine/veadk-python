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

from types import SimpleNamespace
from typing import Any

import pytest

from frontend.server.studio_update_resources import (
    _provision_snapshot_tool,
    reconcile_studio_update_resources,
)
from veadk.utils.cloud_provider import CloudProvider


def _client(
    environment: dict[str, str],
    *,
    role: str = "trn:iam::123:role/CustomerStudioRole",
) -> SimpleNamespace:
    return SimpleNamespace(
        get_function=lambda _request: SimpleNamespace(
            role=role,
            envs=[
                SimpleNamespace(key=key, value=value)
                for key, value in environment.items()
            ],
        )
    )


@pytest.mark.parametrize(
    ("provider", "region"),
    [
        ("volcengine", "cn-beijing"),
        ("byteplus", "ap-southeast-1"),
    ],
)
def test_reconcile_does_not_mutate_the_function_role_policy(
    monkeypatch: pytest.MonkeyPatch,
    provider: CloudProvider,
    region: str,
) -> None:
    monkeypatch.setattr(
        "veadk.cli.frontend_deploy_iam.ensure_default_frontend_role_policy",
        lambda *_args, **_kwargs: pytest.fail("self-update must not mutate IAM"),
    )
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.resolve_studio_storage_for_deploy",
        lambda **_kwargs: pytest.fail("storage must not be reprovisioned"),
    )
    monkeypatch.setattr(
        "frontend.server.studio_update_resources._provision_snapshot_tool",
        lambda **_kwargs: pytest.fail("snapshot tools must not be reprovisioned"),
    )
    environment = {
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": "stable-key",
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": region,
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-tool",
    }

    assert (
        reconcile_studio_update_resources(
            provider=provider,
            region=region,
            application_id="application-id",
            function_id="function-id",
            function_client=_client(
                environment,
                role="trn:iam::123:role/VeADKFrontendServiceRole",
            ),
            access_key="ak",
            secret_key="sk",
            session_token="token",
        )
        == {}
    )


def test_reconcile_studio_update_resources_reuses_existing_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    environment = {
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": "stable-key",
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-tool",
    }
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.resolve_studio_storage_for_deploy",
        lambda **_kwargs: pytest.fail("storage must not be reprovisioned"),
    )
    monkeypatch.setattr(
        "frontend.server.studio_update_resources._provision_snapshot_tool",
        lambda **_kwargs: pytest.fail("snapshot tools must not be reprovisioned"),
    )

    assert (
        reconcile_studio_update_resources(
            provider="byteplus",
            region="ap-southeast-1",
            application_id="application-id",
            function_id="function-id",
            function_client=_client(environment),
            access_key="ak",
            secret_key="sk",
            session_token="token",
        )
        == {}
    )


def test_reconcile_studio_update_resources_provisions_missing_resources(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage_calls: list[dict[str, Any]] = []
    tool_calls: list[dict[str, Any]] = []

    def _storage(**kwargs: Any) -> SimpleNamespace:
        storage_calls.append(kwargs)
        return SimpleNamespace(bucket="studio-bucket", region="ap-southeast-1")

    def _tool(**kwargs: Any) -> str:
        tool_calls.append(kwargs)
        return f"{kwargs['kind']}-tool"

    monkeypatch.setattr(
        "frontend.server.studio_update_resources.resolve_studio_storage_for_deploy",
        _storage,
    )
    monkeypatch.setattr(
        "frontend.server.studio_update_resources._provision_snapshot_tool",
        _tool,
    )
    monkeypatch.setattr(
        "veadk.cli.studio_knowledge_signing.resolve_studio_knowledge_signing_key",
        lambda _environment: "generated-key",
    )

    overrides = reconcile_studio_update_resources(
        provider="byteplus",
        region="ap-southeast-1",
        application_id="application-id",
        function_id="function-id",
        function_client=_client({"SANDBOX_CHAT_CODEX": "existing-tool"}),
        access_key="ak",
        secret_key="sk",
        session_token="token",
    )

    assert overrides == {
        "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": "generated-key",
        "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
        "VEADK_STUDIO_TOS_REGION": "ap-southeast-1",
        "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-tool",
        "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-tool",
        "SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-tool",
    }
    assert storage_calls == [
        {
            "provider": "byteplus",
            "region": "ap-southeast-1",
            "access_key": "ak",
            "secret_key": "sk",
            "session_token": "token",
            "source": {"SANDBOX_CHAT_CODEX": "existing-tool"},
        }
    ]
    assert {call["kind"] for call in tool_calls} == {"codex", "openclaw", "hermes"}
    assert all(call["application_id"] == "application-id" for call in tool_calls)
    assert (
        next(call for call in tool_calls if call["kind"] == "codex")["purpose"]
        == "codex"
    )


def test_reconcile_studio_update_resources_only_repairs_missing_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_calls: list[str] = []
    monkeypatch.setattr(
        "frontend.server.studio_update_resources.resolve_studio_storage_for_deploy",
        lambda **_kwargs: pytest.fail("existing storage must be reused"),
    )
    monkeypatch.setattr(
        "frontend.server.studio_update_resources._provision_snapshot_tool",
        lambda **kwargs: tool_calls.append(kwargs["kind"]) or "hermes-tool",
    )

    overrides = reconcile_studio_update_resources(
        provider="volcengine",
        region="cn-beijing",
        application_id="application-id",
        function_id="function-id",
        function_client=_client(
            {
                "VEADK_STUDIO_KNOWLEDGE_SIGNING_KEY": "stable-key",
                "VEADK_STUDIO_TOS_BUCKET": "studio-bucket",
                "VEADK_STUDIO_TOS_REGION": "cn-beijing",
                "SANDBOX_CHAT_CODEX_SNAPSHOT": "codex-tool",
                "SANDBOX_CHAT_OPENCLAW_SNAPSHOT": "openclaw-tool",
            }
        ),
        access_key="ak",
        secret_key="sk",
        session_token="",
    )

    assert overrides == {"SANDBOX_CHAT_HERMES_SNAPSHOT": "hermes-tool"}
    assert tool_calls == ["hermes"]


def test_provision_codex_snapshot_tool_binds_model_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.studio_sandbox_tool_name_candidates",
        lambda application_id, purpose, *, snapshot: (
            captured.update(
                {
                    "application_id": application_id,
                    "purpose": purpose,
                    "snapshot": snapshot,
                }
            )
            or ("snapshot-tool-name", "legacy-snapshot-tool-name")
        ),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.studio_sandbox_agent_model_name",
        lambda provider: f"{provider}-model",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_code_env_tool",
        lambda **kwargs: captured.update(tool=kwargs) or "tool-id",
    )
    monkeypatch.setattr(
        "veadk.cli.frontend_skill_creator.ensure_skill_creator_model_credential",
        lambda **kwargs: captured.setdefault("credential", kwargs),
    )

    tool_id = _provision_snapshot_tool(
        kind="codex",
        purpose="codex",
        provider="byteplus",
        region="ap-southeast-1",
        application_id="application-id",
        access_key="ak",
        secret_key="sk",
        session_token="token",
    )

    assert tool_id == "tool-id"
    assert captured["purpose"] == "codex"
    assert captured["snapshot"] is True
    assert captured["tool"]["name"] == "snapshot-tool-name"
    assert captured["tool"]["legacy_names"] == ("legacy-snapshot-tool-name",)
    assert captured["tool"]["enable_snapshot"] is True
    assert captured["credential"]["tool_id"] == "tool-id"
    assert captured["credential"]["provider"] == "byteplus"
    assert captured["credential"]["model_name"] == "byteplus-model"


def test_provision_agent_snapshot_tool_binds_provider_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.studio_sandbox_tool_name_candidates",
        lambda *_args, **_kwargs: ("snapshot-tool-name",),
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.studio_sandbox_agent_model_name",
        lambda _provider: "agent-model",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.studio_sandbox_model_base_url",
        lambda _provider: "https://ark.byteplus.example/api/v3",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_tool",
        lambda **kwargs: captured.update(tool=kwargs) or "tool-id",
    )
    monkeypatch.setattr(
        "veadk.cli.studio_sandbox_tools.ensure_studio_agent_model_credential",
        lambda **kwargs: captured.setdefault("credential", kwargs),
    )

    tool_id = _provision_snapshot_tool(
        kind="hermes",
        purpose="hermes",
        provider="byteplus",
        region="ap-southeast-1",
        application_id="application-id",
        access_key="ak",
        secret_key="sk",
        session_token="token",
    )

    assert tool_id == "tool-id"
    assert captured["tool"]["kind"] == "hermes"
    assert captured["tool"]["enable_snapshot"] is True
    assert captured["tool"]["model_name"] == "agent-model"
    assert captured["credential"]["tool_id"] == "tool-id"
    assert captured["credential"]["provider"] == "byteplus"
    assert captured["credential"]["model_base_url"] == (
        "https://ark.byteplus.example/api/v3"
    )
