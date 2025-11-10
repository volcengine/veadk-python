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

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from veadk.auth.veauth.prompt_pilot_veauth import PromptPilotVeAuth
from veadk.auth.veauth.vesearch_veauth import VesearchVeAuth
from veadk.auth.veauth.speech_veauth import get_speech_token


class PromptPilotConfig(BaseModel):
    @cached_property
    def api_key(self) -> str:
        return os.getenv("PROMPT_PILOT_API_KEY") or PromptPilotVeAuth().token


class VeSearchConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOL_VESEARCH_")

    endpoint: int | str = ""

    @cached_property
    def api_key(self) -> str:
        return os.getenv("TOOL_VESEARCH_API_KEY") or VesearchVeAuth().token


class VeSpeechConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="TOOL_VESPEECH_")

    endpoint: int | str = ""

    @cached_property
    def api_key(self) -> str:
        return os.getenv("TOOL_VESPEECH_API_KEY") or get_speech_token()


class BuiltinToolConfigs(BaseModel):
    vesearch: VeSearchConfig = Field(default_factory=VeSearchConfig)
    vespeech: VeSpeechConfig = Field(default_factory=VeSpeechConfig)
