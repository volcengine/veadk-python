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

"""Read-only tools for knowledge bases selected by a dynamic agent."""

from __future__ import annotations

import asyncio
from typing import Any

from google.adk.tools import FunctionTool
from pydantic import BaseModel

from veadk.tools.builtin_tools.create_agent.sources import (
    AgentKitKnowledgePayload,
    CloudCredentials,
)
from veadk.tools.builtin_tools.create_agent.sources.agentkit_knowledge import (
    agentkit_viking_index,
)


def default_knowledge_factory(
    payload: AgentKitKnowledgePayload, credentials: CloudCredentials
) -> Any:
    """Mount one AgentKit VikingDB knowledge base through VeADK."""
    from veadk.knowledgebase import KnowledgeBase

    resource_id = (
        payload.provider_knowledge_id
        if payload.provider_knowledge_id.startswith("kb-")
        else (payload.knowledge_id if payload.knowledge_id.startswith("kb-") else "")
    )
    return KnowledgeBase(
        name=payload.name,
        description=payload.description,
        backend="viking",
        backend_config={
            "index": agentkit_viking_index(payload),
            "resource_id": resource_id,
            "region": payload.region,
            "volcengine_project": payload.project_name or "default",
            "volcengine_access_key": credentials.access_key,
            "volcengine_secret_key": credentials.secret_key,
            "session_token": credentials.session_token,
            "cloud_provider": payload.cloud_provider,
        },
    )


def build_knowledge_tool(
    resources: list[Any], knowledgebases: list[Any]
) -> FunctionTool:
    """Expose all selected bases through one stable read-only search tool."""
    labels = [resource.descriptor.name for resource in resources]

    async def search_selected_knowledge(
        query: str, top_k: int = 5
    ) -> list[dict[str, Any]]:
        """Search all knowledge bases selected for this agent."""
        searches = await asyncio.gather(
            *(
                asyncio.to_thread(knowledgebase.search, query, top_k)
                for knowledgebase in knowledgebases
            ),
            return_exceptions=True,
        )
        output = []
        for resource, result in zip(resources, searches):
            if isinstance(result, BaseException):
                output.append(
                    {
                        "resource_ref": resource.descriptor.ref,
                        "name": resource.descriptor.name,
                        "error": str(result),
                    }
                )
                continue
            entries = [
                item.model_dump(mode="json")
                if isinstance(item, BaseModel)
                else str(item)
                for item in result
            ]
            output.append(
                {
                    "resource_ref": resource.descriptor.ref,
                    "name": resource.descriptor.name,
                    "entries": entries,
                }
            )
        return output

    search_selected_knowledge.__doc__ = (
        "Search the selected read-only knowledge bases: " + ", ".join(labels)
    )
    return FunctionTool(search_selected_knowledge)
