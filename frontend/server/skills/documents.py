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

"""Edit only SKILL.md while preserving every other archive member."""

import io
import zipfile
from pathlib import PurePosixPath

from .archive import validate_skill_archive
from .repository import SkillRepositoryError


def replace_skill_document(content: bytes, document: str) -> bytes:
    original = validate_skill_archive(content)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(content)) as source:
        names = [
            name
            for name in source.namelist()
            if PurePosixPath(name).parts[0] != "__MACOSX"
        ]
        path = next(
            (name for name in names if PurePosixPath(name).as_posix() == "SKILL.md"),
            None,
        )
        if path is None:
            path = next(
                name
                for name in names
                if len(PurePosixPath(name).parts) == 2
                and PurePosixPath(name).name == "SKILL.md"
            )
        with zipfile.ZipFile(output, "w") as target:
            for info in source.infolist():
                target.writestr(
                    info,
                    document.encode("utf-8")
                    if info.filename == path
                    else source.read(info),
                )
    result = output.getvalue()
    updated = validate_skill_archive(result)
    if updated.name != original.name:
        raise SkillRepositoryError(
            "SKILL_VERSION_NAME_MISMATCH", "新版本必须保留原技能名称", status_code=422
        )
    return result
