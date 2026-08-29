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

"""Concurrent collection orchestration for create-agent resources."""

from __future__ import annotations

import asyncio
from typing import Any, Sequence

from veadk.tools.builtin_tools.create_agent.models import (
    AgentCapabilities,
    CollectResourcesResponse,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import ResourceStore
from veadk.tools.builtin_tools.create_agent.sources import ResourceSource


class ResourceCollector:
    """Run every registered source and normalize the combined result."""

    def __init__(
        self,
        *,
        sources: Sequence[ResourceSource],
        store: ResourceStore,
        capabilities: AgentCapabilities,
    ) -> None:
        self._sources = list(sources)
        self._store = store
        self._capabilities = capabilities

    async def collect(
        self, *, owner: str, tool_context: Any = None
    ) -> CollectResourcesResponse:
        collections = await asyncio.gather(
            *(source.collect(tool_context) for source in self._sources),
            return_exceptions=True,
        )

        resources_by_ref = {}
        statuses: list[ResourceSourceStatus] = []
        for source, collection in zip(self._sources, collections):
            if isinstance(collection, BaseException):
                statuses.append(
                    ResourceSourceStatus(
                        source=source.name,
                        status="error",
                        message=str(collection),
                    )
                )
                continue
            if collection.status is not None:
                statuses.append(collection.status)
            for resource in collection.resources:
                resources_by_ref.setdefault(resource.descriptor.ref, resource)

        resources = list(resources_by_ref.values())
        snapshot = self._store.put(
            owner=owner,
            capabilities=self._capabilities,
            resources=resources,
        )
        return CollectResourcesResponse(
            collection_id=snapshot.collection_id,
            capabilities=self._capabilities,
            resources=[resource.descriptor for resource in resources],
            sources=statuses,
        )
