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

"""Process-local AgentKit Identity credential resolution.

The API key is deliberately never written to an environment variable, file,
database, log message, exception, or response.
"""

from __future__ import annotations

import asyncio
import os
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from typing import Any

from veadk.integrations.ve_identity.identity_client import IdentityClient

SESSION_MODEL_CACHE_CAPACITY = 2000
SESSION_MODEL_CACHE_TTL_SECONDS = 60 * 60


class RuntimeIdentityError(RuntimeError):
    """A sanitized Identity failure safe to expose to the Runtime caller."""

    def __init__(self, category: str, retryable: bool) -> None:
        super().__init__(f"AgentKit Identity {category}")
        self.category = category
        self.retryable = retryable


def _api_key_value(value: Any) -> str:
    if isinstance(value, str):
        key = value
    elif isinstance(value, dict):
        key = value.get("api_key") or value.get("ApiKey") or ""
    else:
        key = getattr(value, "api_key", None) or getattr(value, "ApiKey", "")
    if not isinstance(key, str) or not key:
        raise RuntimeIdentityError("invalid_response", False)
    return key


def _category(error: Exception) -> tuple[str, bool]:
    status = getattr(error, "status", None) or getattr(error, "status_code", None)
    if str(status) in {"401", "403"}:
        return "authentication_failed", False
    if str(status) == "404":
        return "provider_not_found", False
    if str(status) in {"408", "429", "500", "502", "503", "504"}:
        return "network_error", True
    text = f"{type(error).__name__} {error}".lower()
    if any(
        token in text
        for token in (
            "unauthorized",
            "forbidden",
            "accessdenied",
            "authentication",
            "invalididentitytoken",
            "401",
            "403",
        )
    ):
        return "authentication_failed", False
    if any(token in text for token in ("notfound", "not found", "404")):
        return "provider_not_found", False
    if any(
        token in text
        for token in (
            "timeout",
            "connection",
            "temporar",
            "429",
            "500",
            "502",
            "503",
            "504",
        )
    ):
        return "network_error", True
    return "identity_error", False


class _CachedKey:
    def __init__(self, value: str, expires_at: float | None) -> None:
        self.value = value
        self.expires_at = expires_at


class RuntimeCredentialProvider:
    """Cache gateway keys until invalidated; model keys have a bounded TTL."""

    def __init__(
        self,
        *,
        runtime_id: str,
        provider_name: str | None = None,
        region: str = "cn-beijing",
        ttl_seconds: float | None = None,
        attempts: int = 3,
        client_factory: Callable[[], Any] | None = None,
        credential_kind: str = "model",
        pool_name: str | None = None,
    ) -> None:
        if not runtime_id:
            raise ValueError("Runtime identity references are required")
        self.runtime_id = runtime_id
        pattern = (
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}"
            if credential_kind == "mcp"
            else r"ma-ark-[a-z2-7]{52}"
        )
        if credential_kind not in {"model", "mcp"}:
            raise RuntimeIdentityError("invalid_provider_reference", False)
        if provider_name is not None and not re.fullmatch(pattern, provider_name):
            raise RuntimeIdentityError("invalid_provider_reference", False)
        self.provider_name = provider_name or runtime_id + "-ma"
        self.region = region
        self.pool_name = pool_name
        max_ttl = SESSION_MODEL_CACHE_TTL_SECONDS if provider_name is not None else 60.0
        if ttl_seconds is None and provider_name is not None:
            ttl_seconds = SESSION_MODEL_CACHE_TTL_SECONDS
        self.ttl_seconds = (
            None if ttl_seconds is None else min(max_ttl, max(0.0, ttl_seconds))
        )
        self.attempts = min(3, max(1, attempts))
        self.client_factory = client_factory or (lambda: IdentityClient(region=region))
        self._cached: _CachedKey | None = None
        self._lock = threading.Lock()

    def invalidate(self) -> None:
        with self._lock:
            self._cached = None

    async def get(self, *, force_refresh: bool = False) -> str:
        return await asyncio.to_thread(self.get_sync, force_refresh=force_refresh)

    def get_sync(self, *, force_refresh: bool = False) -> str:
        """Resolve credentials for the existing synchronous sandbox client."""
        with self._lock:
            now = time.monotonic()
            if (
                not force_refresh
                and self._cached
                and (self._cached.expires_at is None or self._cached.expires_at > now)
            ):
                return self._cached.value
            self._cached = None
            last: RuntimeIdentityError | None = None
            for attempt in range(self.attempts):
                phase = "workload"
                try:
                    client = self.client_factory()
                    token = client.get_workload_access_token(
                        workload_name=self.runtime_id,
                    )
                    token_value = getattr(token, "workload_access_token", None)
                    if not isinstance(token_value, str) or not token_value:
                        raise RuntimeIdentityError("invalid_token_response", False)
                    phase = "provider"
                    kwargs = {
                        "provider_name": self.provider_name,
                        "agent_identity_token": token_value,
                    }
                    if self.pool_name is not None:
                        kwargs["pool_name"] = self.pool_name
                    raw = client.get_api_key(**kwargs)
                    key = _api_key_value(raw)
                    expires_at = (
                        None
                        if self.ttl_seconds is None
                        else time.monotonic() + self.ttl_seconds
                    )
                    self._cached = _CachedKey(key, expires_at)
                    return key
                except RuntimeIdentityError as error:
                    last = error
                except Exception as error:  # noqa: BLE001 - never expose secret-bearing SDK errors.
                    category, retryable = _category(error)
                    if phase == "workload" and category == "provider_not_found":
                        category, retryable = "authentication_failed", False
                    last = RuntimeIdentityError(category, retryable)
                if not last.retryable or attempt + 1 >= self.attempts:
                    break
                time.sleep(0.2 * (2**attempt))
            raise last or RuntimeIdentityError("identity_error", False)


_gateway_providers: dict[tuple[str, str], RuntimeCredentialProvider] = {}
_gateway_providers_lock = threading.Lock()


def get_runtime_credential_provider(
    *, runtime_id: str, region: str = "cn-beijing"
) -> RuntimeCredentialProvider:
    """Share a gateway credential and its refresh lock across clients in this process."""
    cache_key = (runtime_id, region)
    with _gateway_providers_lock:
        provider = _gateway_providers.get(cache_key)
        if provider is None:
            provider = RuntimeCredentialProvider(runtime_id=runtime_id, region=region)
            _gateway_providers[cache_key] = provider
        return provider


class SessionModelCredentials:
    """Bounded LRU of Session model credentials, separate from endpoint keys."""

    def __init__(
        self,
        capacity: int = SESSION_MODEL_CACHE_CAPACITY,
        client_factory=None,
        ttl_seconds: float = SESSION_MODEL_CACHE_TTL_SECONDS,
    ):
        if capacity < 1:
            raise ValueError("credential cache capacity must be positive")
        self.capacity = capacity
        self.client_factory = client_factory
        self.ttl_seconds = ttl_seconds
        self._providers: OrderedDict[tuple[str, str], RuntimeCredentialProvider] = (
            OrderedDict()
        )
        self._lock = threading.Lock()

    async def get(self, session: Any) -> str:
        name = (
            session.get("ark_api_key_provider")
            if isinstance(session, dict)
            else getattr(session, "ark_api_key_provider", None)
        )
        if name is None:
            raise RuntimeIdentityError("missing_provider_reference", False)
        if not isinstance(name, str) or not re.fullmatch(r"ma-ark-[a-z2-7]{52}", name):
            raise RuntimeIdentityError("invalid_provider_reference", False)
        from veadk.integrations.mpa.session_client import _runtime_id_from_environment

        workload = _runtime_id_from_environment()
        if not workload:
            raise RuntimeIdentityError("missing_workload_identity", False)
        cache_key = (workload, name)
        with self._lock:
            provider = self._providers.get(cache_key)
            if provider is None:
                provider = RuntimeCredentialProvider(
                    runtime_id=workload,
                    provider_name=name,
                    region=os.getenv("VOLCENGINE_REGION")
                    or os.getenv("REGION")
                    or "cn-beijing",
                    client_factory=self.client_factory,
                    ttl_seconds=self.ttl_seconds,
                )
                self._providers[cache_key] = provider
                if len(self._providers) > self.capacity:
                    self._providers.popitem(last=False)
            self._providers.move_to_end(cache_key)
        return await provider.get()


session_model_credentials = SessionModelCredentials()


class MCPIdentityHeaders:
    """Keep MCP credentials out of snapshots, model state and tool arguments."""

    def __init__(self, reference: Any, *, client_factory=None):
        def field(name, default=None):
            return (
                reference.get(name, default)
                if isinstance(reference, dict)
                else getattr(reference, name, default)
            )

        self.name = field("Name")
        self.pool_name = field("PoolName")
        self.header = field("HeaderName", "Authorization")
        self.prefix = field("Prefix", "Bearer ")
        if any(
            field(k) is not None for k in ("api_key", "ApiKey", "authorization_token")
        ):
            raise RuntimeIdentityError("invalid_mcp_authorization", False)
        if not isinstance(self.name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.name
        ):
            raise RuntimeIdentityError("invalid_provider_reference", False)
        if not isinstance(self.pool_name, str) or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}", self.pool_name
        ):
            raise RuntimeIdentityError("invalid_provider_reference", False)
        if not isinstance(self.header, str) or not re.fullmatch(
            r"[A-Za-z0-9-]{1,64}", self.header
        ):
            raise RuntimeIdentityError("invalid_mcp_authorization", False)
        if (
            not isinstance(self.prefix, str)
            or len(self.prefix) > 32
            or any(c in self.prefix for c in "\r\n\x00")
        ):
            raise RuntimeIdentityError("invalid_mcp_authorization", False)
        if self.header.lower() in {"host", "cookie"} or self.header.lower().startswith(
            "proxy-"
        ):
            raise RuntimeIdentityError("invalid_mcp_authorization", False)
        self.client_factory = client_factory
        self._provider = None

    def provider(self):
        if self._provider is None:
            from veadk.integrations.mpa.session_client import (
                _runtime_id_from_environment,
            )

            workload = _runtime_id_from_environment()
            if not workload:
                raise RuntimeIdentityError("missing_workload_identity", False)
            self._provider = RuntimeCredentialProvider(
                runtime_id=workload,
                provider_name=self.name,
                credential_kind="mcp",
                pool_name=self.pool_name,
                region=os.getenv("VOLCENGINE_REGION")
                or os.getenv("REGION")
                or "cn-beijing",
                client_factory=self.client_factory,
            )
        return self._provider

    async def prepare(self):
        await self.provider().get()

    def __call__(self, _context):
        key = self.provider().get_sync()
        if any(c in key for c in "\r\n\x00"):
            raise RuntimeIdentityError("invalid_response", False)
        return {self.header: self.prefix + key}
