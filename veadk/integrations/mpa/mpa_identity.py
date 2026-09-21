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

"""Idempotent workload identity provisioning for Studio MPA runtimes."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from volcenginesdkcore.rest import ApiException

from veadk.integrations.mpa.mpa_provision import (
    STUDIO_WORKLOAD_POOL_NAME,
    workload_identity_name,
)


class MpaIdentityError(RuntimeError):
    """Raised when the Studio workload identity cannot be ensured."""


@dataclass(frozen=True)
class MpaIdentityResult:
    workload_pool_name: str
    workload_identity_name: str
    pool_created: bool
    identity_created: bool


def _ensure(
    *,
    get: Callable[[], Any],
    create: Callable[[], Any],
    resource: str,
    get_action: str,
    create_action: str,
) -> bool:
    try:
        get()
        return False
    except ApiException as exc:
        if exc.status != 404:
            raise MpaIdentityError(
                f"failed to read {resource}; requires {get_action}: {exc.reason}"
            ) from exc

    try:
        create()
        return True
    except ApiException as exc:
        if exc.status != 409:
            raise MpaIdentityError(
                f"failed to create {resource}; requires {create_action}: {exc.reason}"
            ) from exc

    try:
        get()
        return False
    except ApiException as exc:
        raise MpaIdentityError(
            f"failed to read {resource} after a concurrent create: {exc.reason}"
        ) from exc


def ensure_studio_workload_identity(
    client: Any, mpa_agent_id: str
) -> MpaIdentityResult:
    """Create or reuse the shared Studio pool and the MPA-specific identity."""
    pool_name = STUDIO_WORKLOAD_POOL_NAME
    identity_name = workload_identity_name(mpa_agent_id)
    pool_created = _ensure(
        get=lambda: client.get_workload_pool(workload_pool_name=pool_name),
        create=lambda: client.create_workload_pool(workload_pool_name=pool_name),
        resource=f"WorkloadPool {pool_name}",
        get_action="id:GetWorkloadPool",
        create_action="id:CreateWorkloadPool",
    )
    identity_created = _ensure(
        get=lambda: client.get_workload_identity(
            workload_pool_name=pool_name, name=identity_name
        ),
        create=lambda: client.create_workload_identity(
            workload_pool_name=pool_name, name=identity_name
        ),
        resource=f"WorkloadIdentity {pool_name}/{identity_name}",
        get_action="id:GetWorkloadIdentity",
        create_action="id:CreateWorkloadIdentity",
    )
    return MpaIdentityResult(
        workload_pool_name=pool_name,
        workload_identity_name=identity_name,
        pool_created=pool_created,
        identity_created=identity_created,
    )
