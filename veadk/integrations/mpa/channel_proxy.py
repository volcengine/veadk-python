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

"""Studio administrator boundary for MPA channel management."""

from urllib.parse import unquote

from fastapi import HTTPException


def channel_management_headers(
    path: str, *, is_admin: bool, api_key: str | None
) -> dict[str, str]:
    # Reject path aliases before forwarding: authorization and the upstream
    # must interpret the same route, including encoded and dot segments.
    if (
        unquote(path) != path
        or "//" in path
        or any(part in {".", ".."} for part in path.split("/"))
    ):
        raise HTTPException(400, "Noncanonical proxy path")
    route = path.strip("/")
    if route != "api/v1/channels" and not route.startswith("api/v1/channels/"):
        return {}
    if not is_admin:
        raise HTTPException(403, "Channel management requires a Studio administrator")
    if route == "api/v1/channels/events" or route.startswith("api/v1/channels/events/"):
        raise HTTPException(403, "Gateway ingress cannot be proxied through Studio")
    key = (api_key or "").strip()
    if key.lower().startswith("bearer "):
        key = key[7:].strip()
    if not key:
        raise HTTPException(503, "Channel management requires a Runtime API key")
    return {"X-MPA-Channel-Key": key}
