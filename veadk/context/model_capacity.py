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

"""Reviewed capacities in tokens, not bytes. No runtime network access.

Match only the listed provider/model IDs and transport aliases. Updating a
family does not update its other revisions. Source URLs and verification dates
belong to each row so changes can be reviewed with their evidence.

``context_window`` is a conservative shared input/output ceiling. If a source
publishes only an input cap (Gemini), reuse that cap as the shared ceiling;
never add the output cap to invent a larger window. For k/K/M abbreviations we
use decimal units conservatively. Exact integer limits retain their units.

Output reserves are SDK planning defaults, NOT API generation parameters or a
promise that arbitrary reasoning fits. Native output settings are preserved.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ModelCapacity:
    provider: str
    model_id: str
    context_window: int
    max_input_tokens: int
    max_output_tokens: int
    source: str
    verified_on: str = "2026-09-28"
    default_output_reserve: int = 16384
    aliases: tuple[str, ...] = ()
    # Capacity and protocol semantics are independently reviewed. Ark Chat
    # max_tokens is answer-only EXCEPT deepseek-v4-1-flash-260910:
    # https://www.volcengine.com/docs/82379/1494384
    default_answer_tokens: int | None = None
    reasoning_token_reserve: int = 0
    answer_only_max_tokens: bool = False
    ark_thinking_controls: bool = False


_ARK = "https://www.volcengine.com/docs/ark/model-list?lang=zh"
_OPENAI = "https://developers.openai.com/api/docs/models/"
_CLAUDE = "https://platform.claude.com/docs/en/about-claude/models/overview"
_GEMINI = "https://ai.google.dev/gemini-api/docs/models/"


def _ark(model_id: str, window: int, input_limit: int, output: int, **kwargs):
    if model_id != "deepseek-v4-1-flash-260910":
        kwargs = {
            "default_answer_tokens": 4096,
            "reasoning_token_reserve": 12288,
            "answer_only_max_tokens": True,
            **kwargs,
        }
    return ModelCapacity(
        "volcengine", model_id, window, input_limit, output, _ARK, **kwargs
    )


def _openai(model_id: str, window: int, output: int, *, page=None, aliases=()):
    return ModelCapacity(
        "openai",
        model_id,
        window,
        window,
        output,
        _OPENAI + (page or model_id),
        aliases=aliases,
    )


MODEL_CAPACITIES: tuple[ModelCapacity, ...] = (
    _ark(
        "doubao-seed-2-1-pro-260628",
        256000,
        256000,
        256000,
        default_answer_tokens=4096,
        reasoning_token_reserve=12288,
        answer_only_max_tokens=True,
        ark_thinking_controls=True,
    ),
    _ark("doubao-seed-2-1-pro-260915", 1024000, 1024000, 256000),
    _ark("doubao-seed-2-1-lite-260915", 1024000, 1024000, 256000),
    _ark("doubao-seed-2-1-turbo-260628", 256000, 256000, 256000),
    _ark("doubao-seed-2-0-lite-260428", 256000, 224000, 128000),
    _ark("doubao-seed-2-0-mini-260428", 256000, 224000, 128000),
    _ark("doubao-seed-2-0-pro-260215", 256000, 224000, 128000),
    _ark("doubao-seed-2-0-lite-260215", 256000, 224000, 128000),
    _ark("doubao-seed-2-0-mini-260215", 256000, 224000, 128000),
    _ark("doubao-seed-2-0-code-preview-260215", 256000, 224000, 128000),
    _ark("deepseek-v4-1-flash-260910", 1024000, 1024000, 384000),
    _ark("deepseek-v4-pro-ga-260813", 1024000, 1024000, 384000),
    _ark("deepseek-v4-flash-ga-260731", 1024000, 1024000, 384000),
    _ark("glm-5-3-flash-260828", 1024000, 1024000, 128000),
    _ark("glm-5-2-260617", 1024000, 1024000, 128000),
    _openai("gpt-6-astra", 1050000, 128000),
    _openai("gpt-5.6-terra", 1050000, 128000),
    _openai("gpt-5.6-luna", 1050000, 128000),
    _openai("gpt-4.1-2025-04-14", 1047576, 32768, page="gpt-4.1", aliases=("gpt-4.1",)),
    _openai("gpt-4o-2024-08-06", 128000, 16384, page="gpt-4o", aliases=("gpt-4o",)),
    ModelCapacity("anthropic", "claude-fable-5-1", 1000000, 1000000, 128000, _CLAUDE),
    ModelCapacity("anthropic", "claude-opus-5-5", 1000000, 1000000, 128000, _CLAUDE),
    ModelCapacity("anthropic", "claude-sonnet-5", 1000000, 1000000, 128000, _CLAUDE),
    ModelCapacity(
        "anthropic", "claude-haiku-4-5-20251001", 200000, 200000, 64000, _CLAUDE
    ),
    ModelCapacity(
        "gemini",
        "gemini-3.8-flash",
        1048576,
        1048576,
        65536,
        _GEMINI + "gemini-3.8-flash",
    ),
)


# Bare IDs identify only their reviewed provider. openai/ is additionally an
# Ark transport spelling, not permission to borrow any provider's capacity.
_CAPACITY_BY_NAME = {
    name: row
    for row in MODEL_CAPACITIES
    for model_id in (row.model_id, *row.aliases)
    for name in (
        model_id,
        f"{row.provider}/{model_id}",
        *([f"openai/{model_id}"] if row.provider == "volcengine" else []),
    )
}


def get_model_capacity(model: str) -> dict:
    """Return a fresh copy so request code cannot mutate the shared table."""
    row = _CAPACITY_BY_NAME.get(model)
    return asdict(row) if row is not None else {}
