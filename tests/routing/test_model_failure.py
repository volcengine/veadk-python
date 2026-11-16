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
"""Circuit-breaker classification against the real provider error shapes."""

import httpx
import pytest
from litellm import (
    APIConnectionError,
    AuthenticationError,
    BadRequestError,
    InternalServerError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServiceUnavailableError,
    Timeout,
)
from volcenginesdkarkruntime._exceptions import (
    ArkAPIConnectionError,
    ArkAPITimeoutError,
    ArkAuthenticationError,
    ArkBadRequestError,
    ArkInternalServerError,
    ArkRateLimitError,
)

from veadk.routing.execution import _http_status, _opens_circuit


def litellm_error(error_type, status: int) -> Exception:
    request = httpx.Request("POST", "https://api.example/v1/chat/completions")
    return error_type(
        message="provider rejected the request",
        model="cheap",
        llm_provider="openai",
        response=httpx.Response(status, request=request),
    )


def ark_error(error_type, status: int) -> Exception:
    request = httpx.Request("POST", "https://ark.example/api/v3/responses")
    return error_type(
        message="provider rejected the request",
        response=httpx.Response(status, request=request),
        body={"code": "InvalidParameter"},
        request_id="request-id",
    )


@pytest.mark.parametrize(
    ("error", "expected_status"),
    [
        (litellm_error(BadRequestError, 400), 400),
        (litellm_error(AuthenticationError, 401), 401),
        (litellm_error(PermissionDeniedError, 403), 403),
        (litellm_error(NotFoundError, 404), 404),
        (ark_error(ArkBadRequestError, 400), 400),
        (ark_error(ArkAuthenticationError, 401), 401),
    ],
    ids=[
        "litellm-400",
        "litellm-401",
        "litellm-403",
        "litellm-404",
        "ark-400",
        "ark-401",
    ],
)
def test_request_specific_4xx_does_not_open_the_cooldown(error, expected_status):
    assert _http_status(error) == expected_status
    assert _opens_circuit(error) is False


@pytest.mark.parametrize(
    "error",
    [
        litellm_error(RateLimitError, 429),
        litellm_error(InternalServerError, 500),
        litellm_error(ServiceUnavailableError, 503),
        Timeout(message="timed out", model="cheap", llm_provider="openai"),
        APIConnectionError(
            message="connection failed", model="cheap", llm_provider="openai"
        ),
        ark_error(ArkRateLimitError, 429),
        ark_error(ArkInternalServerError, 500),
        ArkAPIConnectionError(
            request=httpx.Request("POST", "https://ark.example"), request_id="r"
        ),
        ArkAPITimeoutError(
            request=httpx.Request("POST", "https://ark.example"), request_id="r"
        ),
    ],
    ids=[
        "litellm-429",
        "litellm-500",
        "litellm-503",
        "litellm-timeout",
        "litellm-connection",
        "ark-429",
        "ark-500",
        "ark-connection",
        "ark-timeout",
    ],
)
def test_transient_or_unknown_failures_open_the_cooldown(error):
    assert _opens_circuit(error) is True


def test_string_business_code_is_not_used_as_an_http_status():
    """The Ark SDK keeps ``code`` as a business string, not an HTTP status."""

    error = ark_error(ArkBadRequestError, 400)
    assert error.code == "InvalidParameter"
    assert _http_status(error) == 400
    assert _opens_circuit(error) is False


@pytest.mark.parametrize(
    ("code", "expected"),
    [(400, False), (408, True), (429, True), (503, True)],
)
def test_integer_code_fallback_still_classifies_genai_errors(code, expected):
    """``google.genai.errors.APIError`` exposes the status on ``code``."""

    class GenaiLikeError(Exception):
        pass

    error = GenaiLikeError()
    error.code = code
    assert _http_status(error) == code
    assert _opens_circuit(error) is expected
