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

"""Configure the model: per-agent override, fallbacks, and extra request body.

Three knobs, all set right on the `Agent` (no global config needed):

- `model_name=[primary, backup, ...]` — try the primary model first; if it
  fails, automatically fall back to the next one(s).
- `model_provider` / `model_api_base` / `model_api_key` — override the model for
  *this* agent instead of using the environment defaults.
- `model_extra_config` — extra fields merged into every request. Here we disable
  the model's "thinking" output to get faster, cheaper replies.
"""

import asyncio

from veadk import Agent, Runner


async def main() -> None:
    agent = Agent(
        name="resilient_agent",
        instruction="You are a concise assistant. Answer in one short sentence.",
        # Primary model first; the rest are fallbacks tried in order on failure.
        model_name=["doubao-seed-1-6-250615", "deepseek-v3-2-251201"],
        # Merged into every model request. Disabling "thinking" speeds things up.
        model_extra_config={"extra_body": {"thinking": {"type": "disabled"}}},
    )

    runner = Runner(agent=agent, app_name="model_config")

    answer = await runner.run(
        messages="用一句话解释什么是负载均衡。",
        session_id="demo-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
