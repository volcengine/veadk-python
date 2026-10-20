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

"""System SkillSpace definitions shared with the frontend."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class SystemSkillSpace:
    name: str
    label: str
    description: str
    marker: str
    visibility: str

    @property
    def managed_description(self) -> str:
        return f"{self.description} {self.marker}"


_definitions = json.loads(
    Path(__file__).with_suffix(".json").read_text(encoding="utf-8")
)
SHARE_SPACE = SystemSkillSpace(**_definitions["share"])
REVIEW_SPACE = SystemSkillSpace(**_definitions["review"])
SYSTEM_SKILL_SPACES = (SHARE_SPACE, REVIEW_SPACE)
RESERVED_SKILL_SPACE_NAMES = frozenset(space.name for space in SYSTEM_SKILL_SPACES)
SKILL_SPACE_DISPLAY_NAME_TAG = "display_name"
REVIEW_SOURCE_SPACE_TAG = "studio:review-source-space"
REVIEW_SOURCE_SKILL_TAG = "studio:review-source-skill"
REVIEW_SOURCE_VERSION_TAG = "studio:review-source-version"
REVIEW_SUBMITTED_AT_TAG = "studio:review-submitted-at"
REVIEW_SUBMITTER_ID_TAG = "studio:review-submitter-id"
REVIEW_SUBMITTER_OWNER_TAG = "studio:review-submitter-owner"
REVIEW_STATUS_TAG = "studio:review-status"
REVIEWED_AT_TAG = "studio:reviewed-at"
REVIEWED_BY_TAG = "studio:reviewed-by"
REVIEW_REASON_TAG = "studio:review-reason"
REVIEW_COMMENT_TAG = "studio:review-comment"
REVIEWER_ID_TAG = "studio:reviewer-id"
REVIEWER_OWNER_TAG = "studio:reviewer-owner"
REVIEW_APPROVAL_STARTED_TAG = "studio:review-approval-started"
REVIEW_SHARED_SKILL_TAG = "studio:review-shared-skill"
REVIEW_SHARED_SPACE_TAG = "studio:review-shared-space"
REVIEW_SHARED_VERSION_TAG = "studio:review-shared-version"
SHARED_REVIEW_TAG = "studio:shared-review"
SHARED_SOURCE_VERSION_TAG = "studio:shared-source-version"
SCORE_STATUS_TAG = "studio:score-status"
SCORE_TOTAL_TAG = "studio:score-total"
SCORE_TIME_TAG = "studio:score-time"
SCORE_MODEL_TAG = "studio:score-model"
SCORE_RUBRIC_TAG = "studio:score-rubric"
SCORE_BUCKET_TAG = "studio:score-bucket"
SCORE_KEY_TAG = "studio:score-key"
