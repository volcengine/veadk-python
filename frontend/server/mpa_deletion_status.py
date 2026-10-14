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

"""Bounded, read-only confirmation for an authorized MPA deletion attempt."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

if sys.version_info >= (3, 11):
    from asyncio import timeout
else:
    from async_timeout import timeout

_CONTEXT_TTL = 3600
_CONTEXT_LIMIT = 1024
_CHECK_TIMEOUT = 30
_MISSING_CODE = "InvalidAgentKitRuntime.NotFound"


def runtime_not_found(error: BaseException) -> bool:
    """Recognize a provider code, never a message containing the words NotFound."""
    seen: set[int] = set()
    current: BaseException | None = error
    while current is not None and len(seen) < 8 and id(current) not in seen:
        seen.add(id(current))
        code = getattr(current, "error_code", None)
        if code:
            return code == _MISSING_CODE
        for candidate in (
            getattr(current, "body", None),
            getattr(current, "data", None),
            *current.args,
        ):
            if isinstance(candidate, (str, bytes)):
                try:
                    candidate = json.loads(candidate)
                except (TypeError, ValueError, UnicodeError):
                    continue
            if not isinstance(candidate, Mapping):
                continue
            metadata = candidate.get("ResponseMetadata")
            detail = metadata.get("Error") if isinstance(metadata, Mapping) else None
            if isinstance(detail, Mapping) and detail.get("Code"):
                return detail["Code"] == _MISSING_CODE
        current = current.__cause__
    return False


def mount_mpa_deletion_status(
    app: FastAPI,
    *,
    owner: Callable[[Request], str],
    get_runtime: Callable[[Request, str, str], Any],
    list_page: Callable[[str, str], Mapping[str, Any]],
    credentials: Callable[[], tuple[str, str, str | None]],
    region: Callable[[str], str],
) -> Callable[[Request, str, str], None]:
    contexts: OrderedDict[tuple[str, str, str], tuple[str, float]] = OrderedDict()
    lock = threading.Lock()

    def fingerprint() -> str:
        return hashlib.sha256(json.dumps(credentials()).encode()).hexdigest()

    def remember(request: Request, runtime_id: str, selected_region: str) -> None:
        key = (owner(request), runtime_id, selected_region)
        value = (fingerprint(), time.monotonic())
        with lock:
            contexts.pop(key, None)
            contexts[key] = value
            while len(contexts) > _CONTEXT_LIMIT:
                contexts.popitem(last=False)

    def require_context(key: tuple[str, str, str]) -> None:
        current_fingerprint = fingerprint()
        with lock:
            value = contexts.get(key)
        if (
            value is None
            or time.monotonic() - value[1] > _CONTEXT_TTL
            or value[0] != current_fingerprint
        ):
            raise ValueError("Deletion confirmation context is unavailable")

    normalize_region = region

    @app.get("/web/mpa-runtime-deletion-status")
    async def status(
        request: Request,
        runtimeId: str = Query(min_length=1, max_length=128),
        region: str = Query(min_length=1, max_length=64),
    ) -> JSONResponse:
        identity = owner(request)
        selected_region = normalize_region(region)
        key = (identity, runtimeId, selected_region)
        try:
            require_context(key)
            deleted = False
            async with timeout(_CHECK_TIMEOUT):
                try:
                    await asyncio.to_thread(
                        get_runtime, request, runtimeId, selected_region
                    )
                except HTTPException:
                    raise
                except Exception as error:
                    if not runtime_not_found(error):
                        raise
                    token = ""
                    seen: set[str] = set()
                    for _ in range(20):
                        page = await asyncio.to_thread(
                            list_page, selected_region, token
                        )
                        require_context(key)
                        rows = page.get("AgentKitRuntimes")
                        if not isinstance(rows, list):
                            raise ValueError("Incomplete Runtime listing")
                        for row in rows:
                            ident = (
                                row.get("RuntimeId")
                                if isinstance(row, Mapping)
                                else None
                            )
                            if not isinstance(ident, str) or not ident:
                                raise ValueError("Incomplete Runtime identity")
                            if ident == runtimeId:
                                break
                        else:
                            next_token = page.get("NextToken")
                            if next_token is None:
                                next_token = ""
                            if not isinstance(next_token, str) or next_token in seen:
                                raise ValueError("Invalid Runtime pagination")
                            if not next_token:
                                deleted = True
                                break
                            seen.add(next_token)
                            token = next_token
                            continue
                        break
                    else:
                        raise ValueError("Runtime listing budget exhausted")
            require_context(key)
            return JSONResponse(
                {"deleted": deleted}, headers={"Cache-Control": "no-store"}
            )
        except HTTPException:
            raise
        except Exception:
            raise HTTPException(
                503,
                {
                    "code": "mpa_deletion_unconfirmed",
                    "message": "Runtime deletion is not confirmed; check again later.",
                },
                headers={"Cache-Control": "no-store"},
            ) from None

    return remember
