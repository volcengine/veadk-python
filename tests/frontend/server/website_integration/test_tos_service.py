# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

from __future__ import annotations

from threading import Lock
from types import SimpleNamespace

import pytest

from frontend.server.website_integration.models import CreateWebsiteIntegrationBody
from frontend.server.website_integration.repository import (
    TosWebsiteIntegrationRepository,
)
from frontend.server.website_integration.service import (
    TosWebsiteIntegrationService,
    WebsiteIntegrationStorageError,
)


class _TosError(RuntimeError):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"TOS {status_code}")
        self.status_code = status_code


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self._lock = Lock()
        self.fail_reads = False

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        forbid_overwrite: bool,
        **_: object,
    ) -> None:
        with self._lock:
            object_key = (bucket, key)
            if forbid_overwrite and object_key in self.objects:
                raise _TosError(409)
            self.objects[object_key] = bytes(content)

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        if self.fail_reads:
            raise _TosError(500)
        with self._lock:
            try:
                return [self.objects[(bucket, key)]]
            except KeyError as error:
                raise _TosError(404) from error

    def delete_object(self, *, bucket: str, key: str) -> None:
        with self._lock:
            self.objects.pop((bucket, key), None)

    def list_objects_type2(
        self,
        *,
        bucket: str,
        prefix: str,
        continuation_token: str,
        max_keys: int,
    ) -> SimpleNamespace:
        with self._lock:
            keys = sorted(
                key
                for object_bucket, key in self.objects
                if object_bucket == bucket and key.startswith(prefix)
            )
        start = int(continuation_token or 0)
        selected = keys[start : start + max_keys]
        next_index = start + len(selected)
        truncated = next_index < len(keys)
        return SimpleNamespace(
            contents=[SimpleNamespace(key=key) for key in selected],
            is_truncated=truncated,
            next_continuation_token=str(next_index) if truncated else None,
        )


def _service(
    client: _FakeTosClient,
    *,
    signing_key: str = "stable-test-signing-key",
) -> TosWebsiteIntegrationService:
    return TosWebsiteIntegrationService(
        TosWebsiteIntegrationRepository(
            bucket="studio",
            client_factory=lambda: client,
            root_prefix="test-prefix",
        ),
        signing_key=signing_key,
    )


def _body(domain: str = "example.com") -> CreateWebsiteIntegrationBody:
    return CreateWebsiteIntegrationBody(
        domain=domain,
        runtimeId="runtime-1",
        runtimeName="Runtime One",
        region="cn-beijing",
        appName="agent",
    )


def test_integration_survives_service_recreation_without_plaintext_token() -> None:
    client = _FakeTosClient()
    created = _service(client).create("owner-a", _body())

    stored = b"\n".join(client.objects.values())
    assert created.token.encode() not in stored
    assert b"owner-a" not in stored
    assert all(created.token not in key for _, key in client.objects)

    recreated = _service(client)
    listed = recreated.list("owner-a")
    assert len(listed) == 1
    assert listed[0].token == created.token
    session = recreated.bootstrap(created.token, "https://example.com")
    assert session is not None
    assert recreated.integration_for_session(session.token) is not None


def test_owner_isolation_and_delete_revoke_embed_token() -> None:
    client = _FakeTosClient()
    service = _service(client)
    created = service.create("owner-a", _body())

    assert service.list("owner-b") == []
    assert not service.delete("owner-b", created.id)
    assert service.bootstrap(created.token, "https://example.com") is not None
    assert service.delete("owner-a", created.id)
    assert service.list("owner-a") == []
    assert service.bootstrap(created.token, "https://example.com") is None


def test_different_signing_key_cannot_recreate_or_use_token() -> None:
    client = _FakeTosClient()
    created = _service(client).create("owner-a", _body())
    changed = _service(client, signing_key="different-signing-key")

    with pytest.raises(WebsiteIntegrationStorageError):
        changed.list("owner-a")
    assert changed.bootstrap(created.token, "https://example.com") is None


def test_storage_failures_are_explicit() -> None:
    client = _FakeTosClient()
    service = _service(client)
    created = service.create("owner-a", _body())
    client.fail_reads = True

    with pytest.raises(WebsiteIntegrationStorageError):
        service.bootstrap(created.token, "https://example.com")
