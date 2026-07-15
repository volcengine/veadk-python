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

"""Run the PiAgent MCP example locally."""

from __future__ import annotations

import asyncio

from veadk import Runner

try:
    from examples.piagent_with_mcp.agent import root_agent
except ModuleNotFoundError:
    from agent import root_agent


async def main() -> None:
    runner = Runner(agent=root_agent, app_name="piagent_with_mcp")
    answer = await runner.run(
        messages=(
            "Please check Beijing weather, Beijing air quality, and order "
            "A10086 status. You must call the relevant tools before answering."
        ),
        user_id="local-user",
        session_id="local-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
