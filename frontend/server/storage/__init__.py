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

"""Shared persistent-storage configuration for AgentKit Studio."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote

from veadk.multimodal.models import MediaRef
from veadk.multimodal.storage import TosMediaStorage

StudioProvider = Literal["volcengine", "byteplus"]

STUDIO_STORAGE_ROOT_PREFIX = "veadk-studio/v1"
STUDIO_STORAGE_UNAVAILABLE_REASON = "管理员未配置持久化存储"


def _value(source: Mapping[str, str], key: str) -> str:
    return str(source.get(key) or "").strip()


@dataclass(frozen=True)
class StudioStorageConfig:
    """The two administrator-owned values needed by Studio storage."""

    provider: StudioProvider
    bucket: str
    region: str
    endpoint: str

    @property
    def configured(self) -> bool:
        return bool(self.bucket and self.region)

    @property
    def object_host(self) -> str:
        if not self.configured:
            return ""
        return f"{self.bucket}.{self.endpoint}"

    @property
    def unavailable_reason(self) -> str:
        return "" if self.configured else STUDIO_STORAGE_UNAVAILABLE_REASON

    @classmethod
    def from_env(
        cls,
        provider: StudioProvider,
        source: Mapping[str, str] | None = None,
    ) -> StudioStorageConfig:
        if provider not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported Studio storage provider: {provider}")
        environment = source if source is not None else os.environ
        bucket = _value(environment, "VEADK_STUDIO_TOS_BUCKET")
        region = _value(environment, "VEADK_STUDIO_TOS_REGION")
        endpoint = ""

        # Keep one-release compatibility for existing video-storage deployments.
        # New installations only need the two VEADK_STUDIO_TOS_* values above.
        if not bucket and not region:
            backend = _value(
                environment,
                "VEADK_VIDEO_ASSET_STORAGE",
            ) or _value(environment, "VEADK_MEDIA_STORAGE")
            if backend.lower() == "tos":
                bucket = _value(
                    environment,
                    "VEADK_VIDEO_TOS_BUCKET",
                ) or _value(environment, "DATABASE_TOS_BUCKET")
                region = _value(
                    environment,
                    "VEADK_VIDEO_TOS_REGION",
                ) or _value(environment, "DATABASE_TOS_REGION")
                endpoint = _value(
                    environment,
                    "VEADK_VIDEO_TOS_ENDPOINT",
                ) or _value(environment, "DATABASE_TOS_ENDPOINT")

        if region and not endpoint:
            domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
            endpoint = f"tos-{region}.{domain}"
        return cls(
            provider=provider,
            bucket=bucket,
            region=region,
            endpoint=endpoint,
        )


def studio_object_key(
    ref: MediaRef,
    name: str,
    *,
    root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
) -> str:
    """Build a stable user-first key for a Studio-owned object."""
    segments = (
        root_prefix.strip("/"),
        "users",
        quote(ref.user_id, safe=""),
        quote(ref.app_name, safe=""),
        quote(ref.session_id, safe=""),
        quote(ref.media_id, safe=""),
        quote(name, safe=""),
    )
    if any(not segment for segment in segments):
        raise ValueError("Studio storage object-key segments cannot be empty.")
    return "/".join(segments)


class StudioTosMediaStorage(TosMediaStorage):
    """Use the existing TOS transport with Studio's user-first key layout."""

    def _key(self, ref: MediaRef, name: str) -> str:
        return studio_object_key(ref, name, root_prefix=self._key_prefix)

    def _session_key_prefix(
        self,
        app_name: str,
        user_id: str,
        session_id: str,
    ) -> str:
        segments = (
            self._key_prefix,
            "users",
            quote(user_id, safe=""),
            quote(app_name, safe=""),
            quote(session_id, safe=""),
        )
        return "/".join(segments)


__all__ = [
    "STUDIO_STORAGE_ROOT_PREFIX",
    "STUDIO_STORAGE_UNAVAILABLE_REASON",
    "StudioStorageConfig",
    "StudioTosMediaStorage",
    "studio_object_key",
]
