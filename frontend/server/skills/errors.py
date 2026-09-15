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

"""Preserve upstream errors when crossing the Studio API boundary."""

from __future__ import annotations

from .repository import SkillRepositoryError
from .storage import SkillPublishStorageError


def original_skill_error(error: BaseException) -> BaseException:
    while True:
        original = None
        if isinstance(error, SkillRepositoryError):
            original = error.original_error
        elif isinstance(error, SkillPublishStorageError):
            original = error.__cause__
        if original is None or original is error:
            return error
        error = original


def skill_error_text(error: BaseException) -> str:
    original = original_skill_error(error)
    return str(original) or repr(original)
