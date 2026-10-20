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

"""HTTP boundary used by the native VeFaaS minute-timer function."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import FastAPI

from .app import create_dispatcher
from .models import DispatchSummary

app = FastAPI(title="VeADK Studio cronjob scheduler", docs_url=None, redoc_url=None)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


def _summary(summary: DispatchSummary) -> dict[str, int]:
    return {
        "scanned": summary.scanned,
        "queued": summary.queued,
        "started": summary.started,
        "stale": summary.stale,
        "skipped": summary.skipped,
        "failed": summary.failed,
    }


async def dispatch_current_minute() -> dict[str, int]:
    summary = await create_dispatcher().dispatch_minute(datetime.now(timezone.utc))
    return _summary(summary)


async def execute_ready_runs() -> dict[str, int]:
    summary = await create_dispatcher().execute_ready()
    return _summary(summary)


def _timer_event(value: dict[str, object] | str | None) -> dict[str, object]:
    """Normalize provider-specific timer payload shapes.

    Volcengine sends the configured JSON payload as an object, while BytePlus
    currently delivers the same value as a JSON-encoded string.
    """
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError("Scheduler timer payload is not valid JSON") from error
    if not isinstance(decoded, dict):
        raise ValueError(  # noqa: TRY004 - invalid external payload, not API misuse
            "Scheduler timer payload must be a JSON object"
        )
    return decoded


@app.post("/")
async def handle_timer(
    event: dict[str, object] | str | None = None,
) -> dict[str, int]:
    phase = str(_timer_event(event).get("phase") or "scan")
    if phase == "scan":
        return await dispatch_current_minute()
    if phase == "execute":
        return await execute_ready_runs()
    raise ValueError(f"Unsupported scheduler phase: {phase}")


__all__ = [
    "app",
    "dispatch_current_minute",
    "execute_ready_runs",
    "handle_timer",
    "healthz",
]
