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

"""Secure Skill ZIP validation."""

from __future__ import annotations

import hashlib
import io
import stat
import zipfile
from pathlib import PurePosixPath

from .frontmatter import SkillFrontmatterError, parse_skill_frontmatter

MAX_ARCHIVE_BYTES = 20 * 1024 * 1024
MAX_EXPANDED_BYTES = 20 * 1024 * 1024
MAX_FILES = 100
MAX_PATH_LENGTH = 512


class SkillArchiveError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 422) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code

    def detail(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "retryable": False}


class SkillArchive:
    def __init__(
        self,
        *,
        content: bytes,
        name: str,
        description: str,
        files: list[dict[str, object]],
        skill_md: str,
    ) -> None:
        self.content = content
        self.name = name
        self.description = description
        self.files = files
        self.skill_md = skill_md
        self.sha256 = hashlib.sha256(content).hexdigest()


def _frontmatter(value: str) -> tuple[str, str]:
    try:
        return parse_skill_frontmatter(value)
    except SkillFrontmatterError as error:
        raise SkillArchiveError(error.code, str(error)) from error


def validate_skill_archive(content: bytes) -> SkillArchive:
    if not content:
        raise SkillArchiveError("SKILL_ARCHIVE_EMPTY", "Skill ZIP 不能为空。")
    if len(content) > MAX_ARCHIVE_BYTES:
        raise SkillArchiveError(
            "SKILL_ARCHIVE_TOO_LARGE",
            "Skill ZIP 不能超过 20 MiB。",
            status_code=413,
        )
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            if not infos:
                raise SkillArchiveError("SKILL_ARCHIVE_EMPTY", "Skill ZIP 不能为空。")
            files: dict[str, zipfile.ZipInfo] = {}
            total = 0
            for info in infos:
                raw = info.filename
                path = PurePosixPath(raw)
                normalized = path.as_posix()
                if (
                    not path.parts
                    or path.is_absolute()
                    or "\\" in raw
                    or ".." in path.parts
                    or len(normalized) > MAX_PATH_LENGTH
                ):
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_UNSAFE_PATH",
                        f"Skill ZIP 包含不安全路径：{raw}",
                    )
                folded = normalized.casefold()
                if folded in {item.casefold() for item in files}:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_DUPLICATE_PATH",
                        f"Skill ZIP 包含重复路径：{raw}",
                    )
                mode = info.external_attr >> 16
                file_type = stat.S_IFMT(mode)
                if file_type == stat.S_IFLNK:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_SYMLINK",
                        f"Skill ZIP 不允许符号链接：{raw}",
                    )
                if file_type not in {0, stat.S_IFREG, stat.S_IFDIR}:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_SPECIAL_FILE",
                        f"Skill ZIP 不允许特殊文件：{raw}",
                    )
                if info.is_dir():
                    continue
                files[normalized] = info
                total += info.file_size
                if len(files) > MAX_FILES:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_FILE_COUNT",
                        "Skill 文件数不能超过 100 个。",
                        status_code=413,
                    )
                if total > MAX_EXPANDED_BYTES:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_EXPANDED_TOO_LARGE",
                        "Skill 解压后不能超过 20 MiB。",
                        status_code=413,
                    )
                if info.compress_size and info.file_size / info.compress_size > 200:
                    raise SkillArchiveError(
                        "SKILL_ARCHIVE_SUSPICIOUS_COMPRESSION",
                        f"文件压缩率异常：{raw}",
                        status_code=413,
                    )
            if not files:
                raise SkillArchiveError("SKILL_ARCHIVE_EMPTY", "Skill ZIP 不能为空。")
            wrapper = ""
            if "SKILL.md" not in files:
                roots = {PurePosixPath(path).parts[0] for path in files}
                candidates = [root for root in roots if f"{root}/SKILL.md" in files]
                if len(roots) != 1 or len(candidates) != 1:
                    raise SkillArchiveError(
                        "SKILL_MD_NOT_AT_ROOT",
                        "ZIP 根目录必须包含 SKILL.md；也可以只包一层目录后再放 SKILL.md。",
                    )
                wrapper = candidates[0]
            skill_path = f"{wrapper}/SKILL.md" if wrapper else "SKILL.md"
            try:
                skill_md = archive.read(files[skill_path]).decode("utf-8")
            except UnicodeDecodeError as error:
                raise SkillArchiveError(
                    "SKILL_MD_ENCODING_INVALID",
                    f"{skill_path} 必须使用 UTF-8 编码。",
                ) from error
            prefix = 1 if wrapper else 0
            public_files = [
                {
                    "path": PurePosixPath(
                        *PurePosixPath(path).parts[prefix:]
                    ).as_posix(),
                    "size": info.file_size,
                }
                for path, info in files.items()
            ]
            name, description = _frontmatter(skill_md)
    except zipfile.BadZipFile as error:
        raise SkillArchiveError(
            "SKILL_ARCHIVE_INVALID",
            "选择的文件不是有效的 ZIP。",
        ) from error
    return SkillArchive(
        content=content,
        name=name,
        description=description,
        files=public_files,
        skill_md=skill_md,
    )


__all__ = ["SkillArchive", "SkillArchiveError", "validate_skill_archive"]
