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

import os

from agent import agent, app_name, short_term_memory
from veadk.a2a.ve_a2a_server import init_app
from veadk.tracing.base_tracer import BaseTracer
from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer


# ==============================================================================
# Tracer Config ================================================================

TRACERS: list[BaseTracer] = []

exporters = []
if os.getenv("VEADK_TRACER_APMPLUS", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.apmplus_exporter import APMPlusExporter

    exporters.append(APMPlusExporter())

if os.getenv("VEADK_TRACER_COZELOOP", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.cozeloop_exporter import CozeloopExporter

    exporters.append(CozeloopExporter())

if os.getenv("VEADK_TRACER_TLS", "").lower() == "true":
    from veadk.tracing.telemetry.exporters.tls_exporter import TLSExporter

    exporters.append(TLSExporter())

TRACERS.append(OpentelemetryTracer(exporters=exporters))


agent.tracers.extend(TRACERS)
if not getattr(agent, "before_model_callback", None):
    agent.before_model_callback = []
if not getattr(agent, "after_model_callback", None):
    agent.after_model_callback = []
if not getattr(agent, "after_tool_callback", None):
    agent.after_tool_callback = []
for tracer in TRACERS:
    if tracer.tracer_hook_before_model not in agent.before_model_callback:
        agent.before_model_callback.append(tracer.tracer_hook_before_model)
    if tracer.tracer_hook_after_model not in agent.after_model_callback:
        agent.after_model_callback.append(tracer.tracer_hook_after_model)
    if tracer.tracer_hook_after_tool not in agent.after_tool_callback:
        agent.after_tool_callback.append(tracer.tracer_hook_after_tool)

# Tracer Config ================================================================
# ==============================================================================

app = init_app(
    server_url="0.0.0.0",  # Automatic identification is not supported yet.
    app_name=app_name,
    agent=agent,
    short_term_memory=short_term_memory,
)
