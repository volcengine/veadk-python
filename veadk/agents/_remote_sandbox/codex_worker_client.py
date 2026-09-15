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


"""Async client for the CodeEnv Codex worker HTTP/SSE protocol v1."""

from __future__ import annotations

import asyncio
import json
from urllib.parse import quote

import httpx


class CodexWorkerError(RuntimeError):
    """A sanitized worker failure; never includes credential URLs or wire data."""

    def __init__(self, message: str, *, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


class CodexWorkerClient:
    def __init__(
        self,
        endpoint: str,
        *,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
    ):
        url = httpx.URL(endpoint)
        if (
            url.scheme not in {"http", "https"}
            or not url.host
            or url.userinfo
            or url.fragment
        ):
            raise ValueError(
                "endpoint must be an HTTP(S) URL without userinfo or fragment"
            )
        if url.path.rstrip("/") not in {"", "/v1/codex-worker"}:
            raise ValueError("endpoint path must be / or /v1/codex-worker")
        self._url = url
        self._headers = dict(headers or {})
        if api_key:
            self._headers["X-API-Key"] = api_key
        self._http = None

    async def __aenter__(self):
        self._http = httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(60, connect=10, write=10, pool=10),
            follow_redirects=False,
            trust_env=False,
        )
        return self

    async def __aexit__(self, *args):
        await self._http.aclose()

    def _endpoint(self, path):
        # copy_with preserves platform authentication query parameters.
        return self._url.copy_with(path="/v1/codex-worker" + path)

    async def request(self, method, path, *, body=None, key=None):
        for attempt in range(3):
            try:
                response = await self._http.request(
                    method,
                    self._endpoint(path),
                    json=body,
                    headers={"Idempotency-Key": key} if key else None,
                )
            except httpx.TransportError:
                if attempt == 2:
                    raise CodexWorkerError(
                        "Worker request unavailable; execution may have started"
                    ) from None
                await asyncio.sleep(0.1 * (attempt + 1))
                continue
            if response.status_code >= 400:
                # POST retries only use a stable idempotency key. A 5xx can
                # represent an accepted request, never generate a replacement key.
                if response.status_code >= 500 and key and attempt < 2:
                    await asyncio.sleep(0.1 * (attempt + 1))
                    continue
                raise CodexWorkerError(
                    f"Worker returned HTTP {response.status_code}",
                    status_code=response.status_code,
                )
            if response.status_code >= 300:
                raise CodexWorkerError("Worker redirects are not supported")
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError
                return data
            except ValueError:
                raise CodexWorkerError("Invalid worker response") from None
        raise CodexWorkerError("Worker unavailable")

    async def create_session(self, key):
        result = await self.request("POST", "/sessions", body={}, key=key)
        if result.get("status") != "ready":
            raise CodexWorkerError(
                "Session initialization is unconfirmed; do not create a replacement"
            )
        return result["sessionId"]

    @staticmethod
    def turn_path(sid, tid=None):
        path = f"/sessions/{quote(sid, safe='')}/turns"
        return path if tid is None else path + "/" + quote(tid, safe="")

    async def start_turn(self, sid, task, key):
        return await self.request(
            "POST", self.turn_path(sid), body={"task": task}, key=key
        )

    async def cancel(self, sid, tid):
        # turn/start may still be waiting for its Codex ID. Retry cancellation,
        # not execution, for up to the worker's start RPC deadline.
        for _ in range(40):
            state = await self.request("GET", self.turn_path(sid, tid))
            if state["status"] in {"completed", "failed", "interrupted", "unknown"}:
                return state
            if state.get("codexTurnId"):
                return await self.request("POST", self.turn_path(sid, tid) + "/cancel")
            await asyncio.sleep(0.5)
        raise CodexWorkerError("Cancellation could not confirm the remote turn ID")

    async def events(self, sid, tid, *, after_event_id=0):
        cursor = after_event_id
        for attempt in range(4):
            try:
                async with self._http.stream(
                    "GET",
                    self._endpoint(self.turn_path(sid, tid) + "/events"),
                    headers={"Last-Event-ID": str(cursor)},
                ) as response:
                    if response.status_code != 200:
                        raise CodexWorkerError(
                            f"Worker event stream returned HTTP {response.status_code}"
                        )
                    data = []
                    size = 0
                    async for line in response.aiter_lines():
                        size += len(line)
                        if size > 4 * 1024 * 1024:
                            raise CodexWorkerError("Worker event too large")
                        if line.startswith("data:"):
                            data.append(line[5:].lstrip())
                        elif not line:
                            size = 0
                            if not data:
                                continue
                            try:
                                event = json.loads("\n".join(data))
                            except ValueError:
                                raise CodexWorkerError("Invalid worker event") from None
                            data = []
                            if event.get("schemaVersion") != 1:
                                raise CodexWorkerError(
                                    "Unsupported worker event or expired stream"
                                )
                            if (
                                event.get("sessionId") != sid
                                or event.get("turnId") != tid
                            ):
                                raise CodexWorkerError("Worker event binding mismatch")
                            sequence = event.get("eventId")
                            if not isinstance(sequence, int) or sequence < 1:
                                raise CodexWorkerError("Invalid worker event cursor")
                            if sequence <= cursor:
                                continue
                            cursor = sequence
                            yield event
                            if event["type"] == "turn.completed":
                                return
            except httpx.TransportError:
                pass
            if attempt < 3:
                await asyncio.sleep(0.1 * (attempt + 1))
        raise CodexWorkerError(
            "Worker stream ended without a terminal event; do not restart the task"
        )
