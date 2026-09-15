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

"""Limit shared Agent access to conversation routes and the caller's sessions."""

import re
from typing import Any
from urllib.parse import unquote

from fastapi import HTTPException, Request


async def authorize_shared_proxy(
    request: Request, path: str, method: str, principal: Any
) -> None:
    if principal is None:
        raise HTTPException(401, "Studio identity is required")
    normalized = unquote(path).strip("/")
    if (
        "%" in normalized
        or "\\" in normalized
        or any(part in {".", ".."} for part in normalized.split("/"))
    ):
        raise HTTPException(403, "Shared Agent route is not allowed")
    if method in {"GET", "HEAD"} and (
        normalized == "list-apps" or re.fullmatch(r"web/agent-info/[^/]+", normalized)
    ):
        return
    session = re.fullmatch(
        r"apps/[^/]+/users/([^/]+)/sessions(?:/[^/]+(?:/.*)?)?", normalized
    )
    if session and session[1].casefold() in principal.identifiers:
        return
    if normalized in {"run", "run_sse"} and method == "POST":
        try:
            payload = await request.json()
        except ValueError as error:
            raise HTTPException(400, "Invalid conversation request") from error
        if isinstance(payload, dict):
            user_ids = [payload[key] for key in ("user_id", "userId") if key in payload]
            if user_ids and all(
                isinstance(value, str) and value.casefold() in principal.identifiers
                for value in user_ids
            ):
                return
    raise HTTPException(403, "Shared Agent access is limited to your own conversations")
