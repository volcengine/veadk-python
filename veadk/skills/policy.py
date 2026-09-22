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

"""Session-scoped filtering for remote Skill Space skills."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal


SKILL_SPACE_POLICY_ENV = "SKILL_SPACE_POLICY"
MAX_SKILL_SPACE_POLICY_BYTES = 8192


class SkillSpacePolicyError(ValueError):
    """Raised when ``SKILL_SPACE_POLICY`` is malformed."""


@dataclass(frozen=True)
class SkillSpacePolicy:
    mode: Literal["allow", "deny"]
    ids: frozenset[str]

    def allows(self, skill_id: str | None) -> bool:
        if not skill_id:
            return False
        selected = skill_id in self.ids
        return selected if self.mode == "allow" else not selected

    def to_json(self) -> str:
        return json.dumps(
            {"mode": self.mode, "ids": sorted(self.ids)},
            ensure_ascii=False,
            separators=(",", ":"),
        )


def parse_skill_space_policy(raw_value: str) -> SkillSpacePolicy:
    """Parse the only supported inline policy shape: ``mode`` plus ``ids``."""
    if len(raw_value.encode("utf-8")) > MAX_SKILL_SPACE_POLICY_BYTES:
        raise SkillSpacePolicyError(
            f"{SKILL_SPACE_POLICY_ENV} must not exceed "
            f"{MAX_SKILL_SPACE_POLICY_BYTES} bytes"
        )

    try:
        payload = json.loads(raw_value)
    except json.JSONDecodeError as exc:
        raise SkillSpacePolicyError(
            f"{SKILL_SPACE_POLICY_ENV} must be valid JSON"
        ) from exc

    if not isinstance(payload, dict):
        raise SkillSpacePolicyError(f"{SKILL_SPACE_POLICY_ENV} must be a JSON object")
    if set(payload) != {"mode", "ids"}:
        raise SkillSpacePolicyError(
            f"{SKILL_SPACE_POLICY_ENV} supports exactly 'mode' and 'ids'"
        )

    mode = payload["mode"]
    if mode not in {"allow", "deny"}:
        raise SkillSpacePolicyError(
            f"{SKILL_SPACE_POLICY_ENV}.mode must be 'allow' or 'deny'"
        )

    raw_ids = payload["ids"]
    if not isinstance(raw_ids, list):
        raise SkillSpacePolicyError(f"{SKILL_SPACE_POLICY_ENV}.ids must be a list")

    ids: set[str] = set()
    for skill_id in raw_ids:
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise SkillSpacePolicyError(
                f"{SKILL_SPACE_POLICY_ENV}.ids must contain non-empty strings"
            )
        if skill_id != skill_id.strip():
            raise SkillSpacePolicyError(
                f"{SKILL_SPACE_POLICY_ENV}.ids must not contain surrounding whitespace"
            )
        ids.add(skill_id)

    return SkillSpacePolicy(mode=mode, ids=frozenset(ids))
