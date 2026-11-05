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

"""A minimal Hello World example for VeADK.

This is the simplest possible agent that responds with "Hello World!".
"""

import asyncio

from veadk import Agent, Runner


async def main() -> None:
    agent = Agent(
        name="hello_world_agent",
        description="A simple agent that says hello world.",
        instruction="When asked anything, respond exactly with 'Hello World!'.",
    )

    runner = Runner(agent=agent, app_name="hello_world")

    answer = await runner.run(
        messages="Say hello.",
        session_id="hello-world-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
