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
"""HTTP client for the System One decision API."""

from __future__ import annotations

from typing import Any, Mapping, Protocol

import httpx

from .config import QuestionConfig

DEFAULT_TIMEOUT_SECONDS = 10.0


class DecisionClientError(Exception):
    """A transport or response-shape failure from the decision API."""

    def __init__(self, error_type: str, message: str):
        super().__init__(message)
        self.error_type = error_type
        self.message = message


class DecisionJudge(Protocol):
    """Minimal interface the plugin needs from a decision client."""

    async def judge(
        self, *, state: str, questions: Mapping[str, QuestionConfig]
    ) -> dict[str, Any]: ...


class DecisionClient:
    """Call one batched System One request per checkpoint."""

    def __init__(
        self,
        *,
        endpoint: str,
        api_key: str,
        model: str,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._endpoint = endpoint
        self._api_key = api_key
        self._model = model
        self._timeout = timeout
        self._transport = transport

    @property
    def endpoint(self) -> str:
        return self._endpoint

    async def judge(
        self, *, state: str, questions: Mapping[str, QuestionConfig]
    ) -> dict[str, Any]:
        payload = {
            "model": self._model,
            "state": state,
            "questions": {
                name: {"type": question.type, "instructions": question.instructions}
                for name, question in questions.items()
            },
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "ark-beta-systemone-api": "true",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self._timeout, transport=self._transport
            ) as client:
                response = await client.post(
                    self._endpoint, headers=headers, json=payload
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
        return data
