"""Ephemeral source previews for the first opt-in, read-only lookup.

The normal projection remains the basis for admission and retrieval planning.
Only verified historical text may be shortened, and no preview enters Session.
"""

from __future__ import annotations

import copy
import json
from collections import Counter
from dataclasses import dataclass

from .references import handle, identity, resolve, saved_references
from .runtime import current_scope


@dataclass(frozen=True)
class LookupPreview:
    owner: tuple
    reference: str
    projection: str
    preview: str


def _text(content):
    if not content.parts or len(content.parts) != 1:
        return None
    part = content.parts[0]
    if set(part.model_dump(exclude_none=True)) != {"text"}:
        return None
    return part.text


def build_lookup_previews(scope, original, projected, end, reference, refs, config):
    """Bind previews to an exact archived prefix, never to markers in user text."""
    if (
        not config.verify_sources
        or scope.source_verification_attempted
        or scope.retrieval_calls
        or len(original) != len(projected)
    ):
        return ()
    source = refs.get(reference)
    if (
        not isinstance(source, dict)
        or source.get("kind") != "history"
        or handle(scope, source) != reference
    ):
        return ()
    records = [c.model_dump(mode="json", exclude_none=True) for c in original[:end]]
    if resolve(scope, source) != json.dumps(
        records, ensure_ascii=False, separators=(",", ":")
    ):
        return ()
    previews = []
    for index, (before, after) in enumerate(zip(original[:end], projected[:end])):
        text, projection = _text(before), _text(after)
        if (
            before.role != "user"
            or after.role != "user"
            or text is None
            or projection is None
            or text == projection
            or len(text.encode()) <= 2048
            or any(required in text for required in config.protected_context)
        ):
            continue
        opening = text.encode()[:256].decode(errors="ignore")
        preview = (
            f"[Source {reference}; history record {index}, part 0; "
            f"opening 0:{len(opening)}. More via veadk_read_context.]\n" + opening
        )
        if _smaller(preview, projection):
            previews.append(
                LookupPreview(identity(scope), reference, projection, preview)
            )
    return tuple(previews)


def _smaller(candidate, original):
    # Check both common serializers; escaped text must also be smaller.
    return all(
        len(json.dumps(candidate, ensure_ascii=ascii_only).encode())
        < len(json.dumps(original, ensure_ascii=ascii_only).encode())
        for ascii_only in (False, True)
    )


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from _strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from _strings(item)


def apply_lookup_previews(payload):
    """Called only after eligibility for one forced source lookup is established.

    Unknown or ambiguous wire shapes keep the normal projection. The caller
    still checks the complete final payload and claims its attempt normally.
    """
    scope = current_scope.get()
    if scope is None or not scope.lookup_previews:
        return payload
    messages = payload.get("messages")
    if not isinstance(messages, list) or not all(isinstance(m, dict) for m in messages):
        return payload
    user_indexes = [i for i, m in enumerate(messages) if m.get("role") == "user"]
    if not user_indexes:
        return payload
    counts = Counter(_strings(messages))
    refs = saved_references(scope)
    bindings = {}
    ambiguous = set()
    for entry in scope.lookup_previews:
        if entry.projection in bindings:
            ambiguous.add(entry.projection)
        if entry.owner == identity(scope) and entry.reference in refs:
            bindings[entry.projection] = entry.preview
    result = copy.deepcopy(messages)
    changed = False
    # The final user message is always protected, even if it equals old text.
    for index in user_indexes[:-1]:
        message = result[index]
        if set(message) - {"role", "content", "name"}:
            continue
        content = message.get("content")
        single_part = (
            isinstance(content, list)
            and len(content) == 1
            and isinstance(content[0], dict)
            and set(content[0]) == {"type", "text"}
            and content[0]["type"] == "text"
        )
        text = content[0]["text"] if single_part else content
        if (
            not isinstance(text, str)
            or text not in bindings
            or text in ambiguous
            or counts[text] != 1
            or not _smaller(bindings[text], text)
        ):
            continue
        if single_part:
            content[0]["text"] = bindings[text]
        else:
            message["content"] = bindings[text]
        changed = True
    if changed and _smaller(result, messages):
        return {**payload, "messages": result}
    return payload
