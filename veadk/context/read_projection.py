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

"""Losslessly share read-page ranges within one model input and user turn."""

import json
from collections import Counter

from .history import is_user_turn
from .references import resolve

_FIELDS = {
    "text",
    "offset",
    "end",
    "next_offset",
    "total_characters",
    "complete",
    "reference",
    "source_sha256",
    "remaining_calls",
    "repeated",
    "guidance",
}
_GUIDANCE = (
    "segments partition offset:end; included_in_response points to literal text "
    "at the same offsets in that response, not another alias."
)


def _size(value):
    return len(json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode())


def _segments(value, included):
    """Return a partition; aliases only target literal, already included ranges."""
    start, end = value["offset"], value["end"]
    cursor = start
    result = []
    for left, right, identifier in sorted(included):
        left, right = max(left, cursor), min(right, end)
        if left >= right:
            continue
        if cursor < left:
            result.append(
                {
                    "offset": cursor,
                    "end": left,
                    "text": value["text"][cursor - start : left - start],
                }
            )
        result.append(
            {"offset": left, "end": right, "included_in_response": identifier}
        )
        cursor = right
    if cursor < end:
        result.append(
            {"offset": cursor, "end": end, "text": value["text"][cursor - start :]}
        )
    return result


def compact_pages(contents, groups, scope, references, config, original_response):
    identifiers = Counter(
        p.function_response.id
        for c in contents
        for p in c.parts or []
        if p.function_response
    )
    completed_turns = set()
    turn_index = 0
    last_answered = None
    for content in contents:
        if is_user_turn(content):
            if last_answered == turn_index:
                completed_turns.add(turn_index)
            turn_index += 1
        elif any(p.function_call or p.function_response for p in content.parts or []):
            last_answered = None
        elif content.role == "model" and not any(
            p.function_call for p in content.parts or []
        ):
            if any(p.text and not p.thought for p in content.parts or []):
                last_answered = turn_index
    sources = {}
    included = {}
    # Newest group is immutable. Walk backwards so every alias target already
    # has its final form and contains literal text, preventing alias chains.
    for group_index in range(len(groups) - 1, -1, -1):
        turn, group = groups[group_index]
        for response in reversed(group):
            value = response.response
            if not isinstance(value, dict) or set(value) - _FIELDS:
                continue
            reference = value.get("reference")
            source = references.get(reference) if isinstance(reference, str) else None
            if (
                not source
                or value.get("source_sha256") != source.get("text_hash")
                or not response.id
                or identifiers[response.id] != 1
                or not isinstance(value.get("text"), str)
                or type(value.get("offset")) is not int
                or type(value.get("end")) is not int
                or value["offset"] < 0
                or value["end"] - value["offset"] != len(value["text"])
                or len(value["text"].encode()) > config.retrieval_max_bytes
                or any(
                    s in value["text"] or s in json.dumps(value, ensure_ascii=False)
                    for s in config.protected_context
                )
                or not original_response(scope, response)
            ):
                continue
            if reference not in sources:
                sources[reference] = resolve(scope, source)
            text = sources[reference]
            if (
                text is None
                or value["end"] > len(text)
                or text[value["offset"] : value["end"]] != value["text"]
            ):
                continue
            if turn in completed_turns:
                response.response = {
                    k: value[k] for k in ("reference", "source_sha256", "offset", "end")
                }
                response.response.update(
                    text=value["text"].encode()[:256].decode(errors="ignore"),
                    complete=False,
                    archived=True,
                    guidance="An answered previous turn read this range. Re-read the exact source by reference and offset if needed.",
                )
                continue
            key = (turn, reference, value["source_sha256"])
            ranges = included.setdefault(key, [])
            segments = _segments(value, ranges)
            compacted = {
                k: value[k] for k in ("reference", "source_sha256", "offset", "end")
            }
            compacted["complete"] = False
            if len(segments) == 1 and "included_in_response" in segments[0]:
                compacted["included_in_response"] = segments[0]["included_in_response"]
            else:
                compacted["segments"] = segments
            compacted["guidance"] = _GUIDANCE
            compacted["archived"] = True
            if group_index < len(groups) - 1 and _size(compacted) < _size(value):
                response.response = compacted
                ranges.extend(
                    (s["offset"], s["end"], response.id)
                    for s in segments
                    if "text" in s
                )
            else:
                ranges.append((value["offset"], value["end"], response.id))
                if group_index < len(groups) - 1:
                    response.response = {
                        k: value[k]
                        for k in ("reference", "source_sha256", "offset", "end", "text")
                    }
                    response.response.update(complete=False, archived=True)
