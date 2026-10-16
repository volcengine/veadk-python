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

"""Allowlisted provisioning diagnostics and bounded Worker API recovery."""

from __future__ import annotations

import ast
import asyncio
import json
import logging
import re
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TypeVar

import requests
from agentkit.auth.errors import AuthError, NetworkError
from agentkit.toolkit.errors import ApiError

from .database import DeploymentError

logger = logging.getLogger(__name__)
CATEGORIES = {
    "timeout",
    "connection",
    "throttled",
    "unavailable",
    "permission",
    "invalid_request",
    "not_found",
    "provider_error",
    "ownership",
    "metadata_pending",
    "metadata_missing",
    "resource_failed",
    "configuration_changed",
    "deployment_error",
    "unknown",
    "child_exit",
    "cancelled",
    "interrupted",
    "protocol_error",
}
OPERATIONS = {
    "create_runtime",
    "update_runtime",
    "iam_verify",
    "iam_get_role",
    "iam_create_role",
    "iam_get_policy",
    "iam_create_policy",
    "iam_attach_role_policy",
    "iam_list_attached_role_policies",
    "create_openviking",
    "get_openviking",
    "get_openviking_key",
    "list_model_keys",
    "get_model_key",
    "get_apm_key",
    "aidap_describe_workspaces",
    "aidap_describe_workspace_detail",
    "aidap_create_workspace",
    "aidap_describe_branches",
    "aidap_describe_computes",
    "aidap_describe_workspace_endpoint",
    "aidap_describe_db_accounts",
    "aidap_describe_databases",
    "aidap_describe_db_account_connection",
    "get_reference_worker",
    "find_worker",
    "create_worker",
    "get_worker",
    "provision",
    "supervisor",
    "worker_id",
    "worker_project",
    "worker_managed_by",
    "worker_agent_key",
    "worker_agent_binding",
    "worker_state",
}
CODE_CATEGORIES = {
    "AccessDenied": "permission",
    "Forbidden": "permission",
    "Unauthorized": "permission",
    "InvalidAccessKeyId": "permission",
    "SignatureDoesNotMatch": "permission",
    "InvalidToken": "permission",
    "ExpiredToken": "permission",
    "InvalidParameter": "invalid_request",
    "InvalidParameterValue": "invalid_request",
    "MissingParameter": "invalid_request",
    "ResourceNotFound": "not_found",
    "ResourceNotFound.Tool": "not_found",
    "NotFound": "not_found",
    "ToolNotFound": "not_found",
    "Throttling": "throttled",
    "ThrottlingException": "throttled",
    "TooManyRequests": "throttled",
    "RequestLimitExceeded": "throttled",
    "QuotaExceeded": "throttled",
    "InternalError": "unavailable",
    "InternalServerError": "unavailable",
    "ServiceUnavailable": "unavailable",
    "RequestTimeout": "timeout",
}
DEPLOYMENT_CATEGORIES = {
    "runtimeNameTaken": "invalid_request",
    "runtimeNameCheckFailed": "unavailable",
    "iamPermissionDenied": "permission",
    "iamTrustConflict": "ownership",
    "iamPolicyConflict": "ownership",
    "iamOwnershipConflict": "ownership",
    "iamVerificationFailed": "resource_failed",
    "iamTemporaryFailure": "unavailable",
    "iamConfigurationConflict": "configuration_changed",
    "Worker ownership metadata is incomplete": "metadata_missing",
    "Worker ownership does not match this agent": "ownership",
    "Worker is missing or belongs to another project": "ownership",
    "Worker is attached to another agent": "ownership",
    "Worker name collision without a recorded creation intent": "ownership",
    "Worker differs from registered binding": "configuration_changed",
    "Unfinished worker configuration changed; resume original inputs": "configuration_changed",
    "Worker is not ready; inspect it and retry the same agent": "resource_failed",
}
Diagnostic = dict[str, str | int]
MAX_DIAGNOSTIC_ATTEMPT = 8
_sink: ContextVar[Callable[[Diagnostic], None] | None] = ContextVar(
    "mpa_diagnostic_sink", default=None
)
T = TypeVar("T")


def classify_error(error: BaseException) -> str:
    """Classify structured errors without copying exception text into events."""
    chain = []
    current = error
    while current is not None and len(chain) < 8 and current not in chain:
        chain.append(current)
        current = current.__cause__
    # A wrapped HTTP permission/validation failure is not a connection outage.
    for cause in chain:
        if isinstance(cause, requests.HTTPError) and cause.response is not None:
            status = cause.response.status_code
            if status in (401, 403):
                return "permission"
            if status == 404:
                return "not_found"
            if status == 429:
                return "throttled"
            if status == 408:
                return "timeout"
            if status in (500, 502, 503, 504):
                return "unavailable"
            return "invalid_request" if status in (400, 422) else "provider_error"
        if isinstance(cause, ApiError) and cause.error_code:
            return CODE_CATEGORIES.get(cause.error_code, "provider_error")
    for cause in chain:
        if isinstance(cause, (TimeoutError, requests.Timeout)):
            return "timeout"
        if isinstance(cause, requests.exceptions.SSLError):
            return "invalid_request"
        if isinstance(cause, (ConnectionError, requests.ConnectionError)):
            return "connection"
    if isinstance(error, NetworkError):
        # A wrapped non-transport RequestException (e.g. bad URL) is permanent.
        return "connection" if len(chain) == 1 else "provider_error"
    if isinstance(error, AuthError):
        return "permission"
    if isinstance(error, DeploymentError):
        return DEPLOYMENT_CATEGORIES.get(str(error), "deployment_error")
    if isinstance(error, ValueError):
        return "invalid_request"
    if isinstance(error, ApiError):
        return "provider_error"
    return "unknown"


def safe_request_id(value: object) -> str:
    """Only provider hex/UUID identifiers may cross the diagnostic boundary."""
    return (
        value
        if isinstance(value, str) and re.fullmatch(r"[0-9A-Fa-f-]{16,128}", value)
        else ""
    )


def safe_error_code(value: object) -> str:
    """Retain bounded provider identifiers, never free text or token-shaped values."""
    if (
        not isinstance(value, str)
        or len(value) > 128
        or not re.fullmatch(r"[A-Z][A-Za-z0-9]*(?:[._][A-Za-z0-9]+)*", value)
        or value.upper().startswith(
            ("SK_", "AK_", "ARK_", "TOKEN_", "BEARER_", "SECRET_", "PASSWORD_")
        )
    ):
        return ""
    return value


def sdk_argument_identifiers(value: object) -> tuple[str, str]:
    """Decode bounded JSON or SDK bytes literals; never evaluate provider text."""
    from .openviking import response_metadata

    if not isinstance(value, (str, bytes)) or len(value) > 65536:
        return "", ""
    try:
        if isinstance(value, str) and value.startswith(("b'", 'b"')):
            value = ast.literal_eval(value)
            if not isinstance(value, bytes) or len(value) > 65536:
                return "", ""
        return response_metadata(json.loads(value))
    except (ValueError, TypeError, SyntaxError, RecursionError):
        return "", ""


def failure_identifiers(error: Exception) -> tuple[str, str]:
    """Read bounded SDK metadata through a cycle-safe exception chain."""
    from .openviking import exception_metadata

    code, request_id = "", ""
    cause: BaseException | None = error
    seen: set[int] = set()
    for _ in range(8):
        if cause is None or id(cause) in seen:
            break
        seen.add(id(cause))
        code = code or safe_error_code(getattr(cause, "error_code", None))
        request_id = request_id or safe_request_id(getattr(cause, "request_id", None))
        if isinstance(cause, Exception):
            try:
                response_body = getattr(
                    getattr(cause, "response", None), "content", None
                )
                if (
                    isinstance(response_body, (str, bytes))
                    and len(response_body) > 65536
                ):
                    body_code, body_request_id = "", ""
                else:
                    body_code, body_request_id = exception_metadata(cause)
            except RecursionError:
                body_code, body_request_id = "", ""
            code, request_id = code or body_code, request_id or body_request_id
        if len(cause.args) == 1:
            arg_code, arg_request_id = sdk_argument_identifiers(cause.args[0])
            code, request_id = code or arg_code, request_id or arg_request_id
        cause = cause.__cause__
    return code, request_id


def validate_diagnostic(value: object) -> Diagnostic | None:
    required = {"operation", "category", "attempt", "outcome"}
    if (
        not isinstance(value, dict)
        or not required <= set(value)
        or set(value) - required - {"requestId", "errorCode"}
    ):
        return None
    if (
        not isinstance(value["operation"], str)
        or value["operation"] not in OPERATIONS
        or not isinstance(value["category"], str)
        or value["category"] not in CATEGORIES
        or type(value["attempt"]) is not int
        or not 1 <= value["attempt"] <= MAX_DIAGNOSTIC_ATTEMPT
        or not isinstance(value["outcome"], str)
        or value["outcome"] not in {"retrying", "failed", "cancelled"}
    ):
        return None
    result = {key: value[key] for key in required}
    request_id = safe_request_id(value.get("requestId"))
    if request_id:
        result["requestId"] = request_id
    error_code = safe_error_code(value.get("errorCode"))
    if error_code:
        result["errorCode"] = error_code
    return result


@contextmanager
def diagnostic_scope(sink: Callable[[Diagnostic], None]) -> Iterator[None]:
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def report(
    operation: str,
    category: str,
    *,
    attempt: int = 1,
    outcome: str = "failed",
    request_id: str = "",
    error_code: str = "",
) -> None:
    diagnostic = validate_diagnostic(
        dict(
            operation=operation,
            category=category,
            attempt=attempt,
            outcome=outcome,
            **({"requestId": request_id} if request_id else {}),
            **({"errorCode": error_code} if error_code else {}),
        )
    )
    if diagnostic is None:
        raise ValueError("Invalid internal diagnostic")
    sink = _sink.get()
    if sink is not None:
        sink(diagnostic)
    else:
        logger.warning("MPA creation diagnostic: %s", diagnostic)


async def retry_worker(
    operation: str, call: Callable[[], Awaitable[T]], *, retry_not_found: bool = False
) -> T:
    for attempt in range(1, 5):
        try:
            return await call()
        except Exception as error:
            error_code, request_id = failure_identifiers(error)
            category = classify_error(error)
            if error_code and category in {"provider_error", "unknown"}:
                category = CODE_CATEGORIES.get(error_code, category)
            recoverable = category in {
                "timeout",
                "connection",
                "throttled",
                "unavailable",
            } or (retry_not_found and category == "not_found")
            retrying = recoverable and attempt < 4
            report(
                operation,
                category,
                attempt=attempt,
                outcome="retrying" if retrying else "failed",
                error_code=error_code,
                request_id=request_id,
            )
            if not retrying:
                raise
            await asyncio.sleep(2 ** (attempt - 1))
    raise AssertionError("Worker retry loop exhausted without a result")
