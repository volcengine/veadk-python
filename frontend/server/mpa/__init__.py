"""Studio MPA management composition helpers."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from frontend.server.storage import (
    STUDIO_STORAGE_UNAVAILABLE_REASON,
    StudioProvider,
    StudioStorageConfig,
)
from frontend.server.storage.tos import CredentialResolver, create_tos_client_factory

from .operations import InMemoryMpaOperationRepository, TosMpaOperationRepository
from .runtime_client import MpaRuntimeClient
from .routes import mount_mpa_profile_routes
from .service import MpaAgentOperationService


def create_operation_service(
    *,
    provider: StudioProvider = "volcengine",
    resolve_credentials: CredentialResolver | None = None,
    client_factory: Callable[[], Any] | None = None,
    runtime_client: MpaRuntimeClient | None = None,
    allow_in_memory: bool = False,
) -> MpaAgentOperationService | None:
    """Compose the MPA operation service.

    Production uses TOS for durable CAS. Local Studio development can opt into a
    process-local repository so profile application remains testable without TOS.
    """
    storage = StudioStorageConfig.from_env(provider)
    if not storage.configured:
        if not allow_in_memory:
            return None
        return MpaAgentOperationService(
            repository=InMemoryMpaOperationRepository(),
            runtime_client=runtime_client or MpaRuntimeClient(),
        )
    if client_factory is None:
        if resolve_credentials is None:
            return None
        client_factory = create_tos_client_factory(storage, resolve_credentials)
    return MpaAgentOperationService(
        repository=TosMpaOperationRepository(
            bucket=storage.bucket,
            client_factory=client_factory,
        ),
        runtime_client=runtime_client or MpaRuntimeClient(),
    )


__all__ = [
    "MpaAgentOperationService",
    "STUDIO_STORAGE_UNAVAILABLE_REASON",
    "create_operation_service",
    "mount_mpa_profile_routes",
]
