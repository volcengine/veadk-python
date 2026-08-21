# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0

"""TOS persistence for Studio website integrations."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from frontend.server.storage import STUDIO_STORAGE_ROOT_PREFIX

_INTEGRATION_ID_RE = re.compile(r"[0-9a-f]{32}")
_MAX_RECORD_BYTES = 64 * 1024


class PersistedWebsiteIntegration(BaseModel):
    """Storage-only representation that never contains the embed token."""

    id: str
    owner_hash: str
    domain: str
    runtime_id: str
    runtime_name: str
    region: str
    app_name: str
    token_hash: str
    created_at: datetime


class WebsiteIntegrationConflict(RuntimeError):
    """Raised when an integration id already exists."""


class TosWebsiteIntegrationRepository:
    """Store integration records and per-owner indexes as separate objects."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
        root_prefix: str = STUDIO_STORAGE_ROOT_PREFIX,
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS website integration storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory
        self._prefix = f"{root_prefix.strip('/')}/website-integrations/v1"

    def list(self, owner_hash: str) -> list[PersistedWebsiteIntegration]:
        client = self._client_factory()
        prefix = f"{self._prefix}/owners/{owner_hash}/"
        records: list[PersistedWebsiteIntegration] = []
        for key in self._list_keys(client, prefix):
            integration_id = key.removeprefix(prefix).removesuffix(".json")
            if not _INTEGRATION_ID_RE.fullmatch(integration_id):
                continue
            record = self._get(client, integration_id)
            if record is not None and record.owner_hash == owner_hash:
                records.append(record)
        return sorted(
            records,
            key=lambda item: (item.created_at, item.id),
            reverse=True,
        )

    def get(self, integration_id: str) -> PersistedWebsiteIntegration | None:
        if not _INTEGRATION_ID_RE.fullmatch(integration_id):
            return None
        return self._get(self._client_factory(), integration_id)

    def create(self, record: PersistedWebsiteIntegration) -> None:
        if not _INTEGRATION_ID_RE.fullmatch(record.id):
            raise ValueError("Website integration id is invalid.")
        client = self._client_factory()
        content = record.model_dump_json().encode("utf-8")
        if len(content) > _MAX_RECORD_BYTES:
            raise ValueError("Website integration record is too large.")
        try:
            client.put_object(
                bucket=self._bucket,
                key=self._integration_key(record.id),
                content=content,
                content_length=len(content),
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception as error:
            if _status_code(error) in {409, 412}:
                raise WebsiteIntegrationConflict(
                    "Website integration id already exists."
                ) from error
            raise

        marker = b"{}"
        try:
            client.put_object(
                bucket=self._bucket,
                key=self._owner_key(record.owner_hash, record.id),
                content=marker,
                content_length=len(marker),
                content_type="application/json",
                forbid_overwrite=True,
            )
        except Exception:
            client.delete_object(
                bucket=self._bucket,
                key=self._integration_key(record.id),
            )
            raise

    def delete(self, record: PersistedWebsiteIntegration) -> None:
        client = self._client_factory()
        client.delete_object(
            bucket=self._bucket,
            key=self._integration_key(record.id),
        )
        client.delete_object(
            bucket=self._bucket,
            key=self._owner_key(record.owner_hash, record.id),
        )

    def _get(
        self,
        client: Any,
        integration_id: str,
    ) -> PersistedWebsiteIntegration | None:
        try:
            response = client.get_object(
                bucket=self._bucket,
                key=self._integration_key(integration_id),
            )
        except Exception as error:
            if _status_code(error) == 404:
                return None
            raise
        if hasattr(response, "read"):
            content = response.read(_MAX_RECORD_BYTES + 1)
        else:
            content = b"".join(response)
        if not isinstance(content, bytes) or len(content) > _MAX_RECORD_BYTES:
            raise ValueError("Website integration record is invalid or too large.")
        record = PersistedWebsiteIntegration.model_validate_json(content)
        if record.id != integration_id:
            raise ValueError("Website integration record id does not match its key.")
        return record

    def _list_keys(self, client: Any, prefix: str) -> list[str]:
        continuation_token = ""
        keys: list[str] = []
        while True:
            output = client.list_objects_type2(
                bucket=self._bucket,
                prefix=prefix,
                continuation_token=continuation_token,
                max_keys=1000,
            )
            keys.extend(
                str(item.key)
                for item in (getattr(output, "contents", None) or [])
                if str(getattr(item, "key", "")).endswith(".json")
            )
            if not getattr(output, "is_truncated", False):
                return keys
            continuation_token = str(
                getattr(output, "next_continuation_token", "") or ""
            )
            if not continuation_token:
                raise RuntimeError(
                    "TOS truncated a website integration listing without a "
                    "continuation token."
                )

    def _integration_key(self, integration_id: str) -> str:
        return f"{self._prefix}/integrations/{integration_id}.json"

    def _owner_key(self, owner_hash: str, integration_id: str) -> str:
        return f"{self._prefix}/owners/{owner_hash}/{integration_id}.json"


def owner_digest(owner_id: str) -> str:
    return hashlib.sha256(owner_id.encode("utf-8")).hexdigest()


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _status_code(error: Exception) -> int | None:
    value = getattr(error, "status_code", None)
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


__all__ = [
    "PersistedWebsiteIntegration",
    "TosWebsiteIntegrationRepository",
    "WebsiteIntegrationConflict",
    "owner_digest",
    "token_digest",
]
