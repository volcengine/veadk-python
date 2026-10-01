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

"""Public, immutable policy for automatic context management."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ContextCompressionConfig(BaseModel):
    """Manage model input without changing the session's original events.

    Explicit model/deployment limits may reduce reviewed local capacities.
    Unknown models require ``context_window`` and an output budget before any
    model request. ``off`` disables transformations, not admission checks.
    ``output_reserve`` reserves space during input planning; it never sets a
    model generation limit. Explicit provider total limits are accounted for
    separately. Without such a limit, reasoning can outgrow the reserve and
    the provider may truncate generation at its context limit.

    Native transport timeouts remain unchanged by default. An explicit
    ``request_timeout_seconds`` bounds the entire model turn, including
    summaries and retries. Summaries always have their own cumulative budget
    from turn start; with an explicit request deadline, the smaller of that
    budget and ``summary_time_budget_ratio`` of the request limit applies.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)

    mode: Literal["auto", "off"] = "auto"
    retrieval: Literal["auto", "lexical"] = "auto"
    index_path: str = Field(default=".adk/context-index.sqlite3", min_length=1)
    embedding_max_calls: int = Field(default=64, ge=1, le=512, strict=True)
    # Explicit quality mode: bounded source preparation before query retrieval.
    # Requires configured embedding; no model or new network work by default.
    prepare_index: bool = False
    index_preparation_max_calls: int = Field(default=512, ge=1, le=512, strict=True)
    index_preparation_timeout_seconds: float = Field(default=60, gt=0, le=120)
    # Experimental read-first protocol, disabled until live quality is proven.
    verify_sources: bool = False
    context_window: int | None = Field(default=None, gt=0)
    input_limit: int | None = Field(default=None, gt=0)
    output_reserve: int | None = Field(default=None, gt=0)
    safety_margin: int = Field(default=1024, ge=0)
    # Tool previews start before the more costly historical-summary stage.
    trigger_ratio: float = Field(default=0.8, gt=0, le=1)
    summary_trigger_ratio: float = Field(default=0.95, gt=0, le=1)
    target_ratio: float = Field(default=0.6, gt=0, lt=1)
    keep_recent_turns: int = Field(default=2, ge=1)
    summary_max_tokens: int = Field(default=2048, ge=128)
    summary_timeout_seconds: float = Field(default=60, gt=0, le=120)
    summary_time_budget_seconds: float = Field(default=90, gt=0, le=600)
    summary_time_budget_ratio: float = Field(default=0.75, gt=0, le=1)
    max_summary_calls: int = Field(default=4, ge=1, le=16)
    max_summary_depth: int = Field(default=8, ge=1, le=32)
    max_model_attempts: int = Field(default=3, ge=1, le=8)
    request_timeout_seconds: float | None = Field(default=None, gt=0, le=600)
    tool_result_max_bytes: int = Field(default=16000, ge=1024)
    retrieval_max_bytes: int = Field(default=8000, ge=512, le=64000)
    max_retrieval_calls: int = Field(default=8, ge=1, le=32)
    media_token_reserve: int | None = Field(default=None, gt=0)
    protected_context: tuple[str, ...] = ()

    @model_validator(mode="after")
    def check_thresholds(self):
        if self.target_ratio >= self.trigger_ratio:
            raise ValueError("target_ratio must be below trigger_ratio")
        if self.summary_trigger_ratio < self.trigger_ratio:
            raise ValueError("summary_trigger_ratio must not be below trigger_ratio")
        return self


def resolve_config(value=None) -> ContextCompressionConfig:
    if isinstance(value, ContextCompressionConfig):
        return value
    if value is False:
        return ContextCompressionConfig(mode="off")
    if value is True:
        return ContextCompressionConfig(mode="auto")
    if value is None:
        return ContextCompressionConfig()
    return ContextCompressionConfig.model_validate(value)
