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

"""Use a built-in tool: live web search powered by Volcengine.

VeADK ships ready-made tools under `veadk.tools.builtin_tools`. The `web_search`
tool calls Volcengine's search API, so it needs a Volcengine AK/SK pair
(`VOLCENGINE_ACCESS_KEY` / `VOLCENGINE_SECRET_KEY`) in addition to the model key.
Adding it is the same as any tool: drop it into `tools=[...]`.
"""

import asyncio

from veadk import Agent, Runner
from veadk.tools.builtin_tools.web_search import web_search


async def main() -> None:
    agent = Agent(
        name="search_agent",
        description="An assistant that can search the web for fresh information.",
        instruction=(
            "When a question needs current or factual information you are unsure "
            "about, call `web_search` first, then answer based on the results. "
            "Cite the key facts you found."
        ),
        tools=[web_search],
    )

    runner = Runner(agent=agent, app_name="web_search_demo")

    answer = await runner.run(
        messages="火山引擎最近发布了哪些大模型相关的产品？请联网查一下。",
        session_id="demo-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
