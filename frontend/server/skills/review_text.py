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

"""Keep review text lossless within cloud tag character and length limits."""

from __future__ import annotations

import base64
import binascii

from .repository import SkillRepositoryError

_PREFIX = "b64v1:"
_CHUNK_SIZE = 240


def encode_review_text(key: str, value: str) -> dict[str, str]:
    if not value:
        return {key: ""}
    encoded = base64.urlsafe_b64encode(value.encode("utf-8")).decode("ascii")
    chunks = [encoded[i : i + _CHUNK_SIZE] for i in range(0, len(encoded), _CHUNK_SIZE)]
    return {
        key: f"{_PREFIX}{len(chunks)}:{chunks[0]}",
        **{f"{key}.{i}": chunk for i, chunk in enumerate(chunks[1:], start=1)},
    }


def decode_review_text(tags: dict[str, str], key: str) -> str:
    value = tags.get(key, "")
    if not value.startswith(_PREFIX):
        return value
    try:
        _, count, first = value.split(":", 2)
        size = int(count)
        if not 1 <= size <= 20:
            raise ValueError("Invalid review text chunk count")
        encoded = first + "".join(tags[f"{key}.{i}"] for i in range(1, size))
        return base64.b64decode(encoded, altchars=b"-_", validate=True).decode("utf-8")
    except (ValueError, KeyError, binascii.Error) as exc:
        raise SkillRepositoryError(
            "SKILL_REVIEW_TEXT_UNAVAILABLE",
            "审核记录暂未完整读取，请刷新重试",
            status_code=502,
            retryable=True,
        ) from exc
