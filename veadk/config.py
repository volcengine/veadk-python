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
from typing import Any, Dict, List, MutableMapping, Tuple

from dotenv import find_dotenv
from pydantic_settings import (
    BaseSettings,
    InitSettingsSource,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
    YamlConfigSettingsSource,
)

settings = None
veadk_environments = {}


def flatten_dict(
    d: MutableMapping[str, Any], parent_key: str = "", sep: str = "_"
) -> Dict[str, Any]:
    """Flatten a nested dictionary, using a separator in the keys.
    Useful for pydantic_v1 models with nested fields -- first use
        dct = mdl.model_dump()
    to get a nested dictionary, then use this function to flatten it.
    """
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, MutableMapping):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        yaml_file=find_dotenv(filename="config.yaml", usecwd=True), extra="allow"
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        yaml_source = YamlConfigSettingsSource(settings_cls)
        raw_data = yaml_source()
        flat_data = flatten_dict(raw_data)

        init_source = InitSettingsSource(settings_cls, flat_data)
        return (
            init_source,
            env_settings,
            dotenv_settings,
            file_secret_settings,
        )


def prepare_settings():
    path = find_dotenv(filename="config.yaml", usecwd=True)

    if path == "" or path is None or not os.path.exists(path):
        # logger.warning(
        #     "Default and recommanded config file `config.yaml` not found. Please put it in the root directory of your project."
        # )
        pass
    else:
        # logger.info(f"Loading config file from {path}")
        global settings
        settings = Settings()

        for k, v in settings.model_dump().items():
            global veadk_environments

            k = k.upper()
            if k in os.environ:
                veadk_environments[k] = os.environ[k]
                continue
            veadk_environments[k] = str(v)
            os.environ[k] = str(v)


prepare_settings()


def get_envlist():
    return os.environ.keys()


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

    if allow_false_values:
        return value

    if value:
        return value
    else:
        raise ValueError(
            f"The environment variable `{env_name}` not exists. Please set this in your environment variable or config.yaml."
        )
