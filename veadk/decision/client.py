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
"""HTTP client for the Decision API."""

from __future__ import annotations

import asyncio
from typing import Mapping, Protocol

import httpx

from .types import DecisionQuestion, DecisionRequest, DecisionResponse, DecisionState

DEFAULT_TIMEOUT_SECONDS = 10.0
DEFAULT_LIMITS = httpx.Limits(
    max_connections=10,
    max_keepalive_connections=5,
    keepalive_expiry=30.0,
)


class DecisionClientError(Exception):
    """A transport or response-shape failure from the Decision API."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


class DecisionJudge(Protocol):
    """Minimal interface the content-safety plugin needs from a client."""

    async def judge(
        self, *, state: DecisionState, questions: Mapping[str, DecisionQuestion]
    ) -> DecisionResponse: ...


class DecisionClient:
    """Call one batched Decision API request per checkpoint.

    The underlying ``httpx.AsyncClient`` is created lazily and reused for all
    requests in the same event loop, so connection setup is paid once instead
    of once per checkpoint. ``httpx.AsyncClient`` is event-loop bound; if the
    client is used from a different loop (for example, separate
    ``asyncio.run`` calls in tests), a fresh client is created for that loop.
    """

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
        limits: httpx.Limits | None = None,
    ):
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._transport = transport
        self._limits = limits or DEFAULT_LIMITS
        self._client: httpx.AsyncClient | None = None
        self._client_loop: asyncio.AbstractEventLoop | None = None

    @property
    def endpoint(self) -> str:
        return self._endpoint

    def _get_client(self) -> httpx.AsyncClient:
        loop = asyncio.get_running_loop()
        if self._client is None or self._client_loop is not loop:
            # The previous client belongs to another (possibly closed) loop and
            # cannot be safely awaited here. Production plugins stay on one
            # loop; tests that use separate asyncio.run calls get a fresh client.
            self._client = httpx.AsyncClient(
                timeout=self._timeout,
                transport=self._transport,
                limits=self._limits,
            )
            self._client_loop = loop
        return self._client

    async def aclose(self) -> None:
        """Close the pooled HTTP client. Safe to call more than once."""
        client, self._client = self._client, None
        self._client_loop = None
        if client is not None:
            await client.aclose()

    async def __aenter__(self) -> "DecisionClient":
        return self

    async def __aexit__(self, *args: object) -> None:
        await self.aclose()

    async def judge(
        self, *, state: DecisionState, questions: Mapping[str, DecisionQuestion]
    ) -> DecisionResponse:
        request = DecisionRequest(
            model=self._model,
            state=state,
            questions=questions,
        )
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "ark-beta-systemone-api": "true",
            "Content-Type": "application/json",
        }

        try:
            response = await self._get_client().post(
                self._endpoint, headers=headers, json=request.to_payload()
            )
        except httpx.TimeoutException as exc:
            raise DecisionClientError("timeout", str(exc)) from exc
        except httpx.HTTPError as exc:
            raise DecisionClientError("network", str(exc)) from exc

        if response.status_code != 200:
            raise DecisionClientError(
                "http_status",
                f"decision API returned HTTP {response.status_code}",
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise DecisionClientError("invalid_json", str(exc)) from exc

        if not isinstance(data, dict):
            raise DecisionClientError(
                "invalid_response", "decision API response must be an object"
            )

        try:
            return DecisionResponse.from_payload(data)
        except ValueError as exc:
            raise DecisionClientError("invalid_response", str(exc)) from exc
