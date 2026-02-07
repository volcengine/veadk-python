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
from typing import Any

from dotenv import find_dotenv, load_dotenv, dotenv_values
from pydantic import BaseModel, Field

from veadk.configs.auth_configs import VeIdentityConfig
from veadk.configs.model_configs import RealtimeModelConfig
from veadk.configs.database_configs import (
    MysqlConfig,
    OpensearchConfig,
    RedisConfig,
    TOSConfig,
    VikingKnowledgebaseConfig,
)
from veadk.configs.model_configs import ModelConfig
from veadk.configs.tool_configs import BuiltinToolConfigs, PromptPilotConfig
from veadk.configs.tracing_configs import (
    APMPlusConfig,
    CozeloopConfig,
    PrometheusConfig,
    TLSConfig,
)
from veadk.utils.logger import get_logger
from veadk.utils.misc import set_envs

logger = get_logger(__name__)

env_file_path = os.path.join(os.getcwd(), ".env")
if os.path.isfile(env_file_path):
    load_dotenv(env_file_path)
    env_from_dotenv = dotenv_values(env_file_path)
    logger.info(f"Find `.env` file in {env_file_path}, load envs.")
else:
    env_from_dotenv = {}
    logger.info("No `.env` file found.")

provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
if provider == "byteplus":
    byteplus_access_key = os.getenv("BYTEPLUS_ACCESS_KEY")
    if byteplus_access_key:
        os.environ["VOLCENGINE_ACCESS_KEY"] = byteplus_access_key
    byteplus_secret_key = os.getenv("BYTEPLUS_SECRET_KEY")
    if byteplus_secret_key:
        os.environ["VOLCENGINE_SECRET_KEY"] = byteplus_secret_key


class VeADKConfig(BaseModel):
    model: ModelConfig = Field(default_factory=ModelConfig)
    """Config for agent reasoning model."""

    tool: BuiltinToolConfigs = Field(default_factory=BuiltinToolConfigs)
    prompt_pilot: PromptPilotConfig = Field(default_factory=PromptPilotConfig)

    apmplus_config: APMPlusConfig = Field(default_factory=APMPlusConfig)
    cozeloop_config: CozeloopConfig = Field(default_factory=CozeloopConfig)
    tls_config: TLSConfig = Field(default_factory=TLSConfig)
    prometheus_config: PrometheusConfig = Field(default_factory=PrometheusConfig)

    tos: TOSConfig = Field(default_factory=TOSConfig)
    opensearch: OpensearchConfig = Field(default_factory=OpensearchConfig)
    mysql: MysqlConfig = Field(default_factory=MysqlConfig)
    redis: RedisConfig = Field(default_factory=RedisConfig)
    viking_knowledgebase: VikingKnowledgebaseConfig = Field(
        default_factory=VikingKnowledgebaseConfig
    )

    veidentity: VeIdentityConfig = Field(default_factory=VeIdentityConfig)
    realtime_model: RealtimeModelConfig = Field(default_factory=RealtimeModelConfig)


def getenv(
    env_name: str, default_value: Any = "", allow_false_values: bool = False
) -> str:
    """
    Get environment variable.

    Args:
        env_name (str): The name of the environment variable.
        default_value (str): The default value of the environment variable.
        allow_false_values (bool, optional): Whether to allow the environment variable to be None or false values. Defaults to False.

    Returns:
        str: The value of the environment variable.
    """
    value = os.getenv(env_name, default_value)

    if value == default_value or not value:
        provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
        if provider == "byteplus":
            if env_name == "VOLCENGINE_ACCESS_KEY":
                byteplus_key = os.getenv("BYTEPLUS_ACCESS_KEY")
                if byteplus_key:
                    os.environ["VOLCENGINE_ACCESS_KEY"] = byteplus_key
                    value = byteplus_key
            elif env_name == "VOLCENGINE_SECRET_KEY":
                byteplus_key = os.getenv("BYTEPLUS_SECRET_KEY")
                if byteplus_key:
                    os.environ["VOLCENGINE_SECRET_KEY"] = byteplus_key
                    value = byteplus_key

    if allow_false_values:
        return value

    if value:
        return value
    else:
        raise ValueError(
            f"The environment variable `{env_name}` not exists. Please set this in your environment variable or config.yaml."
        )


config_yaml_path = find_dotenv(filename="config.yaml", usecwd=True)

veadk_environments = dict(env_from_dotenv)

if config_yaml_path:
    logger.info(f"Find `config.yaml` file in {config_yaml_path}")
    config_dict, _veadk_environments = set_envs(
        config_yaml_path=config_yaml_path, env_from_dotenv=env_from_dotenv
    )
    veadk_environments.update(_veadk_environments)
else:
    logger.warning("No `config.yaml` file found.")

settings = VeADKConfig()
