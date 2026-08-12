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

"""Reusable TOS client composition for Studio-owned persistent data."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from . import StudioStorageConfig

CredentialResolver = Callable[[], tuple[str, str, str | None]]
TosClientFactory = Callable[[], Any]


def create_tos_client_factory(
    config: StudioStorageConfig,
    resolve_credentials: CredentialResolver,
) -> TosClientFactory:
    """Create clients lazily so refreshed temporary credentials are respected."""
    if not config.configured:
        raise ValueError(config.unavailable_reason)

    def factory() -> Any:
        import tos

        access_key, secret_key, session_token = resolve_credentials()
        return tos.TosClientV2(
            ak=access_key,
            sk=secret_key,
            security_token=session_token,
            endpoint=config.endpoint,
            region=config.region,
        )

    return factory


__all__ = [
    "CredentialResolver",
    "TosClientFactory",
    "create_tos_client_factory",
]
