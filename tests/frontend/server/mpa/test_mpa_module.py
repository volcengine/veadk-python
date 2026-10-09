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

from frontend.server.mpa import create_operation_service
from frontend.server.mpa.operations import (
    InMemoryMpaOperationRepository,
    TosMpaOperationRepository,
)


class _RuntimeClient:
    pass


def test_create_operation_service_returns_none_without_studio_storage(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)
    monkeypatch.delenv("VEADK_VIDEO_ASSET_STORAGE", raising=False)
    monkeypatch.delenv("VEADK_MEDIA_STORAGE", raising=False)

    assert create_operation_service(runtime_client=_RuntimeClient()) is None


def test_create_operation_service_uses_in_memory_store_for_local_dev(
    monkeypatch,
) -> None:
    monkeypatch.delenv("VEADK_STUDIO_TOS_BUCKET", raising=False)
    monkeypatch.delenv("VEADK_STUDIO_TOS_REGION", raising=False)
    monkeypatch.delenv("VEADK_VIDEO_ASSET_STORAGE", raising=False)
    monkeypatch.delenv("VEADK_MEDIA_STORAGE", raising=False)

    service = create_operation_service(
        runtime_client=_RuntimeClient(),
        allow_in_memory=True,
    )

    assert service is not None
    assert isinstance(service._repository, InMemoryMpaOperationRepository)


def test_create_operation_service_builds_tos_repository_when_configured(
    monkeypatch,
) -> None:
    monkeypatch.setenv("VEADK_STUDIO_TOS_BUCKET", "studio")
    monkeypatch.setenv("VEADK_STUDIO_TOS_REGION", "cn-beijing")

    service = create_operation_service(
        runtime_client=_RuntimeClient(),
        client_factory=lambda: object(),
    )

    assert service is not None
    assert isinstance(service._repository, TosMpaOperationRepository)
