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

"""Invocation-scoped resource snapshots used across the two tool calls."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from veadk.tools.builtin_tools.create_agent.models import (
    AgentCapabilities,
    ResourceDescriptor,
)


@dataclass(frozen=True)
class StoredResource:
    descriptor: ResourceDescriptor
    payload: Any


@dataclass(frozen=True)
class ResourceSnapshot:
    collection_id: str
    owner: str
    capabilities: AgentCapabilities
    resources: dict[str, StoredResource]


class ResourceStore:
    """Small in-memory store; only the latest snapshot per invocation is retained."""

    def __init__(self) -> None:
        self._snapshots: dict[str, ResourceSnapshot] = {}
        self._latest_by_owner: dict[str, str] = {}

    def put(
        self,
        *,
        owner: str,
        capabilities: AgentCapabilities,
        resources: list[StoredResource],
    ) -> ResourceSnapshot:
        previous_id = self._latest_by_owner.get(owner)
        if previous_id:
            self._snapshots.pop(previous_id, None)

        collection_id = f"resources_{uuid4().hex[:12]}"
        snapshot = ResourceSnapshot(
            collection_id=collection_id,
            owner=owner,
            capabilities=capabilities,
            resources={resource.descriptor.ref: resource for resource in resources},
        )
        self._snapshots[collection_id] = snapshot
        self._latest_by_owner[owner] = collection_id
        return snapshot

    def get(self, *, collection_id: str, owner: str) -> ResourceSnapshot:
        snapshot = self._snapshots.get(collection_id)
        if snapshot is None:
            raise ValueError(
                f"Unknown or expired collection_id '{collection_id}'. "
                "Call collect_resources first."
            )
        if snapshot.owner != owner:
            raise ValueError(
                "collection_id belongs to a different invocation or session. "
                "Call collect_resources in the current session."
            )
        return snapshot

    def consume(self, *, collection_id: str, owner: str) -> ResourceSnapshot:
        """Return and remove a snapshot after validating its owner."""
        snapshot = self.get(collection_id=collection_id, owner=owner)
        self._snapshots.pop(collection_id, None)
        if self._latest_by_owner.get(owner) == collection_id:
            self._latest_by_owner.pop(owner, None)
        return snapshot
