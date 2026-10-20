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

"""Wire contract shared by the Runtime and Studio BFF tool channel."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from pydantic import BaseModel, ConfigDict, Field, field_validator

PROTOCOL_VERSION = "studio-tool-channel/1"
DEFAULT_CHANNEL_PATH = "/harness/studio-channel/v1"
CAPABILITIES_SUFFIX = "/capabilities"
HTTP_RUN_SUFFIX = "/http-runs"
HTTP_MESSAGE_SUFFIX = "/http-channels/{channel_id}/messages"
MAX_TOOLS = 64
MAX_CATALOG_BYTES = 512 * 1024
MAX_TOOL_TIMEOUT_MS = 30 * 60 * 1_000


class StudioToolManifest(BaseModel):
    """The non-secret portion of one BFF-owned tool."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
    description: str = Field(min_length=1, max_length=4096)
    input_schema: dict[str, Any]
    executor_revision: str = Field(min_length=1, max_length=128)
    timeout_ms: int = Field(default=30_000, ge=1, le=MAX_TOOL_TIMEOUT_MS)
    idempotent: bool = False
    risk_level: str = Field(default="low", pattern=r"^(low|medium|high)$")

    @field_validator("input_schema")
    @classmethod
    def _validate_input_schema(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value.get("type") != "object":
            raise ValueError("tool input_schema.type must be object")
        properties = value.get("properties", {})
        if not isinstance(properties, dict):
            raise ValueError("tool input_schema.properties must be an object")
        try:
            Draft202012Validator.check_schema(value)
        except SchemaError as error:
            raise ValueError(
                f"tool input_schema is invalid: {error.message}"
            ) from error
        return value


@dataclass(frozen=True)
class CatalogSnapshot:
    """An immutable tool catalog accepted for one Studio scope."""

    scope_id: str
    revision: str
    tools: tuple[StudioToolManifest, ...]


def catalog_revision(tools: list[dict[str, Any]] | list[StudioToolManifest]) -> str:
    """Return a stable content revision for a complete tool catalog."""

    manifests = [
        item.model_dump(mode="json")
        if isinstance(item, StudioToolManifest)
        else StudioToolManifest.model_validate(item).model_dump(mode="json")
        for item in tools
    ]
    manifests.sort(key=lambda item: item["name"])
    canonical = json.dumps(
        manifests,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(canonical).hexdigest()


def validate_catalog(
    *,
    scope_id: str,
    revision: str,
    raw_tools: object,
    reserved_tool_names: set[str],
) -> CatalogSnapshot:
    """Validate and freeze one complete catalog replacement."""

    if not scope_id or len(scope_id) > 256:
        raise ValueError("scope_id must be 1-256 characters")
    if not isinstance(raw_tools, list):
        raise ValueError("catalog tools must be a list")
    if len(raw_tools) > MAX_TOOLS:
        raise ValueError(f"catalog exceeds the {MAX_TOOLS}-tool limit")
    encoded = json.dumps(raw_tools, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    if len(encoded) > MAX_CATALOG_BYTES:
        raise ValueError("catalog exceeds the maximum encoded size")

    tools = tuple(StudioToolManifest.model_validate(item) for item in raw_tools)
    names = [tool.name for tool in tools]
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ValueError(f"duplicate tool names: {', '.join(duplicates)}")
    conflicts = sorted(set(names) & reserved_tool_names)
    if conflicts:
        raise ValueError(f"tool names conflict with the Agent: {', '.join(conflicts)}")
    expected_revision = catalog_revision(list(tools))
    if revision != expected_revision:
        raise ValueError("catalog revision does not match its tool manifests")
    return CatalogSnapshot(scope_id=scope_id, revision=revision, tools=tools)
