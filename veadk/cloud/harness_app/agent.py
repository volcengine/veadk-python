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

"""Assemble a single VeADK agent for the harness server from the environment.

The agent is built once at import time from environment variables (parsed into a
:class:`HarnessConfig`; see ``types.py`` and ``utils.py``). The knowledge base and
long-term memory are only created when their backend is set; the short-term
memory backend defaults to ``local``.

Environment variables:
    MODEL_NAME              Reasoning model name. Default: VeADK default model.
    SYSTEM_PROMPT           Agent instruction. Default: VeADK default instruction.
    DESCRIPTION             Agent description (e.g. for A2A discovery). Default: VeADK default description.
    TOOLS                   Comma-separated built-in tool names, e.g. "web_search,link_reader".
    SKILLS                  Comma-separated skill names, e.g. "data-visualization-cloud,...".
    RUNTIME                 Agent runtime backend: "adk" (default) or "codex".
    HARNESS_NAME            App/index name for the knowledge base and long-term memory
                            (also the served harness name). Default: "harness_app".
    KNOWLEDGEBASE_TYPE      Knowledge base backend (e.g. "viking"). Unset disables it.
    LONG_TERM_MEMORY_TYPE   Long-term memory backend (e.g. "viking"). Unset disables it.
    SHORT_TERM_MEMORY_TYPE  Short-term memory backend (e.g. "sqlite"). Default: "local".
    REGISTRY_TYPE           Remote Agent discovery backend. Currently: "agentkit_a2a".
    REGISTRY_SPACE_ID       AgentKit A2A SpaceId used by SearchAgentCards/GetA2aAgent.
    REGISTRY_TOP_K          Candidate AgentCard count for semantic search. Default: 3.
"""

from veadk.cloud.harness_app.utils import init_harness_agent

agent, short_term_memory = init_harness_agent()
