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

"""Give the agent tools: plain Python functions it can decide to call.

A "tool" in VeADK is just a function with type hints and a docstring. The
docstring is what the model reads to decide *when* and *how* to call it, so
write it for the model, not only for humans.
"""

import asyncio

from veadk import Agent, Runner


def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, e.g. "Beijing".

    Returns:
        A dict with a human-readable weather "result".
    """
    fixed_weather = {
        "beijing": "Sunny, 25°C",
        "shanghai": "Cloudy, 22°C",
        "shenzhen": "Partly cloudy, 29°C",
    }
    return {"result": fixed_weather.get(city.lower().strip(), f"No data for {city}")}


def recommend_clothing(temperature_celsius: int) -> dict[str, str]:
    """Recommend what to wear for a given temperature.

    Args:
        temperature_celsius: The temperature in degrees Celsius.

    Returns:
        A dict with a clothing "result" suggestion.
    """
    if temperature_celsius < 10:
        advice = "Wear a thick coat."
    elif temperature_celsius < 23:
        advice = "A light jacket is enough."
    else:
        advice = "T-shirt weather."
    return {"result": advice}


async def main() -> None:
    agent = Agent(
        name="weather_agent",
        description="An assistant that checks weather and suggests clothing.",
        instruction=(
            "You help users with weather. Use `get_city_weather` to look up "
            "conditions, then `recommend_clothing` based on the temperature. "
            "Always state the temperature you used."
        ),
        tools=[get_city_weather, recommend_clothing],
    )

    runner = Runner(agent=agent, app_name="custom_tools")

    answer = await runner.run(
        messages="北京今天天气怎么样？我该穿什么？",
        session_id="demo-session",
    )
    print(answer)


if __name__ == "__main__":
    asyncio.run(main())
