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

"""Provider-aware cloud credentials for the Studio server process."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

from veadk.consts import VEFAAS_IAM_CRIDENTIAL_PATH
from veadk.utils.cloud_provider import (
    CloudProvider,
    cloud_provider_from_env,
    normalize_cloud_provider,
)


class StudioCloudCredentialError(RuntimeError):
    """Cloud credentials required by a Studio server operation are unavailable."""

    def __init__(self, provider: CloudProvider) -> None:
        self.provider = provider
        label = "BytePlus" if provider == "byteplus" else "Volcengine"
        environment = (
            "BYTEPLUS_ACCESS_KEY/BYTEPLUS_SECRET_KEY"
            if provider == "byteplus"
            else "VOLCENGINE_ACCESS_KEY/VOLCENGINE_SECRET_KEY"
        )
        super().__init__(
            f"{label} credentials not found (set {environment}, or run inside "
            "a VeFaaS function with an IAM role)"
        )


@dataclass(frozen=True, slots=True)
class StudioCloudCredentials:
    """One resolved credential set without provider-specific consumers."""

    access_key: str
    secret_key: str
    session_token: str
    source: str


def _credential_value(payload: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _read_vefaas_iam_credentials() -> StudioCloudCredentials | None:
    try:
        with open(VEFAAS_IAM_CRIDENTIAL_PATH, encoding="utf-8") as credential_file:
            payload = json.load(credential_file)
    except (OSError, ValueError, TypeError):
        return None
    if not isinstance(payload, dict):
        return None
    access_key = _credential_value(payload, "access_key_id", "AccessKeyId")
    secret_key = _credential_value(
        payload,
        "secret_access_key",
        "SecretAccessKey",
    )
    if not access_key or not secret_key:
        return None
    return StudioCloudCredentials(
        access_key=access_key,
        secret_key=secret_key,
        session_token=_credential_value(
            payload,
            "session_token",
            "SessionToken",
        ),
        source="vefaas_iam",
    )


def resolve_studio_cloud_credentials(
    provider: str | None = None,
) -> StudioCloudCredentials:
    """Resolve local environment credentials, then the VeFaaS IAM role."""
    provider_id = (
        normalize_cloud_provider(provider)
        if provider is not None
        else cloud_provider_from_env()
    )
    if provider_id == "byteplus":
        access_key = (os.getenv("BYTEPLUS_ACCESS_KEY") or "").strip()
        secret_key = (os.getenv("BYTEPLUS_SECRET_KEY") or "").strip()
        session_token = (os.getenv("BYTEPLUS_SESSION_TOKEN") or "").strip()
    else:
        access_key = (
            os.getenv("VOLCENGINE_ACCESS_KEY") or os.getenv("VOLC_ACCESSKEY") or ""
        ).strip()
        secret_key = (
            os.getenv("VOLCENGINE_SECRET_KEY") or os.getenv("VOLC_SECRETKEY") or ""
        ).strip()
        session_token = (
            os.getenv("VOLCENGINE_SESSION_TOKEN")
            or os.getenv("VOLC_SESSIONTOKEN")
            or ""
        ).strip()
    if access_key and secret_key:
        return StudioCloudCredentials(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            source="environment",
        )
    iam_credentials = _read_vefaas_iam_credentials()
    if iam_credentials is not None:
        return iam_credentials
    raise StudioCloudCredentialError(provider_id)


def agentkit_client_options(
    region: str,
    *,
    provider: str | None = None,
) -> dict[str, str]:
    """Return safe AgentKit constructor options for the active provider.

    AgentKit already refreshes VeFaaS IAM credentials for Volcengine clients.
    Its BytePlus provider currently skips that source, so Studio bridges the
    same temporary role credentials explicitly only for BytePlus.
    """
    provider_id = (
        normalize_cloud_provider(provider)
        if provider is not None
        else cloud_provider_from_env()
    )
    if provider_id == "volcengine":
        return {"region": region}
    credentials = resolve_studio_cloud_credentials(provider_id)
    return {
        "access_key": credentials.access_key,
        "secret_key": credentials.secret_key,
        "session_token": credentials.session_token,
        "region": region,
    }
