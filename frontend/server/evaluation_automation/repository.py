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

"""Storage for automatic optimization snapshots"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from typing import Any
from urllib.parse import quote

from .models import OptimizationSnapshot

_OPTIMIZATION_KEY_PREFIX = "veadk-studio/v1/evaluation-optimizations"
_MAX_OPTIMIZATION_BYTES = 8 * 1024 * 1024


def auto_item_key(
    *,
    project_name: str,
    runtime_id: str,
    session_id: str,
    message_id: str,
    evaluator_version: str,
) -> str:
    return hashlib.sha256(
        f"{runtime_id}\0{session_id}\0{message_id}\0{evaluator_version}".encode()
    ).hexdigest()


class InMemoryOptimizationRepository:
    """Process-local fallback used when Studio storage is not configured."""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], OptimizationSnapshot] = {}

    async def put(self, snapshot: OptimizationSnapshot) -> None:
        self._items[(snapshot.runtime_id, snapshot.app_name)] = snapshot

    async def get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return self._items.get((runtime_id, app_name))


class TosOptimizationRepository:
    """Persist the latest optimization snapshot for each Runtime application."""

    def __init__(
        self,
        *,
        bucket: str,
        client_factory: Callable[[], Any],
    ) -> None:
        if not bucket.strip():
            raise ValueError("TOS optimization storage requires a bucket.")
        self._bucket = bucket
        self._client_factory = client_factory

    async def put(self, snapshot: OptimizationSnapshot) -> None:
        await asyncio.to_thread(self._put, snapshot)

    def _put(self, snapshot: OptimizationSnapshot) -> None:
        content = snapshot.model_dump_json(by_alias=True).encode("utf-8")
        self._client_factory().put_object(
            bucket=self._bucket,
            key=self._key(snapshot.runtime_id, snapshot.app_name),
            content=content,
            content_type="application/json",
        )

    async def get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        return await asyncio.to_thread(self._get, runtime_id, app_name)

    def _get(
        self,
        runtime_id: str,
        app_name: str,
    ) -> OptimizationSnapshot | None:
        import tos

        try:
            response = self._client_factory().get_object(
                bucket=self._bucket,
                key=self._key(runtime_id, app_name),
            )
        except tos.exceptions.TosServerError as error:
            if error.status_code == 404:
                return None
            raise
        content = b"".join(response)
        if len(content) > _MAX_OPTIMIZATION_BYTES:
            raise ValueError("Studio optimization snapshot is too large.")
        return OptimizationSnapshot.model_validate_json(content)

    @staticmethod
    def _key(runtime_id: str, app_name: str) -> str:
        runtime_segment = quote(runtime_id, safe="")
        app_segment = quote(app_name, safe="")
        return f"{_OPTIMIZATION_KEY_PREFIX}/{runtime_segment}/{app_segment}.json"
