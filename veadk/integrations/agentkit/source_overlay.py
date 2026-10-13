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
"""Credential-free metadata for reopening a source-preserving deployment."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def validate_source_overlay(value: Any) -> dict[str, list[dict[str, str]]]:
    """Validate the complete public contract; never silently drop unsafe fields."""
    if (
        not isinstance(value, dict)
        or set(value) != {"schemaVersion", "mcp"}
        or type(value["schemaVersion"]) is not int
        or value["schemaVersion"] != 1
        or not isinstance(value["mcp"], dict)
        or len(value["mcp"]) > 128
    ):
        raise ValueError("Invalid Studio source overlay")
    result = {}
    count = 0
    for agent_name, entries in value["mcp"].items():
        if (
            not isinstance(agent_name, str)
            or re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", agent_name) is None
            or not isinstance(entries, list)
        ):
            raise ValueError("Invalid Studio source overlay")
        tools, names = [], set()
        for item in entries:
            count += 1
            if (
                count > 256
                or not isinstance(item, dict)
                or set(item) != {"name", "transport", "url", "authTokenEnv"}
                or any(not isinstance(v, str) for v in item.values())
            ):
                raise ValueError("Invalid Studio source overlay")
            name, url, reference = item["name"], item["url"], item["authTokenEnv"]
            parsed = urlsplit(url)
            # Also force validation of malformed ports.
            _ = parsed.port
            if (
                item["transport"] != "http"
                or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,79}", name) is None
                or name in names
                or (
                    reference
                    and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", reference) is None
                )
                or not 1 <= len(url) <= 4096
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username is not None
                or parsed.password is not None
                or "?" in url
                or "#" in url
                or any(ord(c) < 33 or ord(c) == 127 for c in url)
            ):
                raise ValueError("Invalid Studio source overlay")
            names.add(name)
            tools.append(dict(item))
        result[agent_name] = tools
    return result


def _unique_fields(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Invalid Studio source overlay")
        result[key] = value
    return result


def read_source_overlay(environment: Mapping[str, str]) -> dict[str, Any] | None:
    """Read only the image's public manifest, never credential environment values.

    An unavailable manifest blocks editing without blocking the running agent.
    No ordinary Builder draft is produced: its regeneration would lose private code.
    """
    root = environment.get("VEADK_STUDIO_SKILL_OVERLAY")
    if not root:
        return None
    try:
        path = Path(root) / "mcp.json"
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 1024 * 1024:
            raise ValueError("Invalid Studio source overlay")
        with path.open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise ValueError("Invalid Studio source overlay")
        value = {
            "schemaVersion": 1,
            "mcp": json.loads(data, object_pairs_hook=_unique_fields),
        }
        return {"schemaVersion": 1, "mcp": validate_source_overlay(value)}
    except (OSError, ValueError, TypeError, RecursionError):
        return {"schemaVersion": 1, "status": "unavailable"}
