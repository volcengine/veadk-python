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

"""Mutate Skill user tags through the AgentKit resource tagging APIs."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from .repository import SkillRepositoryError
from .consts import REVIEW_APPROVAL_STARTED_TAG, REVIEW_STATUS_TAG, SCORE_STATUS_TAG


class _Tag(BaseModel):
    key: str = Field(alias="Key")
    value: str = Field(alias="Value")


class _Resources(BaseModel):
    resource_type: Literal["skill"] = Field(default="skill", alias="ResourceType")
    resource_ids: list[str] = Field(alias="ResourceIds")


class _TagResources(_Resources):
    tags: list[_Tag] = Field(alias="Tags")


class _TagResult(BaseModel):
    pass


def _mutate(client: Any, action: str, body: BaseModel) -> None:
    from volcengine.ApiInfo import ApiInfo

    # Tag APIs are available online but absent from the current Skills SDK
    client.api_info.setdefault(
        action,
        ApiInfo("POST", "/", {"Action": action, "Version": "2025-10-30"}, {}, {}),
    )
    client._invoke_api(api_action=action, request=body, response_type=_TagResult)


def update_skill_tags(client: Any, skill_id: str, tags: dict[str, str]) -> None:
    from agentkit.sdk.skills import types as sdk

    def read() -> dict[str, str]:
        skill = client.get_skill(sdk.GetSkillRequest(Id=skill_id))
        return {tag.key: tag.value for tag in skill.tags or []}

    previous = read()
    changed = {key: value for key, value in tags.items() if previous.get(key) != value}
    if not changed:
        return
    # Write transition markers last if a long comment requires several requests
    items = sorted(
        changed.items(),
        key=lambda item: (
            item[0]
            in {REVIEW_STATUS_TAG, REVIEW_APPROVAL_STARTED_TAG, SCORE_STATUS_TAG}
        ),
    )
    for start in range(0, len(items), 20):
        _mutate(
            client,
            "TagResources",
            _TagResources(
                ResourceIds=[skill_id],
                Tags=[
                    _Tag(Key=key, Value=value)
                    for key, value in items[start : start + 20]
                ],
            ),
        )
    actual = read()
    if any(actual.get(key) != value for key, value in tags.items()):
        raise SkillRepositoryError(
            "SKILL_REVIEW_TAG_WRITE_FAILED",
            "审批标签尚未保存成功，请刷新后重试",
            status_code=502,
            retryable=True,
        )
