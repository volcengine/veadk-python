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
"""Build the bounded state sent to the Decision API for query routing.

The builder reuses the content-safety media conversion (image/audio/video,
``file_id://`` inlining, 20 MiB and 32K-character limits) so routing and
auditing speak the same System One state format.
"""

from __future__ import annotations

from typing import Any

from veadk.content_safety.state import (
    MAX_STATE_CHARS,
    StateBuilder,
    _media_state_part,
    _parts_segments,
)

DEFAULT_MAX_TURNS = 6
_MEDIA_CHAR_COST = 4_000


class QueryStateBuilder(StateBuilder):
    """Build routing state from the recent conversation and media parts.

    Unlike the content-safety builder, which inspects only the latest user
    message, routing needs enough history to judge whether the request depends
    on a long context. The window is bounded by turn count and characters.
    """

    def __init__(
        self,
        *,
        max_chars: int = MAX_STATE_CHARS,
        max_turns: int = DEFAULT_MAX_TURNS,
        defuse: bool = True,
    ):
        super().__init__(max_chars=max_chars, defuse=defuse)
        self._max_turns = max(1, max_turns)

    def build_for_routing(self, llm_request: Any) -> list[dict[str, Any]]:
        contents = list(getattr(llm_request, "contents", None) or [])
        segments: list[str | dict[str, Any]] = []
        for content in contents[-self._max_turns :]:
            parts = _parts_segments(getattr(content, "parts", None) or [])
            if not parts:
                continue
            role = getattr(content, "role", None) or "user"
            segments.append(f"[{role}]")
            segments.extend(parts)
        return self._finalize_segments(segments)


def request_has_media(llm_request: Any) -> bool:
    """Return whether the request carries image, audio, video, or file input."""

    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            if _media_state_part(part) is not None:
                return True
    return False


def request_text_chars(llm_request: Any) -> int:
    """Approximate the request size in characters for the context gate."""

    total = 0
    for content in getattr(llm_request, "contents", None) or []:
        for part in getattr(content, "parts", None) or []:
            text = getattr(part, "text", None)
            if isinstance(text, str):
                total += len(text)
            elif _media_state_part(part) is not None:
                total += _MEDIA_CHAR_COST
    return total
