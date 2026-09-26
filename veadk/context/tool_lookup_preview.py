"""One-attempt tool previews bound to verified native responses and call IDs.

These wire-only projections never enter Session or increase retrieval credit.
The normal evidence projection is used again after the forced lookup attempt.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass

from .evidence import current_question, evidence_ranges
from .references import digest, handle, identity, resolve, saved_references
from .runtime import current_scope
from .search_budget import contains_protected
from .verification_preview import _smaller


@dataclass(frozen=True)
class ToolLookupPreview:
    owner: tuple
    call_id: str
    tool_name: str
    normal_hash: str
    preview_json: str
    references: tuple[str, ...]


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("ambiguous_json_object")
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError("nonfinite_json_value")


def _decode(value):
    return json.loads(
        value, object_pairs_hook=_unique_object, parse_constant=_invalid_constant
    )


def _question_preview(text, question, opening_preview):
    """Add small verbatim clues for lookup planning without rereading tools.

    The source opening and source identity remain intact. Character positions
    refer to original Unicode text; encoded byte caps also include JSON labels.
    This is evidence for formulating a query, not a claim of complete coverage.
    """
    opening_end = len(text.encode()[:256].decode(errors="ignore"))
    ranges = []
    previous_end = opening_end
    for match in evidence_ranges(
        text, question, 1024, max_ranges=2, focus_truncated=True
    ):
        start, end = max(previous_end, match["offset"]), match["end"]
        if start >= end:
            continue
        ranges.append({"offset": start, "end": end, "text": text[start:end]})
        previous_end = end
    if not ranges:
        return opening_preview
    value = (
        opening_preview
        + "\n[Question-related original excerpts]\n"
        + json.dumps(ranges, ensure_ascii=False, separators=(",", ":"))
    )
    return value if len(value.encode()) <= 2048 else opening_preview


def build_tool_lookup_previews(scope, contents, refs, config):
    if (
        scope is None
        or not config.verify_sources
        or scope.source_verification_attempted
        or scope.retrieval_calls
    ):
        return ()
    responses = [
        part.function_response
        for content in contents
        for part in content.parts or []
        if part.function_response
    ]
    counts = Counter(response.id for response in responses)
    question = current_question(contents)
    entries = []
    for response in responses:
        if (
            not response.id
            or counts[response.id] != 1
            or response.name == "veadk_read_context"
            or not isinstance(response.response, dict)
        ):
            continue
        value = response.response
        try:
            if contains_protected(value, config.protected_context):
                continue
            # Validate the same JSON domain as the wire decoder, including
            # key uniqueness and finite values, before creating a binding.
            _decode(json.dumps(value, ensure_ascii=False, allow_nan=False))
            normal_hash = digest(value)
            preview = copy.deepcopy(value)
            references = []
            for reference, source in refs.items():
                if (
                    reference not in scope.lossy_references
                    or reference in scope.restored_references
                    or source.get("kind") == "history"
                    or source.get("call_id") != response.id
                    or source.get("tool") != response.name
                    or handle(scope, source) != reference
                ):
                    continue
                text = resolve(scope, source)
                if text is None or len(text.encode()) <= 2048:
                    continue
                path = source.get("path")
                if not isinstance(path, list) or not path:
                    continue
                parent = preview
                for key in path[:-1]:
                    parent = parent[key]
                field = path[-1]
                projected = parent[field]
                if not isinstance(projected, str) or reference not in projected:
                    continue
                opening = text.encode()[:256].decode(errors="ignore")
                short = (
                    f"[Source {reference}; original {len(text)} characters; "
                    f"opening 0:{len(opening)}. More via veadk_read_context.]\n"
                    + opening
                )
                enriched = _question_preview(text, question, short)
                if _smaller(enriched, projected):
                    short = enriched
                if _smaller(short, projected):
                    parent[field] = short
                    references.append(reference)
            if references and _smaller(preview, value):
                entries.append(
                    ToolLookupPreview(
                        identity(scope),
                        response.id,
                        response.name,
                        normal_hash,
                        json.dumps(
                            preview,
                            ensure_ascii=False,
                            separators=(",", ":"),
                            allow_nan=False,
                        ),
                        tuple(references),
                    )
                )
        except (ValueError, TypeError, KeyError, IndexError, RecursionError):
            # Unknown application data retains the normal, guarded request.
            continue
    return tuple(entries)


def apply_tool_lookup_previews(payload: dict) -> dict:
    scope = current_scope.get()
    if (
        scope is None
        or scope.source_verification_attempted
        or scope.retrieval_calls
        or not scope.tool_lookup_previews
    ):
        return payload
    messages = payload.get("messages")
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        return payload
    counts = Counter(
        message.get("tool_call_id")
        for message in messages
        if message.get("role") == "tool"
        and isinstance(message.get("tool_call_id"), str)
    )
    calls = {}
    for index, message in enumerate(messages):
        if message.get("role") != "assistant":
            continue
        tool_calls = message.get("tool_calls")
        if tool_calls is None:
            continue
        if not isinstance(tool_calls, list) or not all(
            isinstance(call, dict) for call in tool_calls
        ):
            return payload
        for call in tool_calls:
            if isinstance(call.get("id"), str):
                calls.setdefault(call["id"], []).append((index, call))
    bindings = {}
    for entry in scope.tool_lookup_previews:
        bindings.setdefault(entry.call_id, []).append(entry)
    refs = saved_references(scope)
    result = copy.deepcopy(messages)
    changed = False
    for index, message in enumerate(result):
        call_id = message.get("tool_call_id")
        if (
            message.get("role") != "tool"
            or set(message) - {"role", "content", "tool_call_id", "name"}
            or not isinstance(call_id, str)
            or counts[call_id] != 1
            or len(bindings.get(call_id, [])) != 1
            or len(calls.get(call_id, [])) != 1
            or not isinstance(message.get("content"), str)
        ):
            continue
        entry = bindings[call_id][0]
        call_index, call = calls[call_id][0]
        function = call.get("function")
        if (
            call_index >= index
            or call.get("type") != "function"
            or not isinstance(function, dict)
            or function.get("name") != entry.tool_name
            or message.get("name", entry.tool_name) != entry.tool_name
            or entry.owner != identity(scope)
            or any(
                reference not in refs
                or reference not in scope.lossy_references
                or reference in scope.restored_references
                or resolve(scope, refs[reference]) is None
                for reference in entry.references
            )
        ):
            continue
        try:
            normal = _decode(message["content"])
            if not isinstance(normal, dict) or digest(normal) != entry.normal_hash:
                continue
            if _smaller(entry.preview_json, message["content"]):
                message["content"] = entry.preview_json
                changed = True
        except (ValueError, TypeError, RecursionError):
            continue
    if changed and _smaller(result, messages):
        return {**payload, "messages": result}
    return payload
