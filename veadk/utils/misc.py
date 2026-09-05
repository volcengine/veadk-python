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
import tempfile
import time
import types
from pathlib import Path
from typing import Any, Callable, Dict, List, MutableMapping, Optional, Tuple

import requests
from yaml import safe_load

from veadk.utils.http_defaults import (
    DEFAULT_HTTP_TIMEOUT,
    DEFAULT_STREAM_BUDGET_SECONDS,
)

import __main__


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    """Read a positive int from the environment, mirroring `http_defaults`."""
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except (TypeError, ValueError):
        return default


# Hard ceiling on a single remote download. The wall-clock budget bounds how
# long a transfer may run, not how much it may deliver: 300s on a fast link is
# tens of gigabytes. Some callers materialize the body in memory and others
# write remote skill archives to disk, so both paths share the same limit.
# 256 MiB is far above any generated image, short clip, or normal skill bundle.
MAX_DOWNLOAD_BYTES: int = _env_int("VEADK_MAX_DOWNLOAD_BYTES", 256 * 1024 * 1024)

# Big enough that per-chunk overhead is noise, small enough that the deadline
# and the size cap are re-checked often during a transfer.
_DOWNLOAD_CHUNK_SIZE = 1024 * 1024


def read_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        data = f.readlines()
    data = [x.strip() for x in data]
    return data


def formatted_timestamp() -> str:
    # YYYYMMDDHHMMSS
    return time.strftime("%Y%m%d%H%M%S", time.localtime())


def _consume_remote_file(file_url: str, consume: Callable[[bytes], Any]) -> int:
    """Consume a remote body in bounded chunks and return its byte count."""
    deadline = time.monotonic() + DEFAULT_STREAM_BUDGET_SECONDS
    downloaded = 0
    with requests.get(file_url, timeout=DEFAULT_HTTP_TIMEOUT, stream=True) as response:
        response.raise_for_status()
        for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_SIZE):
            if time.monotonic() > deadline:
                raise requests.exceptions.Timeout(
                    f"download of {file_url} not finished within "
                    f"{DEFAULT_STREAM_BUDGET_SECONDS}s"
                )
            if not chunk:
                continue
            downloaded += len(chunk)
            if downloaded > MAX_DOWNLOAD_BYTES:
                raise ValueError(
                    f"download of {file_url} exceeds the "
                    f"{MAX_DOWNLOAD_BYTES} byte limit "
                    "(override with VEADK_MAX_DOWNLOAD_BYTES)"
                )
            consume(chunk)
    return downloaded


def download_url_to_file(file_url: str, destination: str | os.PathLike[str]) -> int:
    """Download an HTTP(S) URL to a file with time and size bounds.

    The body is streamed to a temporary sibling and atomically moved into
    place only after the complete response succeeds. An existing destination
    therefore survives timeouts, oversized bodies, and other transfer errors.
    """
    if not file_url.startswith(("http://", "https://")):
        raise ValueError(f"download URL must use http(s): {file_url}")

    destination_path = Path(destination)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            prefix=f".{destination_path.name}.",
            suffix=".part",
            dir=destination_path.parent,
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            downloaded = _consume_remote_file(file_url, temporary_file.write)
        os.replace(temporary_path, destination_path)
        temporary_path = None
        return downloaded
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def read_file_to_bytes(file_path: str) -> bytes:
    """Read a local path or an http(s) URL into memory.

    Raises `requests.exceptions.Timeout` if a remote transfer outlives
    `DEFAULT_STREAM_BUDGET_SECONDS`, and `ValueError` if it exceeds
    `MAX_DOWNLOAD_BYTES`. The read half of `DEFAULT_HTTP_TIMEOUT` only bounds
    the gap between two socket reads, so a peer trickling a byte every 59s
    never trips it and would otherwise stream into `response.content` forever:
    unbounded in both wall-clock time and memory.
    """
    if file_path.startswith(("http://", "https://")):
        chunks: List[bytes] = []
        _consume_remote_file(file_path, chunks.append)
        return b"".join(chunks)
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


def set_envs(config_yaml_path: str, env_from_dotenv: dict = None) -> tuple[dict, dict]:
    from veadk.utils.logger import get_logger

    logger = get_logger(__name__)

    with open(config_yaml_path, "r", encoding="utf-8") as yaml_file:
        config_dict = safe_load(yaml_file)

    flatten_config_dict = flatten_dict(config_dict)
    config_upper_map = {k.upper(): v for k, v in flatten_config_dict.items()}
    all_keys = {k.upper() for k in flatten_config_dict.keys()} | set(
        env_from_dotenv.keys() if env_from_dotenv else []
    )
    veadk_environments = {}
    for k in all_keys:
        if k in os.environ:
            logger.info(
                f"Environment variable {k} has been set, value in `config.yaml` will be ignored."
            )
            veadk_environments[k] = os.environ[k]
            continue
        veadk_environments[k] = str(config_upper_map.get(k))
        os.environ[k] = str(config_upper_map.get(k))

    provider = (os.getenv("CLOUD_PROVIDER") or "").lower()
    if provider == "byteplus":
        byteplus_access_key = veadk_environments.get("BYTEPLUS_ACCESS_KEY")
        if byteplus_access_key:
            os.environ["VOLCENGINE_ACCESS_KEY"] = byteplus_access_key
        byteplus_secret_key = veadk_environments.get("BYTEPLUS_SECRET_KEY")
        if byteplus_secret_key:
            os.environ["VOLCENGINE_SECRET_KEY"] = byteplus_secret_key

    return config_dict, veadk_environments


def get_agents_dir():
    """
    Get the directory of agents.

    Returns:
        str: The agents directory (parent directory of the app)
    """
    return os.path.dirname(get_agent_dir())


def get_agent_dir():
    """
    Get the directory of the currently executed entry script.

    Returns:
        str: The agent directory
    """
    # Try using __main__.__file__ (works for most CLI scripts and uv run environments)
    if hasattr(__main__, "__file__"):
        full_path = os.path.dirname(os.path.abspath(__main__.__file__))
    # Fallback to sys.argv[0] (usually gives the entry script path)
    elif len(sys.argv) > 0 and sys.argv[0]:
        full_path = os.path.dirname(os.path.abspath(sys.argv[0]))
    # Fallback to current working directory (for REPL / Jupyter Notebook)
    else:
        full_path = os.getcwd()

    return full_path


async def upload_to_files_api(
    local_path: str,
    fps: Optional[float] = None,
    poll_interval: float = 3.0,
    max_wait_seconds: float = 10 * 60,
) -> str:
    from volcenginesdkarkruntime import AsyncArk

    from veadk.config import getenv, settings
    from veadk.consts import DEFAULT_MODEL_AGENT_API_BASE

    client = AsyncArk(
        api_key=getenv("MODEL_AGENT_API_KEY", settings.model.api_key),
        base_url=getenv("DEFAULT_MODEL_AGENT_API_BASE", DEFAULT_MODEL_AGENT_API_BASE),
    )
    file = await client.files.create(
        file=open(local_path, "rb"),
        purpose="user_data",
        preprocess_configs={
            "video": {
                "fps": fps,
            }
        }
        if fps
        else None,
    )
    await client.files.wait_for_processing(
        id=file.id,
        poll_interval=poll_interval,
        max_wait_seconds=max_wait_seconds,
    )
    return file.id


def write_string_to_file(file_path: str, content: str):
    dir_path = os.path.dirname(file_path)

    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)
