# Copyright (c) 2026 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
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
"""Real-provider E2E for protocol response IDs, explicitly enabled by env.

Run with ``VEADK_PROTOCOL_RESPONSE_ID_LIVE=1`` plus either provider's key:

- ``ARK_API_KEY``: Ark Responses / Chat / Messages (the Messages format uses
  ``ANTHROPIC_BASE_URL``, which points at Ark's Anthropic-compatible endpoint).
- ``DEEPSEEK_API_KEY``: DeepSeek Responses / Chat / Messages (the Messages
  format uses ``DEEPSEEK_ANTHROPIC_BASE``).

Overrides: ``VEADK_RESPONSE_ID_MODEL``, ``ARK_BASE_URL``,
``DEEPSEEK_MODEL``, ``DEEPSEEK_API_BASE``, ``DEEPSEEK_ANTHROPIC_BASE``.

These cases assert the additive contract only: the provider-returned body ID is
logged once per attempt and set as ``veadk.response.id`` on the attempt span and
the enclosing ADK model span. Existing dispatch logs must remain present.
"""

import logging
import os
import re

import pytest
from google.adk.agents import RunConfig
from google.adk.agents.run_config import StreamingMode
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from opentelemetry import trace as trace_api
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.util._once import Once

from veadk import Agent
from veadk.tracing.telemetry.protocol_response_id import RESPONSE_ID_ATTRIBUTE
from veadk.utils.patches import patch_tracer

ARK_BASE = os.getenv("ARK_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3/")
ARK_ANTHROPIC_BASE = os.getenv(
    "ANTHROPIC_BASE_URL", "https://ark.cn-beijing.volces.com/api/compatible"
)
DEEPSEEK_BASE = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
DEEPSEEK_ANTHROPIC_BASE = os.getenv(
    "DEEPSEEK_ANTHROPIC_BASE", "https://api.deepseek.com/anthropic"
)

_UUID = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
)
_ARK_ID = re.compile(r"^[0-9A-Za-z_-]{8,}$")

PROVIDERS = {
    "ark": {
        "key": os.getenv("ARK_API_KEY"),
        "model": os.getenv("VEADK_RESPONSE_ID_MODEL", "deepseek-v4-1-flash-261017"),
        "chat_base": ARK_BASE,
        "responses_base": ARK_BASE,
        "messages_base": ARK_ANTHROPIC_BASE,
        "chat_id": _ARK_ID,
        "messages_id": _ARK_ID,
        # The Responses body ID is distinct from the Ark X-Request-Id.
        "responses_id": re.compile(r"^resp_[0-9A-Za-z_-]+$"),
    },
    "deepseek": {
        "key": os.getenv("DEEPSEEK_API_KEY"),
        "model": os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
        "chat_base": DEEPSEEK_BASE,
        "responses_base": DEEPSEEK_BASE,
        "messages_base": DEEPSEEK_ANTHROPIC_BASE,
        "chat_id": _UUID,
        "messages_id": _UUID,
        "responses_id": _UUID,
    },
}

pytestmark = [
    pytest.mark.protocol_response_id_live,
    pytest.mark.skipif(
        os.getenv("VEADK_PROTOCOL_RESPONSE_ID_LIVE") != "1",
        reason="requires explicit live enablement",
    ),
]

CASES = [
    pytest.param(
        provider,
        api,
        stream,
        marks=pytest.mark.skipif(
            not PROVIDERS[provider]["key"],
            reason=f"missing {provider} credentials",
        ),
        id=f"{provider}-{api}-{'stream' if stream else 'non_stream'}",
    )
    for provider in ("ark", "deepseek")
    for api in ("responses", "chat", "messages")
    for stream in (False, True)
]

ID_LOG = re.compile(
    r"^\[llm-dispatch] response id model=(?P<model>\S+) api=(?P<api>\w+) "
    r"stream=(?P<stream>True|False) response_id=(?P<response_id>\S+)$"
)


class _ListHandler(logging.Handler):
    def __init__(self, records):
        super().__init__()
        self._records = records

    def emit(self, record):
        self._records.append(record.getMessage())


@pytest.fixture
def spans(monkeypatch):
    monkeypatch.setenv("ENABLE_APMPLUS", "false")
    monkeypatch.setenv("ENABLE_COZELOOP", "false")
    monkeypatch.setenv("ENABLE_TLS", "false")
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER", None)
    monkeypatch.setattr(trace_api, "_TRACER_PROVIDER_SET_ONCE", Once())
    provider = TracerProvider()
    exporter = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    trace_api.set_tracer_provider(provider)
    # ADK's module-level tracers must follow this test's replacement provider.
    patch_tracer()
    yield exporter
    provider.shutdown()


@pytest.fixture
def messages():
    records = []
    handler = _ListHandler(records)
    logger = logging.getLogger("veadk")
    logger.addHandler(handler)
    try:
        yield records
    finally:
        logger.removeHandler(handler)


def _agent(provider, api):
    config = PROVIDERS[provider]
    common = {
        "name": f"response_id_{provider}_{api}",
        "model_name": config["model"],
        "instruction": "Reply with the single word OK.",
        "generate_content_config": types.GenerateContentConfig(
            max_output_tokens=64, temperature=0
        ),
    }
    if api == "messages":
        # The token goes through model_api_key so it is never added to
        # model_extra_config, which VeADK logs at INFO level.
        return Agent(
            model_provider="anthropic",
            model_api_key=config["key"],
            model_api_base=config["messages_base"],
            **common,
        )
    return Agent(
        model_provider="openai",
        model_api_key=config["key"],
        model_api_base=config["chat_base"]
        if api == "chat"
        else config["responses_base"],
        enable_responses=api == "responses",
        enable_responses_cache=False,
        **common,
    )


async def _run_turn(agent, stream):
    service = InMemorySessionService()
    runner = Runner(
        app_name="protocol_response_id_live", agent=agent, session_service=service
    )
    session = await service.create_session(
        app_name="protocol_response_id_live", user_id="live_test"
    )
    events = [
        event
        async for event in runner.run_async(
            user_id="live_test",
            session_id=session.id,
            new_message=types.Content(role="user", parts=[types.Part(text="Say OK.")]),
            run_config=RunConfig(
                streaming_mode=StreamingMode.SSE if stream else StreamingMode.NONE
            ),
        )
    ]
    return "".join(
        part.text
        for event in events
        if event.content and not event.partial
        for part in (event.content.parts or [])
        if part.text
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(("provider", "api", "stream"), CASES)
async def test_real_protocol_response_id(provider, api, stream, spans, messages):
    config = PROVIDERS[provider]
    exporter = spans
    exporter.clear()
    messages.clear()

    text = await _run_turn(_agent(provider, api), stream)
    assert text.strip()

    id_logs = [ID_LOG.match(message) for message in messages]
    id_logs = [match for match in id_logs if match is not None]
    assert len(id_logs) == 1, [m for m in messages if "response id" in m]
    entry = id_logs[0]
    assert entry["api"] == api
    assert entry["stream"] == str(stream)
    assert entry["model"].endswith(config["model"])

    response_id = entry["response_id"]
    # A synthesized chatcmpl- ID would prove LiteLLM's Messages conversion was
    # observed instead of the raw provider message.
    assert not response_id.startswith("chatcmpl-")
    assert config[f"{api}_id"].match(response_id), response_id

    exported = exporter.get_finished_spans()
    with_id = {
        span.name: span.attributes[RESPONSE_ID_ATTRIBUTE]
        for span in exported
        if RESPONSE_ID_ATTRIBUTE in span.attributes
    }
    assert with_id.get("model_request") == response_id
    assert any(
        name.startswith("generate_content") and value == response_id
        for name, value in with_id.items()
    )

    # Existing dispatch logs keep their current shape.
    if api == "responses":
        assert any(
            message.startswith("[llm-dispatch] responses.create begin")
            for message in messages
        )
        assert any(
            message.startswith("[llm-dispatch] responses.create end")
            for message in messages
        )
    else:
        assert any(
            message.startswith("[llm-dispatch] acompletion enter")
            for message in messages
        )
        assert any(
            message.startswith("[llm-dispatch] acompletion exit")
            for message in messages
        )
