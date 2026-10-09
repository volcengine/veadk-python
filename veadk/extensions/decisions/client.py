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
    DecisionModelError,
    DecisionModelRequestError,
    DecisionModelResponseError,
)
from veadk.extensions.decisions.types import (
    DecisionResult,
    DecisionUsage,
    parse_answers,
)
from veadk.utils.logger import get_logger

logger = get_logger(__name__)

# Statuses worth retrying: rate limits, transient overload, gateway errors.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504, 529})
_BODY_SNIPPET_LIMIT = 500
# Below this remaining budget an attempt is not worth starting.
_MIN_ATTEMPT_SECONDS = 0.05


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

        Raises:
            DecisionModelRequestError: If the endpoint cannot be reached or
                keeps failing. The retries and their backoff share the
                ``timeout`` budget, so one judgement never outlives it.
            DecisionModelResponseError: If the payload cannot be used.
        """
        payload = self._payload(state, questions, model)
        started = time.perf_counter()
        deadline = time.monotonic() + self.config.timeout
        try:
            with httpx.Client() as client:
                body = self._request(
                    lambda remaining: client.post(
                        self.config.endpoint,
                        json=payload,
                        headers=self._headers(),
                        timeout=remaining,
                    ),
                    deadline=deadline,
                )
        except DecisionModelError:
            raise
        except Exception as exc:  # noqa: BLE001 - optional-capability boundary
            raise DecisionModelRequestError(
                f"decision model call failed: {type(exc).__name__}: {exc}"
            ) from exc
        result = self._to_result(body, started)
        self._log_success(result)
        return result

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
        deadline = time.monotonic() + self.config.timeout
        try:
            async with httpx.AsyncClient() as client:
                body = await self._arequest(
                    lambda remaining: client.post(
                        self.config.endpoint,
                        json=payload,
                        headers=self._headers(),
                        timeout=remaining,
                    ),
                    deadline=deadline,
                )
        except DecisionModelError:
            raise
        except Exception as exc:  # noqa: BLE001 - optional-capability boundary
            raise DecisionModelRequestError(
                f"decision model call failed: {type(exc).__name__}: {exc}"
            ) from exc
        result = self._to_result(body, started)
        self._log_success(result)
        return result

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

    def _request(
        self, send: Callable[[float], httpx.Response], *, deadline: float
    ) -> Mapping[str, Any]:
        """Send one request, retrying transient failures inside the budget.

        Retries and their backoff are cut short once ``deadline`` passes, so a
        flapping endpoint cannot turn one judgement into several timeouts.
        """
        attempts = 0
        failure = "no attempt was made"
        for attempt in range(self.config.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= _MIN_ATTEMPT_SECONDS:
                failure = "the time budget was exhausted"
                break
            attempts += 1
            response: httpx.Response | None = None
            try:
                response = send(remaining)
            except httpx.HTTPError as exc:
                failure = f"transport error: {type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001 - normalized for callers
                raise DecisionModelRequestError(
                    "decision model request could not be sent: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            if response is not None:
                if response.status_code not in RETRYABLE_STATUS:
                    return self._decode(response)
                failure = f"HTTP {response.status_code}: {_body_snippet(response)}"
            if attempt >= self.config.max_retries:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "the time budget was exhausted"
                break
            delay = min(_retry_delay(attempt, response), remaining)
            self._log_retry(delay=delay, attempt=attempt, failure=failure)
            time.sleep(delay)
        raise DecisionModelRequestError(
            f"decision model request failed after {attempts} attempt(s) within "
            f"{self.config.timeout:.1f}s: {failure}"
        )

    async def _arequest(
        self, send: Callable[[float], Any], *, deadline: float
    ) -> Mapping[str, Any]:
        """Asynchronous counterpart of :meth:`_request`."""
        attempts = 0
        failure = "no attempt was made"
        for attempt in range(self.config.max_retries + 1):
            remaining = deadline - time.monotonic()
            if remaining <= _MIN_ATTEMPT_SECONDS:
                failure = "the time budget was exhausted"
                break
            attempts += 1
            response: httpx.Response | None = None
            try:
                response = await send(remaining)
            except httpx.HTTPError as exc:
                failure = f"transport error: {type(exc).__name__}: {exc}"
            except Exception as exc:  # noqa: BLE001 - normalized for callers
                raise DecisionModelRequestError(
                    "decision model request could not be sent: "
                    f"{type(exc).__name__}: {exc}"
                ) from exc
            if response is not None:
                if response.status_code not in RETRYABLE_STATUS:
                    return self._decode(response)
                failure = f"HTTP {response.status_code}: {_body_snippet(response)}"
            if attempt >= self.config.max_retries:
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                failure = "the time budget was exhausted"
                break
            delay = min(_retry_delay(attempt, response), remaining)
            self._log_retry(delay=delay, attempt=attempt, failure=failure)
            await asyncio.sleep(delay)
        raise DecisionModelRequestError(
            f"decision model request failed after {attempts} attempt(s) within "
            f"{self.config.timeout:.1f}s: {failure}"
        )

    def _log_retry(self, *, delay: float, attempt: int, failure: str) -> None:
        """Record one retry, the signal that an endpoint is flapping."""
        logger.warning(
            "decision model request failed, retrying in %.1fs (retry %d/%d, "
            "model=%s): %s",
            delay,
            attempt + 1,
            self.config.max_retries,
            self.config.name,
            failure,
        )

    def _log_success(self, result: DecisionResult) -> None:
        """Record one usable judgement for cost and latency observability."""
        cost = result.usage.cost
        logger.debug(
            "decision model %s answered in %.1fms (input=%d output=%d tokens, cost=%s)",
            result.model or self.config.name,
            result.latency_ms,
            result.usage.input_tokens,
            result.usage.output_tokens,
            f"${cost:.6f}" if cost is not None else "n/a",
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
