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

"""HTTP client for a System One decision endpoint."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from veadk.extensions.decisions.config import DecisionModelConfig
from veadk.extensions.decisions.errors import (
    DecisionModelRequestError,
    DecisionModelResponseError,
)
from veadk.extensions.decisions.types import (
    DecisionResult,
    DecisionUsage,
    parse_answers,
)

# Statuses worth retrying: rate limits, transient overload, gateway errors.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})
_BODY_SNIPPET_LIMIT = 500


class SystemOneClient:
    """Client for the System One evaluation endpoint.

    The hosted service and a self-hosted System One server expose the same
    request/response contract, so one client covers both; only ``api_base``
    differs.
    """

    def __init__(self, config: DecisionModelConfig) -> None:
        if not config.api_key:
            raise DecisionModelRequestError("decision model api_key is required")
        self.config = config

    def evaluate(
        self,
        *,
        state: Any,
        questions: Mapping[str, Any],
        model: str | None = None,
    ) -> DecisionResult:
        """Evaluate questions about one state synchronously.

        Args:
            state: Text or JSON value the questions are asked about.
            questions: Map of question id to question payload.
            model: Model name override; defaults to the configured name.

        Returns:
            The typed answers plus model name, usage, and latency.
        """
        payload = self._payload(state, questions, model)
        started = time.perf_counter()
        with httpx.Client(timeout=self.config.timeout) as client:
            body = self._request(
                lambda: client.post(
                    self.config.endpoint, json=payload, headers=self._headers()
                )
            )
        return self._to_result(body, started)

    async def aevaluate(
        self,
        *,
        state: Any,
        questions: Mapping[str, Any],
        model: str | None = None,
    ) -> DecisionResult:
        """Asynchronous counterpart of :meth:`evaluate`."""
        payload = self._payload(state, questions, model)
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=self.config.timeout) as client:
            body = await self._arequest(
                lambda: client.post(
                    self.config.endpoint, json=payload, headers=self._headers()
                )
            )
        return self._to_result(body, started)

    # -- internals ---------------------------------------------------------

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _payload(
        self, state: Any, questions: Mapping[str, Any], model: str | None
    ) -> dict[str, Any]:
        if not questions:
            raise DecisionModelRequestError("at least one question is required")
        return {
            "state": state,
            "model": model or self.config.name,
            "questions": dict(questions),
        }

    def _request(self, send: Callable[[], httpx.Response]) -> Mapping[str, Any]:
        """Send one request, retrying transient failures with backoff."""
        failure = "no attempt was made"
        for attempt in range(self.config.max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = send()
            except httpx.HTTPError as exc:
                failure = f"transport error: {exc}"
            if response is not None:
                if response.status_code not in RETRYABLE_STATUS:
                    return self._decode(response)
                failure = f"HTTP {response.status_code}: {_body_snippet(response)}"
            if attempt < self.config.max_retries:
                time.sleep(_retry_delay(attempt, response))
                continue
            break
        raise DecisionModelRequestError(
            f"decision model request failed after {self.config.max_retries} "
            f"retries: {failure}"
        )

    async def _arequest(self, send: Callable[[], Any]) -> Mapping[str, Any]:
        """Asynchronous counterpart of :meth:`_request`."""
        failure = "no attempt was made"
        for attempt in range(self.config.max_retries + 1):
            response: httpx.Response | None = None
            try:
                response = await send()
            except httpx.HTTPError as exc:
                failure = f"transport error: {exc}"
            if response is not None:
                if response.status_code not in RETRYABLE_STATUS:
                    return self._decode(response)
                failure = f"HTTP {response.status_code}: {_body_snippet(response)}"
            if attempt < self.config.max_retries:
                await asyncio.sleep(_retry_delay(attempt, response))
                continue
            break
        raise DecisionModelRequestError(
            f"decision model request failed after {self.config.max_retries} "
            f"retries: {failure}"
        )

    def _decode(self, response: httpx.Response) -> Mapping[str, Any]:
        """Reject error statuses and return the decoded JSON object."""
        if response.status_code >= 400:
            raise DecisionModelRequestError(
                f"decision model returned HTTP {response.status_code}: "
                f"{_body_snippet(response)}"
            )
        try:
            body = response.json()
        except ValueError as exc:
            raise DecisionModelResponseError(
                "decision model response is not valid JSON"
            ) from exc
        if not isinstance(body, Mapping):
            raise DecisionModelResponseError(
                "decision model response is not a JSON object"
            )
        return body

    def _to_result(self, body: Mapping[str, Any], started: float) -> DecisionResult:
        raw_answers = body.get("answers")
        if not isinstance(raw_answers, Mapping):
            raise DecisionModelResponseError(
                f"decision model response has no answers object: {body!r}"
            )
        usage = body.get("usage") or {}
        return DecisionResult(
            model=str(body.get("model") or ""),
            answers=parse_answers(raw_answers),
            usage=DecisionUsage(
                input_tokens=_as_int(usage, "input_tokens"),
                output_tokens=_as_int(usage, "output_tokens"),
                cost=_as_float(usage, "cost"),
            ),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )


def _as_int(payload: Mapping[str, Any], key: str) -> int:
    try:
        return int(payload.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def _as_float(payload: Mapping[str, Any], key: str) -> float | None:
    """Read an optional float, keeping ``None`` when it is absent or unusable."""
    raw = payload.get(key)
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _body_snippet(response: httpx.Response) -> str:
    try:
        return response.text[:_BODY_SNIPPET_LIMIT]
    except (UnicodeDecodeError, httpx.ResponseNotRead):
        return ""


def _retry_delay(attempt: int, response: httpx.Response | None) -> float:
    """Backoff for one retry, honouring ``retry-after`` when present."""
    if response is not None:
        raw = response.headers.get("retry-after")
        if raw:
            try:
                return max(0.0, float(raw))
            except ValueError:
                pass  # an HTTP-date is not worth parsing; fall back to backoff
    return 0.5 * (2**attempt)
