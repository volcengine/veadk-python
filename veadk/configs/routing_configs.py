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
"""Opt-in query routing configuration.

Query routing is disabled unless a ``query_routing`` block exists in the
project ``config.yaml`` (or the caller passes an explicit configuration to
:class:`veadk.Agent`). The block is intentionally small: the only required
field is ``simple_models``.

Canonical shape::

    query_routing:
      simple_models:
        - doubao-seed-2-1-lite-260915
      questions:
        - question: 回答是否需要多步推理或长链分析？
          threshold: 0.15

User questions are appended to the four built-in conservative questions. A
question only needs its text and threshold; the Decision API type is always
``noul`` and the answer id is generated as ``custom_1``, ``custom_2``, ...
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)

from veadk.content_safety.config import DecisionConfig

DEFAULT_QUERY_ROUTING_THRESHOLD = 0.15
DEFAULT_QUERY_ROUTING_TIMEOUT_SECONDS = 2.0
MAX_QUERY_ROUTING_CONTEXT_CHARS = 32_000
_REQUEST_OVERRIDE_FIELDS = frozenset(
    {
        "previous_response_id",
        "previous_interaction_id",
        "input",
        "messages",
        "instructions",
        "tools",
        "functions",
    }
)
_CONNECTION_FIELDS = frozenset({"model", "api_key", "api_base", "fallbacks"})

_BUILTIN_QUESTIONS: tuple[tuple[str, str, float], ...] = (
    (
        "is_complex",
        "完成当前用户任务是否需要超出候选模型能力的复杂推理、规划、代码或数学推导？"
        "简单事实问答和单步改写判为否。",
        0.15,
    ),
    (
        "needs_tools",
        "完成当前任务是否需要超出候选模型已声明能力的工具编排或错误恢复？"
        "候选模型支持的简单工具查询判为否。",
        0.15,
    ),
    (
        "needs_long_context",
        "当前用户任务是否必须综合较长历史或多份材料进行全局分析？"
        "仅从少量最近消息提取已明确给出的代号、姓名、数值等事实，判为否；"
        "不能因为任务需要回看历史就判为是。只判断当前任务实际需要的分析。",
        0.15,
    ),
    (
        "is_high_stakes",
        "当前用户任务是否要求医疗、法律、金融、安全等高风险结论，或不可撤销的操作？"
        "一般咨询、创作、草稿和单纯提取已给出的非敏感事实判为否。"
        "历史中曾讨论高风险主题不代表当前任务也是高风险；"
        "但当前任务仍在追问相关建议或操作时判为是。",
        0.05,
    ),
)


class QueryRoutingConfigError(ValueError):
    """Raised when query-routing configuration cannot be trusted."""


class RoutingQuestion(BaseModel):
    """One ``noul`` question sent to the Decision API."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
    )

    id: str = Field(min_length=1, max_length=128)
    instructions: str = Field(
        min_length=1,
        validation_alias=AliasChoices("instructions", "question"),
    )
    threshold: float = Field(
        default=DEFAULT_QUERY_ROUTING_THRESHOLD,
        ge=0.0,
        le=1.0,
    )

    @property
    def type(self) -> Literal["noul"]:
        """The Decision API question type is fixed to ``noul``."""

        return "noul"


class SimpleModelConfig(BaseModel):
    """A manually listed cheap model and its declared capabilities.

    Unknown capabilities are denied by default: a bare model name is treated as
    text-only, without tools, structured output, or media support. Callers can
    opt into more capability per model when the model genuinely supports it.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        populate_by_name=True,
    )

    name: str = Field(
        min_length=1,
        validation_alias=AliasChoices("name", "model", "model_name"),
    )
    supports_tools: bool = False
    capability_description: str | None = Field(
        default=None, min_length=1, max_length=2000
    )
    provider: str | None = None
    api_base: str | None = None
    api_key: SecretStr | None = Field(default=None, repr=False)
    api_key_env: str | None = None
    api: Literal["chat_completions", "responses"] | None = None
    extra_config: dict[str, Any] = Field(default_factory=dict, repr=False)
    supports_media: bool = False
    supports_structured_output: bool = False
    max_context_chars: int = Field(
        default=MAX_QUERY_ROUTING_CONTEXT_CHARS,
        ge=1,
    )

    @property
    def api_key_value(self) -> str | None:
        if self.api_key_env:
            value = os.getenv(self.api_key_env)
            if not value:
                raise QueryRoutingConfigError(
                    f"missing credential variable: {self.api_key_env}"
                )
            return value
        return self.api_key.get_secret_value() if self.api_key else None

    @model_validator(mode="after")
    def _connection_contract(self) -> "SimpleModelConfig":
        if self.api_base:
            DecisionConfig(api_url=self.api_base)
        if self.api_key and self.api_key_env:
            raise ValueError("use only one of api_key and api_key_env")
        forbidden = _CONNECTION_FIELDS | _REQUEST_OVERRIDE_FIELDS
        body = self.extra_config.get("extra_body") or {}
        if forbidden.intersection(self.extra_config) or forbidden.intersection(body):
            raise ValueError(
                "connection, request and fallback fields are not allowed in extra_config"
            )
        return self


def default_questions() -> list[RoutingQuestion]:
    """Return the four built-in conservative questions, in fixed order."""

    return [
        RoutingQuestion(id=name, instructions=instructions, threshold=threshold)
        for name, instructions, threshold in _BUILTIN_QUESTIONS
    ]


class QueryRoutingConfig(BaseModel):
    """Validated, immutable query-routing configuration.

    ``questions`` always contains the built-in questions followed by the
    caller's questions. Built-in ids are reserved, so a custom question can
    never replace a built-in question. Thresholds have explicit overrides.
    """

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        populate_by_name=True,
    )

    simple_models: list[SimpleModelConfig] = Field(min_length=1)
    strong_model: str | None = None
    mode: Literal["enforce", "shadow"] = "shadow"
    builtin_thresholds: dict[str, float] = Field(default_factory=dict)
    questions: list[RoutingQuestion] = Field(default_factory=list)
    decision: DecisionConfig = Field(default_factory=DecisionConfig)
    decision_timeout: float = Field(
        default=DEFAULT_QUERY_ROUTING_TIMEOUT_SECONDS,
        gt=0.0,
        le=30.0,
    )

    @field_validator("simple_models", mode="before")
    @classmethod
    def _normalize_simple_models(cls, value: Any) -> Any:
        if not isinstance(value, list):
            return value
        normalized: list[Any] = []
        for item in value:
            normalized.append({"name": item} if isinstance(item, str) else item)
        return normalized

    @model_validator(mode="before")
    @classmethod
    def _merge_questions(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        provided = data.get("questions") or []
        if not isinstance(provided, list):
            return data

        merged: list[Any] = [
            {
                "id": question.id,
                "instructions": question.instructions,
                "threshold": question.threshold,
            }
            for question in default_questions()
        ]
        thresholds = data.get("builtin_thresholds", {})
        if set(thresholds) - {q["id"] for q in merged}:
            raise ValueError("unknown built-in threshold id")
        for entry in merged:
            if entry["id"] in thresholds:
                entry["threshold"] = thresholds[entry["id"]]
        seen = {question["id"] for question in merged}
        for index, item in enumerate(provided, start=1):
            if isinstance(item, str):
                entry: dict[str, Any] = {"instructions": item}
            elif isinstance(item, RoutingQuestion):
                entry = {
                    "id": item.id,
                    "instructions": item.instructions,
                    "threshold": item.threshold,
                }
            elif isinstance(item, dict):
                entry = dict(item)
            else:
                raise ValueError(
                    "questions items must be strings, mappings, or RoutingQuestion"
                )

            entry.setdefault("id", f"custom_{index}")
            question_id = entry["id"]
            if question_id in seen:
                raise ValueError(
                    f"question id `{question_id}` is reserved or duplicated"
                )
            seen.add(question_id)
            merged.append(entry)

        return {**data, "questions": merged}

    @field_validator("strong_model")
    @classmethod
    def _validate_strong_model(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("strong_model must be non-empty when set")
        return value

    @model_validator(mode="after")
    def _validate_unique_models(self) -> "QueryRoutingConfig":
        names = [model.name for model in self.simple_models]
        if len(names) != len(set(names)):
            raise ValueError("simple_models must not contain duplicate names")
        return self

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QueryRoutingConfig":
        """Build from explicitly supplied code values; environment is ignored."""

        return cls.model_validate(data)

    def questions_hash(self) -> str:
        """Stable hash of the question set, for diagnostics and cache keys."""

        payload = [
            {
                "id": question.id,
                "type": question.type,
                "instructions": question.instructions,
                "threshold": question.threshold,
            }
            for question in self.questions
        ]
        encoded = json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _resolve_config_path(path: str | Path | None, *, optional: bool) -> Path | None:
    from dotenv import find_dotenv

    if path is not None:
        return Path(path)
    found = find_dotenv(filename="config.yaml", usecwd=True)
    if not found:
        if optional:
            return None
        raise QueryRoutingConfigError("no config.yaml found; pass an explicit path")
    return Path(found)


def _read_config_document(config_path: Path) -> dict[str, Any]:
    try:
        text = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise QueryRoutingConfigError(
            f"cannot read query-routing config: {config_path}"
        ) from exc

    try:
        document = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise QueryRoutingConfigError(f"invalid YAML in {config_path}: {exc}") from exc

    if document is None:
        return {}
    if not isinstance(document, dict):
        raise QueryRoutingConfigError("config root must be a mapping")
    return document


def _build_config(block: dict[str, Any], config_path: Path) -> QueryRoutingConfig:
    try:
        return QueryRoutingConfig.model_validate(block)
    except Exception as exc:
        raise QueryRoutingConfigError(
            f"invalid `query_routing` block in {config_path}: {exc}"
        ) from exc


def load_query_routing_config(
    path: str | Path | None = None,
) -> QueryRoutingConfig:
    """Load ``query_routing`` from ``config.yaml``.

    When ``path`` is omitted, the same ``config.yaml`` discovery used by VeADK
    (``find_dotenv`` from the current directory) applies. A missing block is an
    error; use :func:`load_query_routing_config_if_present` for optional
    discovery.
    """

    config_path = _resolve_config_path(path, optional=False)
    assert config_path is not None
    document = _read_config_document(config_path)
    block = document.get("query_routing")
    if not isinstance(block, dict):
        raise QueryRoutingConfigError("config must contain a `query_routing` mapping")
    return _build_config(block, config_path)


def load_query_routing_config_if_present(
    path: str | Path | None = None,
) -> QueryRoutingConfig | None:
    """Load ``query_routing`` when configured, otherwise return ``None``.

    Missing files and a missing ``query_routing`` block mean "not configured"
    and leave routing disabled. A block that exists but is invalid raises, so
    misconfiguration fails at startup instead of silently disabling routing.
    """

    config_path = _resolve_config_path(path, optional=True)
    if config_path is None:
        return None
    document = _read_config_document(config_path)
    block = document.get("query_routing")
    if block is None:
        return None
    if not isinstance(block, dict):
        raise QueryRoutingConfigError(
            f"`query_routing` in {config_path} must be a mapping"
        )
    return _build_config(block, config_path)
