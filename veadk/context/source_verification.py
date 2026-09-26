"""Opt-in, bounded source check at the final LiteLLM boundary.

This is an experimental allowlist, not a claim of provider compatibility or
evidence sufficiency. One read can miss facts. Explicit caller configuration
always wins. Unsupported routes retain the existing behavior.
"""

from __future__ import annotations

from .runtime import current_scope, is_summary

READER = "veadk_read_context"


def source_verification_choice(payload, config):
    scope = current_scope.get()
    if (
        not config.verify_sources
        or config.mode != "auto"
        or is_summary.get()
        or scope is None
        or not scope.source_verification_allowed
        or scope.source_verification_attempted
        or scope.retrieval_calls
        or not (scope.lossy_references - scope.restored_references)
        or payload.get("stream")
        or payload.get("model") != "openai/deepseek-v4-1-flash-260910"
        or not isinstance(payload.get("api_base"), str)
        or payload.get("api_base", "").rstrip("/")
        != "https://ark.cn-beijing.volces.com/api/v3"
    ):
        return None
    extra = payload.get("extra_body") or {}
    if not isinstance(extra, dict) or extra.get("thinking") != {"type": "disabled"}:
        return None
    # ADK always includes response_format=None. A concrete schema is owned by
    # the caller; for tool choice even explicit None/auto retains ownership.
    if (
        payload.get("response_format") is not None
        or extra.get("response_format") is not None
    ):
        return None
    if any(
        key in container
        for container in (payload, extra)
        for key in ("tool_choice", "function_call", "functions")
    ):
        return None
    if not any(
        isinstance(tool, dict)
        and tool.get("type") == "function"
        and isinstance(tool.get("function"), dict)
        and tool["function"].get("name") == READER
        for tool in payload.get("tools") or []
    ):
        return None
    return {"type": "function", "function": {"name": READER}}
