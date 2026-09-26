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

"""Select complete old turns without flattening ADK's Content/Part protocol."""

from __future__ import annotations

import hashlib
import json


def fingerprint(contents) -> str:
    value = [content.model_dump(mode="json", exclude_none=True) for content in contents]
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True).encode()
    ).hexdigest()


def is_user_turn(content) -> bool:
    return (
        content.role == "user"
        and any(
            part.text is not None and not part.thought for part in content.parts or []
        )
        and not any(part.function_response for part in content.parts or [])
    )


def complete_turn_ends(contents) -> list[int]:
    """Return prefix boundaries before user turns with no outstanding calls.

    Opaque/media/code-execution parts stop the eligible prefix. Missing IDs are
    supported only for unambiguous single calls of a given name.
    """
    pending: dict[str, str] = {}
    ends = []
    seen_user = False
    for index, content in enumerate(contents):
        if is_user_turn(content):
            if seen_user and not pending:
                ends.append(index)
            seen_user = True
        for part in content.parts or []:
            populated = part.model_dump(exclude_none=True)
            if any(
                key not in {"text", "function_call", "function_response", "thought"}
                for key in populated
            ):
                return ends
            if part.thought:
                return ends
            call = part.function_call
            result = part.function_response
            if call:
                key = call.id or "name:" + call.name
                if key in pending:
                    return ends
                pending[key] = call.name
            if result:
                key = result.id or "name:" + result.name
                if pending.get(key) != result.name or getattr(
                    result, "will_continue", False
                ):
                    return ends
                del pending[key]
    return ends


def eligible_prefix_end(contents, keep_recent_turns: int) -> int:
    user_starts = [i for i, content in enumerate(contents) if is_user_turn(content)]
    if len(user_starts) <= keep_recent_turns:
        return 0
    cutoff = user_starts[-keep_recent_turns]
    return max(
        (end for end in complete_turn_ends(contents) if end <= cutoff), default=0
    )
