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

"""Runtime feature detection for dynamically created agents."""

from __future__ import annotations

from packaging.version import Version

from veadk.tools.builtin_tools.create_agent.models import AgentCapabilities
from veadk.utils.adk_compat import get_adk_version


MIN_WORKFLOW_ADK_VERSION = Version("2.0.0")


def detect_agent_capabilities() -> AgentCapabilities:
    """Detect supported node types using both version and import checks."""
    version = get_adk_version()
    supports_workflow = False
    if version >= MIN_WORKFLOW_ADK_VERSION:
        try:
            from google.adk.workflow import Edge, START, Workflow  # noqa: F401

            supports_workflow = True
        except (ImportError, AttributeError):
            supports_workflow = False

    agent_types = ["llm", "sequential", "parallel", "loop"]
    if supports_workflow:
        agent_types.append("workflow")
    return AgentCapabilities(
        google_adk_version=str(version),
        agent_types=agent_types,
        max_orchestration_depth=2,
    )
