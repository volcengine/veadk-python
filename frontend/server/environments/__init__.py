# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");

"""Studio execution-environment backend composition."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from typing import Any

from frontend.server.storage import StudioProvider, StudioStorageConfig
from frontend.server.storage.tos import CredentialResolver, create_tos_client_factory
from veadk.utils.cloud_provider import default_region

from .repository import TosEnvironmentRepository
from .resources import EnvironmentResourceSettings, StudioEnvironmentCloudGateway
from .routes import mount_environment_routes
from .service import EnvironmentService


def create_environment_service(
    *,
    provider: StudioProvider = "volcengine",
    resolve_credentials: CredentialResolver | None = None,
    client_factory: Callable[[], Any] | None = None,
    environment: Mapping[str, str] | None = None,
) -> EnvironmentService:
    storage = StudioStorageConfig.from_env(provider, environment)
    if not storage.configured:
        return EnvironmentService(
            None, None, unavailable_reason=storage.unavailable_reason
        )
    if client_factory is None:
        if resolve_credentials is None:
            return EnvironmentService(
                None,
                None,
                unavailable_reason="管理员未配置环境存储与构建凭据。",
            )
        client_factory = create_tos_client_factory(storage, resolve_credentials)
    source = environment if environment is not None else os.environ
    deploy_region = str(source.get("VEADK_STUDIO_DEPLOY_REGION") or "").strip()
    settings = EnvironmentResourceSettings.from_env(
        provider=provider,
        region=deploy_region or default_region(provider),
        bucket=storage.bucket,
        source=source,
    )
    return EnvironmentService(
        TosEnvironmentRepository(
            bucket=storage.bucket,
            client_factory=client_factory,
        ),
        StudioEnvironmentCloudGateway(
            settings,
            resolve_credentials=resolve_credentials,
        ),
    )


__all__ = [
    "EnvironmentService",
    "create_environment_service",
    "mount_environment_routes",
]
