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

"""Keep user-facing SkillSpace names separate from cloud lookup names."""

from typing import Any

from .consts import SKILL_SPACE_DISPLAY_NAME_TAG


def skill_space_display_name(space: Any) -> str:
    for tag in getattr(space, "tags", None) or []:
        if getattr(tag, "key", "") == SKILL_SPACE_DISPLAY_NAME_TAG:
            display_name = str(getattr(tag, "value", "") or "").strip()
            if display_name:
                return display_name
    return str(getattr(space, "name", "") or "")
