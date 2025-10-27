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

import importlib.util
import json
import os
import sys
import time
import types
from typing import Any, Dict, List, MutableMapping, Tuple

import requests
from yaml import safe_load


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.readlines()
    data = [x.strip() for x in data]
    return data


def formatted_timestamp() -> str:
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


def read_file_to_bytes(file_path: str) -> bytes:
    if file_path.startswith(("http://", "https://")):
        response = requests.get(file_path)
        response.raise_for_status()
        return response.content
    else:
        with open(file_path, "rb") as f:
            return f.read()


def load_module_from_file(module_name: str, file_path: str) -> types.ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    if spec:
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        if spec.loader:
            spec.loader.exec_module(module)
            return module
        else:
            raise ImportError(
                f"Could not find loader for module {module_name} from {file_path}"
            )
    else:
        raise ImportError(f"Could not load module {module_name} from {file_path}")


def flatten_dict(
    d: MutableMapping[str, Any], parent_key: str = "", sep: str = "_"
) -> Dict[str, Any]:
    """Flatten a nested dictionary.

    Input:
        {"a": {"b": 1}}
    Output:
        {"a_b": 1}
    """
    items: List[Tuple[str, Any]] = []
    for k, v in d.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, MutableMapping):
            items.extend(flatten_dict(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def safe_json_serialize(obj) -> str:
    """Convert any Python object to a JSON-serializable type or string.

    Args:
      obj: The object to serialize.

    Returns:
      The JSON-serialized object string or <non-serializable> if the object cannot be serialized.
    """

    try:
        return json.dumps(
            obj, ensure_ascii=False, default=lambda o: "<not serializable>"
        )
    except (TypeError, OverflowError):
        return "<not serializable>"


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


def set_envs(config_yaml_path: str) -> tuple[dict, dict]:
    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    with open(config_yaml_path, "r", encoding="utf-8") as yaml_file:
        config_dict = safe_load(yaml_file)

    flatten_config_dict = flatten_dict(config_dict)

    veadk_environments = {}
    for k, v in flatten_config_dict.items():
        k = k.upper()

        if k in os.environ:
            logger.info(
                f"Environment variable {k} has been set, value in `config.yaml` will be ignored."
            )
            veadk_environments[k] = os.environ[k]
            continue
        veadk_environments[k] = str(v)
        os.environ[k] = str(v)

    return config_dict, veadk_environments


def get_temp_dir():
    """
    Return the corresponding temporary directory based on the operating system
    - For Windows systems, return the system's default temporary directory
    - For other systems (macOS, Linux, etc.), return the /tmp directory
    """
    # First determine if it is a Windows system
    if sys.platform.startswith("win"):
        # Windows systems use the temporary directory from environment variables
        return os.environ.get("TEMP", os.environ.get("TMP", r"C:\WINDOWS\TEMP"))
    else:
        # Non-Windows systems (macOS, Linux, etc.) uniformly return /tmp
        return "/tmp"
