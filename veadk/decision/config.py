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
"""Shared, immutable SystemOne connection configuration; enables no consumer."""

from pathlib import Path
import os
from urllib.parse import urlsplit

import yaml
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    ValidationError,
    field_validator,
)

DEFAULT_DECISION_MODEL = "doubao-seed-2-1-lite-260915"


class DecisionConfigError(ValueError):
    """Invalid common decision connection configuration."""


class DecisionConfig(BaseModel):
    """Connection details for the System One decision API.

    ``api_url`` is a complete System One URL and is used verbatim. When it is
    absent, the factory derives ``/api/v1/systemone`` from the effective Ark
    API base. ``api_key`` defaults to the existing Ark credential resolution and
    is stored as a ``SecretStr`` so repr and serialization do not expose it.
    """

    model_config = ConfigDict(hide_input_in_errors=True, extra="forbid", frozen=True)

    api_url: str | None = None
    api_key: SecretStr | None = None
    model: str = Field(default=DEFAULT_DECISION_MODEL, min_length=1)

    @field_validator("api_url")
    @classmethod
    def _validate_api_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.startswith(("http://", "https://")):
            raise ValueError("decision.api_url must start with http:// or https://")
        try:
            parsed = urlsplit(value)
        except ValueError as exc:
            raise ValueError("decision.api_url must be a valid URL") from exc
        if not parsed.hostname:
            raise ValueError("decision.api_url must include a host")
        if parsed.scheme == "http" and parsed.hostname.lower() not in {
            "localhost",
            "127.0.0.1",
            "::1",
        }:
            raise ValueError(
                "decision.api_url must use https unless it targets loopback"
            )
        return value

    @field_validator("api_key")
    @classmethod
    def _validate_api_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and not value.get_secret_value():
            raise ValueError("decision.api_key must be non-empty when set")
        return value

    @property
    def api_key_value(self) -> str | None:
        """Return the plaintext key for the HTTP layer, never for display."""
        return self.api_key.get_secret_value() if self.api_key is not None else None


class _UniqueKeyLoader(yaml.SafeLoader):
    pass


def _unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise DecisionConfigError("decision config requires unique string keys")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_UniqueKeyLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _unique_mapping
)


def load_decision_config(path: str | Path | None = None) -> DecisionConfig:
    """Load root ``decision``; DECISION_* environment values override YAML.

    No file/block means defaults. An explicit unreadable file, invalid block,
    or ambiguous destination/key override fails at startup. Code construction
    bypasses this loader, so explicit values are never overwritten.
    """
    from dotenv import find_dotenv, load_dotenv

    dotenv_path = find_dotenv(filename=".env", usecwd=True)
    if dotenv_path:
        load_dotenv(dotenv_path, override=False)
    location = (
        str(path)
        if path is not None
        else find_dotenv(filename="config.yaml", usecwd=True)
    )
    block = {}
    if location:
        try:
            document = yaml.load(
                Path(location).read_text(encoding="utf-8"), Loader=_UniqueKeyLoader
            )
        except (OSError, yaml.YAMLError):
            raise DecisionConfigError("cannot read decision configuration") from None
        if not isinstance(document, dict):
            raise DecisionConfigError("decision config root must be a mapping")
        block = document.get("decision", {})
        if not isinstance(block, dict):
            raise DecisionConfigError("decision must be a mapping")
        block = dict(block)
    endpoint = os.getenv("DECISION_API_URL")
    key = os.getenv("DECISION_API_KEY")
    if (
        endpoint
        and endpoint != block.get("api_url")
        and block.get("api_key")
        and not key
    ):
        raise DecisionConfigError(
            "DECISION_API_KEY is required when overriding a configured decision destination"
        )
    for field in ("api_url", "api_key", "model"):
        value = os.getenv(f"DECISION_{field.upper()}")
        if value is not None:
            block[field] = value
    try:
        return DecisionConfig.model_validate(block)
    except ValidationError:
        # ValidationError includes raw input; never put credentials into logs.
        raise DecisionConfigError("invalid decision configuration") from None
