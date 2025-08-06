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

from agent import AGENT, APP_NAME, SHORT_TERM_MEMORY
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


AGENT.tracers.extend(TRACERS)
if not getattr(AGENT, "before_model_callback", None):
    AGENT.before_model_callback = []
if not getattr(AGENT, "after_model_callback", None):
    AGENT.after_model_callback = []
for tracer in TRACERS:
    if tracer.llm_metrics_hook not in AGENT.before_model_callback:
        AGENT.before_model_callback.append(tracer.llm_metrics_hook)
    if tracer.token_metrics_hook not in AGENT.after_model_callback:
        AGENT.after_model_callback.append(tracer.token_metrics_hook)

# Tracer Config ================================================================
# ==============================================================================

app = init_app(
    server_url="0.0.0.0",  # Automatic identification is not supported yet.
    app_name=APP_NAME,
    agent=AGENT,
    short_term_memory=SHORT_TERM_MEMORY,
)
