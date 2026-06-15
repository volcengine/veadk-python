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

"""Backend agent for the codex-runtime-on-AgentKit demo.

A plain VeADK ``Agent`` whose inner reasoning/tool loop is driven by the OpenAI
Codex SDK (``runtime="codex"``) instead of ADK's built-in LLM flow. The
``Runner`` still owns session, memory and tracing; Codex only drives the turn.

The configured model (``MODEL_AGENT_*``) is bridged onto Codex's Responses API
by an in-process shim, so a normal Volcengine Ark chat model works unchanged.

The Google ADK agent loader picks up ``root_agent`` from this module.
"""

from veadk import Agent

INSTRUCTION = (
    "You are a helpful assistant. Be concise and answer in the user's language."
)

agent = Agent(
    name="codex_agent",
    description="VeADK agent whose turn loop runs on the OpenAI Codex runtime.",
    instruction=INSTRUCTION,
    runtime="codex",
)

# Required by the Google ADK agent loader.
root_agent = agent
