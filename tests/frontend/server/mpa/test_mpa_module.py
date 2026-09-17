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
