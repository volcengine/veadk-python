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

"""Isolated extraction requests using the application's own model and endpoint."""

from __future__ import annotations

import copy
from urllib.parse import urlsplit

from .budget import ContextBudgetError, model_limits

# Keep authentication, routing and transport configuration. Extraction owns its
# messages, tools, schema and output limits; business state cannot override them.
_BUSINESS_FIELDS = (
    "max_tokens",
    "max_completion_tokens",
    "max_output_tokens",
    "tools",
    "functions",
    "tool_choice",
    "function_call",
    "parallel_tool_calls",
    "response_format",
    "response_schema",
    "response_json_schema",
    "stream",
    "messages",
    "input",
    "instructions",
    "system_instruction",
    "previous_response_id",
    "conversation",
    "context_management",
    "fallbacks",
    "store",
    "caching",
    "expire_at",
    "background",
    "n",
    "temperature",
    "text",
    "stop",
    "stop_sequences",
    "logit_bias",
    "frequency_penalty",
    "presence_penalty",
)


def disable_thinking(payload, *, ark_responses=False):
    """Normalize only an auxiliary request, never a shared Agent configuration.

    Ark uses the same thinking.type switch for Chat and Responses. Other
    configured providers retain their own opt-out dialect. Reasoning-effort
    APIs without a verified off switch fail closed instead of using 'minimal',
    which still reasons. Models without reasoning controls need no extra field.
    """
    result = copy.deepcopy(payload)
    extra = result.get("extra_body") or {}
    if not isinstance(extra, dict):
        raise ContextBudgetError("auxiliary_thinking_unsupported")
    extra = copy.deepcopy(extra)
    model = str(result.get("model", ""))
    limits = model_limits(model)
    endpoint = result.get("api_base") or result.get("base_url") or ""
    host = urlsplit(str(endpoint)).hostname or ""
    ark = ark_responses or (host.startswith("ark.") and host.endswith(".volces.com"))
    ark = (
        ark
        or limits.get("provider") == "volcengine"
        or bool(limits.get("ark_thinking_controls"))
    )
    thinking = result.get("thinking") or extra.get("thinking")
    enable = "enable_thinking" in result or "enable_thinking" in extra
    anthropic = model.startswith("anthropic/") or host == "api.anthropic.com"
    if ark or anthropic:
        for values in (result, extra):
            for key in ("thinking", "reasoning", "reasoning_effort", "enable_thinking"):
                values.pop(key, None)
        if ark and not ark_responses:
            extra["thinking"] = {"type": "disabled"}
        else:
            result["thinking"] = {"type": "disabled"}
    elif thinking is not None:
        raise ContextBudgetError("auxiliary_thinking_unsupported")
    elif enable:
        for values in (result, extra):
            values.pop("reasoning", None)
            values.pop("reasoning_effort", None)
        if "enable_thinking" in result:
            result["enable_thinking"] = False
        if "enable_thinking" in extra:
            extra["enable_thinking"] = False
    elif (
        any(
            values.get(key) is not None
            for values in (result, extra)
            for key in ("reasoning", "reasoning_effort")
        )
        or limits.get("supports_reasoning")
        or limits.get("reasoning_token_reserve", 0)
    ):
        raise ContextBudgetError("auxiliary_thinking_unsupported")
    if extra or "extra_body" in result:
        result["extra_body"] = extra
    return result


def extraction_model(model, config=None):
    """Borrow the configured client; clone mutable request arguments only."""
    additional = getattr(model, "_additional_args", None)
    if additional is None:
        return model
    clone = model.model_copy()
    clone._additional_args = copy.deepcopy(additional)
    for values in (
        clone._additional_args,
        clone._additional_args.get("extra_body", {}),
    ):
        if isinstance(values, dict):
            for key in _BUSINESS_FIELDS:
                values.pop(key, None)
    clone._additional_args["temperature"] = 0
    # Disable before native admission, not just at the final provider boundary.
    from veadk.models.ark_llm import ArkLlm

    normalized = disable_thinking(
        {**clone._additional_args, "model": model.model},
        ark_responses=isinstance(model, ArkLlm),
    )
    normalized.pop("model", None)
    clone._additional_args = normalized
    if hasattr(clone, "_fallbacks_template"):
        clone._fallbacks_template = None
    if hasattr(clone, "fallbacks"):
        clone.fallbacks = []
    if hasattr(clone, "enable_responses_cache"):
        clone.enable_responses_cache = False
    if config is not None:
        clone = clone.with_context_compression(config)
    return clone
