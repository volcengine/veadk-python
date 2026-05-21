"""Compatibility helpers for Google ADK feature/version checks.

This module centralizes ADK capability detection to avoid scattering
hard-coded version checks across the codebase.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from packaging.version import Version, parse as parse_version


@lru_cache(maxsize=1)
def get_adk_version() -> Version:
    """Return installed Google ADK version (best effort)."""
    try:
        from google.adk import version as adk_version

        return parse_version(adk_version.__version__)
    except Exception:
        return parse_version("0.0.0")


def is_adk_gte(version: str) -> bool:
    """Whether installed ADK version is greater than or equal to target."""
    return get_adk_version() >= parse_version(version)


def should_use_async_db_drivers() -> bool:
    """Whether ADK expects async SQLAlchemy DSN schemes for DB sessions."""
    return is_adk_gte("1.19.0")


@lru_cache(maxsize=32)
def llm_request_has_field(field_name: str) -> bool:
    """Check whether ``google.adk.models.LlmRequest`` contains a model field."""
    try:
        from google.adk.models import LlmRequest

        return field_name in getattr(LlmRequest, "model_fields", {})
    except Exception:
        return False


def get_previous_interaction_id(llm_request) -> Optional[str]:
    """Safely read ``previous_interaction_id`` from LlmRequest across ADK versions."""
    return getattr(llm_request, "previous_interaction_id", None)


def get_event_function_calls(event: Any) -> list[Any]:
    """Extract function calls from an ADK event across versions."""
    getter = getattr(event, "get_function_calls", None)
    if callable(getter):
        try:
            calls = getter()
            return list(calls or [])
        except Exception:
            # Fallback to generic part traversal for compatibility.
            pass

    calls: list[Any] = []
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    for part in parts or []:
        function_call = getattr(part, "function_call", None)
        if function_call is not None:
            calls.append(function_call)
    return calls


def get_event_function_responses(event: Any) -> list[Any]:
    """Extract function responses from an ADK event across versions."""
    getter = getattr(event, "get_function_responses", None)
    if callable(getter):
        try:
            responses = getter()
            return list(responses or [])
        except Exception:
            # Fallback to generic part traversal for compatibility.
            pass

    responses: list[Any] = []
    content = getattr(event, "content", None)
    parts = getattr(content, "parts", None) if content is not None else None
    for part in parts or []:
        function_response = getattr(part, "function_response", None)
        if function_response is not None:
            responses.append(function_response)
    return responses
