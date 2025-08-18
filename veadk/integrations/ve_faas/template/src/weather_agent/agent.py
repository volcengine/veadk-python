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

"""Note

Once you put your own agent project in this `src/` directory, you may:

1. remove the template code
2. update the imports in this file to point to your agent's location (e.g., from demo_agent.agent import root_agent, ...)
3. MUST export three global variables from this file:
    - `app_name`
    - `root_agent`: The root agent instance
    - `short_term_memory`: The short-term memory instance
"""

from veadk import Agent
from veadk.tools.demo_tools import get_city_weather

# define your agent here
agent: Agent = Agent(
    name="weather_reporter",
    description="A reporter for weather updates",
    instruction="Once user ask you weather of a city, you need to provide the weather report for that city by calling `get_city_weather`.",
    tools=[get_city_weather],
)

# required from Google ADK Web
root_agent = agent
