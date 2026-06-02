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

"""Observe what the agent did with tracing — local, and/or cloud exporters.

Attach a tracer via `tracers=[...]`. Every LLM call and tool call becomes a span,
and the run gets a `trace_id` (32 hex chars) you can search in your backend.

By default spans are collected in-memory (no credentials needed). Set any of
`ENABLE_APMPLUS` / `ENABLE_COZELOOP` / `ENABLE_TLS` to `true` (and fill in the
matching creds in `.env`) to also ship traces to those Volcengine observability
platforms. APMPlus can authenticate with your Volcengine AK/SK; CozeLoop and TLS
use their own key / ids. See `.env.example`.
"""

import asyncio
import os

from veadk import Agent, Runner
from veadk.tracing.telemetry.exporters.base_exporter import BaseExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

SESSION_ID = "demo-session"


def _enabled(env_name: str) -> bool:
    return os.getenv(env_name, "").lower() == "true"


def build_exporters() -> list[BaseExporter]:
    """Build the cloud exporters enabled via env (their config is read from .env)."""
    exporters: list[BaseExporter] = []
    if _enabled("ENABLE_APMPLUS"):
        from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter

        exporters.append(APMPlusExporter())
    if _enabled("ENABLE_COZELOOP"):
        from veadk.tracing.telemetry.exporters.cozeloop_exporter import (
            CozeloopExporter,
        )

        exporters.append(CozeloopExporter())
    if _enabled("ENABLE_TLS"):
        from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

        exporters.append(TLSExporter())
    return exporters


def get_city_weather(city: str) -> dict[str, str]:
    """Get the current weather for a city.

    Args:
        city: The English name of the city, e.g. "Beijing".
    """
    return {"result": {"beijing": "Sunny, 25°C"}.get(city.lower(), "Unknown")}


async def main() -> None:
    # No exporters -> in-memory only (still yields a trace_id). With ENABLE_* set,
    # the same spans are also shipped to those platforms.
    exporters = build_exporters()
    tracer = OpentelemetryTracer(exporters=exporters)
    print(
        "Exporters:",
        [type(e).__name__ for e in exporters] or "in-memory only (no cloud export)",
    )

    agent = Agent(
        name="traced_agent",
        instruction="Help with weather. Use get_city_weather when asked.",
        tools=[get_city_weather],
        tracers=[tracer],
    )

    runner = Runner(agent=agent, app_name="tracing_demo")

    answer = await runner.run(messages="北京今天天气怎么样？", session_id=SESSION_ID)
    print("Answer:", answer)

    # 32-char hex id tying all spans of this run together. With an exporter
    # enabled, search this id in that platform's UI.
    print("Trace id:", runner.get_trace_id())


if __name__ == "__main__":
    asyncio.run(main())
