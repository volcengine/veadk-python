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


@dataclass(frozen=True)
class SkillSpacePolicySet:
    global_policy: SkillSpacePolicy | None = None
    space_policies: dict[str, SkillSpacePolicy] | None = None

    def allows(self, skill_id: str | None, skill_space_id: str | None = None) -> bool:
        if self.global_policy is not None:
            return self.global_policy.allows(skill_id)
        if not self.space_policies or not skill_space_id:
            return True
        policy = self.space_policies.get(skill_space_id)
        if policy is None:
            return True
        return policy.allows(skill_id)

    def to_json(self) -> str:
        if self.global_policy is not None:
            return self.global_policy.to_json()
        spaces = self.space_policies or {}
        return json.dumps(
            {
                "spaces": {
                    space_id: {
                        "mode": policy.mode,
                        "ids": sorted(policy.ids),
                    }
                    for space_id, policy in sorted(spaces.items())
                }
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )


def _parse_inline_policy(payload: object, path: str) -> SkillSpacePolicy:
    if not isinstance(payload, dict):
        raise SkillSpacePolicyError(f"{path} must be a JSON object")
    if set(payload) != {"mode", "ids"}:
        raise SkillSpacePolicyError(f"{path} supports exactly 'mode' and 'ids'")

    mode = payload["mode"]
    if mode not in {"allow", "deny"}:
        raise SkillSpacePolicyError(f"{path}.mode must be 'allow' or 'deny'")

    raw_ids = payload["ids"]
    if not isinstance(raw_ids, list):
        raise SkillSpacePolicyError(f"{path}.ids must be a list")

    ids: set[str] = set()
    for skill_id in raw_ids:
        if not isinstance(skill_id, str) or not skill_id.strip():
            raise SkillSpacePolicyError(f"{path}.ids must contain non-empty strings")
        if skill_id != skill_id.strip():
            raise SkillSpacePolicyError(
                f"{path}.ids must not contain surrounding whitespace"
            )
        ids.add(skill_id)

    return SkillSpacePolicy(mode=mode, ids=frozenset(ids))


def parse_skill_space_policy(raw_value: str) -> SkillSpacePolicySet:
    """Parse global or per-space remote Skill Space filtering policy."""
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

    if set(payload) == {"mode", "ids"}:
        return SkillSpacePolicySet(
            global_policy=_parse_inline_policy(payload, SKILL_SPACE_POLICY_ENV)
        )

    if set(payload) == {"spaces"}:
        raw_spaces = payload["spaces"]
        if not isinstance(raw_spaces, dict):
            raise SkillSpacePolicyError(
                f"{SKILL_SPACE_POLICY_ENV}.spaces must be a JSON object"
            )
        spaces: dict[str, SkillSpacePolicy] = {}
        for space_id, raw_policy in raw_spaces.items():
            if not isinstance(space_id, str) or not space_id.strip():
                raise SkillSpacePolicyError(
                    f"{SKILL_SPACE_POLICY_ENV}.spaces keys must be non-empty strings"
                )
            if space_id != space_id.strip():
                raise SkillSpacePolicyError(
                    f"{SKILL_SPACE_POLICY_ENV}.spaces keys must not contain "
                    "surrounding whitespace"
                )
            spaces[space_id] = _parse_inline_policy(
                raw_policy,
                f"{SKILL_SPACE_POLICY_ENV}.spaces.{space_id}",
            )
        return SkillSpacePolicySet(space_policies=spaces)

    raise SkillSpacePolicyError(
        f"{SKILL_SPACE_POLICY_ENV} supports exactly 'mode' and 'ids', "
        "or exactly 'spaces'"
    )
