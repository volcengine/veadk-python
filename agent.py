from veadk import Agent, Runner
from veadk.config import getenv
from veadk.knowledgebase import KnowledgeBase
from veadk.memory.long_term_memory import LongTermMemory
from veadk.memory.short_term_memory import ShortTermMemory
from veadk.tools.builtin_tools.web_search import web_search
from veadk.tools.demo_tools import get_city_weather
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter
from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

tracer = OpentelemetryTracer(
    exporters=[
       # CozeloopExporter(),
        APMPlusExporter(),
       TLSExporter(),
    ]
)

agent = Agent(
    name="test",
    tracers=[tracer],
    tools=[get_city_weather],
   # long_term_memory=LongTermMemory(backend="local"),
  #  knowledgebase=KnowledgeBase(backend="local", app_name="veadk_default_app"),
)

short_term_memory = ShortTermMemory()

runner = Runner(agent=agent, short_term_memory=short_term_memory)

import asyncio

for i in range(0, 300):
    res = asyncio.run(
        runner.run(
            messages="搜索我的记忆、知识库，看看能不能获取到北京天气",
            session_id="test_session",
            save_tracing_data=False,
        )
    )

    print(res)

    import time

    time.sleep(5)


# print(getenv("MODEL_AGENT_EXTRA_CONFIG"))