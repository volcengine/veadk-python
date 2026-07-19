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

from veadk import Agent

INSTRUCTION_AGENT = (
    """Route order questions to the order assistant and answer general questions."""
)

INSTRUCTION_AGENT_SUB_1 = """Help the user check and understand an order."""

agent_sub_1 = Agent(
    name="order_assistant",
    description="Handles order questions.",
    instruction=INSTRUCTION_AGENT_SUB_1,
)

agent = Agent(
    name="customer_support",
    description="A generated customer-support multi-agent example.",
    instruction=INSTRUCTION_AGENT,
    sub_agents=[agent_sub_1],
)

AGENT_DISPLAY_NAMES = {
    "customer_support": "customer_support",
    "order_assistant": "order_assistant",
}

# ADK requires the top-level agent to be exported as root_agent.
root_agent = agent
