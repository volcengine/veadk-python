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

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

import pytest
import tos

from frontend.server.evaluation_automation import create_service
from frontend.server.evaluation_automation.models import (
    OptimizationGroup,
    OptimizationSnapshot,
    OptimizationSuggestion,
)
from frontend.server.evaluation_automation.repository import (
    TosOptimizationRepository,
)


class _FakeTosClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}

    def put_object(
        self,
        *,
        bucket: str,
        key: str,
        content: bytes,
        content_type: str,
    ) -> None:
        assert content_type == "application/json"
        self.objects[(bucket, key)] = content

    def get_object(self, *, bucket: str, key: str) -> list[bytes]:
        try:
            return [self.objects[(bucket, key)]]
        except KeyError as error:
            response = SimpleNamespace(request_id="request", headers={}, status=404)
            raise tos.exceptions.TosServerError(
                response,
                "not found",
                "NoSuchKey",
                "host",
                key,
            ) from error


def _optimization_snapshot() -> OptimizationSnapshot:
    return OptimizationSnapshot(
        runtimeId="runtime/id",
        appName="客服/助手",
        generatedAt=datetime(2026, 8, 11, tzinfo=timezone.utc),
        optimizerVersion="v1",
        sourceItemKeys=["case-1"],
        groups=[
            OptimizationGroup(
                priority="high",
                module="prompt",
                items=[
                    OptimizationSuggestion(
                        suggestion="补充回答格式",
                        reason="让输出结构更加稳定。",
                    )
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_tos_optimization_repository_survives_recreation() -> None:
    client = _FakeTosClient()
    repository = TosOptimizationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
    )
    snapshot = _optimization_snapshot()

    await repository.put(snapshot)
    restored = await TosOptimizationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
    ).get(snapshot.runtime_id, snapshot.app_name)

    assert restored == snapshot
    expected_key = (
        "veadk-studio/v1/evaluation-optimizations/"
        "runtime%2Fid/%E5%AE%A2%E6%9C%8D%2F%E5%8A%A9%E6%89%8B.json"
    )
    assert list(client.objects) == [
        (
            "studio-bucket",
            expected_key,
        )
    ]


@pytest.mark.asyncio
async def test_tos_optimization_repository_returns_none_for_missing_object() -> None:
    repository = TosOptimizationRepository(
        bucket="studio-bucket",
        client_factory=_FakeTosClient,
    )

    assert await repository.get("runtime", "agent") is None


@pytest.mark.asyncio
async def test_create_service_reads_optimizations_from_configured_tos(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "studio-bucket")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "cn-beijing")
    client = _FakeTosClient()
    snapshot = _optimization_snapshot()
    await TosOptimizationRepository(
        bucket="studio-bucket",
        client_factory=lambda: client,
    ).put(snapshot)
    credentials_calls = 0

    def resolve_credentials() -> tuple[str, str, None]:
        nonlocal credentials_calls
        credentials_calls += 1
        return "ak", "sk", None

    monkeypatch.setattr(tos, "TosClientV2", lambda **kwargs: client)

    async def openapi_post(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError(kwargs)

    service = create_service(
        provider="volcengine",
        resolve_credentials=resolve_credentials,
    )

    restored = await service.get_optimizations(
        snapshot.runtime_id,
        snapshot.app_name,
    )

    assert restored == snapshot
    assert credentials_calls == 1
    await service.close()
