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

"""Resource-source implementations for :mod:`create_agent`."""

from veadk.tools.builtin_tools.create_agent.sources.agentkit_knowledge import (
    AgentKitKnowledgePayload,
    AgentKitKnowledgeSource,
)
from veadk.tools.builtin_tools.create_agent.sources.base import (
    ResourceSource,
    SourceCollection,
)
from veadk.tools.builtin_tools.create_agent.sources.builtin_tools import (
    BuiltinToolResourceSource,
)
from veadk.tools.builtin_tools.create_agent.sources.cloud import CloudCredentials
from veadk.tools.builtin_tools.create_agent.sources.skills import (
    AgentKitSkillCenterSource,
    SkillHubSearchSource,
    SkillResourceSource,
)

__all__ = [
    "AgentKitKnowledgePayload",
    "AgentKitKnowledgeSource",
    "AgentKitSkillCenterSource",
    "BuiltinToolResourceSource",
    "CloudCredentials",
    "ResourceSource",
    "SkillHubSearchSource",
    "SkillResourceSource",
    "SourceCollection",
]
