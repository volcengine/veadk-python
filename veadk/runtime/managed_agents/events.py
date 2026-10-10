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

"""Opt-in, payload-level tracing for Managed Agent events."""

from __future__ import annotations

import json
import os
import threading
from collections.abc import AsyncIterator, Iterable
from datetime import datetime, timezone
from typing import Any

_OUTPUT_LOCK = threading.Lock()

_SECRET_FIELDS = {
    "authorization",
    "apikey",
    "token",
    "accesstoken",
    "refreshtoken",
    "accesskey",
    "accesskeyid",
    "secretkey",
    "secret",
    "secretaccesskey",
    "sessiontoken",
    "password",
    "clientsecret",
    "credentials",
    "credential",
    "workloadaccesstoken",
    "agentidentitytoken",
    "worktoken",
    "bearertoken",
    "environmentkey",
    "xapikey",
}


def _json_value(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json", warnings=False)
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError("Unsupported event value")


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]"
            if key.lower().replace("_", "").replace("-", "") in _SECRET_FIELDS
            else _redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def trace_event(
    direction: str, source: str, session_id: str | None, event: Any
) -> None:
    """Print one complete JSON record without changing the event or log levels."""
    if os.getenv("MA_DEBUG_EVENTS", "").strip().lower() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return
    try:
        # Normalize SDK/Runner models first so nested credential fields are redacted too.
        payload = _redact(json.loads(json.dumps(event, default=_json_value)))
        record = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "direction": direction,
            "source": source,
            "session_id": session_id,
            "event": payload,
        }
        line = "MA_DEBUG_EVENT " + json.dumps(record, ensure_ascii=False)
        with _OUTPUT_LOCK:
            print(line, flush=True)
    except Exception:
        # Debugging must not fail a turn or expose a secret-bearing exception.
        pass


def trace_events(
    direction: str, source: str, session_id: str | None, events: Iterable[Any]
) -> None:
    for event in events:
        trace_event(direction, source, session_id, event)


def trace_send_response(session_id: str | None, response: Any) -> None:
    events = (
        response.get("data", [])
        if isinstance(response, dict)
        else getattr(response, "data", [])
    )
    trace_events("received", "send_response", session_id, events or [])


async def send_session_events(sdk: Any, session_id: str, *, events: list[Any]) -> Any:
    # Outbound records describe attempted sends; persisted events appear in send_response.
    trace_events("sent", "send", session_id, events)
    response = await sdk.beta.sessions.events.send(session_id, events=events)
    trace_send_response(session_id, response)
    return response


async def iter_session_events(
    sdk: Any, session_id: str, **options: Any
) -> AsyncIterator[Any]:
    async for event in sdk.beta.sessions.events.list(session_id, **options):
        trace_event("received", "list", session_id, event)
        yield event
