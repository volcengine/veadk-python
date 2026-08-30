# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0

"""Shared AgentKit cloud configuration for resource sources."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from veadk.utils.cloud_provider import cloud_provider_from_env, default_region


@dataclass(frozen=True)
class CloudCredentials:
    access_key: str
    secret_key: str
    session_token: str = ""


def resolve_cloud_credentials(tool_context: Any = None) -> CloudCredentials | None:
    """Resolve provider-specific AK/SK or STS credentials for one tool call."""
    state = getattr(tool_context, "state", None) or {}
    provider = cloud_provider_from_env()
    if provider == "byteplus":
        access_key = state.get("BYTEPLUS_ACCESS_KEY") or os.getenv(
            "BYTEPLUS_ACCESS_KEY"
        )
        secret_key = state.get("BYTEPLUS_SECRET_KEY") or os.getenv(
            "BYTEPLUS_SECRET_KEY"
        )
        session_token = state.get("BYTEPLUS_SESSION_TOKEN") or os.getenv(
            "BYTEPLUS_SESSION_TOKEN", ""
        )
    else:
        access_key = state.get("VOLCENGINE_ACCESS_KEY") or os.getenv(
            "VOLCENGINE_ACCESS_KEY"
        )
        secret_key = state.get("VOLCENGINE_SECRET_KEY") or os.getenv(
            "VOLCENGINE_SECRET_KEY"
        )
        session_token = state.get("VOLCENGINE_SESSION_TOKEN") or os.getenv(
            "VOLCENGINE_SESSION_TOKEN", ""
        )

    if access_key and secret_key:
        return CloudCredentials(access_key, secret_key, session_token)

    from veadk.auth.veauth.utils import get_credential_from_vefaas_iam

    credential = get_credential_from_vefaas_iam()
    if not credential.access_key_id or not credential.secret_access_key:
        return None
    return CloudCredentials(
        credential.access_key_id,
        credential.secret_access_key,
        credential.session_token,
    )


def default_agentkit_region() -> str:
    """Return the provider-aware AgentKit control-plane region."""
    return os.getenv("AGENTKIT_TOOL_REGION") or default_region(
        cloud_provider_from_env()
    )
