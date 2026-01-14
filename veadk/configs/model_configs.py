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

import os
from functools import cached_property

from pydantic_settings import BaseSettings, SettingsConfigDict

from veadk.auth.veauth.ark_veauth import get_ark_token
from veadk.auth.veauth.speech_veauth import get_speech_token
from veadk.consts import (
    DEFAULT_MODEL_AGENT_API_BASE,
    DEFAULT_MODEL_AGENT_NAME,
    DEFAULT_MODEL_AGENT_PROVIDER,
    DEFAULT_MODEL_EMBEDDING_NAME,
)


class ModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_AGENT_")

    name: str = DEFAULT_MODEL_AGENT_NAME
    """Model name for agent reasoning."""

    provider: str = DEFAULT_MODEL_AGENT_PROVIDER
    """Model provider for LiteLLM initialization."""

    api_base: str = DEFAULT_MODEL_AGENT_API_BASE
    """The api base of the model for agent reasoning."""

    @cached_property
    def api_key(self) -> str:
        return os.getenv("MODEL_AGENT_API_KEY") or get_ark_token()


class EmbeddingModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_EMBEDDING_")

    name: str = DEFAULT_MODEL_EMBEDDING_NAME
    """Model name for embedding."""

    dim: int = 2560
    """Embedding dim is different from different models."""

    api_base: str = "https://ark.cn-beijing.volces.com/api/v3/"
    """The api base of the model for embedding."""

    @cached_property
    def api_key(self) -> str:
        return (
            os.getenv("MODEL_EMBEDDING_API_KEY")
            or os.getenv("MODEL_AGENT_API_KEY")  # try to use agent's model api key
            or get_ark_token()
        )


class NormalEmbeddingModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_EMBEDDING_")

    name: str = "doubao-embedding-text-240715"
    """Model name for embedding."""

    dim: int = 2560
    """Embedding dim is different from different models."""

    api_base: str = "https://ark.cn-beijing.volces.com/api/v3/"
    """The api base of the model for embedding."""

    api_key: str


class RealtimeModelConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="MODEL_REALTIME_")

    name: str = "doubao_realtime_voice_model"
    """Model name for realtime."""

    api_base: str = "wss://openspeech.bytedance.com/api/v3/realtime/dialogue"
    """The api base of the model for realtime."""

    @cached_property
    def api_key(self) -> str:
        return os.getenv("MODEL_REALTIME_API_KEY") or get_speech_token()
