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

"""Helpers for resolving Studio cloud account metadata."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass

from veadk.cli.studio_telemetry import (
    STUDIO_ACCOUNT_ID_ENV,
    STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV,
)
from veadk.utils.cloud_provider import CloudProvider

_ACCOUNT_ID_RE = re.compile(r"[0-9]+")
_IAM_ACCOUNT_ID_RE = re.compile(r"\biam::(?P<account_id>[0-9]+):")
_STUDIO_TOS_BUCKET_ACCOUNT_ID_RE = re.compile(
    r"(?:^|/)veadk-studio-(?P<account_id>[0-9]+)(?:/|$)"
)
_MAX_RESOLUTION_ERROR_LENGTH = 1000


@dataclass(frozen=True)
class StudioAccountIdResolution:
    """Resolved Studio account id or a sanitized diagnostic error."""

    account_id: str = ""
    error: str = ""


def cloud_account_id_from_value(value: object) -> str:
    """Return a normalized numeric account id from a cloud metadata value."""
    normalized = str(value or "").strip()
    return normalized if _ACCOUNT_ID_RE.fullmatch(normalized) else ""


def studio_account_id_from_remote_function(function: object | None) -> str:
    """Infer a cloud account id from a VeFaaS Function owner or role field."""
    if function is None:
        return ""
    for attribute in ("owner", "Owner"):
        account_id = cloud_account_id_from_value(getattr(function, attribute, ""))
        if account_id:
            return account_id
    for attribute in ("role", "Role"):
        role = str(getattr(function, attribute, "") or "")
        match = _IAM_ACCOUNT_ID_RE.search(role)
        if match:
            return match.group("account_id")
    return ""


def studio_account_id_from_tos_bucket(value: object) -> str:
    """Infer the Studio account id from the deterministic Studio TOS bucket."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = _STUDIO_TOS_BUCKET_ACCOUNT_ID_RE.search(text)
    if not match:
        return ""
    return match.group("account_id")


def studio_account_id_from_environment(
    environment: Mapping[str, object] | None,
) -> str:
    """Resolve account id from Studio environment values when available."""
    if not environment:
        return ""
    account_id = cloud_account_id_from_value(environment.get(STUDIO_ACCOUNT_ID_ENV))
    if account_id:
        return account_id
    return studio_account_id_from_tos_bucket(environment.get("VEADK_STUDIO_TOS_BUCKET"))


def sanitize_account_id_resolution_error(
    error: BaseException,
    *,
    secrets: Iterable[str | None] = (),
) -> str:
    """Return a bounded, credential-redacted error for telemetry diagnostics."""
    message = str(error).strip() or type(error).__name__
    for secret in secrets:
        if secret:
            message = message.replace(secret, "***")
    message = re.sub(r"\s+", " ", message).strip()
    if len(message) > _MAX_RESOLUTION_ERROR_LENGTH:
        message = message[: _MAX_RESOLUTION_ERROR_LENGTH - 1].rstrip() + "…"
    return message or type(error).__name__


def resolve_studio_account_id_metadata(
    *,
    environment: Mapping[str, object] | None = None,
    remote_function: object | None = None,
    access_key: str = "",
    secret_key: str = "",
    session_token: str = "",
    region: str = "",
    provider: CloudProvider | None = None,
    error_formatter: Callable[[BaseException], str] | None = None,
) -> StudioAccountIdResolution:
    """Resolve account id for Studio telemetry without blocking deployment paths."""
    account_id = cloud_account_id_from_value(
        (environment or {}).get(STUDIO_ACCOUNT_ID_ENV)
    )
    if account_id:
        return StudioAccountIdResolution(account_id=account_id)

    account_id = studio_account_id_from_remote_function(remote_function)
    if account_id:
        return StudioAccountIdResolution(account_id=account_id)

    error = ""
    if access_key and secret_key and region:
        from frontend.server.storage.provisioning import (
            resolve_studio_account_id_for_deploy,
        )

        try:
            account_id = resolve_studio_account_id_for_deploy(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                region=region,
                provider=provider,
            )
            account_id = cloud_account_id_from_value(account_id)
            if account_id:
                return StudioAccountIdResolution(account_id=account_id)
        except Exception as exc:
            error = (
                error_formatter(exc)
                if error_formatter is not None
                else sanitize_account_id_resolution_error(
                    exc,
                    secrets=(access_key, secret_key, session_token),
                )
            )

    account_id = studio_account_id_from_environment(environment)
    if account_id:
        return StudioAccountIdResolution(account_id=account_id)

    return StudioAccountIdResolution(error=error)


def studio_account_id_environment(
    resolution: StudioAccountIdResolution,
    *,
    clear_error_on_success: bool = False,
) -> dict[str, str]:
    """Build Function environment overrides for account id telemetry metadata."""
    if resolution.account_id:
        environment = {STUDIO_ACCOUNT_ID_ENV: resolution.account_id}
        if clear_error_on_success:
            environment[STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV] = ""
        return environment
    if resolution.error:
        return {STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV: resolution.error}
    return {}


__all__ = [
    "STUDIO_ACCOUNT_ID_ENV",
    "STUDIO_ACCOUNT_ID_RESOLUTION_ERROR_ENV",
    "StudioAccountIdResolution",
    "cloud_account_id_from_value",
    "resolve_studio_account_id_metadata",
    "sanitize_account_id_resolution_error",
    "studio_account_id_environment",
    "studio_account_id_from_environment",
    "studio_account_id_from_remote_function",
    "studio_account_id_from_tos_bucket",
]
