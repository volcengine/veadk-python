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

"""Provider-scoped AgentKit SDK client construction for Studio."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeVar

from frontend.server.storage import StudioProvider

_Client = TypeVar("_Client")


def create_agentkit_client(
    client_type: Callable[..., _Client],
    *,
    provider: StudioProvider,
    **kwargs: Any,
) -> _Client:
    """Construct a client without consulting another provider's global config."""
    from agentkit.platform.context import default_cloud_provider

    with default_cloud_provider(provider):
        return client_type(**kwargs)
