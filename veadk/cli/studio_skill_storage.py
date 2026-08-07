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

"""Provider-aware object storage for publishing Studio Skill archives."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentkit.platform import VolcConfiguration
from agentkit.platform.context import default_cloud_provider
from agentkit.toolkit.config.constants import DEFAULT_TOS_BUCKET_TEMPLATE_NAME
from agentkit.toolkit.volcengine.sts import VeSTS

from veadk.cli.studio_cloud_credentials import resolve_studio_cloud_credentials
from veadk.utils.cloud_provider import (
    CloudProvider,
    cloud_provider_from_env,
    normalize_cloud_provider,
)

_DEFAULT_PREFIX = "agentkit/skills"
_BUCKET_OWNERSHIP_ATTEMPTS = 6
_BUCKET_OWNERSHIP_DELAY_SECONDS = 2


class StudioSkillStorageError(RuntimeError):
    """A Skill archive could not be stored under the active cloud account."""


@dataclass(frozen=True, slots=True)
class StudioSkillUpload:
    bucket_name: str
    object_key: str
    url: str


def upload_skill_archive(
    archive_path: str | os.PathLike[str],
    *,
    configured_bucket: str = "",
    prefix: str = _DEFAULT_PREFIX,
    region: str,
    provider: CloudProvider | None = None,
) -> StudioSkillUpload:
    """Upload one content-addressed Skill archive through the active provider."""
    archive = Path(archive_path)
    if not archive.is_file():
        raise FileNotFoundError(f"Skill archive not found: {archive}")

    provider_id = normalize_cloud_provider(provider or cloud_provider_from_env())
    platform = VolcConfiguration(
        region=region,
        provider=provider_id,
    )
    try:
        credentials = platform.get_service_credentials("tos")
    except ValueError:
        if provider_id != "byteplus":
            raise
        credentials = resolve_studio_cloud_credentials(provider_id)
    endpoint = platform.get_service_endpoint("tos")

    import tos

    client = tos.TosClientV2(
        credentials.access_key,
        credentials.secret_key,
        endpoint.host,
        endpoint.region,
        security_token=credentials.session_token or None,
        connection_time=10,
        socket_timeout=30,
        max_retry_count=2,
    )
    try:
        bucket_name = configured_bucket.strip() or _default_bucket_name(
            credentials.access_key,
            credentials.secret_key,
            credentials.session_token,
            region=region,
            provider=provider_id,
        )
        _ensure_owned_bucket(
            client,
            bucket_name=bucket_name,
            region=endpoint.region,
        )
        effective_prefix = prefix.strip() or _DEFAULT_PREFIX
        object_key = f"{effective_prefix.rstrip('/')}/{archive.name}"
        client.put_object_from_file(
            bucket=bucket_name,
            key=object_key,
            file_path=str(archive),
        )
        return StudioSkillUpload(
            bucket_name=bucket_name,
            object_key=object_key,
            url=f"https://{bucket_name}.{endpoint.host}/{object_key}",
        )
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()


def _default_bucket_name(
    access_key: str,
    secret_key: str,
    session_token: str,
    *,
    region: str,
    provider: CloudProvider,
) -> str:
    with default_cloud_provider(provider):
        account_id = VeSTS(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            region=region,
        ).get_account_id()
    if account_id is None or not str(account_id).strip():
        raise StudioSkillStorageError(
            "Cloud account ID is unavailable for Skill storage."
        )
    bucket_name = DEFAULT_TOS_BUCKET_TEMPLATE_NAME.replace(
        "{{account_id}}", str(account_id).strip()
    )
    if "{{" in bucket_name or "}}" in bucket_name:
        raise StudioSkillStorageError(
            "Default Skill storage bucket template is unresolved."
        )
    bucket_name = re.sub(r"[^a-z0-9-]", "-", bucket_name.lower())[:63]
    if len(bucket_name) < 3:
        raise StudioSkillStorageError("Default Skill storage bucket name is invalid.")
    return bucket_name


def _owned_buckets(client: Any) -> dict[str, str]:
    response = client.list_buckets()
    return {
        str(getattr(bucket, "name", "") or ""): str(
            getattr(bucket, "location", "") or ""
        )
        for bucket in (getattr(response, "buckets", None) or [])
        if getattr(bucket, "name", None)
    }


def _ensure_owned_bucket(
    client: Any,
    *,
    bucket_name: str,
    region: str,
) -> None:
    owned = _owned_buckets(client)
    if bucket_name in owned:
        _require_bucket_region(bucket_name, owned[bucket_name], region)
        return

    try:
        client.create_bucket(bucket=bucket_name)
    except Exception as error:
        if getattr(error, "status_code", None) != 409:
            raise

    for attempt in range(_BUCKET_OWNERSHIP_ATTEMPTS):
        owned = _owned_buckets(client)
        if bucket_name in owned:
            _require_bucket_region(bucket_name, owned[bucket_name], region)
            return
        if attempt + 1 < _BUCKET_OWNERSHIP_ATTEMPTS:
            time.sleep(_BUCKET_OWNERSHIP_DELAY_SECONDS)
    raise StudioSkillStorageError(
        f"Skill storage bucket '{bucket_name}' is not owned by the active account."
    )


def _require_bucket_region(
    bucket_name: str,
    actual_region: str,
    expected_region: str,
) -> None:
    if actual_region and actual_region != expected_region:
        raise StudioSkillStorageError(
            f"Skill storage bucket '{bucket_name}' belongs to region "
            f"'{actual_region}', not '{expected_region}'."
        )
