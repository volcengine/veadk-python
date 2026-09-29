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

import asyncio
import json

import pytest

from veadk.skills import utils
from veadk.skills import registry as registry_module
from veadk.skills.policy import (
    MAX_SKILL_SPACE_POLICY_BYTES,
    SkillSpacePolicyError,
    parse_skill_space_policy,
)
from veadk.skills.skill import Skill
from veadk.skills.registry import VeSkillRegistry


def _skill(skill_id: str | None, name: str) -> Skill:
    return Skill(
        id=skill_id,
        name=name,
        description=f"{name} description",
        path=f"skills/{name}.zip",
        skill_space_id="ss-test",
    )


@pytest.mark.parametrize(
    ("raw_value", "message"),
    [
        ('{"mode":"other","ids":[]}', "mode"),
        ('{"mode":"allow","ids":"skill-1"}', "ids must be a list"),
        ('{"mode":"allow","ids":[""]}', "non-empty strings"),
        ('{"mode":"allow","ids":[],"v":1}', "exactly 'mode' and 'ids'"),
        ('{"ref":"skill-policy-1"}', "exactly 'mode' and 'ids'"),
    ],
)
def test_parse_skill_space_policy_rejects_unsupported_shapes(raw_value, message):
    with pytest.raises(SkillSpacePolicyError, match=message):
        parse_skill_space_policy(raw_value)


def test_parse_skill_space_policy_rejects_values_over_create_session_limit():
    raw_value = "x" * (MAX_SKILL_SPACE_POLICY_BYTES + 1)

    with pytest.raises(SkillSpacePolicyError, match="must not exceed 8192 bytes"):
        parse_skill_space_policy(raw_value)


def test_policy_json_is_compact_and_deduplicated():
    policy = parse_skill_space_policy(
        '{"mode": "deny", "ids": ["skill-2", "skill-1", "skill-2"]}'
    )

    assert policy.to_json() == '{"mode":"deny","ids":["skill-1","skill-2"]}'


@pytest.mark.parametrize(
    ("mode", "ids", "expected"),
    [
        ("deny", ["skill-2"], ["skill-1"]),
        ("allow", ["skill-2"], ["skill-2"]),
        ("deny", [], ["skill-1", "skill-2"]),
        ("allow", [], []),
    ],
)
def test_load_skills_from_cloud_applies_policy(
    monkeypatch: pytest.MonkeyPatch,
    mode: str,
    ids: list[str],
    expected: list[str],
):
    monkeypatch.setenv(
        "SKILL_SPACE_POLICY",
        json.dumps({"mode": mode, "ids": ids}),
    )
    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        lambda _space_id, *, raise_on_error=False: [
            _skill("skill-1", "one"),
            _skill("skill-2", "two"),
        ],
    )

    skills = utils.load_skills_from_cloud("ss-test")

    assert [skill.id for skill in skills] == expected


def test_missing_policy_keeps_all_remote_skills(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("SKILL_SPACE_POLICY", raising=False)
    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        lambda _space_id, *, raise_on_error=False: [
            _skill("skill-1", "one"),
            _skill("skill-2", "two"),
        ],
    )

    skills = utils.load_skills_from_cloud("ss-test")

    assert [skill.id for skill in skills] == ["skill-1", "skill-2"]


def test_policy_excludes_remote_skills_without_stable_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "SKILL_SPACE_POLICY",
        '{"mode":"deny","ids":[]}',
    )
    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        lambda _space_id, *, raise_on_error=False: [_skill(None, "missing-id")],
    )

    assert utils.load_skills_from_cloud("ss-test") == []


def test_invalid_policy_disables_remote_skills_without_listing_space(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SKILL_SPACE_POLICY", '{"mode":"allow","ids":[],"v":1}')
    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        lambda *_args, **_kwargs: pytest.fail("invalid policy must fail closed"),
    )

    assert utils.load_skills_from_cloud("ss-test") == []


def test_registry_get_skill_cannot_bypass_deny_policy(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv(
        "SKILL_SPACE_POLICY",
        '{"mode":"deny","ids":["skill-1"]}',
    )
    monkeypatch.setattr(
        utils,
        "_load_skills_from_space_id",
        lambda _space_id, *, raise_on_error=False: [_skill("skill-1", "one")],
    )
    monkeypatch.setattr(
        registry_module,
        "materialize_remote_skill",
        lambda *_args, **_kwargs: pytest.fail("denied Skill must not be downloaded"),
    )

    registry = VeSkillRegistry(skill_source_id="ss-test")

    with pytest.raises(ValueError, match="not found"):
        asyncio.run(registry.get_skill(name="one"))
