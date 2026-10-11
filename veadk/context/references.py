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

"""Session-scoped, hash-checked references; original events are the only store."""

from __future__ import annotations

import hashlib
import json


def identity(scope):
    return (
        scope.session.app_name,
        scope.session.user_id,
        scope.session.id,
        scope.agent_name,
        scope.branch,
    )


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def state_key(scope):
    return "veadk:references:" + digest(identity(scope))[:24]


def saved_references(scope):
    if scope is None:
        return {}
    key = state_key(scope)
    refs = {}
    # Event deltas also preserve references across last-writer-wins state races.
    for event in scope.session.events:
        values = event.actions.state_delta.get(key, {})
        if isinstance(values, dict):
            refs.update(values)
    for state in (scope.session.state, scope.pending_state):
        values = state.get(key, {})
        if isinstance(values, dict):
            refs.update(values)
    return {
        ref: source
        for ref, source in refs.items()
        if isinstance(source, dict) and ref == handle(scope, source)
    }


def handle(scope, source):
    return "ctx_" + digest([identity(scope), source])[:24]


def register(scope, refs, source, *, persist=True):
    ref = handle(scope, source)
    refs[ref] = source
    # Persist metadata only; never duplicate original content in Session state.
    if persist:
        scope.pending_state[state_key(scope)] = dict(refs)
    return ref


def resolve(scope, source):
    from .source_context import checked_metadata

    events = {event.id: event for event in scope.session.events}
    positions = {event.id: i for i, event in enumerate(scope.session.events)}
    if source.get("kind") == "history":
        records = []
        for descriptor in source.get("events", []):
            event = events.get(descriptor["id"])
            if (
                event is None
                or event.content is None
                or event.author not in {"user", scope.agent_name}
                or (event.branch or "") not in {"", scope.branch}
            ):
                return None
            value = event.content.model_dump(mode="json", exclude_none=True)
            if digest(value) != descriptor["hash"]:
                return None
            try:
                context = checked_metadata(scope, event, positions)
            except (ValueError, TypeError, KeyError):
                return None
            if descriptor.get("context_hash") != (
                digest(context) if context is not None else None
            ):
                return None
            records.append(value)
        text = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    else:
        event = events.get(source.get("event_id"))
        if (
            event is None
            or event.author != scope.agent_name
            or (event.branch or "") != scope.branch
            or event.content is None
        ):
            return None
        try:
            response = event.content.parts[source["part"]].function_response
            if response.name != source.get(
                "tool", response.name
            ) or response.id != source.get("call_id", response.id):
                return None
            text = response.response
            for key in source.get("path", [source.get("field")]):
                text = text[key]
        except (KeyError, IndexError, TypeError, AttributeError):
            return None
    if not isinstance(text, str) or digest(text) != source.get("text_hash"):
        return None
    return text


def archive_history(scope, contents, refs):
    """Register only the exact prefix actually provided to this Agent."""
    from .source_context import checked_metadata

    if scope is None or not contents:
        return None
    candidates = iter(scope.session.events)
    positions = {event.id: i for i, event in enumerate(scope.session.events)}
    descriptors, records = [], []
    for content in contents:
        value = content.model_dump(mode="json", exclude_none=True)
        for event in candidates:
            if (
                event.content is not None
                and event.author in {"user", scope.agent_name}
                and (event.branch or "") in {"", scope.branch}
                and event.content.model_dump(mode="json", exclude_none=True) == value
            ):
                descriptor = {"id": event.id, "hash": digest(value)}
                try:
                    context = checked_metadata(scope, event, positions)
                except (ValueError, TypeError, KeyError):
                    return None
                if context is not None:
                    descriptor["context_hash"] = digest(context)
                descriptors.append(descriptor)
                records.append(value)
                break
        else:
            return None
    text = json.dumps(records, ensure_ascii=False, separators=(",", ":"))
    return register(
        scope,
        refs,
        {"kind": "history", "events": descriptors, "text_hash": digest(text)},
        persist=False,
    )
