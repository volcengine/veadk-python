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

"""Website integration state, token signing, and domain validation."""

from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Protocol, TypeVar
from urllib.parse import SplitResult, urlsplit
from uuid import uuid4

from .models import (
    CreateWebsiteIntegrationBody,
    WebsiteIntegration,
    WebsiteIntegrationSession,
)
from .repository import (
    PersistedWebsiteIntegration,
    TosWebsiteIntegrationRepository,
    owner_digest,
    token_digest,
)

_T = TypeVar("_T")


def _parsed_domain(value: str) -> SplitResult:
    raw = value.strip()
    if not raw or "*" in raw:
        raise ValueError("请输入有效域名")
    parsed = urlsplit(raw if "://" in raw else f"//{raw}")
    if parsed.scheme and parsed.scheme not in {"http", "https"}:
        raise ValueError("仅支持 http 或 https 网站")
    if parsed.username or parsed.password:
        raise ValueError("域名不能包含登录信息")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("请输入域名，不要包含路径或参数")
    if not parsed.hostname:
        raise ValueError("请输入有效域名")
    try:
        _ = parsed.port
    except ValueError as error:
        raise ValueError("端口格式不正确") from error
    return parsed


def _normalized_hostname(hostname: str) -> str:
    host = hostname.rstrip(".").lower()
    if not host:
        raise ValueError("请输入有效域名")
    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        pass
    try:
        ascii_host = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise ValueError("请输入有效域名") from error
    labels = ascii_host.split(".")
    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not all(character.isalnum() or character == "-" for character in label)
        for label in labels
    ):
        raise ValueError("请输入有效域名")
    return ascii_host


def normalize_domain(value: str) -> str:
    parsed = _parsed_domain(value)
    hostname = _normalized_hostname(parsed.hostname or "")
    return f"{hostname}:{parsed.port}" if parsed.port is not None else hostname


def origin_matches_domain(origin: str, domain: str) -> bool:
    try:
        parsed_origin = urlsplit(origin.strip())
        if parsed_origin.scheme not in {"http", "https"}:
            return False
        if (
            not parsed_origin.hostname
            or parsed_origin.username
            or parsed_origin.password
            or parsed_origin.path not in {"", "/"}
            or parsed_origin.query
            or parsed_origin.fragment
        ):
            return False
        origin_host = _normalized_hostname(parsed_origin.hostname)
        origin_port = parsed_origin.port
        configured = _parsed_domain(domain)
        configured_host = _normalized_hostname(configured.hostname or "")
        configured_port = configured.port
    except (ValueError, UnicodeError):
        return False
    return origin_host == configured_host and (
        configured_port is None or configured_port == origin_port
    )


class WebsiteIntegrationService(Protocol):
    def list(self, owner_id: str) -> list[WebsiteIntegration]: ...

    def create(
        self, owner_id: str, body: CreateWebsiteIntegrationBody
    ) -> WebsiteIntegration: ...

    def delete(self, owner_id: str, integration_id: str) -> bool: ...

    def bootstrap(
        self, token: str, origin: str
    ) -> WebsiteIntegrationSession | None: ...

    def integration_for_session(self, token: str) -> WebsiteIntegration | None: ...


class WebsiteIntegrationStorageError(RuntimeError):
    """Raised when persistent website integration data cannot be accessed."""


class WebsiteIntegrationTokenSigner:
    """Create reproducible embed tokens without storing their plaintext."""

    _PREFIX = "wsi_"

    def __init__(self, signing_key: bytes | str) -> None:
        normalized = (
            signing_key.encode("utf-8") if isinstance(signing_key, str) else signing_key
        )
        if not normalized:
            raise ValueError("Website integration signing key must not be empty.")
        self._signing_key = normalized

    def token(self, integration_id: str) -> str:
        signature = hmac.new(
            self._signing_key,
            b"veadk-studio-website-integration-v1\0" + integration_id.encode("ascii"),
            hashlib.sha256,
        ).digest()
        encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
        return f"{self._PREFIX}{integration_id}.{encoded}"

    def integration_id(self, token: str) -> str | None:
        value = token.strip()
        if not value.startswith(self._PREFIX):
            return None
        integration_id, separator, _ = value[len(self._PREFIX) :].partition(".")
        if separator != "." or len(integration_id) != 32:
            return None
        try:
            int(integration_id, 16)
        except ValueError:
            return None
        expected = self.token(integration_id)
        return integration_id if hmac.compare_digest(value, expected) else None


class InMemoryWebsiteIntegrationService:
    """Process-local storage used by the first website integration iteration."""

    def __init__(self, *, session_ttl: timedelta = timedelta(hours=1)) -> None:
        self._session_ttl = session_ttl
        self._integrations: dict[str, WebsiteIntegration] = {}
        self._integration_tokens: dict[str, str] = {}
        self._sessions: dict[str, WebsiteIntegrationSession] = {}
        self._lock = RLock()

    def list(self, owner_id: str) -> list[WebsiteIntegration]:
        with self._lock:
            items = [
                item
                for item in self._integrations.values()
                if item.owner_id == owner_id
            ]
        return sorted(items, key=lambda item: item.created_at, reverse=True)

    def create(
        self, owner_id: str, body: CreateWebsiteIntegrationBody
    ) -> WebsiteIntegration:
        domain = normalize_domain(body.domain)
        integration = WebsiteIntegration(
            id=uuid4().hex,
            owner_id=owner_id,
            domain=domain,
            runtime_id=body.runtime_id.strip(),
            runtime_name=body.runtime_name.strip(),
            region=body.region.strip(),
            app_name=body.app_name.strip(),
            token=f"wsi_{secrets.token_urlsafe(32)}",
            created_at=datetime.now(timezone.utc),
        )
        with self._lock:
            self._integrations[integration.id] = integration
            self._integration_tokens[integration.token] = integration.id
        return integration

    def delete(self, owner_id: str, integration_id: str) -> bool:
        with self._lock:
            integration = self._integrations.get(integration_id)
            if integration is None or integration.owner_id != owner_id:
                return False
            del self._integrations[integration_id]
            self._integration_tokens.pop(integration.token, None)
            stale_sessions = [
                token
                for token, session in self._sessions.items()
                if session.integration_id == integration_id
            ]
            for token in stale_sessions:
                self._sessions.pop(token, None)
        return True

    def bootstrap(self, token: str, origin: str) -> WebsiteIntegrationSession | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            integration_id = self._integration_tokens.get(token)
            integration = (
                self._integrations.get(integration_id) if integration_id else None
            )
            if integration is None or not origin_matches_domain(
                origin, integration.domain
            ):
                return None
            session = WebsiteIntegrationSession(
                token=f"wsis_{secrets.token_urlsafe(32)}",
                integration_id=integration.id,
                expires_at=now + self._session_ttl,
            )
            self._sessions[session.token] = session
            self._purge_expired(now)
            return session

    def integration_for_session(self, token: str) -> WebsiteIntegration | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._purge_expired(now)
            session = self._sessions.get(token)
            if session is None or session.expires_at <= now:
                return None
            return self._integrations.get(session.integration_id)

    def _purge_expired(self, now: datetime) -> None:
        expired = [
            token
            for token, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for token in expired:
            self._sessions.pop(token, None)


class TosWebsiteIntegrationService:
    """Persist integrations in TOS while keeping short sessions process-local."""

    def __init__(
        self,
        repository: TosWebsiteIntegrationRepository,
        *,
        signing_key: bytes | str,
        session_ttl: timedelta = timedelta(hours=1),
    ) -> None:
        self._repository = repository
        self._signer = WebsiteIntegrationTokenSigner(signing_key)
        self._session_ttl = session_ttl
        self._sessions: dict[str, WebsiteIntegrationSession] = {}
        self._lock = RLock()

    def list(self, owner_id: str) -> list[WebsiteIntegration]:
        owner_hash = owner_digest(owner_id)
        records = self._storage_call(lambda: self._repository.list(owner_hash))
        return [self._integration(record, owner_id=owner_id) for record in records]

    def create(
        self, owner_id: str, body: CreateWebsiteIntegrationBody
    ) -> WebsiteIntegration:
        integration_id = uuid4().hex
        token = self._signer.token(integration_id)
        record = PersistedWebsiteIntegration(
            id=integration_id,
            owner_hash=owner_digest(owner_id),
            domain=normalize_domain(body.domain),
            runtime_id=body.runtime_id.strip(),
            runtime_name=body.runtime_name.strip(),
            region=body.region.strip(),
            app_name=body.app_name.strip(),
            token_hash=token_digest(token),
            created_at=datetime.now(timezone.utc),
        )
        self._storage_call(lambda: self._repository.create(record))
        return self._integration(record, owner_id=owner_id)

    def delete(self, owner_id: str, integration_id: str) -> bool:
        record = self._storage_call(lambda: self._repository.get(integration_id))
        if record is None or record.owner_hash != owner_digest(owner_id):
            return False
        self._storage_call(lambda: self._repository.delete(record))
        with self._lock:
            stale_sessions = [
                token
                for token, session in self._sessions.items()
                if session.integration_id == integration_id
            ]
            for token in stale_sessions:
                self._sessions.pop(token, None)
        return True

    def bootstrap(self, token: str, origin: str) -> WebsiteIntegrationSession | None:
        integration_id = self._signer.integration_id(token)
        if integration_id is None:
            return None
        record = self._storage_call(lambda: self._repository.get(integration_id))
        if (
            record is None
            or not hmac.compare_digest(record.token_hash, token_digest(token))
            or not origin_matches_domain(origin, record.domain)
        ):
            return None
        now = datetime.now(timezone.utc)
        session = WebsiteIntegrationSession(
            token=f"wsis_{secrets.token_urlsafe(32)}",
            integration_id=record.id,
            expires_at=now + self._session_ttl,
        )
        with self._lock:
            self._sessions[session.token] = session
            self._purge_expired(now)
        return session

    def integration_for_session(self, token: str) -> WebsiteIntegration | None:
        now = datetime.now(timezone.utc)
        with self._lock:
            self._purge_expired(now)
            session = self._sessions.get(token)
            if session is None or session.expires_at <= now:
                return None
            integration_id = session.integration_id
        record = self._storage_call(lambda: self._repository.get(integration_id))
        if record is None:
            with self._lock:
                self._sessions.pop(token, None)
            return None
        return self._integration(record)

    def _integration(
        self,
        record: PersistedWebsiteIntegration,
        *,
        owner_id: str = "",
    ) -> WebsiteIntegration:
        token = self._signer.token(record.id)
        if not hmac.compare_digest(record.token_hash, token_digest(token)):
            raise WebsiteIntegrationStorageError("网站集成签名密钥与持久化数据不匹配")
        return WebsiteIntegration(
            id=record.id,
            owner_id=owner_id,
            domain=record.domain,
            runtime_id=record.runtime_id,
            runtime_name=record.runtime_name,
            region=record.region,
            app_name=record.app_name,
            token=token,
            created_at=record.created_at,
        )

    def _purge_expired(self, now: datetime) -> None:
        expired = [
            token
            for token, session in self._sessions.items()
            if session.expires_at <= now
        ]
        for token in expired:
            self._sessions.pop(token, None)

    @staticmethod
    def _storage_call(operation: Callable[[], _T]) -> _T:
        try:
            return operation()
        except WebsiteIntegrationStorageError:
            raise
        except Exception as error:
            raise WebsiteIntegrationStorageError(
                "网站集成持久化存储暂时不可用"
            ) from error


__all__ = [
    "InMemoryWebsiteIntegrationService",
    "TosWebsiteIntegrationService",
    "WebsiteIntegrationService",
    "WebsiteIntegrationStorageError",
    "WebsiteIntegrationTokenSigner",
    "normalize_domain",
    "origin_matches_domain",
]
