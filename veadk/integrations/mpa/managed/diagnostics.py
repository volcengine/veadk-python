"""Allowlisted provisioning diagnostics and bounded Worker API recovery."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
import logging
from typing import TypeVar

from agentkit.auth.errors import AuthError, NetworkError
from agentkit.toolkit.errors import ApiError
import requests

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
    "InternalError": "unavailable",
    "InternalServerError": "unavailable",
    "ServiceUnavailable": "unavailable",
    "RequestTimeout": "timeout",
}
DEPLOYMENT_CATEGORIES = {
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


def validate_diagnostic(value: object) -> Diagnostic | None:
    if not isinstance(value, dict) or set(value) != {
        "operation",
        "category",
        "attempt",
        "outcome",
    }:
        return None
    if (
        not isinstance(value["operation"], str)
        or value["operation"] not in OPERATIONS
        or not isinstance(value["category"], str)
        or value["category"] not in CATEGORIES
        or type(value["attempt"]) is not int
        or not 1 <= value["attempt"] <= 4
        or not isinstance(value["outcome"], str)
        or value["outcome"] not in {"retrying", "failed", "cancelled"}
    ):
        return None
    return dict(value)


@contextmanager
def diagnostic_scope(sink: Callable[[Diagnostic], None]) -> Iterator[None]:
    token = _sink.set(sink)
    try:
        yield
    finally:
        _sink.reset(token)


def report(
    operation: str, category: str, *, attempt: int = 1, outcome: str = "failed"
) -> None:
    diagnostic = validate_diagnostic(
        dict(operation=operation, category=category, attempt=attempt, outcome=outcome)
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
            category = classify_error(error)
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
            )
            if not retrying:
                raise
            await asyncio.sleep(2 ** (attempt - 1))
    raise AssertionError("Worker retry loop exhausted without a result")
