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

"""Observe what the agent did with tracing.

Attach a tracer via `tracers=[...]`. Every LLM call and tool call becomes a span,
and the run gets a `trace_id` you can correlate in an observability backend.

To ship traces to a platform, set the matching env vars
(`ENABLE_COZELOOP=true`, `ENABLE_APMPLUS=true`, `ENABLE_TLS=true`) and configure
their endpoints/keys; VeADK wires up the exporters automatically and you can then
search for the printed `trace_id` in that platform's UI.
"""

import asyncio

from veadk import Agent, Runner
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

SESSION_ID = "demo-session"


def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, e.g. "Beijing".
    """
    return {"result": {"beijing": "Sunny, 25°C"}.get(city.lower(), "Unknown")}


async def main() -> None:
    tracer = OpentelemetryTracer()

    agent = Agent(
        name="traced_agent",
        instruction="Help with weather. Use get_city_weather when asked.",
        tools=[get_city_weather],
        tracers=[tracer],
    )

    runner = Runner(agent=agent, app_name="tracing_demo")

    answer = await runner.run(messages="北京今天天气怎么样？", session_id=SESSION_ID)
    print("Answer:", answer)

    # Each LLM/tool call was recorded as a span under this trace id. With a
    # platform exporter enabled (see README), search this id in its UI.
    print("Trace id:", runner.get_trace_id())


if __name__ == "__main__":
    asyncio.run(main())
