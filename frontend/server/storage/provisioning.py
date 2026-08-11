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

"""Provision the shared persistent-storage bucket used by AgentKit Studio."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from . import StudioProvider, StudioStorageConfig

_ACCOUNT_ID_RE = re.compile(r"[0-9]+")


class StudioStorageProvisioningError(RuntimeError):
    """Raised when Studio storage cannot be resolved safely."""


def _resolve_account_id(
    *,
    access_key: str,
    secret_key: str,
    session_token: str,
    region: str,
) -> str:
    from agentkit.toolkit.volcengine.sts import VeSTS

    account_id = VeSTS(
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
        region=region,
    ).get_account_id()
    if account_id is None:
        raise StudioStorageProvisioningError("无法获取当前云账号 ID。")
    return str(account_id).strip()


def _create_tos_client(
    *,
    provider: StudioProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str,
) -> Any:
    import tos

    domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
    return tos.TosClientV2(
        ak=access_key,
        sk=secret_key,
        security_token=session_token,
        endpoint=f"tos-{region}.{domain}",
        region=region,
    )


def _listed_buckets(client: Any) -> dict[str, str]:
    try:
        result = client.list_buckets()
    except Exception as error:
        raise StudioStorageProvisioningError(
            f"无法读取当前账号的 TOS 桶：{error}"
        ) from error
    return {
        str(getattr(bucket, "name", "") or "").strip(): str(
            getattr(bucket, "location", "") or ""
        ).strip()
        for bucket in (getattr(result, "buckets", None) or [])
        if str(getattr(bucket, "name", "") or "").strip()
    }


def _storage_config(
    provider: StudioProvider,
    bucket: str,
    region: str,
) -> StudioStorageConfig:
    return StudioStorageConfig.from_env(
        provider,
        {
            "VEADK_STUDIO_TOS_BUCKET": bucket,
            "VEADK_STUDIO_TOS_REGION": region,
        },
    )


def _auto_bucket_name(account_id: str) -> str:
    normalized = account_id.strip()
    if not _ACCOUNT_ID_RE.fullmatch(normalized):
        raise StudioStorageProvisioningError("云账号 ID 格式无效，无法生成 TOS 桶名。")
    bucket = f"veadk-studio-{normalized}"
    if len(bucket) > 63:
        raise StudioStorageProvisioningError("云账号 ID 过长，无法生成合法 TOS 桶名。")
    return bucket


def resolve_studio_storage_for_deploy(
    *,
    provider: StudioProvider,
    region: str,
    access_key: str,
    secret_key: str,
    session_token: str = "",
    source: Mapping[str, str | None],
) -> StudioStorageConfig:
    """Resolve explicit storage or create the account-stable default bucket."""
    explicit_bucket = str(source.get("VEADK_STUDIO_TOS_BUCKET") or "").strip()
    auto_created = not explicit_bucket
    bucket = explicit_bucket
    if not bucket:
        try:
            account_id = _resolve_account_id(
                access_key=access_key,
                secret_key=secret_key,
                session_token=session_token,
                region=region,
            )
        except StudioStorageProvisioningError:
            raise
        except Exception as error:
            raise StudioStorageProvisioningError(
                f"无法获取当前云账号 ID：{error}"
            ) from error
        bucket = _auto_bucket_name(account_id)

    client = _create_tos_client(
        provider=provider,
        region=region,
        access_key=access_key,
        secret_key=secret_key,
        session_token=session_token,
    )
    buckets = _listed_buckets(client)
    existing_region = buckets.get(bucket)
    if existing_region:
        if existing_region != region:
            raise StudioStorageProvisioningError(
                f"TOS 桶 {bucket} 已位于 {existing_region}，不能在部署地域 {region} 重复创建。"
            )
        return _storage_config(provider, bucket, region)

    if not auto_created:
        raise StudioStorageProvisioningError(
            f"管理员配置的 TOS 桶 {bucket} 不存在于部署地域 {region}。"
        )

    try:
        # TOS defaults to private ACL when acl is omitted.
        client.create_bucket(bucket=bucket)
    except Exception as error:
        # A concurrent deployment may have created the same deterministic bucket.
        if _listed_buckets(client).get(bucket) == region:
            return _storage_config(provider, bucket, region)
        status_code = getattr(error, "status_code", None)
        error_code = str(getattr(error, "code", "") or error)
        if status_code == 409 or "BucketAlready" in error_code:
            raise StudioStorageProvisioningError(
                f"TOS 桶名 {bucket} 已被其他账号占用，请由管理员显式配置其他桶名。"
            ) from error
        raise StudioStorageProvisioningError(
            f"创建 Studio TOS 桶 {bucket} 失败：{error}"
        ) from error

    return _storage_config(provider, bucket, region)


__all__ = [
    "StudioStorageProvisioningError",
    "resolve_studio_storage_for_deploy",
]
