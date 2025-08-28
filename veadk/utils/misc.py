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
import sys
import time
import types
from typing import Any, Dict, List, MutableMapping, Tuple

import requests


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.readlines()
    data = [x.strip() for x in data]
    return data


def formatted_timestamp() -> str:
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


def read_png_to_bytes(png_path: str) -> bytes:
    # Determine whether it is a local file or a network file
    if png_path.startswith(("http://", "https://")):
        # Network file: Download via URL and return bytes
        response = requests.get(png_path)
        response.raise_for_status()  # Check if the HTTP request is successful
        return response.content
    else:
        # Local file
        with open(png_path, "rb") as f:
            data = f.read()
    return data


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
