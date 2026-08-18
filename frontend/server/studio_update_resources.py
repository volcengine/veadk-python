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

"""Provision account-local resources introduced after a Studio deployment."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Literal

from frontend.server.storage.provisioning import resolve_studio_storage_for_deploy
from veadk.utils.cloud_provider import CloudProvider

SnapshotKind = Literal["codex", "openclaw", "hermes"]

_SNAPSHOT_ENVIRONMENTS: tuple[tuple[str, SnapshotKind, str], ...] = (
    ("SANDBOX_CHAT_CODEX_SNAPSHOT", "codex", "codex"),
    ("SANDBOX_CHAT_OPENCLAW_SNAPSHOT", "openclaw", "openclaw"),
    ("SANDBOX_CHAT_HERMES_SNAPSHOT", "hermes", "hermes"),
)


def _function_config(
    function_client: Any,
    function_id: str,
) -> dict[str, str]:
    import volcenginesdkvefaas

    function = function_client.get_function(
        volcenginesdkvefaas.GetFunctionRequest(id=function_id)
    )
    environment = {
        str(item.key): str(item.value)
        for item in (getattr(function, "envs", None) or [])
        if getattr(item, "key", None)
    }
    return environment


def _provision_snapshot_tool(
    *,
    kind: SnapshotKind,
    purpose: str,
    provider: CloudProvider,
    region: str,
    application_id: str,
    access_key: str,
    secret_key: str,
    session_token: str,
) -> str:
    from veadk.cli.frontend_skill_creator import (
        ensure_skill_creator_model_credential,
    )
    from veadk.cli.studio_sandbox_tools import (
        ensure_studio_agent_model_credential,
        ensure_studio_agent_tool,
        ensure_studio_code_env_tool,
        studio_sandbox_agent_model_name,
        studio_sandbox_model_base_url,
        studio_sandbox_tool_name_candidates,
    )

    tool_names = studio_sandbox_tool_name_candidates(
        application_id,
        purpose,
        snapshot=True,
    )
    tool_name = tool_names[0]
    model_name = studio_sandbox_agent_model_name(provider)
    if kind == "codex":
        tool_id = ensure_studio_code_env_tool(
            name=tool_name,
            legacy_names=tool_names[1:],
            enable_snapshot=True,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
        )
        ensure_skill_creator_model_credential(
            tool_id=tool_id,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            provider=provider,
            model_name=model_name,
        )
        return tool_id

    tool_id = ensure_studio_agent_tool(
        name=tool_name,
        kind=kind,
        enable_snapshot=True,
        model_name=model_name,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )
    ensure_studio_agent_model_credential(
        tool_id=tool_id,
        kind=kind,
        model_name=model_name,
        model_base_url=studio_sandbox_model_base_url(provider),
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        provider=provider,
    )
    return tool_id


def reconcile_studio_update_resources(
    *,
    provider: CloudProvider,
    region: str,
    application_id: str,
    function_id: str,
    function_client: Any,
    access_key: str,
    secret_key: str,
    session_token: str,
) -> dict[str, str]:
    """Return environment overrides for resources missing from an older Studio."""
    environment = _function_config(function_client, function_id)
    overrides: dict[str, str] = {}

    from veadk.cli.studio_knowledge_signing import (
        STUDIO_KNOWLEDGE_SIGNING_KEY_ENV,
        resolve_studio_knowledge_signing_key,
    )

    if not str(environment.get(STUDIO_KNOWLEDGE_SIGNING_KEY_ENV) or "").strip():
        overrides[STUDIO_KNOWLEDGE_SIGNING_KEY_ENV] = (
            resolve_studio_knowledge_signing_key(environment)
        )

    if not (
        environment.get("VEADK_STUDIO_TOS_BUCKET")
        and environment.get("VEADK_STUDIO_TOS_REGION")
    ):
        storage = resolve_studio_storage_for_deploy(
            provider=provider,
            region=region,
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            source=environment,
        )
        overrides.update(
            {
                "VEADK_STUDIO_TOS_BUCKET": storage.bucket,
                "VEADK_STUDIO_TOS_REGION": storage.region,
            }
        )

    missing_snapshot_tools = [
        item for item in _SNAPSHOT_ENVIRONMENTS if not environment.get(item[0])
    ]
    if missing_snapshot_tools:
        with ThreadPoolExecutor(max_workers=len(missing_snapshot_tools)) as executor:
            futures = {
                environment_key: executor.submit(
                    _provision_snapshot_tool,
                    kind=kind,
                    purpose=purpose,
                    provider=provider,
                    region=region,
                    application_id=application_id,
                    access_key=access_key,
                    secret_key=secret_key,
                    session_token=session_token,
                )
                for environment_key, kind, purpose in missing_snapshot_tools
            }
            for environment_key, _kind, _purpose in missing_snapshot_tools:
                overrides[environment_key] = futures[environment_key].result()

    return overrides


__all__ = ["reconcile_studio_update_resources"]
