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

"""Production dependency assembly for the minute-triggered VeFaaS function."""

from __future__ import annotations

import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any, cast

from .dispatcher import Dispatcher
from .entrypoint import make_handler
from .executor import ProviderRuntimeExecutor
from .models import ProviderName
from .runtime_provider import (
    AgentKitRuntimeConnectionResolver,
    AgentKitRuntimeProvider,
    RuntimeConnectionResolver,
    resolve_service_credentials,
)
from .tos_repository import TosSchedulerRepository


@dataclass(frozen=True)
class SchedulerSettings:
    provider: ProviderName
    bucket: str
    storage_region: str
    storage_endpoint: str
    replica_id: str
    pre_ack_attempts: int = 2
    ready_batch_size: int = 500
    execution_concurrency: int = 8

    def __post_init__(self) -> None:
        if self.provider not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported scheduler provider: {self.provider}")
        if not all(
            value.strip()
            for value in (
                self.bucket,
                self.storage_region,
                self.storage_endpoint,
                self.replica_id,
            )
        ):
            raise ValueError("Scheduler storage and replica settings are required")
        if self.pre_ack_attempts < 1:
            raise ValueError("Scheduler retry attempts must be positive")
        if self.ready_batch_size < 1 or self.execution_concurrency < 1:
            raise ValueError("Scheduler queue limits must be positive")

    @classmethod
    def from_env(cls, source: Mapping[str, str] | None = None) -> SchedulerSettings:
        environment = source if source is not None else os.environ
        provider_value = str(
            environment.get("AGENTKIT_CLOUD_PROVIDER")
            or environment.get("CLOUD_PROVIDER")
            or "volcengine"
        ).strip()
        if provider_value not in {"volcengine", "byteplus"}:
            raise ValueError(f"Unsupported scheduler provider: {provider_value}")
        provider = cast(ProviderName, provider_value)
        region = str(environment.get("VEADK_STUDIO_TOS_REGION") or "").strip()
        endpoint = str(environment.get("VEADK_STUDIO_TOS_ENDPOINT") or "").strip()
        if region and not endpoint:
            domain = "bytepluses.com" if provider == "byteplus" else "volces.com"
            endpoint = f"tos-{region}.{domain}"
        return cls(
            provider=provider,
            bucket=str(environment.get("VEADK_STUDIO_TOS_BUCKET") or "").strip(),
            storage_region=region,
            storage_endpoint=endpoint,
            replica_id=str(
                environment.get("VEFAAS_INSTANCE_NAME")
                or environment.get("HOSTNAME")
                or "studio-scheduler"
            ).strip(),
            pre_ack_attempts=int(
                str(environment.get("STUDIO_CRONJOB_PRE_ACK_ATTEMPTS") or "2")
            ),
            ready_batch_size=int(
                str(environment.get("STUDIO_CRONJOB_READY_BATCH_SIZE") or "500")
            ),
            execution_concurrency=int(
                str(environment.get("STUDIO_CRONJOB_EXECUTION_CONCURRENCY") or "8")
            ),
        )


def create_dispatcher(
    settings: SchedulerSettings | None = None,
    *,
    tos_client_factory: Callable[[], Any] | None = None,
    runtime_resolver: RuntimeConnectionResolver | None = None,
) -> Dispatcher:
    """Construct all cloud dependencies while preserving injectable test seams."""
    resolved = settings or SchedulerSettings.from_env()
    client_factory = tos_client_factory or _tos_client_factory(resolved)
    repository = TosSchedulerRepository(
        bucket=resolved.bucket,
        client_factory=client_factory,
        provider=resolved.provider,
    )
    resolver = runtime_resolver or AgentKitRuntimeConnectionResolver()
    executor = ProviderRuntimeExecutor(
        [AgentKitRuntimeProvider(resolved.provider, resolver)]
    )
    return Dispatcher(
        repository,
        executor,
        replica_id=resolved.replica_id,
        pre_ack_attempts=resolved.pre_ack_attempts,
        ready_batch_size=resolved.ready_batch_size,
        execution_concurrency=resolved.execution_concurrency,
    )


def _tos_client_factory(settings: SchedulerSettings) -> Callable[[], Any]:
    def create() -> Any:
        import tos

        credentials = resolve_service_credentials(settings.provider)
        return tos.TosClientV2(
            ak=credentials.access_key,
            sk=credentials.secret_key,
            security_token=credentials.session_token or None,
            endpoint=settings.storage_endpoint,
            region=settings.storage_region,
        )

    return create


def handler(event: Any, context: Any) -> dict[str, int]:
    """VeFaaS entry point; cloud trigger invokes this function once per minute."""
    return make_handler(create_dispatcher())(event, context)


__all__ = ["SchedulerSettings", "create_dispatcher", "handler"]
