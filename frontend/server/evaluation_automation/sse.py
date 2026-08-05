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

"""Incremental inspection of proxied Runtime SSE responses."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable

from .models import RunSseActivity


class RunSseObservation:
    """Track whether a proxied stream completed without an SSE error payload."""

    def __init__(self, activity: RunSseActivity) -> None:
        self.activity = activity
        self._buffer = b""
        self._failed = False
        self._saw_event = False

    @property
    def succeeded(self) -> bool:
        return self._saw_event and not self._failed

    def feed(self, chunk: bytes) -> None:
        if self._failed or not chunk:
            return
        self._buffer += chunk
        lines = self._buffer.split(b"\n")
        self._buffer = lines.pop()
        for line in lines:
            self._inspect_line(line.rstrip(b"\r"))

    def finish(self) -> None:
        """Inspect a final unterminated SSE line after a normal upstream EOF."""
        if self._buffer:
            self._inspect_line(self._buffer.rstrip(b"\r"))
            self._buffer = b""

    def _inspect_line(self, line: bytes) -> None:
        if not line.startswith(b"data:"):
            return
        payload = line[5:].strip()
        if not payload or payload == b"[DONE]":
            return
        try:
            value = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return
        if not isinstance(value, dict):
            return
        if (
            value.get("error")
            or value.get("errorMessage")
            or value.get("error_message")
        ):
            self._failed = True
            return
        self._saw_event = True


async def observed_sse_stream(
    source: AsyncIterator[bytes],
    observation: RunSseObservation,
    on_completed: Callable[[RunSseActivity], None],
) -> AsyncIterator[bytes]:
    """Forward chunks and notify only after a successful, normally exhausted stream."""
    async for chunk in source:
        observation.feed(chunk)
        yield chunk
    observation.finish()
    if observation.succeeded:
        on_completed(observation.activity)
