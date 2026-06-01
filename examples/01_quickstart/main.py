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

"""The smallest possible VeADK program: one agent, one question, one answer.

An `Agent` holds the model + instruction; a `Runner` drives a conversation
with it. `runner.run(...)` is async and returns the final text answer.
"""

import asyncio

from veadk import Agent, Runner


async def main() -> None:
    agent = Agent(
        name="quickstart_agent",
        description="A friendly assistant that answers in one short paragraph.",
        instruction="You are a helpful assistant. Answer concisely in the user's language.",
    )

    runner = Runner(agent=agent, app_name="quickstart")

    answer = await runner.run(
        messages="用一句话介绍火山引擎（Volcengine）。",
        session_id="demo-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
