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

"""AgentKit knowledge-base resource collection."""

from __future__ import annotations

import asyncio
import os
import re
from dataclasses import dataclass
from typing import Any

from veadk.tools.builtin_tools.create_agent.models import (
    ResourceDescriptor,
    ResourceSourceStatus,
)
from veadk.tools.builtin_tools.create_agent.resource_store import StoredResource
from veadk.tools.builtin_tools.create_agent.sources.base import SourceCollection
from veadk.tools.builtin_tools.create_agent.sources.cloud import (
    CloudCredentials,
    default_agentkit_region,
    resolve_cloud_credentials,
)
from veadk.utils.cloud_provider import cloud_provider_from_env


@dataclass(frozen=True)
class AgentKitKnowledgePayload:
    knowledge_id: str
    provider_knowledge_id: str
    provider_type: str
    name: str
    description: str
    project_name: str
    region: str
    cloud_provider: str


class AgentKitKnowledgeSource:
    """List every AgentKit VikingDB knowledge base when credentials are available."""

    name = "agentkit_knowledge"

    def __init__(
        self,
        *,
        region: str | None = None,
        project_name: str | None = None,
        client_factory=None,
        credential_resolver=None,
    ) -> None:
        self.region = region or default_agentkit_region()
        self.project_name = project_name or os.getenv("VEADK_STUDIO_PROJECT") or None
        self._client_factory = client_factory or _default_client_factory
        self._credential_resolver = credential_resolver or resolve_cloud_credentials

    async def collect(self, tool_context: Any = None) -> SourceCollection:
        try:
            credentials = await asyncio.to_thread(
                self._credential_resolver, tool_context
            )
        except Exception as exc:
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name,
                    status="skipped",
                    message=f"Credentials unavailable: {exc}",
                )
            )
        if credentials is None:
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name,
                    status="skipped",
                    message="AK/SK or STS credentials are unavailable.",
                )
            )

        try:
            resources = await asyncio.to_thread(self._list_all, credentials)
            return SourceCollection(
                resources=resources,
                status=ResourceSourceStatus(
                    source=self.name, status="ok", count=len(resources)
                ),
            )
        except Exception as exc:
            return SourceCollection(
                status=ResourceSourceStatus(
                    source=self.name, status="error", message=str(exc)
                )
            )

    def _list_all(self, credentials: CloudCredentials) -> list[StoredResource]:
        from agentkit.sdk.knowledge import types as knowledge_types

        client = self._client_factory(credentials, self.region)
        resources: list[StoredResource] = []
        next_token = ""
        seen_tokens: set[str] = set()

        for _ in range(100):
            response = client.list_knowledge_bases(
                knowledge_types.ListKnowledgeBasesRequest(
                    MaxResults=100,
                    NextToken=next_token or None,
                    ProjectName=self.project_name,
                    Filters=[
                        knowledge_types.FiltersItemForListKnowledgeBases(
                            Name="provider_type",
                            Values=["VIKINGDB_KNOWLEDGE"],
                        )
                    ],
                )
            )
            for item in response.knowledge_bases or []:
                resource = self._to_resource(item)
                if resource is not None:
                    resources.append(resource)

            token = str(response.next_token or "")
            if not token or token in seen_tokens:
                break
            seen_tokens.add(token)
            next_token = token

        return resources

    def _to_resource(self, item: Any) -> StoredResource | None:
        knowledge_id = str(getattr(item, "knowledge_id", "") or "").strip()
        provider_id = str(getattr(item, "provider_knowledge_id", "") or "").strip()
        name = str(getattr(item, "name", "") or "").strip()
        if not knowledge_id:
            return None

        payload = AgentKitKnowledgePayload(
            knowledge_id=knowledge_id,
            provider_knowledge_id=provider_id,
            provider_type=str(getattr(item, "provider_type", "") or ""),
            name=name or knowledge_id,
            description=str(getattr(item, "description", "") or ""),
            project_name=str(
                getattr(item, "project_name", "") or self.project_name or ""
            ),
            region=str(getattr(item, "region", "") or self.region),
            cloud_provider=cloud_provider_from_env(),
        )
        descriptor = ResourceDescriptor(
            ref=f"agentkit_kb:{knowledge_id}",
            kind="knowledge_base",
            name=payload.name,
            description=payload.description,
            source=self.name,
            metadata={
                "knowledge_id": knowledge_id,
                "provider_knowledge_id": provider_id,
                "provider_type": payload.provider_type,
                "project_name": payload.project_name,
                "region": payload.region,
            },
        )
        return StoredResource(descriptor=descriptor, payload=payload)


def _default_client_factory(credentials: CloudCredentials, region: str):
    from agentkit.platform.context import default_cloud_provider
    from agentkit.sdk.knowledge.client import AgentkitKnowledgeClient

    with default_cloud_provider(cloud_provider_from_env()):
        return AgentkitKnowledgeClient(
            access_key=credentials.access_key,
            secret_key=credentials.secret_key,
            session_token=credentials.session_token,
            region=region,
        )


def agentkit_viking_index(payload: AgentKitKnowledgePayload) -> str:
    """Map AgentKit metadata to the VikingDB index expected by VeADK."""
    provider_id = payload.provider_knowledge_id.strip()
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,127}", provider_id):
        return provider_id
    return payload.name
