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

"""Dynamic routing: a coordinator that delegates to specialist sub-agents.

Unlike the fixed pipeline in example 06 (`SequentialAgent`), here a regular
`Agent` is given `sub_agents=[...]` and the LLM itself decides which specialist
to hand the request to (this is the ADK "transfer" / agent-as-router pattern).

The key is each sub-agent's `description`: that's what the coordinator reads to
choose where to route. Write descriptions for the router, not just for humans.
"""

import asyncio

from veadk import Agent, Runner


def get_exchange_rate(base: str, quote: str) -> dict[str, float]:
    """Get a (mock) currency exchange rate.

    Args:
        base: ISO code of the base currency, e.g. "USD".
        quote: ISO code of the quote currency, e.g. "CNY".
    """
    rates = {("USD", "CNY"): 7.18, ("EUR", "CNY"): 7.80, ("USD", "EUR"): 0.92}
    return {"rate": rates.get((base.upper(), quote.upper()), 1.0)}


def build_coordinator() -> Agent:
    finance_agent = Agent(
        name="finance_agent",
        description="Handles money, currencies, and exchange-rate questions.",
        instruction="Answer finance questions. Use get_exchange_rate for conversions.",
        tools=[get_exchange_rate],
    )

    translator_agent = Agent(
        name="translator_agent",
        description="Translates text between languages.",
        instruction="Translate exactly what the user asks, and nothing else.",
    )

    return Agent(
        name="coordinator",
        description="Front desk that routes requests to the right specialist.",
        instruction=(
            "You are a router. Decide which specialist should handle the user's "
            "request and transfer to it. Do not answer specialist questions "
            "yourself."
        ),
        sub_agents=[finance_agent, translator_agent],
    )


async def main() -> None:
    runner = Runner(agent=build_coordinator(), app_name="agent_routing")

    print(
        "Q1 ->",
        await runner.run(
            messages="100 美元能换多少人民币？",
            session_id="demo-1",
        ),
    )

    print(
        "Q2 ->",
        await runner.run(
            messages="把“今天天气真好”翻译成英文。",
            session_id="demo-2",
        ),
    )


if __name__ == "__main__":
    asyncio.run(main())
