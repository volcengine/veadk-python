import asyncio

from veadk import Agent, Runner
from veadk.tools.demo_tools import get_city_weather

weather_reporter = Agent(
    name="weather_reporter",
    description="A weather reporter agent to report the weather.",
    tools=[get_city_weather],
)

suggester = Agent(
    name="suggester",
    description="A suggester agent that can give some clothing suggestions according to a city's weather.",
    instruction="""Provide clothing suggestions based on weather temperature: 
    wear a coat when temperature is below 15°C, wear long sleeves when temperature is between 15-25°C, 
    wear short sleeves when temperature is above 25°C.""",
)

root_agent = Agent(
    name="planner",
    description="A planner that can generate a suggestion according to a city's weather.",
    instruction="""Invoke weather reporter agent first to get the weather, 
                then invoke suggester agent to get the suggestion. Return the final response to user.""",
    sub_agents=[weather_reporter, suggester],
)

if __name__ == "__main__":
    runner = Runner(root_agent)
    response = asyncio.run(runner.run("北京穿衣建议"))
    print(response)
