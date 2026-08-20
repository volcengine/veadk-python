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

"""Dependency-injected entry point for a once-per-minute VeFaaS trigger."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from .dispatcher import Dispatcher


def make_handler(dispatcher: Dispatcher) -> Callable[[Any, Any], dict[str, int]]:
    """Build a synchronous cloud handler without retaining scheduling state."""

    def handler(_event: Any, _context: Any) -> dict[str, int]:
        summary = asyncio.run(dispatcher.dispatch_minute(datetime.now(timezone.utc)))
        return {
            "scanned": summary.scanned,
            "started": summary.started,
            "stale": summary.stale,
            "skipped": summary.skipped,
            "failed": summary.failed,
        }

    return handler
