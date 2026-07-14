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

"""A minimal VeADK agent using ``runtime="piagent"``.

The agent uses VeADK's normal model configuration from `.env`, `config.yaml`,
or environment variables such as MODEL_AGENT_NAME and MODEL_AGENT_API_KEY. The
only piagent-specific local test requirement is a platform-matching Pi binary.
"""

from veadk import Agent


def get_order_status(order_id: str) -> dict[str, str]:
    """Query a demo order status.

    Args:
        order_id: The order id to query, for example A10086.
    """
    return {
        "order_id": order_id,
        "status": "paid",
        "shipping": "will arrive tomorrow",
    }


INSTRUCTION = (
    "You are a helpful assistant. Answer concisely in the user's language. "
    "When the user asks about an order, you must call get_order_status before "
    "answering. Do not invent order status without using the tool."
)

agent = Agent(
    name="piagent_basic_agent",
    description="VeADK agent whose turn loop runs on the Pi runtime.",
    instruction=INSTRUCTION,
    runtime="piagent",
    tools=[get_order_status],
)

# Required by ADK-style agent loaders.
root_agent = agent
