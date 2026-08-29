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

"""Dynamic sub-agent creation toolset."""

from veadk.tools.builtin_tools.create_agent.models import (
    AgentBlueprint,
    AgentCapabilities,
    CollectResourcesResponse,
    CreateAgentsResponse,
    ResourceDescriptor,
)
from veadk.tools.builtin_tools.create_agent.resource_store import (
    ResourceStore,
    StoredResource,
)
from veadk.tools.builtin_tools.create_agent.sources import (
    ResourceSource,
    SourceCollection,
)
from veadk.tools.builtin_tools.create_agent.toolset import CreateAgentToolset

__all__ = [
    "AgentBlueprint",
    "AgentCapabilities",
    "CollectResourcesResponse",
    "CreateAgentToolset",
    "CreateAgentsResponse",
    "ResourceDescriptor",
    "ResourceSource",
    "ResourceStore",
    "SourceCollection",
    "StoredResource",
]
