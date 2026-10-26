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

"""Work dispatcher implemented with the published Anthropic HTTP/Work APIs.

Poll credentials belong to the environment. Claimed Work credentials belong to
one lease. Neither credential nor secret-bearing API error text is logged.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import random
import time
from collections.abc import Awaitable, Callable, Mapping
from typing import Any
from uuid import uuid4

import anthropic
import httpx2
from anthropic.types.beta.environments import BetaSelfHostedWork

logger = logging.getLogger(__name__)
poll_trace_logger = logging.getLogger("anthropic.managed_agent_poll")
HEARTBEAT_INTERVAL = 30.0
LEASE_TTL = 90.0
CLEANUP_TIMEOUT = 10.0


def sessions_token(secret: str | None) -> str | None:
    """Extract a per-Work token; opaque malformed secrets never enter errors."""
    if not secret:
        return None
    try:
        value = json.loads(base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4)))
        token = value.get("sessions_token") if isinstance(value, dict) else None
        return token if isinstance(token, str) and token else None
    except (ValueError, TypeError, UnicodeError):
        return None


def _non_auth_headers(headers: Mapping[str, Any]) -> dict[str, Any]:
    return {
        k: v
        for k, v in headers.items()
        if k.lower() not in {"authorization", "x-api-key"}
    }


def scoped_client(client: Any, token: str) -> Any:
    """Preserve transport/settings while replacing all inherited authentication."""
    scoped = client.copy(
        auth_token=token,
        credentials=None,
        set_default_headers=_non_auth_headers(client.default_headers),
        max_retries=0,
    )
    # copy(api_key=None) inherits the parent key in SDK 1.3.0.
    scoped.api_key = None
    return scoped


def _retryable(error: Exception) -> bool:
    status = getattr(error, "status_code", None)
    return (
        status in (408, 409, 429)
        or (isinstance(status, int) and status >= 500)
        or isinstance(
            error, (anthropic.APIConnectionError, httpx2.TransportError, TimeoutError)
        )
    )


def _authentication_error(error: Exception) -> bool:
    return getattr(error, "status_code", None) in (401, 403)


def _poll_trace(event: str, **fields: Any) -> None:
    if os.getenv("MANAGED_AGENT_POLL_TRACE", "").strip().lower() == "true":
        poll_trace_logger.info(
            json.dumps(
                {"event": event, **fields}, separators=(",", ":"), sort_keys=True
            )
        )


class EnvironmentWorkDispatcher:
    """Bounded concurrent leases, with FIFO execution for each Session.

    ``drain`` interrupts polling and waits for accepted Work. Cancelling ``run``
    cancels handlers and waits for their cleanup. ``ready`` is set only after a
    validated successful poll, including an empty 204 response.
    """

    def __init__(
        self,
        client: Any,
        *,
        handler: Callable[[Any, Any], Awaitable[None]],
        environment_id: str,
        environment_key: str,
        account_work: bool = False,
        worker_id: str | None = None,
        extra_headers: Mapping[str, Any] | None = None,
    ):
        if not environment_key or (not environment_id and not account_work):
            raise ValueError(
                "Work dispatcher requires configured credentials and scope"
            )
        self.client = client
        self.handler = handler
        self.environment_id = environment_id
        self.environment_key = environment_key
        self.account_work = account_work
        self.worker_id = worker_id or f"worker-{uuid4().hex}"
        self.headers = _non_auth_headers(extra_headers or {})
        self.draining = False
        self.ready = asyncio.Event()
        self._drain_event = asyncio.Event()
        self.poll_task: asyncio.Task | None = None
        self._session_tails: dict[str, asyncio.Future] = {}

    def drain(self) -> None:
        self.draining = True
        self._drain_event.set()
        if self.poll_task is not None:
            self.poll_task.cancel()

    async def _poll(self, client: Any) -> BetaSelfHostedWork | None:
        headers = {
            "anthropic-beta": "managed-agents-2026-04-01",
            **self.headers,
            "Anthropic-Worker-ID": self.worker_id,
        }
        trace_id = f"poll_{uuid4().hex}"
        if os.getenv("MANAGED_AGENT_POLL_TRACE", "").strip().lower() == "true":
            headers["X-MA-Poll-Trace-ID"] = trace_id
        started = time.monotonic()
        _poll_trace(
            "poll_started", request_id=trace_id, account_scope=self.account_work
        )
        try:
            # Inspect 204 before parsing: SDK 1.3's typed poll result otherwise
            # constructs an empty Work. Both paths use public SDK interfaces.
            if self.account_work:
                # Account model Work is a VeADK gateway extension, not a Claude
                # endpoint. The official SDK supports custom requests via get.
                response = await client.get(
                    "/v1/model-work/poll",
                    cast_to=httpx2.Response,
                    options={"headers": headers, "params": {"block_ms": 999}},
                )
            else:
                raw = await client.beta.environments.work.with_raw_response.poll(
                    self.environment_id,
                    block_ms=999,
                    anthropic_worker_id=self.worker_id,
                    extra_headers=headers,
                )
                response = raw.http_response
            if response.status_code == 204:
                item = None
            else:
                media = (
                    response.headers.get("content-type", "")
                    .split(";", 1)[0]
                    .strip()
                    .lower()
                )
                if response.status_code != 200 or media != "application/json":
                    raise ValueError("Work poll returned an unexpected response")
                try:
                    item = BetaSelfHostedWork.model_validate(response.json())
                    if not item.id or not item.environment_id or not item.data.id:
                        raise ValueError()
                    if self.account_work and not sessions_token(item.secret):
                        raise ValueError()
                    if (
                        not self.account_work
                        and item.environment_id != self.environment_id
                    ):
                        raise ValueError()
                except Exception:
                    raise ValueError("Work poll returned malformed Work") from None
        except Exception as error:
            _poll_trace(
                "poll_error",
                request_id=trace_id,
                error_type=type(error).__name__,
                status=getattr(error, "status_code", None),
                retry=_retryable(error),
            )
            raise
        self.ready.set()
        _poll_trace(
            "poll_completed",
            request_id=trace_id,
            status=response.status_code,
            result="work" if item is not None else "empty",
            duration_ms=round((time.monotonic() - started) * 1000, 3),
        )
        return item

    async def _pause(self, delay: float) -> None:
        try:
            await asyncio.wait_for(self._drain_event.wait(), timeout=delay)
        except asyncio.TimeoutError:
            pass

    async def run(
        self, *, max_items: int | None = None, max_concurrency: int = 1
    ) -> int:
        if max_concurrency < 1 or (max_items is not None and max_items < 1):
            raise ValueError("Work limits must be positive")
        client = scoped_client(self.client, self.environment_key)
        active: set[asyncio.Task] = set()
        count = attempt = 0
        try:
            while not self.draining and (max_items is None or count < max_items):
                completed = {task for task in active if task.done()}
                for task in completed:
                    active.remove(task)
                    task.result()
                if len(active) >= max_concurrency:
                    await asyncio.wait(active, return_when=asyncio.FIRST_COMPLETED)
                    continue
                self.poll_task = asyncio.create_task(self._poll(client))
                try:
                    while not self.poll_task.done():
                        done, _ = await asyncio.wait(
                            {self.poll_task, *active},
                            return_when=asyncio.FIRST_COMPLETED,
                        )
                        for task in done - {self.poll_task}:
                            active.remove(task)
                            task.result()
                    item = await self.poll_task
                except asyncio.CancelledError:
                    if self.draining and self.poll_task.cancelled():
                        break
                    raise
                except Exception as error:
                    if not _retryable(error):
                        raise
                    attempt += 1
                    await self._pause(min(2 ** min(attempt, 5), 30) + random.random())
                    continue
                finally:
                    if self.poll_task is not None and not self.poll_task.done():
                        self.poll_task.cancel()
                        await asyncio.gather(self.poll_task, return_exceptions=True)
                    self.poll_task = None
                attempt = 0
                if item is None:
                    await self._pause(0.25)
                    continue
                session = item.data.id
                previous = self._session_tails.get(session)
                finished = asyncio.get_running_loop().create_future()
                self._session_tails[session] = finished
                active.add(
                    asyncio.create_task(self._handle_item(item, previous, finished))
                )
                count += 1
            if active:
                await asyncio.gather(*active)
            return count
        finally:
            for task in active:
                if not task.done():
                    task.cancel()
            if active:
                await asyncio.gather(*active, return_exceptions=True)

    async def _handle_item(
        self,
        item: BetaSelfHostedWork,
        previous: asyncio.Future | None = None,
        finished: asyncio.Future | None = None,
    ) -> None:
        token = sessions_token(item.secret)
        client = scoped_client(self.client, token or self.environment_key)
        work = client.beta.environments.work
        lost = False
        fenced = asyncio.Event()
        beat = handler = None

        async def heartbeat_loop() -> None:
            nonlocal lost
            last, interval, ttl = "NO_HEARTBEAT", HEARTBEAT_INTERVAL, LEASE_TTL
            success = time.monotonic()
            while True:
                try:
                    response = await asyncio.wait_for(
                        work.heartbeat(
                            item.id,
                            environment_id=item.environment_id,
                            expected_last_heartbeat=last,
                            extra_headers=self.headers,
                        ),
                        timeout=min(
                            interval, max(0.001, ttl - (time.monotonic() - success))
                        ),
                    )
                except Exception as error:
                    if getattr(error, "status_code", None) == 412:
                        lost = True
                        return
                    if not _retryable(error):
                        raise
                    if time.monotonic() - success >= ttl:
                        lost = True
                        return
                else:
                    last = response.last_heartbeat
                    success = time.monotonic()
                    if response.ttl_seconds > 0:
                        ttl = float(response.ttl_seconds)
                        interval = min(ttl / 2, HEARTBEAT_INTERVAL)
                    if response.state in {"stopping", "stopped"}:
                        return
                    if not response.lease_extended:
                        lost = True
                        return
                    fenced.set()
                await asyncio.sleep(
                    min(interval, max(0.001, ttl - (time.monotonic() - success)))
                )

        async def ordered_handler() -> None:
            await fenced.wait()
            if previous is not None:
                await asyncio.shield(previous)
            await self.handler(item, client)

        try:
            await work.ack(
                item.id, environment_id=item.environment_id, extra_headers=self.headers
            )
            beat = asyncio.create_task(heartbeat_loop())
            handler = asyncio.create_task(ordered_handler())
            done, _ = await asyncio.wait(
                {beat, handler}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in done:
                task.result()
        except asyncio.CancelledError:
            raise
        except Exception as error:
            if getattr(error, "status_code", None) == 412:
                lost = True
            if _authentication_error(error):
                raise
            logger.error("Managed Work failed: %s", type(error).__name__)
        finally:
            # Keep a live heartbeat through asynchronous handler teardown.
            if handler is not None:
                if not handler.done():
                    handler.cancel()
                await asyncio.gather(handler, return_exceptions=True)
            if beat is not None:
                if not beat.done():
                    beat.cancel()
                await asyncio.gather(beat, return_exceptions=True)
            try:
                if not lost:

                    async def stop() -> None:
                        try:
                            await asyncio.wait_for(
                                work.stop(
                                    item.id,
                                    environment_id=item.environment_id,
                                    force=True,
                                    extra_headers=self.headers,
                                ),
                                CLEANUP_TIMEOUT,
                            )
                        except Exception as error:
                            if _authentication_error(error):
                                raise
                            if getattr(error, "status_code", None) != 409:
                                logger.error(
                                    "Managed Work stop failed: %s", type(error).__name__
                                )

                    cleanup = asyncio.create_task(stop())
                    try:
                        await asyncio.shield(cleanup)
                    except asyncio.CancelledError:
                        await cleanup
                        raise
            finally:
                if finished is not None:
                    if not finished.done():
                        finished.set_result(None)
                    if self._session_tails.get(item.data.id) is finished:
                        self._session_tails.pop(item.data.id, None)
