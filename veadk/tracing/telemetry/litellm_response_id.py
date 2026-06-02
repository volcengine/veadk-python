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

"""Record the model provider's response id on the LLM trace span.

Google ADK drops the litellm response's ``id`` when it builds its
``LlmResponse``, so the tracer never sees it. For Volcengine Ark that id equals
the ``x-request-id`` response header — the most useful identifier for
correlating with the provider's logs.

A pure litellm callback can read the id but cannot attach it to the span:
litellm runs its success callbacks detached from the OpenTelemetry context, so
``get_current_span()`` there is non-recording. We therefore wrap
``LiteLLMClient.acompletion`` (the in-context point where the raw response is
available, inside ADK's ``generate_content`` span) and set the standard
GenAI attribute ``gen_ai.response.id`` on the current span.

The patch is applied lazily — only when a VeADK OpenTelemetry tracer is created
(see :mod:`veadk.tracing.telemetry.opentelemetry_tracer`), in the same spirit as
``patch_google_adk_telemetry``. With no tracer, nothing is patched and existing
code paths are untouched; when patched but not recording, it is a no-op.
"""

from __future__ import annotations

from opentelemetry import trace

from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# OpenTelemetry GenAI semantic convention: unique id of the model response.
GEN_AI_RESPONSE_ID = "gen_ai.response.id"

_patched = False


def _set_response_id_on_current_span(response_obj: object) -> None:
    response_id = getattr(response_obj, "id", None)
    if not response_id:
        return
    span = trace.get_current_span()
    if span and span.is_recording():
        span.set_attribute(GEN_AI_RESPONSE_ID, str(response_id))


def register() -> None:
    """Wrap ``LiteLLMClient.acompletion`` once to record ``gen_ai.response.id``."""
    global _patched
    if _patched:
        return

    try:
        from google.adk.models.lite_llm import LiteLLMClient
    except Exception as e:  # pragma: no cover - litellm present whenever models run
        logger.debug(f"Skip gen_ai.response.id patch: {e}")
        return

    original = LiteLLMClient.acompletion
    if getattr(original, "_veadk_response_id_wrapped", False):
        _patched = True
        return

    async def acompletion(self, model, messages, tools, **kwargs):
        response = await original(self, model, messages, tools, **kwargs)
        # Non-streaming returns a ModelResponse carrying ``id``; the streaming
        # wrapper has no stable id here, so this is a no-op for it.
        _set_response_id_on_current_span(response)
        return response

    acompletion._veadk_response_id_wrapped = True  # type: ignore[attr-defined]
    LiteLLMClient.acompletion = acompletion  # type: ignore[method-assign]
    _patched = True
    logger.debug("Wrapped LiteLLMClient.acompletion to record gen_ai.response.id")
