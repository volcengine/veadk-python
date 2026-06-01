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

"""Force the agent to return structured JSON with `output_schema`.

Pass a Pydantic model as `output_schema` and the agent's reply is guaranteed to
match that schema — ideal for extraction / classification where you want to
`json.loads(...)` the result instead of parsing free text.

Note: when `output_schema` is set, the agent returns *only* the structured
answer and cannot call tools or transfer to sub-agents.
"""

import asyncio
import json

from pydantic import BaseModel, Field

from veadk import Agent, Runner


class Ticket(BaseModel):
    """A structured support ticket extracted from a user's message."""

    summary: str = Field(description="One-line summary of the issue.")
    category: str = Field(description="One of: billing, bug, feature_request, other.")
    priority: str = Field(description="One of: low, medium, high.")
    sentiment: str = Field(description="One of: positive, neutral, negative.")


async def main() -> None:
    agent = Agent(
        name="ticket_extractor",
        description="Turns a free-text complaint into a structured ticket.",
        instruction="Extract a support ticket from the user's message.",
        output_schema=Ticket,
    )

    runner = Runner(agent=agent, app_name="structured_output")

    raw = await runner.run(
        messages=(
            "你们的 App 又崩溃了！我每次点开账单页面就闪退，已经第三次了，"
            "非常影响我交月费，请尽快处理！"
        ),
        session_id="demo-session",
    )

    # `raw` is a JSON string that matches the Ticket schema.
    ticket = Ticket.model_validate_json(raw)
    print(json.dumps(ticket.model_dump(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
