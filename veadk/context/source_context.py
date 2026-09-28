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

"""Keep host-declared source context with verbatim historical excerpts.

Applications may bind an imported message to earlier, short original records
(for example its conversation date or document heading) before persistence.
Bindings are selection metadata, never evidence of truth or authorization.
Do not copy this reserved namespace from LLM output or untrusted imports.
"""

from __future__ import annotations

import copy

from .references import digest, identity
from .runtime import ContextScope

METADATA_KEY = "veadk:source_context:v1"
MAX_CONTEXTS = 4
MAX_CONTEXT_BYTES = 2048


def _value(event):
    content = event.content
    if (
        content is None
        or content.role not in {"user", "model"}
        or not content.parts
        or any(
            p.text is None or set(p.model_dump(exclude_none=True)) != {"text"}
            for p in content.parts
        )
    ):
        raise ValueError("source_context_requires_plain_original_records")
    return content.model_dump(mode="json", exclude_none=True)


def _allowed(scope, event):
    return event.author in {"user", scope.agent_name} and (event.branch or "") in {
        "",
        scope.branch,
    }


def metadata(event):
    values = getattr(event, "custom_metadata", None)
    return values.get(METADATA_KEY) if isinstance(values, dict) else None


def checked_metadata(scope, event, positions=None):
    """Validate all dependencies against this Session; return a detached value."""
    value = metadata(event)
    if value is None:
        return None
    if (
        not isinstance(value, dict)
        or set(value) != {"version", "identity", "event_id", "event_hash", "contexts"}
        or type(value["version"]) is not int
        or value["version"] != 1
        or value["identity"] != digest(identity(scope))
        or not _allowed(scope, event)
        or value["event_id"] != event.id
        or value["event_hash"] != digest(_value(event))
    ):
        raise ValueError("invalid_source_context_binding")
    contexts = value["contexts"]
    if not isinstance(contexts, list) or not 1 <= len(contexts) <= MAX_CONTEXTS:
        raise ValueError("invalid_source_context_count")
    events = scope.session.events
    if positions is None:
        positions = {item.id: i for i, item in enumerate(events)}
    if len(positions) != len(events):
        raise ValueError("ambiguous_source_event_identity")
    owner_index = positions.get(event.id, len(events))
    if (
        owner_index < len(events)
        and digest(_value(events[owner_index])) != value["event_hash"]
    ):
        raise ValueError("source_owner_changed")
    seen, size = set(), 0
    for context in contexts:
        if (
            not isinstance(context, dict)
            or set(context) != {"id", "hash"}
            or not isinstance(context["id"], str)
            or context["id"] in seen
            or not isinstance(context["hash"], str)
        ):
            raise ValueError("invalid_source_context_descriptor")
        index = positions.get(context["id"])
        if index is None or index >= owner_index:
            raise ValueError("source_context_must_precede_message")
        target = events[index]
        if not _allowed(scope, target) or metadata(target) is not None:
            raise ValueError("source_context_scope_or_chain_invalid")
        if digest(_value(target)) != context["hash"]:
            raise ValueError("source_context_changed")
        size += sum(len(p.text.encode("utf-8")) for p in target.content.parts)
        if size > MAX_CONTEXT_BYTES:
            raise ValueError("source_context_too_large")
        seen.add(context["id"])
    return copy.deepcopy(value)


def bind_history_context(event, *, session, agent_name, context_event_ids, branch=""):
    """Return an Event copy bound to existing context, before append_event().

    Importers obtain IDs from structured source groups, not by parsing arbitrary
    message text. SQLite stores the ordinary Event.custom_metadata unchanged.
    Existing persisted Events are never modified by this function.
    """
    if any(item.id == event.id for item in session.events):
        raise ValueError("bind_before_persisting_event")
    ids = tuple(context_event_ids)
    if not 1 <= len(ids) <= MAX_CONTEXTS or any(not isinstance(i, str) for i in ids):
        raise ValueError("invalid_source_context_count")
    events = {item.id: item for item in session.events}
    if any(i not in events for i in ids):
        raise ValueError("source_context_not_in_session")
    scope = ContextScope(session=session, agent_name=agent_name, branch=branch)
    updated = event.model_copy(deep=True)
    values = dict(updated.custom_metadata or {})
    values[METADATA_KEY] = {
        "version": 1,
        "identity": digest(identity(scope)),
        "event_id": event.id,
        "event_hash": digest(_value(event)),
        "contexts": [{"id": i, "hash": digest(_value(events[i]))} for i in ids],
    }
    updated.custom_metadata = values
    checked_metadata(scope, updated)
    return updated


def context_links(scope, source):
    """Resolve dependencies only within this exact authorized archived prefix."""
    events = {item.id: item for item in scope.session.events}
    session_positions = {item.id: i for i, item in enumerate(scope.session.events)}
    descriptors = source["events"]
    positions = {item["id"]: i for i, item in enumerate(descriptors)}
    if len(positions) != len(descriptors):
        raise ValueError("ambiguous_archive_identity")
    links = {}
    for index, descriptor in enumerate(descriptors):
        event = events.get(descriptor["id"])
        if event is None:
            raise ValueError("source_event_missing")
        value = checked_metadata(scope, event, session_positions)
        expected = digest(value) if value is not None else None
        if descriptor.get("context_hash") != expected:
            raise ValueError("source_context_binding_changed")
        if value is not None:
            targets = []
            for context in value["contexts"]:
                target = positions.get(context["id"])
                if target is None or target >= index:
                    raise ValueError("source_context_outside_archive")
                targets.append(target)
            links[index] = tuple(targets)
    return links


def with_context(contents, regions, links):
    """Add complete required records before admission; never trim dependencies."""
    result = list(regions)
    for index in sorted({r[0] for r in regions}):
        for target in links.get(index, ()):
            result.extend(
                (target, p, 0, len(part.text))
                for p, part in enumerate(contents[target].parts)
                if part.text
            )
    return result


def render_block(contents, region, links):
    index, part, start, end = region
    targets = links.get(index, ())
    context = (
        ", source context messages " + ",".join(map(str, targets)) if targets else ""
    )
    return (
        f"[message {index}, role {contents[index].role}, part {part}, "
        f"characters {start}:{end}{context}]\n"
        + contents[index].parts[part].text[start:end]
    )
