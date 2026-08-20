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

from datetime import datetime, timezone

from fastapi import FastAPI

from .app import create_dispatcher

app = FastAPI(title="VeADK Studio cronjob scheduler", docs_url=None, redoc_url=None)


@app.get("/healthz")
async def healthz() -> dict[str, bool]:
    return {"ok": True}


@app.post("/")
async def dispatch_current_minute() -> dict[str, int]:
    summary = await create_dispatcher().dispatch_minute(datetime.now(timezone.utc))
    return {
        "scanned": summary.scanned,
        "started": summary.started,
        "stale": summary.stale,
        "skipped": summary.skipped,
        "failed": summary.failed,
    }


__all__ = ["app", "dispatch_current_minute", "healthz"]
