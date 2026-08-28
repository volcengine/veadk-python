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

"""TOS storage helpers for Studio Skill publishing."""

from __future__ import annotations

import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from frontend.server.storage import StudioProvider, StudioStorageConfig
from frontend.server.storage.tos import create_tos_client_factory
from veadk.utils.cloud_provider import cloud_provider_from_env

_IAM_CREDENTIAL_PATH = Path("/var/run/secrets/iam/credential")
_DEFAULT_SKILL_PREFIX = "agentkit/skills"

SkillPublishBucketMode = Literal[
    "skill-env",
    "studio-storage",
    "config",
    "auto-generated",
]


class SkillPublishStorageError(RuntimeError):
    """Raised when Skill publishing storage cannot be resolved safely."""


@dataclass(frozen=True)
class SkillPublishCredentials:
    access_key: str
    secret_key: str
    session_token: str
    source: str


@dataclass(frozen=True)
class SkillPublishStorage:
    provider: StudioProvider
    region: str
    bucket: str
    prefix: str
    endpoint: str
    bucket_mode: SkillPublishBucketMode

    @property
    def auto_bucket(self) -> bool:
        return self.bucket_mode == "auto-generated"


def _read_vefaas_iam_credentials() -> SkillPublishCredentials | None:
    try:
        with _IAM_CREDENTIAL_PATH.open(encoding="utf-8") as stream:
            data = json.load(stream)
    except (OSError, ValueError):
        return None
    access_key = str(data.get("access_key_id") or data.get("AccessKeyId") or "")
    secret_key = str(data.get("secret_access_key") or data.get("SecretAccessKey") or "")
    session_token = str(data.get("session_token") or data.get("SessionToken") or "")
    if access_key and secret_key:
        return SkillPublishCredentials(
            access_key=access_key,
            secret_key=secret_key,
            session_token=session_token,
            source="iam-file",
        )
    return None


def resolve_skill_publish_credentials(
    *,
    provider: StudioProvider | None = None,
    source: Mapping[str, str] | None = None,
) -> SkillPublishCredentials:
    resolved_provider = provider or cloud_provider_from_env()
    environment = source if source is not None else os.environ
    if resolved_provider == "byteplus":
        access_key = str(environment.get("BYTEPLUS_ACCESS_KEY") or "")
        secret_key = str(environment.get("BYTEPLUS_SECRET_KEY") or "")
        session_token = str(environment.get("BYTEPLUS_SESSION_TOKEN") or "")
        if access_key and secret_key:
            return SkillPublishCredentials(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                source="env",
            )
    else:
        access_key = str(
            environment.get("VOLCENGINE_ACCESS_KEY")
            or environment.get("VOLC_ACCESSKEY")
            or ""
        )
        secret_key = str(
            environment.get("VOLCENGINE_SECRET_KEY")
            or environment.get("VOLC_SECRETKEY")
            or ""
        )
        session_token = str(
            environment.get("VOLCENGINE_SESSION_TOKEN")
            or environment.get("VOLC_SESSIONTOKEN")
            or ""
        )
        if access_key and secret_key:
            return SkillPublishCredentials(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                source="env",
            )

    iam_credentials = _read_vefaas_iam_credentials()
    if iam_credentials is not None:
        return iam_credentials

    try:
        from agentkit.platform.configuration import VolcConfiguration

        credentials = VolcConfiguration(
            provider=resolved_provider
        ).get_service_credentials("tos")
    except Exception as error:
        raise SkillPublishStorageError(
            f"无法解析 Skill 发布所需的 TOS 凭证：{error}"
        ) from error
    access_key = str(getattr(credentials, "access_key", "") or "")
    secret_key = str(getattr(credentials, "secret_key", "") or "")
    if not access_key or not secret_key:
        raise SkillPublishStorageError("Skill 发布所需的 TOS 凭证为空。")
    return SkillPublishCredentials(
        access_key=access_key,
        secret_key=secret_key,
        session_token=str(getattr(credentials, "session_token", "") or ""),
        source=str(getattr(credentials, "source", "") or "sdk"),
    )


def resolve_skill_publish_storage(
    *,
    region: str,
    config_bucket: str = "",
    config_prefix: str = "",
    source: Mapping[str, str] | None = None,
) -> SkillPublishStorage:
    provider = cloud_provider_from_env()
    environment = source if source is not None else os.environ
    prefix = (
        str(environment.get("VEADK_SKILL_CREATOR_TOS_PREFIX") or "").strip()
        or config_prefix.strip()
        or _DEFAULT_SKILL_PREFIX
    )
    skill_bucket = str(environment.get("VEADK_SKILL_CREATOR_TOS_BUCKET") or "").strip()
    studio_storage = StudioStorageConfig.from_env(provider, environment)
    if skill_bucket:
        bucket = skill_bucket
        bucket_mode: SkillPublishBucketMode = "skill-env"
    elif studio_storage.bucket:
        if studio_storage.region and studio_storage.region != region:
            raise SkillPublishStorageError(
                "Studio TOS 桶地域与 Skill 发布地域不一致："
                f"{studio_storage.bucket} 位于 {studio_storage.region}，"
                f"当前发布地域为 {region}。"
            )
        bucket = studio_storage.bucket
        bucket_mode = "studio-storage"
    elif config_bucket.strip():
        bucket = config_bucket.strip()
        bucket_mode = "config"
    else:
        from agentkit.toolkit.volcengine.services.tos_service import TOSService

        bucket = TOSService.generate_bucket_name()
        bucket_mode = "auto-generated"

    endpoint_region = region.strip()
    if not endpoint_region:
        raise SkillPublishStorageError("Skill 发布地域为空，无法确定 TOS endpoint。")
    domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
    return SkillPublishStorage(
        provider=provider,
        region=endpoint_region,
        bucket=bucket,
        prefix=prefix,
        endpoint=f"tos-{endpoint_region}.{domain}",
        bucket_mode=bucket_mode,
    )


def _create_tos_client(
    storage: SkillPublishStorage,
    credentials: SkillPublishCredentials,
) -> Any:
    config = StudioStorageConfig(
        provider=storage.provider,
        bucket=storage.bucket,
        region=storage.region,
        endpoint=storage.endpoint,
    )
    return create_tos_client_factory(
        config,
        lambda: (
            credentials.access_key,
            credentials.secret_key,
            credentials.session_token,
        ),
    )()


def _listed_buckets(client: Any) -> dict[str, str]:
    try:
        result = client.list_buckets()
    except Exception as error:
        raise SkillPublishStorageError(
            f"无法读取当前账号的 TOS 桶，已阻止上传 Skill 包：{error}"
        ) from error
    return {
        str(getattr(bucket, "name", "") or "").strip(): str(
            getattr(bucket, "location", "") or ""
        ).strip()
        for bucket in (getattr(result, "buckets", None) or [])
        if str(getattr(bucket, "name", "") or "").strip()
    }


def ensure_skill_publish_bucket(
    storage: SkillPublishStorage,
    credentials: SkillPublishCredentials,
) -> None:
    client = _create_tos_client(storage, credentials)
    buckets = _listed_buckets(client)
    existing_region = buckets.get(storage.bucket)
    if existing_region:
        if existing_region != storage.region:
            raise SkillPublishStorageError(
                f"TOS 桶 {storage.bucket} 已位于 {existing_region}，"
                f"不能用于发布地域 {storage.region}。"
            )
        return

    try:
        client.create_bucket(bucket=storage.bucket)
    except Exception as error:
        buckets = _listed_buckets(client)
        if buckets.get(storage.bucket) == storage.region:
            return
        status_code = getattr(error, "status_code", None)
        error_code = str(getattr(error, "code", "") or error)
        if status_code == 409 or "BucketAlready" in error_code:
            raise SkillPublishStorageError(
                f"TOS 桶名 {storage.bucket} 已被其他账号占用，已阻止上传 Skill 包。"
            ) from error
        raise SkillPublishStorageError(
            f"创建 Skill 发布 TOS 桶 {storage.bucket} 失败：{error}"
        ) from error

    deadline = time.time() + 10
    while time.time() < deadline:
        buckets = _listed_buckets(client)
        if buckets.get(storage.bucket) == storage.region:
            return
        time.sleep(2)
    raise SkillPublishStorageError(
        f"创建 TOS 桶 {storage.bucket} 后无法确认归属，已阻止上传 Skill 包。"
    )


def upload_skill_archive(
    zip_abs: str,
    storage: SkillPublishStorage,
    credentials: SkillPublishCredentials,
) -> str:
    client = _create_tos_client(storage, credentials)
    effective_prefix = storage.prefix.strip("/") or _DEFAULT_SKILL_PREFIX
    key = f"{effective_prefix}/{Path(zip_abs).name}"
    try:
        client.put_object_from_file(
            bucket=storage.bucket,
            key=key,
            file_path=zip_abs,
            content_type="application/zip",
        )
    except Exception as error:
        raise SkillPublishStorageError(
            f"上传 Skill 包到 TOS 失败：bucket={storage.bucket}, key={key}, error={error}"
        ) from error
    return f"https://{storage.bucket}.{storage.endpoint}/{key}"


__all__ = [
    "SkillPublishCredentials",
    "SkillPublishStorage",
    "SkillPublishStorageError",
    "ensure_skill_publish_bucket",
    "resolve_skill_publish_credentials",
    "resolve_skill_publish_storage",
    "upload_skill_archive",
]
