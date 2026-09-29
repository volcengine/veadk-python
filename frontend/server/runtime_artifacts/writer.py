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

"""Write artifacts using the Studio identity and storage credentials"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
from threading import Lock
from typing import Any

from frontend.server.runtime_artifacts.service import (
    RuntimeArtifactError,
    _mime_type,
    _path,
)
from frontend.server.storage import StudioStorageConfig
from frontend.server.storage.tos import CredentialResolver, create_tos_client_factory
from frontend.server.studio_tools.registry import (
    StudioToolExecutionContext,
    StudioToolExecutionError,
    StudioToolRuntimeError,
)
from veadk.utils.cloud_provider import CloudProvider, cloud_provider_from_env

ARTIFACT_WRITE_MAX_BYTES = 1024 * 1024
_IAM_CREDENTIAL_PATH = Path("/var/run/secrets/iam/credential")


def _resolve_credentials(provider: CloudProvider) -> tuple[str, str, str | None]:
    prefix = "BYTEPLUS" if provider == "byteplus" else "VOLCENGINE"
    access_key = os.getenv(f"{prefix}_ACCESS_KEY")
    secret_key = os.getenv(f"{prefix}_SECRET_KEY")
    token = os.getenv(f"{prefix}_SESSION_TOKEN")
    if provider == "volcengine":
        token = token or os.getenv("VOLC_SESSIONTOKEN")
    if access_key or secret_key or token:
        if not access_key or not secret_key:
            raise StudioToolRuntimeError("Studio 存储凭据不完整，请联系管理员")
        return access_key, secret_key, token or None

    try:
        data = json.loads(_IAM_CREDENTIAL_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("Invalid credential document")
        access_key = data.get("access_key_id") or data.get("AccessKeyId")
        secret_key = data.get("secret_access_key") or data.get("SecretAccessKey")
        token = data.get("session_token") or data.get("SessionToken")
        if not isinstance(access_key, str) or not isinstance(secret_key, str):
            raise ValueError("Missing role credentials")
        if not access_key or not secret_key or not isinstance(token, str) or not token:
            raise ValueError("Missing role token")
        return access_key, secret_key, token
    except (OSError, ValueError):
        raise StudioToolRuntimeError(
            "Studio 存储角色凭据不可用，请联系管理员"
        ) from None


class StudioArtifactWriter:
    def __init__(
        self, config: StudioStorageConfig, resolve_credentials: CredentialResolver
    ) -> None:
        self._config = config
        self._resolve_credentials = resolve_credentials
        self._credentials: tuple[str, str, str | None] | None = None
        self._client: Any = None
        self._lock = Lock()

    @classmethod
    def from_env(cls) -> StudioArtifactWriter:
        provider = cloud_provider_from_env()
        return cls(
            StudioStorageConfig.from_env(provider),
            lambda: _resolve_credentials(provider),
        )

    def _storage_client(self) -> Any:
        # Resolve on every invocation so a rotated role token replaces the pooled
        # client before the next write; credentials never cross the tool channel
        with self._lock:
            credentials = self._resolve_credentials()
            if self._client is None or self._credentials != credentials:
                client = create_tos_client_factory(self._config, lambda: credentials)()
                self._client = client
                self._credentials = credentials
            return self._client

    def write(
        self, arguments: dict[str, Any], context: StudioToolExecutionContext
    ) -> dict[str, Any]:
        if not context.owner_id or context.user_id != context.owner_id:
            raise StudioToolExecutionError("无法确认当前会话的产物所有者")
        path = arguments.get("path")
        content = arguments.get("content")
        if set(arguments) != {"path", "content"} or not isinstance(path, str):
            raise StudioToolExecutionError("只接受相对文件路径和 UTF-8 文本内容")
        if not isinstance(content, str):
            raise StudioToolExecutionError("产物内容必须是 UTF-8 文本")
        try:
            owner = _path(context.owner_id, single_segment=True)
            session = _path(context.session_id, single_segment=True)
            path = _path(path)
            key = _path(f"artifacts/{owner}/{session}/{path}")
            encoded = content.encode("utf-8")
        except (RuntimeArtifactError, UnicodeError):
            raise StudioToolExecutionError("产物路径或文本内容无效") from None
        if len(encoded) > ARTIFACT_WRITE_MAX_BYTES:
            raise StudioToolExecutionError("单个产物不能超过 1 MiB，请拆分文件")
        if not self._config.configured:
            raise StudioToolRuntimeError("Studio 尚未配置产物存储，请联系管理员")
        mime_type = _mime_type(path)
        try:
            self._storage_client().put_object(
                bucket=self._config.bucket,
                key=key,
                content=encoded,
                content_type=mime_type,
            )
        except StudioToolExecutionError:
            raise
        except Exception:
            # SDK exceptions may include signed request headers or URLs
            raise StudioToolRuntimeError(
                "产物保存失败，请检查 Studio 存储角色权限和网络后重试"
            ) from None
        return {
            "status": "saved",
            "artifact": {
                "path": path,
                "name": PurePosixPath(path).name,
                "mimeType": mime_type,
                "size": len(encoded),
                "sha256": hashlib.sha256(encoded).hexdigest(),
            },
        }
