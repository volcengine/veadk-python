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

"""Server-owned credentials for editing the selected MPA's instructions."""

import posixpath
from urllib.parse import unquote

from fastapi import HTTPException


def agents_md_management_headers(
    path: str, *, is_admin: bool, api_key: str | None
) -> dict[str, str]:
    base = "api/v1/studio/agents-md"
    routes = (path.strip("/"), posixpath.normpath("/" + unquote(path)).strip("/"))
    if not any(route == base or route.startswith(base + "/") for route in routes):
        return {}
    if (
        unquote(path) != path
        or "//" in path
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise HTTPException(400, "Noncanonical proxy path")
    if not is_admin:
        raise HTTPException(403, "AGENTS.md editing requires a Studio administrator")
    key = (api_key or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise HTTPException(503, "AGENTS.md editing requires a Runtime API key")
    return {"X-MPA-Studio-Key": key}
