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

"""Local capacity resolution and conservative, credential-free input accounting.

No tokenizers, model weights, count APIs or catalogues are downloaded at runtime.
The UTF-8 estimator is deliberately conservative and reported as estimated;
provider framing and non-text inputs require a separate allowance.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from importlib.util import find_spec
from pathlib import Path
from typing import Any

from .config import ContextCompressionConfig
from .model_capacity import get_model_capacity


class ContextBudgetError(ValueError):
    """A safe, actionable error without prompt, tool or credential content."""

    def __init__(self, code: str, *, input_tokens=0, budget=0):
        self.code = code
        self.input_tokens = input_tokens
        self.budget = budget
        guidance = (
            "Model capacity is unknown. Use a reviewed provider/model ID from "
            "veadk.context.model_capacity, or set "
            'Agent(context_compression={"context_window": <verified total tokens>, '
            '"output_reserve": <reserved output tokens>}). '
            "For ep-* or private deployments, verify the deployment's limits; "
            "configure each fallback separately. No LLM request was sent to this model."
            if code in {"model_capacity_required", "fallback_capacity_required"}
            else "Reduce input or configure a supported larger window."
        )
        super().__init__(
            f"Context management: {code}; estimated input={input_tokens}, "
            f"budget={budget}. {guidance}"
        )


@dataclass(frozen=True)
class ContextBudget:
    window: int
    output: int
    available: int
    estimator: str = "utf8_upper_bound"


@lru_cache(maxsize=1)
def _catalogue() -> dict:
    spec = find_spec("litellm")
    if spec is None or spec.origin is None:
        return {}
    path = Path(spec.origin).parent / "model_prices_and_context_window_backup.json"
    if not path.is_file():
        return {}
    try:
        catalogue = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return catalogue if isinstance(catalogue, dict) else {}


def model_limits(model: str) -> dict:
    reviewed = get_model_capacity(model)
    if reviewed:
        return reviewed
    catalogue = _catalogue()
    # An installed LiteLLM catalogue is a secondary local table. Never strip
    # arbitrary provider prefixes, use family prefixes, or make network calls.
    candidates = [model]
    if model.startswith("openai/"):
        bare = model.removeprefix("openai/")
        candidates.extend(("volcengine/" + bare, bare))
    for candidate in candidates:
        entry = catalogue.get(candidate)
        if not isinstance(entry, dict):
            continue
        provider = entry.get("litellm_provider")
        if candidate != model and provider not in {"openai", "volcengine"}:
            continue
        window = entry.get("context_window") or entry.get("max_input_tokens")
        if type(window) is int and window > 0:
            return dict(entry)
    return {}


def resolve_budget(
    model: str, config: ContextCompressionConfig, max_output: int | None = None
) -> ContextBudget | None:
    limits = model_limits(model)
    known_window = limits.get("context_window") or limits.get("max_input_tokens")
    window = config.context_window or known_window
    if isinstance(known_window, int) and known_window > 0 and window:
        window = min(window, known_window)
    if not isinstance(window, int) or window <= 0:
        return None
    output = (
        max_output
        or config.output_reserve
        or limits.get("default_output_reserve")
        or limits.get("default_output_tokens")
        or limits.get("max_output_tokens")
    )
    if not isinstance(output, int) or output <= 0:
        raise ContextBudgetError("output_budget_required")
    maximum_output = limits.get("max_output_tokens")
    if isinstance(maximum_output, int) and output > maximum_output:
        raise ContextBudgetError("output_limit_exceeds_model_capacity")
    available = min(
        config.input_limit or window,
        limits.get("max_input_tokens") or window,
        window - output - config.safety_margin,
    )
    if available <= 0:
        raise ContextBudgetError("insufficient_budget", budget=available)
    return ContextBudget(window, output, available)


_MEDIA_KEYS = {
    "inline_data",
    "file_data",
    "image_url",
    "input_audio",
    "video_url",
    "file_id",
    "file_url",
}
_INPUT_KEYS = {
    "messages",
    "input",
    "instructions",
    "tools",
    "functions",
    "response_format",
    "text",
    "system_instruction",
    "response_schema",
    "response_json_schema",
}
_OUTPUT_KEYS = ("max_completion_tokens", "max_output_tokens", "max_tokens")
_RESERVED_EXTRA_KEYS = (
    _INPUT_KEYS
    | set(_OUTPUT_KEYS)
    | {
        "model",
        "previous_response_id",
        "conversation",
        "context_management",
        "context_compression",
        "stream",
        "fallbacks",
    }
)


def output_limit(payload: dict) -> int | None:
    """Do not guess which conflicting provider output setting wins."""
    values = [payload[key] for key in _OUTPUT_KEYS if payload.get(key) is not None]
    if any(type(value) is not int or value <= 0 for value in values):
        raise ContextBudgetError("invalid_output_limit")
    if len(set(values)) > 1:
        raise ContextBudgetError("conflicting_output_limits")
    return values[0] if values else None


def resolve_payload_budget(
    payload: dict, config: ContextCompressionConfig
) -> ContextBudget | None:
    """Distinguish an answer limit from a total limit for verified models.

    A planning reserve is not an output cap. Without an explicit total limit,
    the provider still governs generation and may truncate long reasoning at
    its context limit. Admission promises space for the reserve, not unlimited
    generation. Unknown model semantics retain the existing catalogue policy.
    """
    model = str(payload.get("model", ""))
    limits = model_limits(model)
    output = output_limit(payload)
    if limits.get("answer_only_max_tokens"):
        answer = payload.get("max_tokens")
        total = any(
            payload.get(key) is not None
            for key in ("max_completion_tokens", "max_output_tokens")
        )
        if answer is not None and total:
            # Ark rejects both parameters even when their values are equal.
            raise ContextBudgetError("conflicting_output_limits")
        extra = payload.get("extra_body")
        thinking = payload.get("thinking")
        if isinstance(extra, dict):
            thinking = extra.get("thinking", thinking)
        disabled = isinstance(thinking, dict) and thinking.get("type") == "disabled"
        if answer is not None:
            headroom = 0 if disabled else limits["reasoning_token_reserve"]
            output = max(answer + headroom, config.output_reserve or 0)
        elif output is None and disabled:
            output = config.output_reserve or limits["default_answer_tokens"]
    return resolve_budget(model, config, output)


def fallback_config(
    model: str, config: ContextCompressionConfig, override=None, *, payload=None
):
    """A primary deployment's explicit window does not describe a fallback."""
    if override is not None:
        # Endpoint-specific SDK policy is consumed locally, never sent to the API.
        updates = ContextCompressionConfig.model_validate(override)
        return config.model_copy(
            update={
                "context_window": updates.context_window,
                "input_limit": updates.input_limit,
                "output_reserve": updates.output_reserve or config.output_reserve,
            }
        )
    fallback = config.model_copy(update={"context_window": None, "input_limit": None})
    if resolve_payload_budget(payload or {"model": model}, fallback) is None:
        raise ContextBudgetError("fallback_capacity_required")
    return fallback


def _json_value(value: Any, *, media_reserve: int | None) -> Any:
    if isinstance(value, type) and hasattr(value, "model_json_schema"):
        value = value.model_json_schema()
    elif hasattr(value, "model_dump"):
        value = value.model_dump(exclude_none=True, mode="python")
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in _MEDIA_KEYS and item is not None:
                if media_reserve is None:
                    raise ContextBudgetError("media_budget_required")
                result[key] = "[media counted separately]"
            else:
                result[str(key)] = _json_value(item, media_reserve=media_reserve)
        return result
    if isinstance(value, (list, tuple)):
        return [_json_value(item, media_reserve=media_reserve) for item in value]
    if isinstance(value, bytes):
        # Signed/opaque protocol blocks must also contribute to the estimate.
        return "x" * (4 * ((len(value) + 2) // 3))
    return value


def count_input(payload: dict, config: ContextCompressionConfig) -> int:
    selected = {key: value for key, value in payload.items() if key in _INPUT_KEYS}
    extra = payload.get("extra_body")
    if isinstance(extra, dict) and _RESERVED_EXTRA_KEYS.intersection(extra):
        raise ContextBudgetError("reserved_payload_override")
    value = _json_value(selected, media_reserve=config.media_token_reserve)
    encoded = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    # JSON syntax overcounts textual inputs, but avoids undercounting tools,
    # schemas, Chinese, code and provider message wrappers as len(text)//4 does.
    return len(encoded.encode("utf-8")) + (config.media_token_reserve or 0)


def request_payload(request) -> dict:
    config = request.config
    return {
        **(
            {"max_output_tokens": config.max_output_tokens}
            if config.max_output_tokens is not None
            else {}
        ),
        "messages": request.contents,
        "system_instruction": config.system_instruction,
        "tools": config.tools,
        "response_schema": config.response_schema,
        "response_json_schema": config.response_json_schema,
    }


def check_payload(payload: dict, config: ContextCompressionConfig) -> ContextBudget:
    budget = resolve_payload_budget(payload, config)
    if budget is None:
        raise ContextBudgetError("model_capacity_required")
    if payload.get("previous_response_id") or payload.get("conversation"):
        raise ContextBudgetError("unaccounted_server_history")
    tokens = count_input(payload, config)
    if tokens > budget.available:
        raise ContextBudgetError(
            "input_too_large", input_tokens=tokens, budget=budget.available
        )
    return budget
