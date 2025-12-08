import asyncio
from veadk import Agent, Runner
from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

# init tracing exporter
exporters = [
    APMPlusExporter(),
]
tracer = OpentelemetryTracer(exporters=exporters)

# Define the Agent
agent = Agent(
    tracers=[tracer],
)

runner = Runner(agent=agent)

response = asyncio.run(runner.run(messages="hi!"))
print(response)
