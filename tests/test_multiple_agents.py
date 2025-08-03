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

from veadk import Agent
from veadk.tools.demo_tools import get_city_weather


def test_multiple_agents():
    weather_reporter = Agent(
        name="weather_reporter",
        description="A weather reporter agent to report the weather.",
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        tools=[get_city_weather],
    )
    suggester = Agent(
        name="suggester",
        description="A suggester agent that can give some clothing suggestions according to a city's weather.",
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
    )

    planner_agent = Agent(
        name="planner",
        description="A planner that can generate a suggestion according to a city's weather.",
        instruction="Invoke weather reporter agent first to get the weather, then invoke suggester agent to get the suggestion. Return the final response to user.",
        model_name="test_model_name",
        model_provider="test_model_provider",
        model_api_key="test_model_api_key",
        model_api_base="test_model_api_base",
        sub_agents=[weather_reporter, suggester],
    )

    assert planner_agent.sub_agents == [weather_reporter, suggester]
    assert weather_reporter.parent_agent == planner_agent
    assert suggester.parent_agent == planner_agent
