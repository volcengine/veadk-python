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

"""Provider-scoped Runtime transport for Agent review metadata."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from typing import Any

from agentkit.sdk.runtime import types as sdk
from agentkit.sdk.runtime.client import AgentkitRuntimeClient

from frontend.server.agentkit_clients import create_agentkit_client
from frontend.server.storage import StudioProvider

from .tags import write_runtime_tags


class AgentReviewRepository:
    def __init__(
        self,
        provider: StudioProvider,
        credentials: Callable[[], tuple[str, str, str | None]],
    ):
        self.provider: StudioProvider = provider
        self.credentials = credentials

    def client(self, region: str) -> Any:
        access_key, secret_key, token = self.credentials()
        return create_agentkit_client(
            AgentkitRuntimeClient,
            provider=self.provider,
            access_key=access_key,
            secret_key=secret_key,
            session_token=token or "",
            region=region,
        )

    def get(self, region: str, runtime_id: str) -> Any:
        return self.client(region).get_runtime(
            sdk.GetRuntimeRequest.model_validate({"RuntimeId": runtime_id})
        )

    def list(self, region: str) -> Iterator[Any]:
        client = self.client(region)
        token = ""
        seen: set[str] = set()
        while True:
            response = client.list_runtimes(
                sdk.ListRuntimesRequest.model_validate(
                    {"MaxResults": 100, **({"NextToken": token} if token else {})}
                )
            )
            yield from response.agent_kit_runtimes or []
            token = str(response.next_token or "")
            if not token:
                return
            if token in seen:
                raise RuntimeError("AgentKit returned a repeated Runtime page token")
            seen.add(token)

    def write(self, region: str, runtime_id: str, values: dict[str, str]) -> None:
        write_runtime_tags(self.client(region), runtime_id, values)
