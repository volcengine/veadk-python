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

"""Tracing regression: a Codex turn must produce an indexable ``call_llm`` span.

``_InMemoryExporter`` indexes a session *only* from spans literally named
``call_llm`` carrying ``gen_ai.session.id``
(``veadk/tracing/telemetry/exporters/inmemory_exporter.py:82``). ADK opens that
span inside ``base_llm_flow``, which the Codex runtime replaces wholesale -- so
before the runtime opened its own, every Codex trace dump was ``[]``,
``OpentelemetryTracer.dump()`` wrote an empty list, and
``base_evaluator.build_eval_set`` then raised ``ValueError: Unsupported file
format`` at ``base_evaluator.py:419``. Nothing in between reported a problem.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path

import pytest
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.genai import types

# The differential harness owns the offline Codex doubles (a fake SDK that
# drives the real shim over ASGI, and the scripted backend). Import them by
# path so this file runs on its own as well as inside a full-tree collection.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "differential"))

import fake_codex_sdk  # noqa: E402
from scripted_backend import Round, ScriptedBackend  # noqa: E402


# Deliberately no per-test global ``TracerProvider`` swap: ADK's and VeADK's
# module-level tracers are ``ProxyTracer`` objects that memoize the first real
# provider they resolve, so replacing (or shutting down) the provider mid-session
# makes every later span vanish -- indistinguishable from the bug under test.
# ``OpentelemetryTracer`` attaches its own in-memory exporter to whichever
# provider is already active, which is order-independent.


@pytest.mark.asyncio
async def test_codex_run_emits_call_llm_span_with_session_id(monkeypatch) -> None:
    from veadk import Agent
    from veadk.runtime import get_runtime
    from veadk.tracing.telemetry.opentelemetry_tracer import OpentelemetryTracer

    fake_codex_sdk.install_openai_codex_stub()
    get_runtime.cache_clear()

    from veadk.runtime.codex import runtime as runtime_module
    from veadk.runtime.codex.proxy import ResponsesShim

    backend = ScriptedBackend([Round(text="Beijing is sunny.", usage=(11, 7))])
    shim = ResponsesShim("https://backend.invalid/v1", "backend-key")
    shim.url = f"http://shim-{uuid.uuid4().hex[:12]}"
    fake_codex_sdk.SHIM_REGISTRY[shim.url] = shim

    async def fake_get_shim(api_base, api_key):
        return shim

    monkeypatch.setattr(
        "veadk.runtime.codex.proxy.litellm.aresponses", backend.as_aresponses()
    )
    monkeypatch.setattr(runtime_module, "get_shim", fake_get_shim)
    monkeypatch.setattr(runtime_module, "AsyncCodex", fake_codex_sdk.ShimDrivingCodex)

    tracer = OpentelemetryTracer(exporters=[])
    agent = Agent(
        name="traced_codex_agent",
        description="A traced codex agent.",
        instruction="Answer the user.",
        model_name="scripted-model",
        model_api_base="https://backend.invalid/v1",
        model_api_key="backend-key",
        runtime="codex",
        tracers=[tracer],
    )

    session_id = f"session-{uuid.uuid4().hex[:8]}"
    session_service = InMemorySessionService()
    await session_service.create_session(
        app_name="tracing", user_id="user", session_id=session_id
    )
    runner = Runner(app_name="tracing", agent=agent, session_service=session_service)

    events = [
        event
        async for event in runner.run_async(
            user_id="user",
            session_id=session_id,
            new_message=types.Content(role="user", parts=[types.Part(text="weather?")]),
        )
    ]
    try:
        assert events, "the codex run produced no events at all"

        exporter = tracer._inmemory_exporter._exporter
        call_llm_spans = [s for s in exporter._spans if s.name == "call_llm"]
        assert call_llm_spans, (
            "no call_llm span: " f"{sorted({s.name for s in exporter._spans})}"
        )
        attributes = dict(call_llm_spans[0].attributes or {})
        assert attributes.get("gen_ai.session.id") == session_id, attributes

        # The property the exporter's session index -- and therefore every
        # trace dump and every evaluation built from one -- actually depends on.
        assert exporter.get_finished_spans(session_id), (
            "get_finished_spans() is empty, so OpentelemetryTracer.dump() would "
            "write [] and base_evaluator.build_eval_set would raise"
        )

        # The span must carry the turn's tokens, not merely exist: an
        # untokened call_llm span still produces a useless trace dump.
        usage = {
            key: value
            for key, value in attributes.items()
            if key.startswith("gen_ai.usage.")
        }
        assert usage, f"call_llm span carries no token usage: {sorted(attributes)}"
        assert usage.get("gen_ai.usage.input_tokens") == 11, usage
        assert usage.get("gen_ai.usage.output_tokens") == 7, usage
    finally:
        fake_codex_sdk.SHIM_REGISTRY.clear()
        get_runtime.cache_clear()
