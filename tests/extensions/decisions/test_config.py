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

"""Configuration tests for the decision-model extension."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veadk.extensions.decisions import (
    DEFAULT_API_BASE,
    DEFAULT_MODEL_NAME,
    DecisionModelConfig,
)


def test_default_config_is_disabled() -> None:
    config = DecisionModelConfig()
    assert config.enabled is False
    assert config.provider == "typesafe"
    assert config.name == DEFAULT_MODEL_NAME
    assert config.api_base == DEFAULT_API_BASE
    assert config.configured is False


def test_from_env_reads_every_field() -> None:
    config = DecisionModelConfig.from_env(
        {
            "DECISION_MODEL_ENABLED": "true",
            "DECISION_MODEL_PROVIDER": "systemone",
            "DECISION_MODEL_NAME": "jev-1.13.0",
            "DECISION_MODEL_API_BASE": "http://localhost:9000/",
            "DECISION_MODEL_API_KEY": "secret",
            "DECISION_MODEL_TIMEOUT": "12.5",
            "DECISION_MODEL_MAX_RETRIES": "1",
        }
    )
    assert config.enabled is True
    assert config.provider == "systemone"
    assert config.name == "jev-1.13.0"
    assert config.api_base == "http://localhost:9000"
    assert config.api_key == "secret"
    assert config.timeout == 12.5
    assert config.max_retries == 1
    assert config.endpoint == "http://localhost:9000/v1/systemone"
    assert config.configured is True


def test_from_env_keeps_defaults_for_unusable_values() -> None:
    config = DecisionModelConfig.from_env(
        {
            "DECISION_MODEL_ENABLED": "maybe",
            "DECISION_MODEL_PROVIDER": "unknown",
            "DECISION_MODEL_TIMEOUT": "soon",
            "DECISION_MODEL_MAX_RETRIES": "many",
        }
    )
    assert config.enabled is False
    assert config.provider == "typesafe"
    assert config.timeout == 30.0
    assert config.max_retries == 3


@pytest.mark.parametrize(
    "api_base",
    ["https://api.typesafe.ai", "https://api.typesafe.ai/"],
)
def test_endpoint_normalization(api_base: str) -> None:
    config = DecisionModelConfig(api_base=api_base)
    assert config.endpoint == "https://api.typesafe.ai/v1/systemone"


def test_endpoint_is_not_duplicated_when_already_complete() -> None:
    config = DecisionModelConfig(api_base="https://gateway.internal/v1/systemone")
    assert config.endpoint == "https://gateway.internal/v1/systemone"
    assert config.api_base == "https://gateway.internal/v1/systemone"


def test_empty_api_base_is_rejected() -> None:
    with pytest.raises(ValidationError):
        DecisionModelConfig(api_base="   ")


def test_enabled_without_api_key_is_not_configured() -> None:
    config = DecisionModelConfig(enabled=True)
    assert config.configured is False


def test_config_yaml_spelling_is_accepted() -> None:
    """``model.decision.*`` in config.yaml arrives as ``MODEL_DECISION_*``."""
    config = DecisionModelConfig.from_env(
        {
            "MODEL_DECISION_ENABLED": "True",
            "MODEL_DECISION_NAME": "jev-1.13.0",
            "MODEL_DECISION_API_KEY": "from-config-yaml",
        }
    )
    assert config.enabled is True
    assert config.name == "jev-1.13.0"
    assert config.api_key == "from-config-yaml"
    assert config.configured is True


def test_explicit_env_spelling_wins_over_config_yaml() -> None:
    config = DecisionModelConfig.from_env(
        {
            "DECISION_MODEL_API_KEY": "from-env",
            "MODEL_DECISION_API_KEY": "from-config-yaml",
        }
    )
    assert config.api_key == "from-env"
