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

"""Two questions over a long tool result, with recoverable SQLite sessions."""

import asyncio
from pathlib import Path

from veadk import Agent, Runner
from veadk.memory.short_term_memory import ShortTermMemory


def get_inventory_report() -> str:
    """Return the complete synthetic inventory report for all 430 records."""
    return "".join(
        f"Record {i}: warehouse {i * 17}, audited balance {i * 23} units.\n"
        for i in range(430)
    )


async def main() -> None:
    data = Path(".adk")
    data.mkdir(exist_ok=True)
    memory = ShortTermMemory(
        backend="sqlite",
        local_database_path=str(data / "compression-demo.db"),
    )
    agent = Agent(
        name="inventory_assistant",
        instruction=(
            "Use get_inventory_report for the first inventory question. "
            "Answer from the report with record ID, balance and unit. "
            "For follow-up questions use retained evidence; read the original "
            "context only if the needed details are missing."
        ),
        tools=[get_inventory_report],
        # Demonstration only: lower the input budget to trigger compression
        # with a small synthetic report. Omit this override in production.
        # With embedding configured, preparation and reranking default to on.
        context_compression={"input_limit": 16000},
    )
    runner = Runner(
        agent=agent,
        short_term_memory=memory,
        app_name="compression_demo",
        user_id="demo_user",
    )
    for question in (
        "Fetch the inventory report. What is the audited balance for Record 113?",
        "From the same report, what is the audited balance for Record 227?",
    ):
        print(await runner.run(messages=question, session_id="inventory_session"))


if __name__ == "__main__":
    asyncio.run(main())
